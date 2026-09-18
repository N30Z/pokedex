import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .database import SessionLocal, init_db
from .models import Pokemon, PokemonSpecies


app = FastAPI(
    title="Pokédex Backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_PATH = os.getenv("MEDIA_PATH", "/data")

init_db()

app.mount(
    "/media",
    StaticFiles(directory=MEDIA_PATH),
    name="media",
)


@app.get("/")
def root():
    return {
        "name": "Pokédex Backend",
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


def serialize(pokemon: Pokemon):
    species = pokemon.species

    return {
        "id": pokemon.id,
        "name": pokemon.name,
        "german_name": species.german_name if species else None,
        "types": json.loads(pokemon.types or "[]"),
        "height_m": pokemon.height_m,
        "weight_kg": pokemon.weight_kg,
        "category": species.german_genus if species else None,
        "generation": species.generation if species else None,
        "legendary": species.legendary if species else False,
        "mythical": species.mythical if species else False,
        "capture_rate": species.capture_rate if species else None,
        "base_happiness": species.base_happiness if species else None,
        "abilities": json.loads(pokemon.abilities or "[]"),
        "description_de": species.description_de if species else None,
        "sprite": pokemon.sprite_url,
        "shiny": pokemon.shiny_url,
        "cry": pokemon.cry_url,
    }


@app.get("/api/pokemon")
def list_pokemon(
    search: str | None = None,
    limit: int = 40,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    db = SessionLocal()

    try:
        query = (
            select(Pokemon)
            .join(PokemonSpecies)
            .where(Pokemon.is_default.is_(True))
        )

        if search:
            like = f"%{search.strip().lower()}%"
            query = query.where(
                Pokemon.name.ilike(like)
                | PokemonSpecies.german_name.ilike(like)
            )

        total = db.scalar(
            select(func.count()).select_from(query.subquery())
        )

        rows = db.scalars(
            query.order_by(Pokemon.id).offset(offset).limit(limit)
        ).all()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [serialize(p) for p in rows],
        }

    finally:
        db.close()


@app.get("/api/pokemon/{identifier}")
def get_pokemon(identifier: str):

    db = SessionLocal()

    try:

        if identifier.isdigit():

            pokemon = db.get(
                Pokemon,
                int(identifier),
            )

        else:

            pokemon = db.scalar(
                select(Pokemon)
                .join(PokemonSpecies)
                .where(
                    (Pokemon.name == identifier.lower())
                    | (PokemonSpecies.german_name == identifier)
                )
            )

        if pokemon is None:
            raise HTTPException(
                status_code=404,
                detail="Pokémon nicht gefunden",
            )

        return serialize(pokemon)

    finally:
        db.close()


@app.get("/api/count")
def count():

    db = SessionLocal()

    try:
        return {
            "pokemon": db.query(Pokemon).count()
        }

    finally:
        db.close()
