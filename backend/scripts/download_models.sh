#!/usr/bin/env sh
# Fetches the faster-whisper STT model and Piper TTS voice used by
# backend/app/voice.py into ./models, so the voice endpoints work.
#
# Run once from the repo root: backend/scripts/download_models.sh
#
# Picks a small/fast default Whisper model (multilingual "small", forced to
# German at inference time in voice.py). For better recognition accuracy on
# Pokémon names, swap WHISPER_MODEL_ID for a larger one (e.g.
# Systran/faster-whisper-medium) and re-run — WHISPER_MODEL_PATH in
# docker-compose.yml doesn't need to change, only the files underneath it.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODELS_DIR="${MODELS_DIR:-$REPO_ROOT/models}"

WHISPER_MODEL_ID="${WHISPER_MODEL_ID:-Systran/faster-whisper-small}"
WHISPER_BASE_URL="https://huggingface.co/${WHISPER_MODEL_ID}/resolve/main"

PIPER_MODEL_URL="${PIPER_MODEL_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx}"
PIPER_CONFIG_URL="${PIPER_CONFIG_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json}"

mkdir -p "$MODELS_DIR"

WHISPER_DIR="$MODELS_DIR/whisper-de"

if [ -f "$WHISPER_DIR/model.bin" ]; then
    echo "Whisper-Modell bereits vorhanden unter $WHISPER_DIR, überspringe."
else
    echo "Lade Whisper-Modell ($WHISPER_MODEL_ID) ..."
    mkdir -p "$WHISPER_DIR"
    for file in config.json model.bin tokenizer.json vocabulary.txt; do
        curl -fL -o "$WHISPER_DIR/$file" "$WHISPER_BASE_URL/$file"
    done
    echo "Whisper-Modell installiert unter $WHISPER_DIR"
fi

if [ -f "$MODELS_DIR/piper-de.onnx" ] && [ -f "$MODELS_DIR/piper-de.onnx.json" ]; then
    echo "Piper-Modell bereits vorhanden unter $MODELS_DIR/piper-de.onnx, überspringe."
else
    echo "Lade Piper-Stimme von $PIPER_MODEL_URL ..."
    curl -fL -o "$MODELS_DIR/piper-de.onnx" "$PIPER_MODEL_URL"
    curl -fL -o "$MODELS_DIR/piper-de.onnx.json" "$PIPER_CONFIG_URL"
    echo "Piper-Modell installiert unter $MODELS_DIR/piper-de.onnx"
fi

echo "Fertig. Backend neu starten (docker compose restart pokedex), damit die Modelle geladen werden."
