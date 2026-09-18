import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .database import SessionLocal, init_db
from .models import Pokemon


app = FastAPI(
    title="Pokédex Backend",
    version="0.1.0",
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
    return {
        "id": pokemon.id,
        "name": pokemon.name,
        "german_name": pokemon.german_name,
        "types": json.loads(pokemon.types or "[]"),
        "height_m": pokemon.height_m,
        "weight_kg": pokemon.weight_kg,
        "category": pokemon.category,
        "generation": pokemon.generation,
        "legendary": pokemon.legendary,
        "mythical": pokemon.mythical,
        "capture_rate": pokemon.capture_rate,
        "base_happiness": pokemon.base_happiness,
        "abilities": json.loads(pokemon.abilities or "[]"),
        "description_de": pokemon.description_de,
        "sprite": pokemon.sprite_url,
        "shiny": pokemon.shiny_url,
        "cry": pokemon.cry_url,
    }


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
                select(Pokemon).where(
                    (Pokemon.name == identifier.lower())
                    | (Pokemon.german_name == identifier)
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
