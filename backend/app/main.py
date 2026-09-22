import difflib
import json
import os

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import voice
from .database import SessionLocal, init_db
from .models import Pokemon, PokemonSpecies, SpeciesEvolution


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
STATIC_PATH = os.getenv("STATIC_PATH", "static")

init_db()

app.mount(
    "/media",
    StaticFiles(directory=MEDIA_PATH),
    name="media",
)


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
        "baby": species.baby if species else False,
        "capture_rate": species.capture_rate if species else None,
        "base_happiness": species.base_happiness if species else None,
        "gender_rate": species.gender_rate if species else None,
        "hatch_counter": species.hatch_counter if species else None,
        "color": species.color if species else None,
        "color_de": species.color_de if species else None,
        "shape": species.shape if species else None,
        "shape_de": species.shape_de if species else None,
        "habitat": species.habitat if species else None,
        "habitat_de": species.habitat_de if species else None,
        "growth_rate": species.growth_rate if species else None,
        "growth_rate_de": species.growth_rate_de if species else None,
        "abilities": json.loads(pokemon.abilities or "[]"),
        "stats": json.loads(pokemon.stats or "[]"),
        "description_de": species.description_de if species else None,
        "sprite": pokemon.sprite_url,
        "shiny": pokemon.shiny_url,
        "cry": pokemon.cry_url,
        "artwork": pokemon.artwork_url,
        "artwork_shiny": pokemon.artwork_shiny_url,
    }


def serialize_evolution_species(db, species_id):
    species = db.get(PokemonSpecies, species_id)

    if species is None:
        return {
            "species_id": species_id,
            "name": None,
            "german_name": None,
            "sprite": None,
        }

    default_pokemon = db.scalar(
        select(Pokemon).where(
            Pokemon.species_id == species_id,
            Pokemon.is_default.is_(True),
        )
    )

    return {
        "species_id": species_id,
        "pokemon_id": default_pokemon.id if default_pokemon else None,
        "name": species.name,
        "german_name": species.german_name,
        "sprite": default_pokemon.sprite_url if default_pokemon else None,
    }


def fuzzy_pokemon_ids(db, term, limit=60, threshold=0.6):
    """Typo-tolerant fallback for when a plain substring search finds nothing.

    Scores every default Pokémon's English/German name against the search
    term with difflib's ratio (stdlib, no extra dependency) and keeps close
    matches. The dataset is small (~1300 species), so scoring it in Python
    on every fallback call is cheap and needs no separate search index.
    """
    term_norm = term.strip().lower()

    if not term_norm:
        return []

    candidates = db.execute(
        select(Pokemon.id, Pokemon.name, PokemonSpecies.german_name)
        .join(PokemonSpecies)
        .where(Pokemon.is_default.is_(True))
    ).all()

    scored = []

    for pokemon_id, name, german_name in candidates:
        ratio = max(
            difflib.SequenceMatcher(None, term_norm, (name or "").lower()).ratio(),
            difflib.SequenceMatcher(None, term_norm, (german_name or "").lower()).ratio(),
        )

        if ratio >= threshold:
            scored.append((ratio, pokemon_id))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [pokemon_id for _, pokemon_id in scored[:limit]]


def match_transcript_to_pokemon(db, transcript: str):
    """Match a German speech transcript to a default Pokémon.

    German-only (unlike the text search box, which also matches English
    names) since this only ever receives spoken German. Tries a substring
    match first, then falls back to fuzzy_pokemon_ids's difflib scoring
    (reused rather than duplicated) for typo/mishearing tolerance.
    """
    term = transcript.strip()

    if not term:
        return None

    like = f"%{term.lower()}%"

    pokemon = db.scalar(
        select(Pokemon)
        .join(PokemonSpecies)
        .where(
            Pokemon.is_default.is_(True),
            PokemonSpecies.german_name.ilike(like),
        )
    )

    if pokemon is not None:
        return pokemon, 1.0

    candidate_ids = fuzzy_pokemon_ids(db, term, limit=1)

    if not candidate_ids:
        return None

    pokemon = db.get(Pokemon, candidate_ids[0])

    confidence = difflib.SequenceMatcher(
        None, term.lower(), (pokemon.species.german_name or "").lower()
    ).ratio()

    return pokemon, confidence


def serialize_evolution_edge(db, edge, other_species_id):
    info = serialize_evolution_species(db, other_species_id)

    info.update(
        {
            "trigger": edge.trigger,
            "min_level": edge.min_level,
            "item": edge.item,
            "min_happiness": edge.min_happiness,
        }
    )

    return info


