"""Self-hosted voice pipeline: German speech-to-text (faster-whisper) and
text-to-speech (Piper), plus WAV transcoding for the existing cry files.

Everything here targets one fixed wire format — 16kHz mono 16-bit PCM WAV —
for mic uploads, TTS output, and cry output alike, so the ESP32/ESPHome side
only ever needs a single playback rate and no on-device audio decoder.

Model files (a faster-whisper CTranslate2 model, a Piper German voice) are
large binary assets fetched separately via backend/scripts/download_models.sh,
not bundled into the Docker image. They're loaded lazily on first use rather
than at import time, so the rest of the app keeps working when they're
absent; callers should catch VoiceUnavailable and turn it into a 503.
"""

import hashlib
import io
import os
import re
import subprocess
import wave

import numpy as np
from faster_whisper import WhisperModel
from piper import PiperVoice

MEDIA_PATH = os.getenv("MEDIA_PATH", "/data")

WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", "/models/whisper-de")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "/models/piper-de.onnx")
PIPER_CONFIG_PATH = os.getenv(
    "PIPER_CONFIG_PATH", "/models/piper-de.onnx.json"
)

SAMPLE_RATE = 16000

TTS_CACHE_PATH = os.path.join(MEDIA_PATH, "tts")
CRIES_WAV_CACHE_PATH = os.path.join(MEDIA_PATH, "cries_wav")
DISPLAY_CACHE_PATH = os.path.join(MEDIA_PATH, "display")

# The ESP32's GC9A01 panel is 240x240; images are pre-scaled to exactly that.
DISPLAY_SIZE = 240

os.makedirs(TTS_CACHE_PATH, exist_ok=True)
os.makedirs(CRIES_WAV_CACHE_PATH, exist_ok=True)
os.makedirs(DISPLAY_CACHE_PATH, exist_ok=True)

# Piper's German espeak phonemizer reads "ch" as in "Bach", which mangles
# names whose "ch" comes from Japanese/English/Spanish ("Pikachu" ->
# "Pika-chu"). Respelled phonetically before synthesis. Deliberately an
# explicit list, not a "ch" -> "tsch" rule: many German names (Nachtara,
# Sichlor, Lichtel, ...) need the German "ch".
PRONUNCIATION_DE = {
    "Pikachu": "Pikatschu",
    "Raichu": "Raitschu",
    "Pichu": "Pitschu",
    "Jirachi": "Dschiratschi",
    "Pachirisu": "Patschirisu",
    "Machollo": "Matschollo",
    "Machomei": "Matschomei",
    "Nockchan": "Nocktschan",
    "Puponcho": "Pupontscho",
    "Picochilla": "Picotschilla",
    "Mortcha": "Morttscha",
    "Fatalitcha": "Fatalittscha",
}

_PRONUNCIATION_RE = re.compile(
    r"\b(" + "|".join(map(re.escape, PRONUNCIATION_DE)) + r")\b"
)

_whisper_model = None
_piper_voice = None


class VoiceUnavailable(Exception):
    """Raised when a required model file isn't present on disk yet."""


def get_whisper_model():
    global _whisper_model

    if _whisper_model is None:
        if not os.path.isdir(WHISPER_MODEL_PATH):
            raise VoiceUnavailable(
                f"Whisper-Modell nicht gefunden unter {WHISPER_MODEL_PATH}. "
                "backend/scripts/download_models.sh ausführen."
            )
        _whisper_model = WhisperModel(
            WHISPER_MODEL_PATH,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            local_files_only=True,
        )

    return _whisper_model


def get_piper_voice():
    global _piper_voice

    if _piper_voice is None:
        if not os.path.isfile(PIPER_MODEL_PATH) or not os.path.isfile(
            PIPER_CONFIG_PATH
        ):
            raise VoiceUnavailable(
                f"Piper-Modell nicht gefunden unter {PIPER_MODEL_PATH}. "
                "backend/scripts/download_models.sh ausführen."
            )
        _piper_voice = PiperVoice.load(
            PIPER_MODEL_PATH, config_path=PIPER_CONFIG_PATH
        )

    return _piper_voice


def _write_wav(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)

    return buffer.getvalue()


