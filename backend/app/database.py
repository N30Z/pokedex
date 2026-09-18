import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/pokedex.db")

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def sync_schema(target_engine=None):
    """Create missing tables and add missing columns.

    There is no migration tool (e.g. Alembic) in this project. This is a
    minimal stand-in so adding a nullable column to a model doesn't
    require dropping the whole database: create_all() alone only creates
    tables that don't exist yet, it never alters existing ones.
    """
    target_engine = target_engine or engine

    from . import models  # noqa: F401  (registers all tables on Base.metadata)

    Base.metadata.create_all(bind=target_engine)

    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    with target_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue

            existing_columns = {
                col["name"] for col in inspector.get_columns(table.name)
            }

            for column in table.columns:
                if column.name in existing_columns:
                    continue

                col_type = column.type.compile(dialect=target_engine.dialect)

                conn.execute(
                    text(
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {col_type}'
                    )
                )


def init_db():
    sync_schema()
