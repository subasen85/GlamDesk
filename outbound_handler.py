"""
GlamDesk – outbound_handler.py
A small FastAPI (or Flask) server that:

  POST /outbound-call  ← Twilio hits this when the customer answers
                          Returns TwiML that streams audio to Deepgram

This runs alongside main.py (inbound calls) on a different port (5001).
Or you can merge the /outbound-call route into your existing main.py
websocket server — both approaches work.

Run:  uvicorn outbound_handler:app --port 5001
"""

import os
import json
import asyncio
import base64
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

SERVER_URL   = os.getenv("GLAMDESK_SERVER_URL", "https://yourngrok.ngrok.io")
DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY")


# ─────────────────────────────────────────────────────────────────────────────
# Route 1: Twilio webhook — called when customer picks up
# Returns TwiML that opens a Media Stream to our WS handler
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/outbound-call")
@app.post("/outbound-call")
async def outbound_call(request: Request):
    """
    Twilio calls this URL when the customer answers.
    We respond with TwiML that:
      1. Says nothing (the Deepgram agent greets them)
      2. Opens a bidirectional media stream to /outbound-stream
    """
    params = dict(request.query_params)
    appt_id   = params.get("appt_id",   "")
    name      = params.get("name",      "there")
    service   = params.get("service",   "your appointment")
    appt_time = params.get("appt_time", "")

    # Encode context into the WebSocket URL as query params
    from urllib.parse import urlencode
    ws_params = urlencode({"name": name, "service": service, "appt_time": appt_time})
    ws_url = f"{SERVER_URL.replace('https','wss').replace('http','ws')}/outbound-stream?{ws_params}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" />
  </Connect>
</Response>"""

    return PlainTextResponse(content=twiml, media_type="application/xml")


# ─────────────────────────────────────────────────────────────────────────────
# Route 2: WebSocket — bridges Twilio audio ↔ Deepgram voice agent
# Same pattern as main.py but with a reminder-specific system prompt
# ─────────────────────────────────────────────────────────────────────────────

def build_reminder_config(name: str, service: str, appt_time: str) -> dict:
    """
    Same structure as config.json but with a custom greeting and prompt
    for the outbound reminder call.
    """
    return {
        "type": "Settings",
        "audio": {
            "input":  {"encoding": "mulaw", "sample_rate": 8000},
            "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
        },
        "agent": {
            "language": "en",
            "listen": {
                "provider": {"type": "deepgram", "model": "nova-3"}
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.6,
                },
                "prompt": (
                    f"You are GlamDesk, a friendly AI assistant calling {name} "
                    f"to remind them about their upcoming {service} appointment at {appt_time}. "
                    f"Keep the call short and warm. Confirm if they are still coming. "
                    f"If they want to cancel or reschedule, note it and tell them the salon "
                    f"team will follow up. Do not offer to book or look up other appointments. "
                    f"End the call politely after confirmation."
                ),
                "functions": [],  # No DB functions needed for a reminder call
            },
            "speak": {
                "provider": {"type": "deepgram", "model": "aura-2-thalia-en"}
            },
            "greeting": (
                f"Hello, may I speak with {name}? "
                f"This is GlamDesk calling to remind you about your "
                f"{service} appointment today at {appt_time}. "
                f"Are you still able to make it?"
            ),
        },
    }


@app.websocket("/outbound-stream")
async def outbound_stream(websocket, name: str = "there",
                          service: str = "appointment", appt_time: str = ""):
    """
    WebSocket handler — mirrors twilio_handler() in main.py
    but builds config dynamically with the customer's details.
    """
    audio_queue     = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    sts_ws_ctx = websockets.connect(
        "wss://agent.deepgram.com/v1/agent/converse",
        subprotocols=["token", DEEPGRAM_KEY],
    )

    async with sts_ws_ctx as sts_ws:
        config = build_reminder_config(name, service, appt_time)
        await sts_ws.send(json.dumps(config))

        await asyncio.wait([
            asyncio.ensure_future(_sts_sender(sts_ws, audio_queue)),
            asyncio.ensure_future(_sts_receiver(sts_ws, websocket, streamsid_queue)),
            asyncio.ensure_future(_twilio_receiver(websocket, audio_queue, streamsid_queue)),
        ])

    await websocket.close()


# ── Internal helpers (identical to main.py) ───────────────────────────────────

async def _sts_sender(sts_ws, audio_queue):
    while True:
        chunk = await audio_queue.get()
        await sts_ws.send(chunk)


async def _sts_receiver(sts_ws, twilio_ws, streamsid_queue):
    streamsid = await streamsid_queue.get()
    async for message in sts_ws:
        if isinstance(message, str):
            decoded = json.loads(message)
            if decoded.get("type") == "UserStartedSpeaking":
                await twilio_ws.send(json.dumps({"event": "clear", "streamSid": streamsid}))
            continue
        media_message = {
            "event": "media",
            "streamSid": streamsid,
            "media": {"payload": base64.b64encode(message).decode("ascii")},
        }
        await twilio_ws.send(json.dumps(media_message))


async def _twilio_receiver(twilio_ws, audio_queue, streamsid_queue):
    BUFFER_SIZE = 20 * 160
    inbuffer = bytearray()
    async for message in twilio_ws:
        try:
            data  = json.loads(message)
            event = data["event"]
            if event == "start":
                streamsid_queue.put_nowait(data["start"]["streamSid"])
            elif event == "media":
                chunk = base64.b64decode(data["media"]["payload"])
                if data["media"]["track"] == "inbound":
                    inbuffer.extend(chunk)
            elif event == "stop":
                break
            while len(inbuffer) >= BUFFER_SIZE:
                audio_queue.put_nowait(inbuffer[:BUFFER_SIZE])
                inbuffer = inbuffer[BUFFER_SIZE:]
        except Exception:
            break
