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

- `PokemonSpecies` — one row per species (the German name/genus/description, generation, legendary/mythical/baby flags, capture rate, etc. all live here, not on `Pokemon`).
- `Pokemon` — one row per variety/form-group (e.g. `pikachu`, `pikachu-gmax`), FK'd to a species. Types/abilities/stats are stored as JSON-encoded strings in `Text` columns, not normalized tables — decode with `json.loads` when reading (see `serialize()` in `main.py`).
- `PokemonForm` — sub-forms of a `Pokemon` (e.g. mega evolutions, regional forms), also with JSON-encoded `types`.

### Backend (`backend/app/`)

- `database.py` — engine/session setup; `DATABASE_PATH` env var controls the SQLite file location (default `/data/pokedex.db`). `init_db()` calls `Base.metadata.create_all` — there is no migration system (e.g. Alembic); schema changes require recreating the DB or manually altering it.
- `main.py` — routes. `/api/pokemon` lists/searches default-form Pokémon (paginated); `/api/pokemon/{identifier}` accepts either a numeric ID, English lowercase name, or exact German name. `serialize()` pulls localized/species-level fields (`german_name`, `description_de`, `legendary`, etc.) off `pokemon.species`, not off `Pokemon` directly — those columns only exist on `PokemonSpecies`, so don't reintroduce direct `Pokemon.german_name`-style access. `/media` serves `MEDIA_PATH` (default `/data`) as static files. The `StaticFiles(directory=STATIC_PATH, html=True)` mount at `/` for the frontend is registered *last*, after every `/api/*` route and the `/media` mount — Starlette matches routes in registration order, so a mount at `/` registered earlier would shadow everything. When adding new API routes, add them before that final mount. CORS is wide open (`allow_origins=["*"]`); harmless here since API and UI are same-origin, but left in case the API is ever called cross-origin.
- Sessions are created and closed manually per-request (`SessionLocal()` / `db.close()` in a `finally`) rather than via a FastAPI dependency — follow that pattern when adding routes.

### Importer (`importer/import.py`)

- Fully idempotent/resumable: every entity is upserted by primary key (`db.get(...)` then create-if-missing), and already-downloaded media files are skipped if they already exist and are non-empty. Safe to re-run to pick up new PokeAPI data.
- Commits after each species (and after each form) rather than batching, so a killed run loses at most partial progress on the current species.
- HTTP calls go through `get_json()`, which retries on failure/429 with backoff and returns `None` on persistent failure or 404 — callers must handle `None` (skip and continue), not raise.
- All PokeAPI localized content is pulled for `"de"` specifically (`get_localized_name`/`get_localized_genus`/`get_localized_description`); there's no multi-language support to preserve when editing these.

## Running locally

Everything runs via Docker Compose; there's no documented way to run the backend or importer outside containers (no local venv setup, no lockfile beyond `requirements.txt`).

```bash
# Start the backend + web UI on port 1510, persists to ./data
docker compose up -d pokedex

# Run the importer once to populate/refresh the DB (uses the "import" profile)
docker compose --profile import run --rm importer

# Backend logs
docker compose logs -f pokedex
```

The backend container mounts `./backend/app` into `/app/app` and `./frontend` into `/app/static` for live editing of either without rebuilding (matching the image's `WORKDIR /app` and the `STATIC_PATH` default of `static`). The importer container separately mounts the whole `./backend` (not `./backend/app`) into `/backend`, since it imports `app.models` via `sys.path`.

There are no automated tests, linter, or formatter configured in this repo.
