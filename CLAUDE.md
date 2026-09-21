# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted German-language Pokédex: a FastAPI backend serving Pokémon data (with German names/descriptions) from a local SQLite database and a web UI, plus a one-shot importer that pulls and localizes data from PokeAPI (https://pokeapi.co/api/v2) into that database and downloads sprite/cry media to disk.

## Architecture

Two independent services sharing one SQLite database file and one media directory, wired together only via `docker-compose.yml`:

- **`backend/`** — FastAPI app (`backend/app/`). Serves JSON endpoints over the DB, serves downloaded media, and serves the `frontend/` static files (mounted at `/`) — all on one port (1510). Its Dockerfile builds from the repo root so it can `COPY` both `backend/app` and `frontend` into the image.
- **`frontend/`** — static HTML/CSS/JS site (no build step, no framework, no separate container). Calls the backend's JSON API with relative paths (same origin), so there's no API base URL to configure.
- **`importer/`** — standalone script (`importer/import.py`), not a long-running service. Run on demand to populate/refresh the database. It imports `backend/app/models.py` directly (via `sys.path.insert(0, "/backend")`, mapped by the `./backend:/backend` volume in compose), so the backend and importer always share the same SQLAlchemy models — don't fork the schema between them.

Data flow: `importer/import.py` walks PokeAPI's full species list, and for each species fetches species data + every variety's pokemon data + every form's data, upserts rows into `pokemon_species` / `pokemon` / `pokemon_forms`, and downloads sprites/shiny sprites/cries into `/data/{sprites,shiny,cries}`. The backend then reads that same SQLite file and serves it read-only; it never writes.

### Data model (`backend/app/models.py`)

