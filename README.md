# Pokédex

A self-hosted, German-language Pokédex: a FastAPI backend serving Pokémon data from a local SQLite database and a web UI to browse and search it, plus a one-shot importer that pulls and localizes data from [PokeAPI](https://pokeapi.co/api/v2) (including sprites and cries) into that database. Optionally, an ESP32 running [ESPHome](https://esphome.io) can act as a voice-driven physical front end — see [ESP32 voice interface](#esp32-voice-interface) below.

## Services

| Service    | Description                                                                                  | Default URL             |
|------------|-----------------------------------------------------------------------------------------------|--------------------------|
| `pokedex`  | FastAPI backend: JSON API, downloaded media, and the web UI, all on one port                  | http://localhost:1510    |
| `importer` | One-shot script that fetches data from PokeAPI into the shared database                       | –                        |

## Getting started

Requires Docker and Docker Compose.

```bash
# 1. Populate the database (run once, or re-run any time to refresh data)
docker compose --profile import run --rm importer

# 2. Start the backend, which also serves the web UI
docker compose up -d pokedex

# Optional: fetch the German STT/TTS models for the ESP32 voice interface.
# Only needed if you're using that; everything else works without it.
backend/scripts/download_models.sh
```

Open http://localhost:1510 in your browser to use the Pokédex. The importer downloads data for every Pokémon species and its media (sprites, shiny sprites, cries) from PokeAPI, so the first run can take a while and needs internet access; it's safe to interrupt and re-run, since it skips anything already imported.

Data and media are persisted to `./data` on the host.

## API

The web UI, JSON API, and media are all served from the same port (1510). The JSON API lives under `/api`, with interactive docs at `/docs`.

- `GET /api/pokemon?search=&limit=&offset=` — list/search default Pokémon forms (paginated, `limit` max 100). `search` matches either the English or German name.
- `GET /api/pokemon/{identifier}` — fetch a single Pokémon by numeric ID, English name, or exact German name. Includes base stats, type matchups (`double_damage_from`/`half_damage_from`/`no_damage_from` per type, for computing a weakness chart), abilities with German names/effects, species traits (color, shape, habitat, growth rate, gender ratio, egg cycles), and `evolves_from`/`evolves_to` evolution chain data.
- `GET /api/count` — total number of Pokémon in the database.
- `GET /media/...` — serves downloaded sprites (`sprites/`), shiny sprites (`shiny/`), and cries (`cries/`).

Voice interface (used by the ESP32 firmware, see below) — all audio is 16kHz mono 16-bit PCM WAV, and every endpoint here returns `503` if its model files haven't been fetched yet (see [Configuration](#configuration)):

- `POST /api/voice/recognize` — send a raw WAV recording as the request body (`Content-Type: audio/wav`). Transcribes it and matches the German transcript to a Pokémon, returning `{"transcript", "matched": true/false, "id"?, "name"?, "german_name"?, "confidence"?}`.
- `GET /api/pokemon/{identifier}/tts/name` / `.../tts/description` — synthesized German speech (`audio/wav`) of the Pokémon's name / description, cached after first generation.
- `GET /api/pokemon/{identifier}/cry.wav` — the Pokémon's cry, transcoded to the same WAV format as the TTS endpoints.

## Configuration

Environment variables (set in `docker-compose.yml`):

- `DATABASE_PATH` — path to the SQLite file (default `/data/pokedex.db`).
- `MEDIA_PATH` — directory the backend serves under `/media` (default `/data`).
- `STATIC_PATH` — directory the backend serves the web UI from (default `static`, i.e. the bundled `frontend/` files).
- `WHISPER_MODEL_PATH` — directory of the faster-whisper STT model (default `/models/whisper-de`), fetched via `backend/scripts/download_models.sh`. The voice endpoints return `503` until it exists.
- `WHISPER_DEVICE` — inference device for STT (default `cpu`).
- `WHISPER_COMPUTE_TYPE` — faster-whisper compute type (default `int8`, a good CPU speed/accuracy tradeoff).
- `PIPER_MODEL_PATH` / `PIPER_CONFIG_PATH` — the Piper TTS voice's `.onnx` model and its `.onnx.json` config (defaults `/models/piper-de.onnx` / `/models/piper-de.onnx.json`), also fetched via `download_models.sh`.

## ESP32 voice interface

An ESP32 running [ESPHome](https://esphome.io) can act as a physical, voice-driven front end: press a button to wake it from deep sleep, say a Pokémon's German name into its microphone, and it looks the Pokémon up against the API above, shows its sprite on a display, plays its cry, and speaks its name and description — then goes back to sleep. Speech recognition and synthesis run fully offline in the backend container (faster-whisper + Piper, see [Configuration](#configuration)), no cloud APIs involved.

See [`esp32/README.md`](esp32/README.md) for wiring, flashing, and setup, and run `backend/scripts/download_models.sh` first to fetch the required models.

## Development

There's no local (non-Docker) dev setup, build tooling, or test suite — everything runs via the containers above. The backend container mounts `./backend/app` and `./frontend` directly for live code editing without rebuilding.

See `CLAUDE.md` for a deeper architecture overview (data model, import flow, code conventions) aimed at AI coding assistants.
