import asyncio
import json
import os
import sys
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/backend")

from app.database import sync_schema
from app.models import (
    PokemonSpecies,
    Pokemon,
    PokemonForm,
    SpeciesEvolution,
)


API = "https://pokeapi.co/api/v2"

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/data/pokedex.db",
)

MEDIA_PATH = Path("/data")

SPRITES_PATH = MEDIA_PATH / "sprites"
SHINY_PATH = MEDIA_PATH / "shiny"
CRIES_PATH = MEDIA_PATH / "cries"
ARTWORK_PATH = MEDIA_PATH / "artwork"
ARTWORK_SHINY_PATH = MEDIA_PATH / "artwork-shiny"

SPRITES_PATH.mkdir(parents=True, exist_ok=True)
SHINY_PATH.mkdir(parents=True, exist_ok=True)
CRIES_PATH.mkdir(parents=True, exist_ok=True)
ARTWORK_PATH.mkdir(parents=True, exist_ok=True)
ARTWORK_SHINY_PATH.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine)

sync_schema(engine)


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


ARTWORK_SIZE = 1024


async def download_artwork(
    client: httpx.AsyncClient,
    url: str | None,
    target: Path,
    size: int = ARTWORK_SIZE,
):
    """Download PokeAPI artwork and upscale it to a fixed square canvas.

    PokeAPI's official-artwork sprites are natively only 475x475, so this
    doesn't add real detail - it just gives the frontend lightbox a
    consistently large, pre-rendered image instead of upscaling in the
    browser on every view.
    """
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

        image = Image.open(BytesIO(response.content)).convert("RGBA")

        scale = size / max(image.width, image.height)
        new_size = (
            max(1, round(image.width * scale)),
            max(1, round(image.height * scale)),
        )
        image = image.resize(new_size, Image.LANCZOS)

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        offset = (
            (size - image.width) // 2,
            (size - image.height) // 2,
        )
        canvas.paste(image, offset, image)

        canvas.save(target)

        return str(target)

    except Exception as exc:
        print(
            f"    Artwork-Fehler: {url}: {exc}"
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


ROMAN_NUMERALS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}


def generation_number(generation):
    if not generation:
        return None

    name = generation.get("name", "")

    return ROMAN_NUMERALS.get(name.split("-")[-1])


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


def get_localized_short_effect(data, language="de"):
    for entry in data.get("effect_entries", []):
        if entry.get("language", {}).get("name") == language:
            return entry.get("short_effect")

    return None


# ---------------------------------------------------------
# Cached lookups for shared/enum-like PokeAPI resources
# ---------------------------------------------------------

COLOR_CACHE = {}
SHAPE_CACHE = {}
HABITAT_CACHE = {}
GROWTH_RATE_CACHE = {}
ABILITY_CACHE = {}
TYPE_CACHE = {}

STAT_NAMES_DE = {
    "hp": "KP",
    "attack": "Angriff",
    "defense": "Verteidigung",
    "special-attack": "Sp. Angriff",
    "special-defense": "Sp. Verteidigung",
    "speed": "Initiative",
}


async def get_localized_resource_name(client, cache, endpoint, slug):
    if not slug:
        return None

    if slug in cache:
        return cache[slug]

    data = await get_json(client, f"{API}/{endpoint}/{slug}")

    name_de = get_localized_name(data) if data else None

    cache[slug] = name_de

    return name_de


async def get_ability_de(client, slug):
    if not slug:
        return None

    if slug in ABILITY_CACHE:
        return ABILITY_CACHE[slug]

    data = await get_json(client, f"{API}/ability/{slug}")

    result = {
        "name_de": get_localized_name(data) if data else None,
        "effect_de": (
            get_localized_description(data)
            or get_localized_short_effect(data)
        )
        if data
        else None,
    }

    ABILITY_CACHE[slug] = result

    return result