- `PokemonSpecies` — one row per species (the German name/genus/description, generation, legendary/mythical/baby flags, capture rate, gender rate, hatch counter, evolution chain id, etc. all live here, not on `Pokemon`). Color/shape/habitat/growth-rate are stored twice: the raw PokeAPI English slug (`color`, `shape`, `habitat`, `growth_rate`) and its German translation (`color_de`, `shape_de`, `habitat_de`, `growth_rate_de`), fetched once per distinct slug and cached during import since these are small enumerations shared across many species.
- `Pokemon` — one row per variety/form-group (e.g. `pikachu`, `pikachu-gmax`), FK'd to a species. `types`/`abilities`/`stats` are JSON-encoded strings in `Text` columns, not normalized tables — decode with `json.loads` when reading (see `serialize()` in `main.py`). Each type entry additionally carries that type's damage relations (`double_damage_from`/`half_damage_from`/`no_damage_from`, each a list of opposing type slugs) fetched from PokeAPI at import time; the client combines a dual-type Pokémon's own two relation sets multiplicatively to get overall weaknesses/resistances rather than the backend precomputing it. Each ability entry carries `name_de`/`effect_de` fetched from PokeAPI's `/ability/{name}` (falls back from German flavor text to German short effect text; PokeAPI doesn't always have both). Each stat entry carries `name_de` from a small hardcoded map (`STAT_NAMES_DE` in the importer — only 6 stats exist, not worth an API round trip).
- `PokemonForm` — sub-forms of a `Pokemon` (e.g. mega evolutions, regional forms), also with JSON-encoded `types` (no damage relations embedded here, unlike `Pokemon.types`).
- `SpeciesEvolution` — one row per evolution edge (`from_species_id` → `to_species_id`, both `PokemonSpecies.id`; `from_species_id` is null only for a chain's root). Populated in a second pass after all species/pokemon are imported (so referenced species always already exist), by fetching each distinct `evolution_chain_id` once from `/evolution-chain/{id}` and recursively flattening its tree (`flatten_evolution_chain` in the importer). Duplicate evolution methods across game versions (same trigger/level/item/happiness) are deduped per edge. `trigger`/`min_level`/`item`/`min_happiness` are pulled out as columns for easy display; the full raw `evolution_details` dict is kept in `details` (JSON text) for anything not otherwise modeled (e.g. time-of-day, held item, location).

### Backend (`backend/app/`)

- `database.py` — engine/session setup; `DATABASE_PATH` env var controls the SQLite file location (default `/data/pokedex.db`). There is no real migration system (e.g. Alembic). Instead, `init_db()` (backend) and the importer both call `sync_schema()`, which runs `Base.metadata.create_all` (creates missing *tables*) and then, for tables that already exist, diffs each model's columns against `PRAGMA table_info` and issues `ALTER TABLE ... ADD COLUMN` for anything missing. This only supports *adding* nullable columns — it can't rename/drop/retype a column or change constraints, so anything beyond adding a field still needs recreating the DB or a manual migration. Both the backend and the importer must go through `sync_schema()` (the importer imports it from `app.database` rather than calling `Base.metadata.create_all` itself) so a schema change is picked up regardless of which process starts first against an existing database file.
- `main.py` — routes. `/api/pokemon` lists/searches default-form Pokémon (paginated). `search` does a plain `ILIKE '%term%'` substring match against English/German name first; only if that returns zero rows does it fall back to `fuzzy_pokemon_ids()`, a pure-Python (stdlib `difflib`) typo-tolerant scan over all default Pokémon names — cheap since it only runs on the rare no-match case over ~1300 rows, and needs no search index/extra dependency. `ids` (csv of Pokémon ids) and `types` (csv of type slugs, ANDed) are optional extra filters on top of `search`, layered on the same query — `types` matches by `LIKE`-searching the `Pokemon.types` JSON text for `"name": "<slug>"`, since types aren't a normalized column (see `Pokemon.types` above). `/api/pokemon/{identifier}` accepts either a numeric ID, English lowercase name, or exact German name, and additionally includes `evolves_from`/`evolves_to` (each entry is a `serialize_evolution_species()` result — species id, the *default Pokémon's own id* for API lookups, names, sprite — plus the edge's `trigger`/`min_level`/`item`/`min_happiness`); the list endpoint's `serialize()` output does not include evolution data, to keep list responses light. `serialize()` pulls localized/species-level fields (`german_name`, `description_de`, `legendary`, `color_de`, etc.) off `pokemon.species`, not off `Pokemon` directly — those columns only exist on `PokemonSpecies`, so don't reintroduce direct `Pokemon.german_name`-style access. `/media` serves `MEDIA_PATH` (default `/data`) as static files. The `StaticFiles(directory=STATIC_PATH, html=True)` mount at `/` for the frontend is registered *last*, after every `/api/*` route and the `/media` mount — Starlette matches routes in registration order, so a mount at `/` registered earlier would shadow everything. When adding new API routes, add them before that final mount. CORS is wide open (`allow_origins=["*"]`); harmless here since API and UI are same-origin, but left in case the API is ever called cross-origin.
- Sessions are created and closed manually per-request (`SessionLocal()` / `db.close()` in a `finally`) rather than via a FastAPI dependency — follow that pattern when adding routes.

### Voice interface (`backend/app/voice.py`, `esp32/`)

- An ESP32 running [ESPHome](https://esphome.io) (`esp32/pokedex.yaml`, no PlatformIO/Arduino project) is a physical front end: button press wakes it from deep sleep, it records ~4s from an I2S mic, POSTs the audio to the backend, and on a match shows the sprite, plays the cry, and speaks the name/description through an I2S speaker before sleeping again. See `esp32/README.md` for wiring/flashing — not duplicated here.
- All speech runs self-hosted/offline in the backend container: Vosk for German STT, Piper for German TTS — no cloud APIs. Both are lazy-loaded in `voice.py` (`get_vosk_model()`/`get_piper_voice()`) and raise `VoiceUnavailable`, turned into a 503 by the routes in `main.py`, when their model files aren't present under `/models` yet — this keeps the voice endpoints optional so the rest of the app (and `sync_schema()`/DB) is unaffected by whether the (large, not-in-image) model files have been fetched via `backend/scripts/download_models.sh`.
- One fixed wire format — 16kHz mono 16-bit PCM WAV — is used for the mic upload *and* every audio response (TTS name, TTS description, cry), deliberately, so the ESPHome `microphone`/`speaker` components need only one `sample_rate`/`bits_per_sample` config and the firmware never needs an on-device audio codec.
- `POST /api/voice/recognize` transcribes the uploaded WAV then matches the transcript to a Pokémon via `match_transcript_to_pokemon()` (substring `ILIKE` against `PokemonSpecies.german_name` first, falling back to the existing `fuzzy_pokemon_ids()` — German-only, unlike the text search box, since this only ever receives spoken German) and always returns 200 JSON with `matched: true/false` (a non-match is a normal outcome for the firmware to branch on, not an HTTP error).
- `GET /api/pokemon/{id}/tts/name`, `.../tts/description`, and `.../cry.wav` return `audio/wav`, generated via `synthesize_tts()`/`transcode_cry_to_wav()` (the latter shells out to `ffmpeg`, added to the backend image) and cached to disk under `MEDIA_PATH` (`tts/`, `cries_wav/`) keyed by a text hash / pokemon id respectively — plain files, not DB rows, since nothing here needs querying.
- Sprite display does **not** go through the backend at all: ESPHome's `online_image` component decodes the existing `/media/sprites/{id}.png` (served by the pre-existing `/media` static mount) directly on-device, so there's no dedicated image endpoint to keep in sync.

### Importer (`importer/import.py`)

- Fully idempotent/resumable: every entity is upserted by primary key (`db.get(...)` then create-if-missing), and already-downloaded media files are skipped if they already exist and are non-empty. Safe to re-run to pick up new PokeAPI data. `SpeciesEvolution` rows are the exception: they're not upserted per-row, but deleted-and-reinserted per `chain_id` each time that chain is processed (`import_evolution_chain`), which is simpler and equally idempotent given the low row count.
- Commits after each species (and after each form) rather than batching, so a killed run loses at most partial progress on the current species. Evolution chains are a separate pass after the whole species/pokemon loop finishes, so a run killed mid-way imports species/pokemon but not evolutions until re-run to completion.
- HTTP calls go through `get_json()`, which retries on failure/429 with backoff and returns `None` on persistent failure or 404 — callers must handle `None` (skip and continue), not raise.
- All PokeAPI localized content is pulled for `"de"` specifically (`get_localized_name`/`get_localized_genus`/`get_localized_description`); there's no multi-language support to preserve when editing these.
- Shared/enum-like PokeAPI resources referenced by many species or pokemon (types, abilities, colors, shapes, habitats, growth rates) are fetched once per distinct slug and memoized in module-level dicts (`TYPE_CACHE`, `ABILITY_CACHE`, `COLOR_CACHE`, etc.) rather than once per pokemon/species — e.g. `grass` type damage relations are fetched once even though hundreds of Pokémon have that type. These caches live for the process lifetime of a single import run only; they are not persisted.

## Running locally

Everything runs via Docker Compose; there's no documented way to run the backend or importer outside containers (no local venv setup, no lockfile beyond `requirements.txt`).

```bash
# Fetch the German Vosk/Piper voice models once, into ./models (optional —
# only needed for the ESP32 voice interface; everything else works without it)
backend/scripts/download_models.sh

# Start the backend + web UI on port 1510, persists to ./data
docker compose up -d pokedex

# Run the importer once to populate/refresh the DB (uses the "import" profile)
docker compose --profile import run --rm importer

# Or run it on a recurring schedule instead (uses the "scheduler" profile;
# re-runs import.py every IMPORT_INTERVAL_SECONDS, default 7 days)
docker compose --profile scheduler up -d importer-scheduler

# Backend logs
docker compose logs -f pokedex
```

The backend container mounts `./backend/app` into `/app/app` and `./frontend` into `/app/static` for live editing of either without rebuilding (matching the image's `WORKDIR /app` and the `STATIC_PATH` default of `static`). The importer container separately mounts the whole `./backend` (not `./backend/app`) into `/backend`, since it imports `app.models` via `sys.path`. `importer-scheduler` builds the same image as `importer` but overrides the entrypoint to `importer/loop.sh`, a shell loop that re-runs `import.py` and sleeps `IMPORT_INTERVAL_SECONDS` between runs — it's a separate opt-in service/profile, not the default behavior of `importer`.

There are no automated tests, linter, or formatter configured in this repo.