def transcribe_wav(wav_bytes: bytes) -> str:
    """Transcribe a 16kHz mono 16-bit PCM WAV blob to German text.

    The ESP32 firmware fully controls the format it sends, so a WAV that
    doesn't match is rejected rather than resampled/converted.
    """
    model = get_whisper_model()

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        if (
            wav_file.getnchannels() != 1
            or wav_file.getsampwidth() != 2
            or wav_file.getframerate() != SAMPLE_RATE
        ):
            raise ValueError(
                "Erwartet wird 16kHz mono 16-bit PCM WAV "
                f"(erhalten: {wav_file.getnchannels()}ch, "
                f"{wav_file.getsampwidth() * 8}bit, "
                f"{wav_file.getframerate()}Hz)"
            )

        frames = wav_file.readframes(wav_file.getnframes())

    # faster-whisper expects float32 samples in [-1, 1], not raw PCM16.
    audio = (
        np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    )

    # The fixed ~4s recording window (esp32/pokedex.yaml) has silence
    # padding around the spoken word; vad_filter trims that instead of
    # letting Whisper hallucinate text for it.
    segments, _info = model.transcribe(
        audio,
        language="de",
        vad_filter=True,
    )

    return " ".join(segment.text.strip() for segment in segments).strip()


def synthesize_tts(text: str) -> bytes:
    """Synthesize German text to a cached 16kHz mono 16-bit PCM WAV."""
    # Applied before hashing, so editing PRONUNCIATION_DE regenerates the
    # affected cache entries instead of serving stale audio.
    text = _PRONUNCIATION_RE.sub(lambda m: PRONUNCIATION_DE[m.group(1)], text)
    cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache_path = os.path.join(TTS_CACHE_PATH, f"{cache_key}.wav")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as cached:
            return cached.read()

    voice = get_piper_voice()
    native_rate = voice.config.sample_rate

    native_buffer = io.BytesIO()

    with wave.open(native_buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    native_wav_bytes = native_buffer.getvalue()

    if native_rate != SAMPLE_RATE:
        with wave.open(io.BytesIO(native_wav_bytes), "rb") as native_wav:
            pcm_bytes = native_wav.readframes(native_wav.getnframes())
        wav_bytes = _resample_pcm16_wav(pcm_bytes, native_rate, SAMPLE_RATE)
    else:
        wav_bytes = native_wav_bytes

    with open(cache_path, "wb") as out_file:
        out_file.write(wav_bytes)

    return wav_bytes


def _resample_pcm16_wav(
    pcm_bytes: bytes, src_rate: int, dst_rate: int
) -> bytes:
    """Resample raw PCM16 mono audio via ffmpeg, returning a WAV blob."""
    src_wav = _write_wav(pcm_bytes, src_rate)

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ar",
            str(dst_rate),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=src_wav,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    return result.stdout


def transcode_cry_to_wav(cry_ogg_path: str, pokemon_id: int) -> bytes:
    """Transcode a Pokémon's cry .ogg to a cached 16kHz mono 16-bit WAV."""
    cache_path = os.path.join(CRIES_WAV_CACHE_PATH, f"{pokemon_id}.wav")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as cached:
            return cached.read()

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            cry_ogg_path,
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            "-f",
            "wav",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    wav_bytes = result.stdout

    with open(cache_path, "wb") as out_file:
        out_file.write(wav_bytes)

    return wav_bytes


def render_display_image(src_png_path: str, cache_name: str) -> bytes:
    """Scale artwork to a cached 240x240 opaque RGB PNG for the ESP32 display.

    PokeAPI artwork is ~1MP with an alpha channel — too big for the ESP32 to
    decode quickly, and online_image's RGB565 has no alpha — so it's scaled
    down and flattened onto black (the display's background) here instead.
    """
    cache_path = os.path.join(DISPLAY_CACHE_PATH, f"{cache_name}.png")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as cached:
            return cached.read()

    size = f"{DISPLAY_SIZE}x{DISPLAY_SIZE}"

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            src_png_path,
            "-filter_complex",
            f"color=c=black:s={size}[bg];"
            f"[0:v]scale={DISPLAY_SIZE}:{DISPLAY_SIZE}:flags=lanczos[fg];"
            "[bg][fg]overlay=shortest=1,format=rgb24",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-f",
            "image2pipe",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    png_bytes = result.stdout

    with open(cache_path, "wb") as out_file:
        out_file.write(png_bytes)

    return png_bytes
