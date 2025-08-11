import os
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
WS_URL = "ws://localhost:8765"
   # <-- Node.js WebSocket server (change if needed)
PLAY_LOCALLY = False             # True = also play translated audio locally (pygame)
SOURCE_LANG = "en"
TARGET_LANG = "hi"

# Suppress Vosk internal logs
logging.getLogger("vosk").setLevel(logging.ERROR)

# Load Vosk model for speech recognition
def load_vosk_model():
    model_path = os.path.abspath("d:/code/video-call/video trs/model")  # update if needed
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Vosk model not found at {model_path}. Download from https://alphacephei.com/vosk/models"
        )
    return Model(model_path)

vosk_model = load_vosk_model()

# Translate using deep_translator
def translate(text, source_lang=SOURCE_LANG, target_lang=TARGET_LANG):
    try:
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as e:
        print(f"[Translation Error] {e}")
        return ""

# TTS using gTTS -> returns mp3 bytes
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

# optional local play
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

# send a single websocket message to Node (connect-send-close)
async def _send_ws_message_async(payload_json_str):
    import websockets
    try:
        async with websockets.connect(WS_URL, max_size=None) as ws:
            await ws.send(payload_json_str)
            # Optionally wait for ack
            try:
                # wait short time for ack
                ack = await asyncio.wait_for(ws.recv(), timeout=0.5)
                # print("WS ack:", ack)
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        print("[WS send error]", e)

def send_ws_message(payload: dict):
    # run a short-lived asyncio connection to send the message
    try:
        payload_json = json.dumps(payload)
        asyncio.run(_send_ws_message_async(payload_json))
    except Exception as e:
        print("[WS run error]", e)

# Real-time speech recognition, translation, and sending to Node
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

                    # translate
                    translated = translate(text, source_lang, target_lang)
                    print(f"[Translated] {translated}")

                    # TTS -> mp3 bytes
                    mp3_bytes = tts_mp3_bytes(translated, lang=target_lang)
                    if not mp3_bytes:
                        print("[Warning] empty mp3 bytes, skipping send")
                        continue

                    # optionally play locally
                    if PLAY_LOCALLY:
                        speak_local(mp3_bytes)

                    # base64 encode audio for JSON transport
                    audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")

                    # payload
                    payload = {
                        "type": "translation",
                        "text": translated,
                        "audio_b64": audio_b64,
                        "src": source_lang,
                        "tgt": target_lang,
                        "timestamp": int(time.time() * 1000)
                    }

                    # send to Node.js
                    # NOTE: this opens a short-lived websocket connection per translation.
                    send_ws_message(payload)

            else:
                # optional: handle partial result
                partial = json.loads(recognizer.PartialResult()).get("partial", "")
                if partial:
                    # you can choose to send partial captions to Node as well
                    partial_payload = {
                        "type": "partial",
                        "text": partial,
                        "src": source_lang,
                        "tgt": target_lang,
                        "timestamp": int(time.time() * 1000)
                    }
                    # small optimization: don't send every tiny partial (commented)
                    # send_ws_message(partial_payload)
                    # print("[Partial]", partial)
                    pass

        except KeyboardInterrupt:
            print("Stopping...")
            break
        except Exception as e:
            print(f"[Audio Error] {e}")
            # small sleep to avoid busy loop on repeated errors
            time.sleep(0.1)

    try:
        stream.stop_stream()
        stream.close()
        audio.terminate()
    except:
        pass

# If you still want the webcam display & subtitles, you can keep display_video in a separate process.
# For now we'll focus on sending translations to Node.

if __name__ == "__main__":
    real_time_translation()
