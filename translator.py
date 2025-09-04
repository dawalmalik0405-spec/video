import os
import json
import base64
import asyncio
import time
import webrtcvad
from deep_translator import GoogleTranslator
from gtts import gTTS
from tempfile import NamedTemporaryFile
import websockets
import speech_recognition as sr

# ===================== CONFIG =====================
# Detect environment: Railway, Render, or local
RAILWAY_URL = os.getenv("RAILWAY_STATIC_URL")


if RAILWAY_URL:
    WS_URL = f"wss://{RAILWAY_URL}"
else:
    WS_URL = "ws://localhost:9000"  # local dev default

SOURCE_LANG = "en"              # default source
TARGET_LANG = "hi"              # default target
SAMPLE_RATE = 16000             # audio sample rate
SAMPLE_WIDTH = 2                # 16-bit audio
FRAME_DURATION_MS = 20          # frame size for VAD (10, 20, or 30 ms)
FRAME_SIZE = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0)) * SAMPLE_WIDTH
# ==================================================

# --- Language normalization ---
LANG_ALIASES = {
    "en": "en", "english": "en",
    "hi": "hi", "hindi": "hi",
    "cn": "zh-CN", "zh": "zh-CN", "zh-cn": "zh-CN",
    "zh_cn": "zh-CN", "chinese": "zh-CN",
    "de": "de", "german": "de"
}

def normalize_lang(code: str) -> str:
    if not code:
        return ""
    return LANG_ALIASES.get(code.strip().lower(), code.strip().lower())

# --- Translation / TTS ---
def translate(text, source_lang=None, target_lang=None):
    src = normalize_lang(source_lang or SOURCE_LANG)
    tgt = normalize_lang(target_lang or TARGET_LANG)
    try:
        return GoogleTranslator(source=src, target=tgt).translate(text)
    except Exception as e:
        print(f"[Translation Error] {e}")
        return ""

def tts_mp3_bytes(text, lang=None):
    lng = normalize_lang(lang or TARGET_LANG)
    try:
        with NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tmp = fp.name
        tts = gTTS(text=text, lang=lng)
        tts.save(tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        os.remove(tmp)
        return data
    except Exception as e:
        print(f"[TTS Error] {e}")
        return b""

# --- Keepalive pings ---
async def keepalive(ws):
    while True:
        try:
            await ws.send(json.dumps({"type": "ping"}))
        except:
            break
        await asyncio.sleep(10)

# --- Main WebSocket handler ---
async def ws_handler():
    global SOURCE_LANG, TARGET_LANG

    vad = webrtcvad.Vad(2)
    audio_buffer = bytearray()
    speech_accum = bytearray()
    silence_count = 0
    max_silence_frames = 8  # ~1.2s

    async with websockets.connect(WS_URL, max_size=None, ping_interval=None) as ws:
        print(f"✅ Connected to Node.js server at {WS_URL}")
        asyncio.create_task(keepalive(ws))

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)

                # --- Update langs dynamically ---
                if data.get("type") == "setLangs":
                    SOURCE_LANG = normalize_lang(data["src"])
                    TARGET_LANG = normalize_lang(data["tgt"])
                    print(f"✅ Updated languages: {SOURCE_LANG} -> {TARGET_LANG}")
                    continue

                # --- Audio chunks ---
                if data.get("type") == "audio":
                    chunk = base64.b64decode(data["audio_b64"])
                    audio_buffer.extend(chunk)
                    print(f"🎧 Received chunk: {len(chunk)} bytes, buffer={len(audio_buffer)}")

                    src_lang = SOURCE_LANG
                    tgt_lang = TARGET_LANG

                    # Process buffer in 20ms frames
                    while len(audio_buffer) >= FRAME_SIZE:
                        frame = audio_buffer[:FRAME_SIZE]
                        audio_buffer = audio_buffer[FRAME_SIZE:]

                        try:
                            is_speech = vad.is_speech(frame, sample_rate=SAMPLE_RATE)
                        except Exception as e:
                            print("[VAD error]", e)
                            continue

                        if is_speech:
                            silence_count = 0
                            speech_accum.extend(frame)
                        else:
                            silence_count += 1

                        # Flush speech after silence
                        if silence_count >= max_silence_frames and len(speech_accum) > 6400:
                            recognizer = sr.Recognizer()
                            audio_data = sr.AudioData(bytes(speech_accum), SAMPLE_RATE, SAMPLE_WIDTH)

                            try:
                                text = recognizer.recognize_google(audio_data, language=src_lang)
                                print(f"[Recognized] {text}")
                            except sr.UnknownValueError:
                                print("[STT] Could not understand audio")
                                text = ""
                            except sr.RequestError as e:
                                print(f"[STT Error] {e}")
                                text = ""

                            speech_accum.clear()
                            silence_count = 0

                            if not text:
                                continue

                            translated = translate(text, src_lang, tgt_lang)
                            print(f"[Translated] {translated}")

                            mp3_bytes = tts_mp3_bytes(translated, tgt_lang)
                            if mp3_bytes:
                                print(f"[TTS] Generated {len(mp3_bytes)} bytes")

                            payload = {
                                "type": "translation",
                                "text": translated,
                                "audio_b64": base64.b64encode(mp3_bytes).decode("utf-8") if mp3_bytes else "",
                                "src": src_lang,
                                "tgt": tgt_lang,
                                "timestamp": int(time.time() * 1000)
                            }
                            await ws.send(json.dumps(payload))
                            print("✅ Sent translation payload back to Node.js")

            except Exception as e:
                print("[WS error]", e)
                await asyncio.sleep(1)

# --- Entry ---
if __name__ == "__main__":
    asyncio.run(ws_handler())
