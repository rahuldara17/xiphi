# app/api/v1/endpoints/events.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

# Import Postgres models related to events/conferences/sessions
# YOU MUST ADAPT THESE IMPORTS BASED ON YOUR ACTUAL POSTGRES MODEL FILE
from postgres.models import Event as PgEvent # Your 'events' table model
from postgres.models import Conference as PgConference # Your 'conferences' table model
from postgres.models import User as PgUser # To link organizers/presenters/users

# Import Pydantic schemas for Conference and Event creation
from app.models.person import ConferenceCreate, ConferenceRead, EventCreate, EventRead, EventType # Import EventType Enum

# Import Neo4j CRUD functions for Conference/Event
from app.db.neo4j import (
    create_conference_node_neo4j, create_event_node_neo4j,
    create_presenter_event_link_neo4j, create_exhibitor_event_link_neo4j
)

# NEW IMPORT: Import the helper for finding/creating locations
from app.services.process import find_or_create_location # Ensure this function is defined in app/services/process.py

# Assuming get_db provides AsyncSession for Postgres
from app.db.database import get_db

router = APIRouter()


@router.post("/conferences/", response_model=ConferenceRead, status_code=status.HTTP_201_CREATED)
async def create_conference_api(conference_payload: ConferenceCreate, db: AsyncSession = Depends(get_db)):
    """
    Creates a new Conference record in PostgreSQL (conferences table) and synchronizes it to Neo4j.
    """
    # 1. Generate new UUID for this conference (primary key in Postgres conferences table)
    new_conference_uuid = uuid.uuid4()

    # 2. Check if organizer_user_id exists in Postgres
    organizer_pg_id = None
    if conference_payload.organizer_user_id:
        organizer_result = await db.execute(select(PgUser).filter(PgUser.user_id == conference_payload.organizer_user_id))
        organizer_pg = organizer_result.scalars().first()
        if not organizer_pg:
            raise HTTPException(status_code=404, detail=f"Organizer User with ID {conference_payload.organizer_user_id} not found.")
        organizer_pg_id = organizer_pg.user_id

    # 3. Create record in Postgres 'conferences' table
    pg_conference = PgConference( # Use PgConference model for the conferences table
        conference_id=new_conference_uuid,
        name=conference_payload.name,
        description=conference_payload.description,
        start_date=conference_payload.start_date,
        end_date=conference_payload.end_date,
        # FIX: Correctly pass 'location' (text) to PgConference, as per your DB schema
        location=conference_payload.location_name,
        organizer_id=organizer_pg_id, # Link to Postgres User ID
        logo_url=str(conference_payload.logo_url) if conference_payload.logo_url else None,
        website_url=str(conference_payload.website_url) if conference_payload.website_url else None
        # valid_from, valid_to, etc. may be set by default in your PgConference model
    )
    db.add(pg_conference)
    await db.commit()
    await db.refresh(pg_conference)

    # 4. Synchronize to Neo4j (create the :Conference node)
    await create_conference_node_neo4j(
        conference_id=str(pg_conference.conference_id), # Use Postgres conference_id as Neo4j conferenceID
        name=pg_conference.name,
        description=pg_conference.description,
        start_date=pg_conference.start_date,
        end_date=pg_conference.end_date,
        location_name=pg_conference.location, # Location name from PgConference (matches what was just saved)
        organizer_user_id=str(organizer_pg_id) if organizer_pg_id else None, # Pass string UUID to Neo4j
        logo_url=pg_conference.logo_url,
        website_url=pg_conference.website_url
    )
    return ConferenceRead.from_orm(pg_conference)

# ... (rest of the file remains unchanged) ...
# --- Endpoint to Create a New Event (Component) for a Conference ---
@router.post("/conferences/{conference_id_from_url}/events/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event_api( # Renamed from create_session_api
    conference_id_from_url: str,
    event_payload: EventCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new Event record (component) in PostgreSQL (events table) for a given Conference,
    and synchronizes it to Neo4j.
    """
    # 1. Verify Parent Conference exists in Postgres
    pg_conference_result = await db.execute(select(PgConference).filter(
        PgConference.conference_id == UUID(conference_id_from_url)
    ))
    pg_conference = pg_conference_result.scalars().first()
    if not pg_conference:
        raise HTTPException(status_code=404, detail=f"Parent Conference with ID {conference_id_from_url} not found in PostgreSQL.")

    # 2. Generate new UUID for this event record (event_id in Postgres)
    new_event_uuid = uuid.uuid4()

    # FIX: Process location_name to get location_id for Event (component)
    location_pg_id = None
    if event_payload.location_name:
        location_info = await find_or_create_location(db, event_payload.location_name)
        location_pg_id = location_info["location_id"]


    # 3. Create record in Postgres 'events' table
    pg_event = PgEvent( # Using PgEvent for component event model
        event_id=new_event_uuid,
        conference_id=pg_conference.conference_id, # Link to parent conference's ID (UUID)
        title=event_payload.title,
        description=event_payload.description,
        event_type=event_payload.event_type.value, # Set specific event type (use .value)
        start_time=event_payload.start_time,
        end_time=event_payload.end_time,
        location_id=location_pg_id, # FIX: Pass location_id here (FK)
        organizer_id=None # Assuming event_payload doesn't have organizer_user_id for event
        # ... map other fields from event_payload ...
    )
    db.add(pg_event)
    await db.commit()
    await db.refresh(pg_event)

    # 4. Synchronize to Neo4j
    await create_event_node_neo4j( # Renamed function
        event_id=str(pg_event.event_id), # Use Postgres event_id as Neo4j eventID
        conference_id=str(pg_conference.conference_id), # Use Postgres conference_id as Neo4j conferenceID
        title=pg_event.title,
        event_type=pg_event.event_type, # Use the string value from Postgres
        start_time=pg_event.start_time,
        end_time=pg_payload.end_time, # Fix typo here: was event_payload.end_time
        location_name=event_payload.location_name # Keep passing name to Neo4j
    )
    
    # 5. Link presenters to event if provided in payload
    if event_payload.presenter_user_ids:
        from app.db.neo4j import create_presenter_event_link_neo4j
        for presenter_id in event_payload.presenter_user_ids:
            await create_presenter_event_link_neo4j(str(presenter_id), str(pg_event.event_id))
    
    # 6. Link exhibitors to event if provided in payload (especially for exhibition type events)
    if event_payload.exhibitor_user_ids:
        if event_payload.event_type != EventType.exhibition:
            print(f"Warning: Exhibitor IDs provided for non-exhibition event type '{event_payload.event_type}'. Linking anyway.")
        from app.db.neo4j import create_exhibitor_event_link_neo4j
        for exhibitor_id in event_payload.exhibitor_user_ids:
            await create_exhibitor_event_link_neo4j(str(exhibitor_id), str(pg_event.event_id))

    return EventRead.from_orm(pg_event)