async def get_type_damage_relations(client, slug):
    if not slug:
        return None

    if slug in TYPE_CACHE:
        return TYPE_CACHE[slug]

    data = await get_json(client, f"{API}/type/{slug}")

    relations = (data or {}).get("damage_relations", {})

    result = {
        "double_damage_from": [
            t["name"] for t in relations.get("double_damage_from", [])
        ],
        "half_damage_from": [
            t["name"] for t in relations.get("half_damage_from", [])
        ],
        "no_damage_from": [
            t["name"] for t in relations.get("no_damage_from", [])
        ],
    }

    TYPE_CACHE[slug] = result

    return result


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

    species.color_de = await get_localized_resource_name(
        client, COLOR_CACHE, "pokemon-color", species.color
    )

    species.shape = (
        species_data.get("shape") or {}
    ).get("name")

    species.shape_de = await get_localized_resource_name(
        client, SHAPE_CACHE, "pokemon-shape", species.shape
    )

    species.habitat = (
        species_data.get("habitat") or {}
    ).get("name")

    species.habitat_de = await get_localized_resource_name(
        client, HABITAT_CACHE, "pokemon-habitat", species.habitat
    )

    species.growth_rate = (
        species_data.get("growth_rate") or {}
    ).get("name")

    species.growth_rate_de = await get_localized_resource_name(
        client, GROWTH_RATE_CACHE, "growth-rate", species.growth_rate
    )

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

    type_entries = []

    for entry in pokemon_data.get("types", []):
        type_name = entry["type"]["name"]
        relations = await get_type_damage_relations(client, type_name)

        type_entries.append(
            {
                "slot": entry["slot"],
                "name": type_name,
                **(relations or {}),
            }
        )

    pokemon.types = json.dumps(type_entries, ensure_ascii=False)

    ability_entries = []

    for entry in pokemon_data.get("abilities", []):
        ability_name = entry["ability"]["name"]
        ability_de = await get_ability_de(client, ability_name)

        ability_entries.append(
            {
                "name": ability_name,
                "hidden": entry["is_hidden"],
                "slot": entry["slot"],
                **(ability_de or {}),
            }
        )

    pokemon.abilities = json.dumps(ability_entries, ensure_ascii=False)

    pokemon.stats = json.dumps(
        [
            {
                "name": entry["stat"]["name"],
                "name_de": STAT_NAMES_DE.get(entry["stat"]["name"]),
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

    other_sprites = sprites.get("other") or {}

    artwork_url = (
        other_sprites.get("official-artwork") or {}
    ).get("front_default")

    artwork_shiny_url = (
        other_sprites.get("official-artwork") or {}
    ).get("front_shiny")

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

    pokemon.artwork_url = await download_artwork(
        client,
        artwork_url,
        ARTWORK_PATH / f"{pokemon_id}.png",
    )

    pokemon.artwork_shiny_url = await download_artwork(
        client,
        artwork_shiny_url,
        ARTWORK_SHINY_PATH / f"{pokemon_id}.png",
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
# Evolution chains
# ---------------------------------------------------------

def flatten_evolution_chain(node, edges=None):
    edges = [] if edges is None else edges

    from_species_id = extract_id_from_url(
        node.get("species", {}).get("url")
    )

    for evo in node.get("evolves_to", []):
        to_species_id = extract_id_from_url(
            evo.get("species", {}).get("url")
        )

        seen = set()

        for detail in evo.get("evolution_details") or [{}]:
            key = (
                (detail.get("trigger") or {}).get("name"),
                detail.get("min_level"),
                (detail.get("item") or {}).get("name"),
                detail.get("min_happiness"),
            )

            if key in seen:
                continue

            seen.add(key)

            edges.append(
                {
                    "from_species_id": from_species_id,
                    "to_species_id": to_species_id,
                    "trigger": key[0],
                    "min_level": key[1],
                    "item": key[2],
                    "min_happiness": key[3],
                    "details": detail,
                }
            )

        flatten_evolution_chain(evo, edges)

    return edges


async def import_evolution_chain(client, db, chain_id):
    chain_data = await get_json(
        client,
        f"{API}/evolution-chain/{chain_id}/",
    )

    if not chain_data:
        return

    edges = flatten_evolution_chain(chain_data.get("chain", {}))

    db.query(SpeciesEvolution).filter(
        SpeciesEvolution.chain_id == chain_id
    ).delete()

    for edge in edges:
        db.add(
            SpeciesEvolution(
                chain_id=chain_id,
                from_species_id=edge["from_species_id"],
                to_species_id=edge["to_species_id"],
                trigger=edge["trigger"],
                min_level=edge["min_level"],
                item=edge["item"],
                min_happiness=edge["min_happiness"],
                details=json.dumps(edge["details"], ensure_ascii=False),
            )
        )

    db.commit()


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
        evolution_chain_ids = set()

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

                if species.evolution_chain_id:
                    evolution_chain_ids.add(
                        species.evolution_chain_id
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

            # ---------------------------------------------
            # Entwicklungsketten
            # ---------------------------------------------

            print()
            print(
                f"Lade {len(evolution_chain_ids)} "
                "Entwicklungsketten..."
            )

            for index, chain_id in enumerate(
                sorted(evolution_chain_ids),
                start=1,
            ):
                print(
                    f"[{index}/{len(evolution_chain_ids)}] "
                    f"Kette #{chain_id}"
                )

                await import_evolution_chain(
                    client,
                    db,
                    chain_id,
                )

        finally:
            db.close()

    print()
    print("==============================")
    print("Import abgeschlossen")
    print("==============================")


if __name__ == "__main__":
    asyncio.run(main())
