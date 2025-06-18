# app/services/process.py
import numpy as np
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sentence_transformers import SentenceTransformer
from postgres.models import Location
# Removed GraphComputationState, increment_profile_update_count, reset_and_update_similarity_state imports
from postgres.models import SkillInterest, Company, JobRole # Ensure these are still here
import uuid
from datetime import datetime, timezone # Use timezone for consistency


model = SentenceTransformer("all-MiniLM-L6-v2")


def generate_embedding(text: str) -> list[float]:
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


async def find_or_create_skill_interest(db: AsyncSession, entity_name: str, entity_type: str) -> Dict[str, Any]:
    """
    Finds the closest existing skill/interest or creates a new one if no sufficient match.
    Uses vector search + full-text search.
    Args:
        db: The async database session.
        entity_name: The raw skill or interest name provided by the user.
        entity_type: 'skill' or 'interest' (could be used for filtering in the future if needed)
    Returns:
        A dictionary with 'skill_interest_id' (UUID string) and 'name' (normalized name).
    """
    embedding = generate_embedding(entity_name)

    # Step 1: Vector search - top N by L2 similarity
    # You might consider increasing LIMIT if you have a very large dataset
    # And potentially filtering by 'type' if your SkillInterest model has one
    vector_query = (
        select(
            SkillInterest.skill_interest_id,
            SkillInterest.name,
            SkillInterest.embedding # Fetch embedding to calculate more precise similarity if needed
        )
        .order_by(SkillInterest.embedding.l2_distance(embedding))
        .limit(5) # Get top 5 semantic matches
    )
    result = await db.execute(vector_query)
    top_entities_from_vector = result.fetchall()

    found_match = None

    if top_entities_from_vector:
        # Step 2: Full-text search over top 5 entities (more precise matching)
        top_entity_ids = [str(row.skill_interest_id) for row in top_entities_from_vector]
        id_placeholders = ','.join(f"'{id}'" for id in top_entity_ids)

        # Using ts_rank to get the best full-text match among the semantically close ones
        fulltext_query = text(f"""
            SELECT skill_interest_id, name FROM skills_interests
            WHERE skill_interest_id IN ({id_placeholders})
            AND to_tsvector('english', name) @@ plainto_tsquery(:entity_name)
            ORDER BY ts_rank(to_tsvector('english', name), plainto_tsquery(:entity_name)) DESC
            LIMIT 1
        """)
        fulltext_result = await db.execute(fulltext_query, {"entity_name": entity_name})
        found_match = fulltext_result.fetchone()

    if found_match:
        print(f"Found existing {entity_type} via hybrid search: {found_match.name}")
        return {
            "skill_interest_id": str(found_match.skill_interest_id),
            "name": found_match.name
        }
    elif top_entities_from_vector:
        # Fallback to top vector match if full-text search yielded no *exact* lexical overlap
        # You might add a similarity threshold here (e.g., if L2 distance > X, create new)
        top_vector_match = top_entities_from_vector[0]
        print(f"Using top vector match for {entity_type}: {top_vector_match.name}")
        return {
            "skill_interest_id": str(top_vector_match.skill_interest_id),
            "name": top_vector_match.name
        }
    else:
        # Step 3: No close match found, create a new skill/interest entry
        print(f"No close match found for {entity_name}. Creating new {entity_type}.")
        new_id = uuid.uuid4()
        new_entity = SkillInterest(
            skill_interest_id=new_id,
            name=entity_name, # Store the exact provided name
            embedding=embedding # Store the embedding of the new entity
        )
        db.add(new_entity)
        await db.flush() # Flush to get the ID without committing yet
        return {
            "skill_interest_id": str(new_id),
            "name": entity_name
        }


# --- New functions for normalizing Companies and Job Roles ---

async def find_or_create_company(db: AsyncSession, company_name: str) -> Dict[str, Any]:
    """
    Finds an existing company by name or creates a new one.
    This could be extended with fuzzy matching if needed.
    """
    result = await db.execute(select(Company).filter(Company.name == company_name))
    existing_company = result.scalars().first()

    if existing_company:
        print(f"Found existing company: {existing_company.name}")
        return {
            "company_id": str(existing_company.company_id),
            "name": existing_company.name
        }
    else:
        print(f"Creating new company: {company_name}")
        new_id = uuid.uuid4()
        new_company = Company(
            company_id=new_id,
            name=company_name
        )
        db.add(new_company)
        await db.flush() # Flush to get the ID
        return {
            "company_id": str(new_id),
            "name": company_name
        }

async def find_or_create_job_role(db: AsyncSession, job_role_title: str) -> Dict[str, Any]:
    """
    Finds an existing job role by title or creates a new one.
    This could be extended with fuzzy matching if needed.
    """
    # Filter by JobRole.name, as that's the column name in the model
    result = await db.execute(select(JobRole).filter(JobRole.name == job_role_title))
    existing_job_role = result.scalars().first()

    if existing_job_role:
        # Access existing_job_role.name, as that's the column name
        print(f"Found existing job role: {existing_job_role.name}") # <-- FIXED THIS LINE
        return {
            "job_role_id": str(existing_job_role.job_role_id),
            "title": existing_job_role.name # Return existing_job_role.name as 'title'
        }
    else:
        print(f"Creating new job role: {job_role_title}")
        new_id = uuid.uuid4()
        new_job_role = JobRole(
            job_role_id=new_id,
            name=job_role_title # Create with 'name', as that's the column name
        )
        db.add(new_job_role)
        await db.flush() # Flush to get the ID
        return {
            "job_role_id": str(new_id),
            "title": job_role_title # Return the provided job_role_title as 'title'
        }
async def find_or_create_location(db: AsyncSession, location_name: str) -> Dict[str, Any]:
    """
    Finds a location by name in Postgres, or creates it if it doesn't exist.
    Returns the location's ID and name.
    """
    result = await db.execute(select(Location).filter(Location.name == location_name))
    location_obj = result.scalars().first()
    if not location_obj:
        new_location_uuid = uuid.uuid4()
        location_obj = Location(location_id=new_location_uuid, name=location_name)
        db.add(location_obj)
        await db.commit()
        await db.refresh(location_obj)
        print(f"Postgres: Created new Location: {location_name} (ID: {new_location_uuid})")
    return {"location_id": location_obj.location_id, "name": location_obj.name}