import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/backend")

from app.models import Base, PokemonSpecies, Pokemon, PokemonForm


API = "https://pokeapi.co/api/v2"

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/data/pokedex.db",
)

MEDIA_PATH = Path("/data")

SPRITES_PATH = MEDIA_PATH / "sprites"
SHINY_PATH = MEDIA_PATH / "shiny"
CRIES_PATH = MEDIA_PATH / "cries"

SPRITES_PATH.mkdir(parents=True, exist_ok=True)
SHINY_PATH.mkdir(parents=True, exist_ok=True)
CRIES_PATH.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(engine)


# ---------------------------------------------------------
# HTTP
# ---------------------------------------------------------

async def get_json(
    client: httpx.AsyncClient,
    url: str,
    retries: int = 5,
):
    for attempt in range(1, retries + 1):
        try:
            response = await client.get(
                url,
                timeout=60,
                follow_redirects=True,
            )

            if response.status_code == 404:
                print(f"    404: {url}")
                return None

            if response.status_code == 429:
                wait = attempt * 3
                print(
                    f"    HTTP 429 - warte {wait}s"
                )
                await asyncio.sleep(wait)
                continue

            response.raise_for_status()

            return response.json()

        except Exception as exc:
            print(
                f"    Fehler ({attempt}/{retries}): "
                f"{exc}"
            )

            if attempt < retries:
                await asyncio.sleep(attempt * 2)

    print(f"    ENDGÜLTIG FEHLER: {url}")

    return None


async def download_file(
    client: httpx.AsyncClient,
    url: str | None,
    target: Path,
):
    if not url:
        return None

    if target.exists() and target.stat().st_size > 0:
        return str(target)

    try:
        response = await client.get(
            url,
            timeout=120,
            follow_redirects=True,
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        target.write_bytes(response.content)

        return str(target)

    except Exception as exc:
        print(
            f"    Download-Fehler: {url}: {exc}"
        )

        return None


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def get_localized_name(data, language="de"):
    for entry in data.get("names", []):
        if entry.get("language", {}).get("name") == language:
            return entry.get("name")

    return None


def get_localized_genus(data, language="de"):
    for entry in data.get("genera", []):
        if entry.get("language", {}).get("name") == language:
            return entry.get("genus")

    return None


def get_localized_description(data, language="de"):
    entries = [
        entry
        for entry in data.get("flavor_text_entries", [])
        if entry.get("language", {}).get("name") == language
    ]

    if not entries:
        return None

    # Neueste verfügbare deutsche Beschreibung
    text = entries[-1].get("flavor_text", "")

    return (
        text
        .replace("\n", " ")
        .replace("\f", " ")
        .replace("  ", " ")
        .strip()
    )


def generation_number(generation):
    if not generation:
        return None

    name = generation.get("name", "")

    try:
        return int(name.split("-")[-1])
    except Exception:
        return None


def extract_id_from_url(url):
    if not url:
        return None

    try:
        return int(
            url.rstrip("/").split("/")[-1]
        )
    except Exception:
        return None


def safe_filename(name):
    return (
        name
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "-")
    )


# ---------------------------------------------------------
# Species
# ---------------------------------------------------------

async def import_species(
    client,
    db,
    species_data,
):
    species_id = species_data["id"]
    species_name = species_data["name"]

    species = db.get(
        PokemonSpecies,
        species_id,
    )

    if species is None:
        species = PokemonSpecies(
            id=species_id,
            name=species_name,
        )
        db.add(species)

    species.name = species_name

    species.german_name = get_localized_name(
        species_data,
        "de",
    )

    species.german_genus = get_localized_genus(
        species_data,
        "de",
    )

    species.description_de = (
        get_localized_description(
            species_data,
            "de",
        )
    )

    species.generation = generation_number(
        species_data.get("generation")
    )

    species.capture_rate = (
        species_data.get("capture_rate")
    )

    species.base_happiness = (
        species_data.get("base_happiness")
    )

    species.gender_rate = (
        species_data.get("gender_rate")
    )

    species.hatch_counter = (
        species_data.get("hatch_counter")
    )

    species.legendary = bool(
        species_data.get("is_legendary")
    )

    species.mythical = bool(
        species_data.get("is_mythical")
    )

    species.baby = bool(
        species_data.get("is_baby")
    )

    species.color = (
        species_data.get("color") or {}
    ).get("name")

    species.shape = (
        species_data.get("shape") or {}
    ).get("name")

    species.habitat = (
        species_data.get("habitat") or {}
    ).get("name")

    species.growth_rate = (
        species_data.get("growth_rate") or {}
    ).get("name")

    evolution_chain = species_data.get(
        "evolution_chain"
    )

    species.evolution_chain_id = (
        extract_id_from_url(
            evolution_chain.get("url")
        )
        if evolution_chain
        else None
    )

    db.commit()

    return species


# ---------------------------------------------------------
# Pokemon
# ---------------------------------------------------------

