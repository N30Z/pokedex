# Pokédex

A self-hosted, German-language Pokédex: a FastAPI backend serving Pokémon data from a local SQLite database and a web UI to browse and search it, plus a one-shot importer that pulls and localizes data from [PokeAPI](https://pokeapi.co/api/v2) (including sprites and cries) into that database.

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
```

Open http://localhost:1510 in your browser to use the Pokédex. The importer downloads data for every Pokémon species and its media (sprites, shiny sprites, cries) from PokeAPI, so the first run can take a while and needs internet access; it's safe to interrupt and re-run, since it skips anything already imported.

Data and media are persisted to `./data` on the host.

## API

The web UI, JSON API, and media are all served from the same port (1510). The JSON API lives under `/api`, with interactive docs at `/docs`.

- `GET /api/pokemon?search=&limit=&offset=` — list/search default Pokémon forms (paginated, `limit` max 100). `search` matches either the English or German name.
- `GET /api/pokemon/{identifier}` — fetch a single Pokémon by numeric ID, English name, or exact German name. Includes base stats, type matchups (`double_damage_from`/`half_damage_from`/`no_damage_from` per type, for computing a weakness chart), abilities with German names/effects, species traits (color, shape, habitat, growth rate, gender ratio, egg cycles), and `evolves_from`/`evolves_to` evolution chain data.
- `GET /api/count` — total number of Pokémon in the database.
- `GET /media/...` — serves downloaded sprites (`sprites/`), shiny sprites (`shiny/`), and cries (`cries/`).

## Configuration

Environment variables (set in `docker-compose.yml`):

- `DATABASE_PATH` — path to the SQLite file (default `/data/pokedex.db`).
- `MEDIA_PATH` — directory the backend serves under `/media` (default `/data`).
- `STATIC_PATH` — directory the backend serves the web UI from (default `static`, i.e. the bundled `frontend/` files).

## Development

There's no local (non-Docker) dev setup, build tooling, or test suite — everything runs via the containers above. The backend container mounts `./backend/app` and `./frontend` directly for live code editing without rebuilding.

See `CLAUDE.md` for a deeper architecture overview (data model, import flow, code conventions) aimed at AI coding assistants.
