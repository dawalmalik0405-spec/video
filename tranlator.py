import os
import zipfile
import urllib.request
import cv2
import pyaudio
import json
import logging
import base64
import asyncio
import time
from deep_translator import GoogleTranslator
from vosk import Model, KaldiRecognizer
from gtts import gTTS
import pygame
from tempfile import NamedTemporaryFile

# CONFIG
WS_URL = os.getenv("WS_URL", "ws://localhost:9000")  # Now connects locally

PLAY_LOCALLY = False
SOURCE_LANG = "hi"
TARGET_LANG = "en"

MODEL_DIR = "model"
MODEL_URL = os.getenv(
    "VOSK_MODEL_URL",
    "https://alphacephei.com/vosk/models/vosk-model-hi-0.22.zip"
)

logging.getLogger("vosk").setLevel(logging.ERROR)

def ensure_vosk_model():
    if os.path.exists(MODEL_DIR):
        print(f"Vosk model already present at ./{MODEL_DIR}")
        return
    print("📦 Vosk model not found. Downloading now...")
    zip_path = "model.zip"
    urllib.request.urlretrieve(MODEL_URL, zip_path)
    print("✅ Download complete. Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(".")
    os.remove(zip_path)
    extracted = [d for d in os.listdir(".") if os.path.isdir(d) and ("vosk-model" in d)]
    if extracted:
        os.rename(extracted[0], MODEL_DIR)
    print(f"✅ Vosk model ready at ./{MODEL_DIR}")

ensure_vosk_model()

def load_vosk_model():
    model_path = os.path.abspath(MODEL_DIR)
    return Model(model_path)

vosk_model = load_vosk_model()

def translate(text, source_lang=SOURCE_LANG, target_lang=TARGET_LANG):
    try:
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as e:
        print(f"[Translation Error] {e}")
        return ""

def tts_mp3_bytes(text, lang=TARGET_LANG):
    try:
        with NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tmp = fp.name
        tts = gTTS(text=text, lang=lang)
        tts.save(tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        os.remove(tmp)
        return data
    except Exception as e:
        print(f"[TTS Error] {e}")
        return b""

def speak_local(audio_bytes):
    try:
        with NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tmp = fp.name
            fp.write(audio_bytes)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.quit()
        os.remove(tmp)
    except Exception as e:
        print(f"[Local Play Error] {e}")

async def _send_ws_message_async(payload_json_str):
    import websockets
    try:
        async with websockets.connect(WS_URL, max_size=None) as ws:
            await ws.send(payload_json_str)
    except Exception as e:
        print("[WS send error]", e)

def send_ws_message(payload: dict):
    try:
        payload_json = json.dumps(payload)
        asyncio.run(_send_ws_message_async(payload_json))
    except Exception as e:
        print("[WS run error]", e)

def real_time_translation(source_lang=SOURCE_LANG, target_lang=TARGET_LANG):
    recognizer = KaldiRecognizer(vosk_model, 16000)
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=2048)
    stream.start_stream()

    print(f"🎤 Listening... Translating from {source_lang} to {target_lang} (Ctrl+C to stop)")
    while True:
        try:
            data = stream.read(4096, exception_on_overflow=False)
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    print(f"[Recognized] {text}")
                    translated = translate(text, source_lang, target_lang)
                    print(f"[Translated] {translated}")
                    mp3_bytes = tts_mp3_bytes(translated, lang=target_lang)
                    if PLAY_LOCALLY:
                        speak_local(mp3_bytes)
                    audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")
                    payload = {
                        "type": "translation",
                        "text": translated,
                        "audio_b64": audio_b64,
                        "src": source_lang,
                        "tgt": target_lang,
                        "timestamp": int(time.time() * 1000)
                    }
                    send_ws_message(payload)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Audio Error] {e}")
            time.sleep(0.1)

if __name__ == "__main__":
    real_time_translation()
