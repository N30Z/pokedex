#!/usr/bin/env sh
# Fetches the German Vosk STT model and Piper TTS voice used by
# backend/app/voice.py into ./models, so the voice endpoints work.
#
# Run once from the repo root: backend/scripts/download_models.sh
#
# Picks small/fast default models. For better recognition accuracy, swap
# VOSK_MODEL_URL for a larger German Vosk model (see alphacephei.com/vosk/models)
# and re-run.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODELS_DIR="${MODELS_DIR:-$REPO_ROOT/models}"

VOSK_MODEL_URL="${VOSK_MODEL_URL:-https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip}"
PIPER_MODEL_URL="${PIPER_MODEL_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx}"
PIPER_CONFIG_URL="${PIPER_CONFIG_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json}"

mkdir -p "$MODELS_DIR"

if [ -d "$MODELS_DIR/vosk-de" ]; then
    echo "Vosk-Modell bereits vorhanden unter $MODELS_DIR/vosk-de, überspringe."
else
    echo "Lade Vosk-Modell von $VOSK_MODEL_URL ..."
    TMP_ZIP="$MODELS_DIR/vosk-de.zip"
    curl -fL -o "$TMP_ZIP" "$VOSK_MODEL_URL"
    unzip -q "$TMP_ZIP" -d "$MODELS_DIR"
    rm "$TMP_ZIP"
    # The zip extracts to a versioned directory name (e.g. vosk-model-small-de-0.15);
    # normalize it to the fixed name VOSK_MODEL_PATH expects.
    EXTRACTED_DIR=$(find "$MODELS_DIR" -maxdepth 1 -type d -name 'vosk-model-*' | head -n 1)
    if [ -n "$EXTRACTED_DIR" ]; then
        mv "$EXTRACTED_DIR" "$MODELS_DIR/vosk-de"
    fi
    echo "Vosk-Modell installiert unter $MODELS_DIR/vosk-de"
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
