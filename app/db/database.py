# app/db/database.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker # <-- ADD async_sessionmaker here
from sqlalchemy.orm import declarative_base # Keep if Base is defined here, otherwise remove
from app.core.config import settings # Assuming this is your correct settings import path
from postgres.models import Base# <-- IMPORTANT: Ensure you import Base from your ORM models file

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{settings.POSTGRES_USER}:"
    f"{settings.POSTGRES_PASSWORD}@"
    f"{settings.POSTGRES_HOST}:"
    f"{settings.POSTGRES_PORT}/"
    f"{settings.POSTGRES_DB}"
)
# Note: If your app.core.config.py already defines a full settings.DATABASE_URL string,
# you can use that directly instead of reconstructing it here.

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = async_sessionmaker( # <-- CHANGE THIS LINE: from sessionmaker to async_sessionmaker
    engine, expire_on_commit=False, class_=AsyncSession
)

# Base = declarative_base() # <-- If Base is imported from app.db.models, remove this line to avoid redefinition.
                          #    If your Base is genuinely defined *only* in this file, keep it.
                          #    Typically, Base is in a separate models.py file.


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session