async def import_pokemon(
    client,
    db,
    pokemon_data,
    species,
    is_default=False,
):
    pokemon_id = pokemon_data["id"]
    pokemon_name = pokemon_data["name"]

    pokemon = db.get(
        Pokemon,
        pokemon_id,
    )

    if pokemon is None:
        pokemon = Pokemon(
            id=pokemon_id,
            name=pokemon_name,
            species_id=species.id,
        )
        db.add(pokemon)

    pokemon.name = pokemon_name
    pokemon.species_id = species.id
    pokemon.is_default = bool(
        pokemon_data.get(
            "is_default",
            is_default,
        )
    )

    pokemon.height_m = (
        pokemon_data.get("height", 0) / 10
    )

    pokemon.weight_kg = (
        pokemon_data.get("weight", 0) / 10
    )

    pokemon.types = json.dumps(
        [
            {
                "slot": entry["slot"],
                "name": entry["type"]["name"],
            }
            for entry in pokemon_data.get(
                "types",
                [],
            )
        ],
        ensure_ascii=False,
    )

    pokemon.abilities = json.dumps(
        [
            {
                "name": entry["ability"]["name"],
                "hidden": entry["is_hidden"],
                "slot": entry["slot"],
            }
            for entry in pokemon_data.get(
                "abilities",
                [],
            )
        ],
        ensure_ascii=False,
    )

    pokemon.stats = json.dumps(
        [
            {
                "name": entry["stat"]["name"],
                "value": entry["base_stat"],
                "effort": entry["effort"],
            }
            for entry in pokemon_data.get(
                "stats",
                [],
            )
        ],
        ensure_ascii=False,
    )

    sprites = pokemon_data.get(
        "sprites",
        {},
    )

    normal_url = sprites.get(
        "front_default"
    )

    shiny_url = sprites.get(
        "front_shiny"
    )

    cries = pokemon_data.get(
        "cries",
        {},
    )

    cry_url = (
        cries.get("latest")
        or cries.get("legacy")
    )

    pokemon.sprite_url = await download_file(
        client,
        normal_url,
        SPRITES_PATH / f"{pokemon_id}.png",
    )

    pokemon.shiny_url = await download_file(
        client,
        shiny_url,
        SHINY_PATH / f"{pokemon_id}.png",
    )

    pokemon.cry_url = await download_file(
        client,
        cry_url,
        CRIES_PATH / f"{pokemon_id}.ogg",
    )

    db.commit()

    # -----------------------------------------------------
    # Forms
    # -----------------------------------------------------

    for form_ref in pokemon_data.get(
        "forms",
        [],
    ):
        form_data = await get_json(
            client,
            form_ref["url"],
        )

        if not form_data:
            continue

        form_id = form_data["id"]

        form = db.get(
            PokemonForm,
            form_id,
        )

        if form is None:
            form = PokemonForm(
                id=form_id,
                name=form_data["name"],
                pokemon_id=pokemon.id,
            )
            db.add(form)

        form.name = form_data["name"]
        form.pokemon_id = pokemon.id

        form.form_name = (
            form_data.get("form_name")
        )

        form.is_default = bool(
            form_data.get("is_default")
        )

        form.is_battle_only = bool(
            form_data.get("is_battle_only")
        )

        form.is_mega = bool(
            form_data.get("is_mega")
        )

        form.types = json.dumps(
            [
                entry["type"]["name"]
                for entry in form_data.get(
                    "types",
                    [],
                )
            ],
            ensure_ascii=False,
        )

        form_sprites = (
            form_data.get("sprites") or {}
        )

        form.sprite_url = (
            form_sprites.get(
                "front_default"
            )
        )

        form.shiny_url = (
            form_sprites.get(
                "front_shiny"
            )
        )

        db.commit()

    return pokemon


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

async def main():

    print()
    print("==============================")
    print("Pokédex Importer")
    print("==============================")
    print()

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Local-Pokedex/1.0"
        }
    ) as client:

        print("Lade Species-Liste...")

        species_list = await get_json(
            client,
            f"{API}/pokemon-species?limit=20000",
        )

        if not species_list:
            print("Species-Liste konnte nicht geladen werden.")
            return

        species_entries = species_list["results"]

        print(
            f"{len(species_entries)} Species gefunden."
        )

        db = SessionLocal()

        try:

            for index, entry in enumerate(
                species_entries,
                start=1,
            ):

                species_name = entry["name"]

                # -----------------------------------------
                # Species laden
                # -----------------------------------------

                species_data = await get_json(
                    client,
                    entry["url"],
                )

                if not species_data:
                    print(
                        f"[{index}/{len(species_entries)}] "
                        f"{species_name} -> ÜBERSPRUNGEN"
                    )
                    continue

                german = (
                    get_localized_name(
                        species_data,
                        "de",
                    )
                    or species_name
                )

                print(
                    f"[{index}/{len(species_entries)}] "
                    f"{german} ({species_name})"
                )

                species = await import_species(
                    client,
                    db,
                    species_data,
                )

                # -----------------------------------------
                # ALLE VARIETIES
                # -----------------------------------------

                varieties = species_data.get(
                    "varieties",
                    [],
                )

                for variety in varieties:

                    pokemon_ref = variety.get(
                        "pokemon"
                    )

                    if not pokemon_ref:
                        continue

                    pokemon_name = pokemon_ref["name"]

                    pokemon_data = await get_json(
                        client,
                        pokemon_ref["url"],
                    )

                    if not pokemon_data:
                        print(
                            f"    -> Variante "
                            f"{pokemon_name} übersprungen"
                        )
                        continue

                    await import_pokemon(
                        client,
                        db,
                        pokemon_data,
                        species,
                        is_default=variety.get(
                            "is_default",
                            False,
                        ),
                    )

                # Sicherung nach jeder Species
                db.commit()

        finally:
            db.close()

    print()
    print("==============================")
    print("Import abgeschlossen")
    print("==============================")


if __name__ == "__main__":
    asyncio.run(main())
