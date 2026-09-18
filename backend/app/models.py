from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class PokemonSpecies(Base):
    __tablename__ = "pokemon_species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    german_name: Mapped[str | None] = mapped_column(String(100))
    german_genus: Mapped[str | None] = mapped_column(String(100))
    description_de: Mapped[str | None] = mapped_column(Text)

    generation: Mapped[int | None] = mapped_column(Integer)
    capture_rate: Mapped[int | None] = mapped_column(Integer)
    base_happiness: Mapped[int | None] = mapped_column(Integer)

    gender_rate: Mapped[int | None] = mapped_column(Integer)
    hatch_counter: Mapped[int | None] = mapped_column(Integer)

    legendary: Mapped[bool] = mapped_column(Boolean, default=False)
    mythical: Mapped[bool] = mapped_column(Boolean, default=False)
    baby: Mapped[bool] = mapped_column(Boolean, default=False)

    color: Mapped[str | None] = mapped_column(String(50))
    color_de: Mapped[str | None] = mapped_column(String(50))
    shape: Mapped[str | None] = mapped_column(String(50))
    shape_de: Mapped[str | None] = mapped_column(String(50))
    habitat: Mapped[str | None] = mapped_column(String(50))
    habitat_de: Mapped[str | None] = mapped_column(String(50))
    growth_rate: Mapped[str | None] = mapped_column(String(50))
    growth_rate_de: Mapped[str | None] = mapped_column(String(100))

    evolution_chain_id: Mapped[int | None] = mapped_column(Integer)

    pokemon: Mapped[list["Pokemon"]] = relationship(
        back_populates="species",
        cascade="all, delete-orphan",
    )


class Pokemon(Base):
    __tablename__ = "pokemon"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.id"),
        index=True,
    )

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    height_m: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)

    types: Mapped[str] = mapped_column(Text, default="[]")
    abilities: Mapped[str] = mapped_column(Text, default="[]")
    stats: Mapped[str] = mapped_column(Text, default="[]")

    sprite_url: Mapped[str | None] = mapped_column(String(500))
    shiny_url: Mapped[str | None] = mapped_column(String(500))
    cry_url: Mapped[str | None] = mapped_column(String(500))

    species: Mapped["PokemonSpecies"] = relationship(
        back_populates="pokemon"
    )

    forms: Mapped[list["PokemonForm"]] = relationship(
        back_populates="pokemon",
        cascade="all, delete-orphan",
    )


class PokemonForm(Base):
    __tablename__ = "pokemon_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)

    pokemon_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon.id"),
        index=True,
    )

    form_name: Mapped[str | None] = mapped_column(String(100))

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_battle_only: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mega: Mapped[bool] = mapped_column(Boolean, default=False)

    types: Mapped[str] = mapped_column(Text, default="[]")

    sprite_url: Mapped[str | None] = mapped_column(String(500))
    shiny_url: Mapped[str | None] = mapped_column(String(500))

    pokemon: Mapped["Pokemon"] = relationship(
        back_populates="forms"
    )


class SpeciesEvolution(Base):
    __tablename__ = "species_evolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, index=True)

    from_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("pokemon_species.id"),
        index=True,
    )
    to_species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.id"),
        index=True,
    )

    trigger: Mapped[str | None] = mapped_column(String(50))
    min_level: Mapped[int | None] = mapped_column(Integer)
    item: Mapped[str | None] = mapped_column(String(100))
    min_happiness: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str] = mapped_column(Text, default="{}")