@app.get("/api/pokemon")
def list_pokemon(
    search: str | None = None,
    ids: str | None = None,
    types: str | None = None,
    generation: int | None = None,
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
            substring_query = query.where(
                Pokemon.name.ilike(like)
                | PokemonSpecies.german_name.ilike(like)
            )

            substring_hit = db.scalar(
                select(func.count()).select_from(substring_query.subquery())
            )

            if substring_hit:
                query = substring_query
            else:
                query = query.where(
                    Pokemon.id.in_(fuzzy_pokemon_ids(db, search))
                )

        if ids:
            id_list = [
                int(part)
                for part in ids.split(",")
                if part.strip().isdigit()
            ]
            query = query.where(Pokemon.id.in_(id_list))

        if generation:
            query = query.where(PokemonSpecies.generation == generation)

        if types:
            type_list = [
                part.strip().lower()
                for part in types.split(",")
                if part.strip()
            ]
            for type_slug in type_list:
                escaped = (
                    type_slug
                    .replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                query = query.where(
                    Pokemon.types.like(
                        f'%"name": "{escaped}"%',
                        escape="\\",
                    )
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


def _get_pokemon_or_404(db, identifier: str) -> Pokemon:
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

    return pokemon


@app.get("/api/pokemon/{identifier}")
def get_pokemon(identifier: str):

    db = SessionLocal()

    try:
        pokemon = _get_pokemon_or_404(db, identifier)

        result = serialize(pokemon)

        species_id = pokemon.species_id

        evolves_from = db.scalars(
            select(SpeciesEvolution).where(
                SpeciesEvolution.to_species_id == species_id
            )
        ).all()

        evolves_to = db.scalars(
            select(SpeciesEvolution).where(
                SpeciesEvolution.from_species_id == species_id
            )
        ).all()

        result["evolves_from"] = [
            serialize_evolution_edge(db, e, e.from_species_id)
            for e in evolves_from
        ]

        result["evolves_to"] = [
            serialize_evolution_edge(db, e, e.to_species_id)
            for e in evolves_to
        ]

        return result

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


@app.post("/api/voice/recognize")
async def recognize_voice(request: Request):
    wav_bytes = await request.body()

    try:
        transcript = voice.transcribe_wav(wav_bytes)
    except voice.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (ValueError, EOFError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db = SessionLocal()

    try:
        match = match_transcript_to_pokemon(db, transcript)

        if match is None:
            return {"transcript": transcript, "matched": False}

        pokemon, confidence = match

        return {
            "transcript": transcript,
            "matched": True,
            "confidence": confidence,
            "id": pokemon.id,
            "name": pokemon.name,
            "german_name": pokemon.species.german_name if pokemon.species else None,
        }

    finally:
        db.close()


@app.get("/api/pokemon/{identifier}/tts/name")
def get_pokemon_tts_name(identifier: str):
    db = SessionLocal()

    try:
        pokemon = _get_pokemon_or_404(db, identifier)
        german_name = pokemon.species.german_name if pokemon.species else None

        if not german_name:
            raise HTTPException(
                status_code=404,
                detail="Kein deutscher Name vorhanden",
            )

        try:
            wav_bytes = voice.synthesize_tts(german_name)
        except voice.VoiceUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        return Response(content=wav_bytes, media_type="audio/wav")

    finally:
        db.close()


@app.get("/api/pokemon/{identifier}/tts/description")
def get_pokemon_tts_description(identifier: str):
    db = SessionLocal()

    try:
        pokemon = _get_pokemon_or_404(db, identifier)
        species = pokemon.species
        description = species.description_de if species else None

        if not description:
            raise HTTPException(
                status_code=404,
                detail="Keine deutsche Beschreibung vorhanden",
            )

        try:
            wav_bytes = voice.synthesize_tts(description)
        except voice.VoiceUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        return Response(content=wav_bytes, media_type="audio/wav")

    finally:
        db.close()


@app.get("/api/pokemon/{identifier}/cry.wav")
def get_pokemon_cry_wav(identifier: str):
    db = SessionLocal()

    try:
        pokemon = _get_pokemon_or_404(db, identifier)

        if not pokemon.cry_url or not os.path.isfile(pokemon.cry_url):
            raise HTTPException(
                status_code=404,
                detail="Kein Cry vorhanden",
            )

        wav_bytes = voice.transcode_cry_to_wav(pokemon.cry_url, pokemon.id)

        return Response(content=wav_bytes, media_type="audio/wav")

    finally:
        db.close()


@app.get("/api/pokemon/{identifier}/display.png")
def get_pokemon_display_image(identifier: str, shiny: bool = False):
    db = SessionLocal()

    try:
        pokemon = _get_pokemon_or_404(db, identifier)

        # Shiny artwork is missing for some forms; fall back to the normal one.
        candidates = (["artwork-shiny"] if shiny else []) + ["artwork"]
        src_path = None
        folder = None

        for folder in candidates:
            path = os.path.join(MEDIA_PATH, folder, f"{pokemon.id}.png")

            if os.path.isfile(path):
                src_path = path
                break

        if src_path is None:
            raise HTTPException(
                status_code=404,
                detail="Kein Artwork vorhanden",
            )

        png_bytes = voice.render_display_image(
            src_path, f"{folder}-{pokemon.id}"
        )

        return Response(content=png_bytes, media_type="image/png")

    finally:
        db.close()


app.mount(
    "/",
    StaticFiles(directory=STATIC_PATH, html=True),
    name="frontend",
)
