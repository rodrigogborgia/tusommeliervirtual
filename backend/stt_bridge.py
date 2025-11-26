import asyncio
import json
import websockets
from config import STT_WS_URL, STT_SAMPLE_RATE

async def transcribe_raw_bytes(audio_bytes: bytes):
    async with websockets.connect(STT_WS_URL) as ws:
        cfg = json.dumps({"config": {"sample_rate": STT_SAMPLE_RATE}})
        await ws.send(cfg)
        await ws.send(audio_bytes)
        await ws.send(json.dumps({"eof": 1}))

        final_text = ""
        while True:
            try:
                msg = await ws.recv()
            except:
                break
            try:
                jobj = json.loads(msg)
                if "text" in jobj:
                    final_text = jobj.get("text", "")
                    break
            except:
                continue
        return final_text

def transcribe_file(path: str):
    with open(path, "rb") as f:
        audio = f.read()
    return asyncio.run(transcribe_raw_bytes(audio))
