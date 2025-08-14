import os, zipfile, urllib.request, json, logging, base64, asyncio, time
import pyaudio
from deep_translator import GoogleTranslator
from vosk import Model, KaldiRecognizer
from gtts import gTTS
import pygame
from tempfile import NamedTemporaryFile

# -------------------
# CONFIG
# -------------------
WS_URL = os.getenv("WS_URL", "wss://video-call-hindi.onrender.com")
PLAY_LOCALLY = False
SOURCE_LANG = "hi"
TARGET_LANG = "en"

MODEL_DIR = "model"
MODEL_URL = os.getenv("VOSK_MODEL_URL", "https://alphacephei.com/vosk/models/vosk-model-hi-0.22.zip")

logging.getLogger("vosk").setLevel(logging.ERROR)


# -------------------
# Vosk model bootstrap
# -------------------
def ensure_vosk_model():
    if os.path.isdir(MODEL_DIR):
        print(f"✅ Vosk model already present at ./{MODEL_DIR}")
        return

    print("📦 Vosk model not found. Downloading now...")
    zip_path = "model.zip"
    urllib.request.urlretrieve(MODEL_URL, zip_path)
    print("✅ Download complete. Extracting...")

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(".")

    os.remove(zip_path)

    # Rename the extracted folder to MODEL_DIR
    extracted = [d for d in os.listdir(".") if os.path.isdir(d) and ("vosk-model" in d)]
    if extracted:
        os.rename(extracted[0], MODEL_DIR)

    print(f"✅ Vosk model ready at ./{MODEL_DIR}")


ensure_vosk_model()


def load_vosk_model():
    return Model(os.path.abspath(MODEL_DIR))


vosk_model = load_vosk_model()


# -------------------
# Translation + TTS
# -------------------
def translate(text, source_lang=SOURCE_LANG, target_lang=TARGET_LANG):
    if not text:
        return ""
    try:
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as e:
        print(f"[Translation Error] {e}")
        return ""


def tts_mp3_bytes(text, lang=TARGET_LANG):
    if not text:
        return b""
    try:
        with NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tmp = fp.name
        gTTS(text=text, lang=lang).save(tmp)
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


# -------------------
# Persistent WebSocket sender
# -------------------
class WSSender:
    def __init__(self, url: str):
        self.url = url
        self._queue = asyncio.Queue()
        self._stop = asyncio.Event()

    async def start(self):
        import websockets
        backoff = 1
        while not self._stop.is_set():
            try:
                print(f"[WS] Connecting to {self.url} ...")
                async with websockets.connect(self.url, max_size=None, ping_interval=20, ping_timeout=20) as ws:
                    print("[WS] Connected.")
                    backoff = 1
                    while not self._stop.is_set():
                        try:
                            msg = await asyncio.wait_for(self._queue.get(), timeout=20.0)
                        except asyncio.TimeoutError:
                            continue
                        if msg is None:
                            await ws.close(code=1000, reason="Normal Closure")  # ✅ Valid close code
                            print("[WS] Closed (app requested).")
                            return
                        await ws.send(msg)
            except Exception as e:
                print(f"[WS] Disconnected: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10)

    async def send_json(self, payload: dict):
        try:
            await self._queue.put(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            print(f"[WS enqueue error] {e}")

   async def stop(self):
    self._stop.set()
    await self._queue.put(None)
    try:
        if self._ws is not None:
            await self._ws.close(code=1000, reason="Normal Closure")
    except Exception as e:
        print(f"[WS close error] {e}")



# -------------------
# Main audio loop
# -------------------
async def translate_loop(ws_sender: WSSender):
    recognizer = KaldiRecognizer(vosk_model, 16000)
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=2048)
    stream.start_stream()

    print(f"🎤 Listening... Translating from {SOURCE_LANG} → {TARGET_LANG} (Ctrl+C to stop)")
    try:
        while True:
            data = stream.read(4096, exception_on_overflow=False)
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()
                if not text:
                    continue

                print(f"[Recognized] {text}")
                translated = translate(text, SOURCE_LANG, TARGET_LANG).strip()
                print(f"[Translated] {translated}")

                mp3_bytes = tts_mp3_bytes(translated, lang=TARGET_LANG)
                if not mp3_bytes:
                    continue

                if PLAY_LOCALLY:
                    speak_local(mp3_bytes)

                audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")
                payload = {
                    "type": "translation",
                    "text": translated,
                    "audio_b64": audio_b64,
                    "src": SOURCE_LANG,
                    "tgt": TARGET_LANG,
                    "timestamp": int(time.time() * 1000)
                }
                await ws_sender.send_json(payload)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        try:
            stream.stop_stream()
            stream.close()
            audio.terminate()
        except:
            pass


# -------------------
# Entrypoint
# -------------------
async def main():
    sender = WSSender(WS_URL)
    ws_task = asyncio.create_task(sender.start())
    mic_task = asyncio.create_task(translate_loop(sender))

    try:
        await mic_task
    finally:
        await sender.stop()
        await ws_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


