from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Base  # your models.py where Base is declared

# Example: PostgreSQL connection URL with pgvector support
DATABASE_URL = "postgresql://postgres:sam12345@localhost:5432/new4"

# Create engine with connection pooling, etc.
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set True to debug SQL queries
    pool_size=10,
    max_overflow=20,
    future=True  # Use SQLAlchemy 2.0 style
)

# Bind metadata to engine (so Base.metadata knows which engine to use)
Base.metadata.bind = engine

# Create session factory
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))

def get_db():
    """Dependency function to get a session (typical for FastAPI or others)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Optional: create tables if they don't exist (be cautious in production)
def create_tables():
    Base.metadata.create_all(bind=engine)