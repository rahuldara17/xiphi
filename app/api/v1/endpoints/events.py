# app/api/v1/endpoints/events.py

from fastapi import APIRouter, Depends, HTTPException, status,UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session 
import csv
import io
from app.db.neo4j import create_user_conference_registration_neo4j
from app.models.person import AttendeeClaimRegistrationRequest, AttendeeClaimRegistrationResponse 
# Import Postgres models related to events/conferences/sessions
# YOU MUST ADAPT THESE IMPORTS BASED ON YOUR ACTUAL POSTGRES MODEL FILE
from postgres.models import Event as PgEvent # Your 'events' table model
from postgres.models import Conference as PgConference # Your 'conferences' table model
from postgres.models import User as PgUser # To link organizers/presenters/users
from app.models.person import BulkRegistrationUploadResponse
# Import Pydantic schemas for Conference and Event creation
from app.models.person import ConferenceCreate, ConferenceRead, EventCreate, EventRead, EventType # Import EventType Enum
from postgres.models import UserRegistration
from postgres.models import Location
from sqlalchemy.orm import selectinload
# Import Neo4j CRUD functions for Conference/Event
from app.db.neo4j import (
    create_conference_node_neo4j, create_event_node_neo4j,
    create_presenter_event_link_neo4j, create_exhibitor_event_link_neo4j,
    create_user_conference_registration_neo4j
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
    Location is now canonicalized via find_or_create_location.
    """
    new_conference_uuid = uuid.uuid4()

    organizer_pg_id = None
    if conference_payload.organizer_id:
        organizer_result = await db.execute(select(PgUser).filter(PgUser.user_id == conference_payload.organizer_id))
        organizer_pg = organizer_result.scalars().first()
        if not organizer_pg:
            raise HTTPException(status_code=404, detail=f"Organizer User with ID {conference_payload.organizer_id} not found.")
        organizer_pg_id = organizer_pg.user_id

    # Process location_name to get canonical location_id
    location_pg_id = None
    neo4j_location_name = None
    if conference_payload.location_name:
        location_info = await find_or_create_location(db, conference_payload.location_name)
        location_pg_id = UUID(location_info["location_id"])
        neo4j_location_name = location_info["name"]

    # Create record in Postgres 'conferences' table
    pg_conference = PgConference(
        conference_id=new_conference_uuid,
        name=conference_payload.name,
        description=conference_payload.description,
        start_date=conference_payload.start_date,
        end_date=conference_payload.end_date,
        location_id=location_pg_id, # Store the canonical location ID
        venue_details=conference_payload.venue_details,
        organizer_id=organizer_pg_id,
        logo_url=str(conference_payload.logo_url) if conference_payload.logo_url else None,
        website_url=str(conference_payload.website_url) if conference_payload.website_url else None
    )
    db.add(pg_conference)
    await db.commit() # Commit the new conference to the DB

    # --- FIX FOR MISSINGGREENLET ERROR ---
    # After commit, the object is detached or relationships might not be loaded.
    # Re-query the object and eagerly load the 'location_rel' relationship.
    stmt_loaded_conference = select(PgConference).options(selectinload(PgConference.location_rel)).filter(
        PgConference.conference_id == pg_conference.conference_id # Filter by the ID of the conference we just created
    )
    result_loaded_conference = await db.execute(stmt_loaded_conference)
    pg_conference_loaded = result_loaded_conference.scalar_one_or_none()
    
    if not pg_conference_loaded: # This should ideally not happen after a successful commit
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve newly created conference with location data for response.")

    # Synchronize to Neo4j (use the eagerly loaded object for its properties)
    await create_conference_node_neo4j(
        conference_id=str(pg_conference_loaded.conference_id), # Use loaded object
        name=pg_conference_loaded.name,
        description=pg_conference_loaded.description,
        start_date=pg_conference_loaded.start_date,
        end_date=pg_conference_loaded.end_date,
        location=pg_conference_loaded.location_name, # Accesses the @property which now has loaded relationship
        organizer_id=str(organizer_pg_id) if organizer_pg_id else None,
        logo_url=pg_conference_loaded.logo_url,
        website_url=pg_conference_loaded.website_url
    )
    # Return using the eagerly loaded object
    return ConferenceRead.from_orm(pg_conference_loaded)

# ... (rest of the file remains unchanged) ...
# --- Endpoint to Create a New Event (Component) for a Conference ---
@router.post("/conferences/{conference_id_from_url}/events/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event_api(
   
    event_payload: EventCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new Event record in PostgreSQL for a given Conference.
    Event location is stored as a direct string (event_details).
    It is NOT pushed to Neo4j for this event node.
    """
    # 1. Validate conference_id consistency (URL vs. Payload)
   
   
    # 3. Generate new UUID for this event record (event_id in Postgres)
    new_event_uuid = uuid.uuid4()

    # (No location processing logic for events here, as event_details is a direct string)

    # 4. Create record in Postgres 'events' table
    pg_event = PgEvent(
        event_id=new_event_uuid,
        conference_id=event_payload.conference_id,
        title=event_payload.title,
        description=event_payload.description,
        event_type=event_payload.event_type.value,
        start_time=event_payload.start_time,
        end_time=event_payload.end_time,
        
        # --- NEW: Save event_details directly as a string ---
        venue_details=event_payload.venue_details, # Pass the string from payload
        # location_id is no longer part of PgEvent here

        # organizer_id is not taken from payload in EventCreate now, set as per your model
    )
    db.add(pg_event)
    await db.commit()
    await db.refresh(pg_event)

    neo4j_event_type = None
    if pg_event.event_type:
        if isinstance(pg_event.event_type, EventType):
            neo4j_event_type = pg_event.event_type.value
        else:
            neo4j_event_type = str(pg_event.event_type)

    # 5. Synchronize to Neo4j
    await create_event_node_neo4j(
        event_id=str(pg_event.event_id),
        conference_id=str(pg_event.conference_id),
        title=pg_event.title,
        event_type=neo4j_event_type,
        start_time=pg_event.start_time,
        end_time=pg_event.end_time,
        # --- REMOVED: location=pg_event.venue_detail ---
        # As per your instruction not to store event venue_detail in Neo4j
    )
    
    # ... (Link presenters/exhibitors to event) ...

    return EventRead.from_orm(pg_event)



@router.post(
    "/api/v1/organizers/{organizer_id}/conferences/{conference_id}/attendees/upload-csv",
    response_model=BulkRegistrationUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="[DEVELOPMENT ONLY] Upload CSV of Attendee Registration IDs for a Conference by Organizer ID",
    description="""
    **WARNING: This endpoint is for DEVELOPMENT/TESTING 
    """
)
async def upload_attendees_csv(
    organizer_id: UUID,
    conference_id: UUID,
    file: UploadFile = File(..., description="CSV file containing registration IDs."),
    db: AsyncSession = Depends(get_db) # <--- Use AsyncSession here
):
    # --- TEMPORARY AUTHORIZATION CHECK ---
    # Use await db.execute(select(...)) and .scalar_one_or_none()
    stmt = select(PgConference).filter(PgConference.conference_id == conference_id)
    result = await db.execute(stmt)
    conference = result.scalar_one_or_none()

    if not conference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conference not found."
        )
    if conference.organizer_id != organizer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage this conference with the provided organizer ID."
        )

    # --- File Type Validation (unchanged) ---
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only CSV files are allowed."
        )

    # --- Read and Parse the CSV Content (unchanged except for async file read) ---
    content = await file.read() # Already awaited
    
    try:
        csv_string = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode CSV file. Ensure it's UTF-8 encoded."
        )

    csv_file = io.StringIO(csv_string)
    reader = csv.reader(csv_file)

    header = None
    raw_reg_ids_from_file = []
    
    try:
        first_row = next(reader, None)
        if first_row:
            if any(field.strip() and not field.strip().isdigit() for field in first_row):
                header = [h.strip().lower() for h in first_row]
            else:
                raw_reg_ids_from_file.append(first_row[0].strip())
        
        reg_id_column_index = 0
        if header:
            if 'reg_id' in header:
                reg_id_column_index = header.index('reg_id')
            elif 'registration_id' in header:
                reg_id_column_index = header.index('registration_id')

        for i, row in enumerate(reader):
            if not row: continue
            try:
                reg_id = row[reg_id_column_index].strip()
                if reg_id:
                    raw_reg_ids_from_file.append(reg_id)
            except IndexError:
                print(f"Skipping malformed row {i+2} in CSV: {row}")
        
    except StopIteration:
        if not raw_reg_ids_from_file:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file is empty or contains no valid data rows.")


    if not raw_reg_ids_from_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid registration IDs found in the CSV file after parsing."
        )
    
    unique_reg_ids_in_file_batch = list(set(raw_reg_ids_from_file))
    total_ids_in_file_count = len(raw_reg_ids_from_file)

    # --- 3. Process and Store Registration IDs (Database Operations) ---
    successfully_registered_count = 0
    skipped_duplicates_count = 0
    failed_entries_list = []

    new_user_registrations = []

    # Use begin() and commit() / rollback() on the AsyncSession directly
    # For nested transactions, you'd manage it differently, but for a simple endpoint, this is fine.
    try:
        for reg_id_to_process in unique_reg_ids_in_file_batch:
            # Check for GLOBAL uniqueness of reg_id in the database using PgUserRegistration
            stmt = select(UserRegistration).filter(
                UserRegistration.reg_id == reg_id_to_process
            )
            result = await db.execute(stmt)
            existing_registration = result.scalar_one_or_none()

            if existing_registration:
                skipped_duplicates_count += 1
                continue 

            new_registration = UserRegistration(
                reg_id=reg_id_to_process,
                conference_id=conference_id,
                user_id=None, # Initially NULL as per schema
                registered_by_organizer_at=datetime.now(timezone.utc),
                status="pre_registered",
                valid_from=None, # Set if needed. Use datetime.now(timezone.utc) if server_default not used
                valid_to=None    # Set if needed. Use `text("'infinity'").compile()` or datetime accordingly
            )
            new_user_registrations.append(new_registration)
            successfully_registered_count += 1

        db.add_all(new_user_registrations) # Add all new ORM objects to the session
        await db.commit() # <--- AWAIT COMMIT

    except Exception as e:
        await db.rollback() # <--- AWAIT ROLLBACK
        print(f"FATAL: Database error during bulk insert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected database error occurred during bulk registration. Please try again. Error: {e}"
        )
    
    # --- 4. Return Response ---
    return BulkRegistrationUploadResponse(
        conference_id=conference_id,
        file_name=file.filename,
        total_ids_in_file=total_ids_in_file_count,
        successfully_registered=successfully_registered_count,
        skipped_duplicates=skipped_duplicates_count,
        failed_entries=failed_entries_list,
        message=f"CSV upload processed. Successfully pre-registered {successfully_registered_count} unique attendees for conference {conference_id} by organizer {organizer_id}."
    )


@router.post(
    "/api/v1/users/me/claim-registration",
    response_model=AttendeeClaimRegistrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate User and Claim Registration ID",
    description="""Allows a user to log in with their email and password, and simultaneously claim their unique registration ID (reg_id) for a conference.
    If the reg_id is already claimed by this user, it will act as a successful login/confirmation.
    **(Currently uses plain-text password comparison for development)**"""
)
async def claim_registration(
    request_payload: AttendeeClaimRegistrationRequest,
    db: AsyncSession = Depends(get_db)
):
    # --- 1. User Authentication ---
    stmt = select(PgUser).filter(PgUser.email == request_payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    # --- TEMPORARY: Direct password comparison (HIGHLY INSECURE FOR PRODUCTION) ---
    if request_payload.password != user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    # --- END TEMPORARY ADJUSTMENT ---

    # Authentication successful, 'user' object now holds the authenticated user's data.

    # --- 2. Find Registration Record (regardless of claim status) ---
    # We first find the registration record, whether claimed or not.
    stmt_reg = select(UserRegistration).filter(
        UserRegistration.reg_id == request_payload.reg_id
    )
    result_reg = await db.execute(stmt_reg)
    registration_record = result_reg.scalar_one_or_none()

    if not registration_record:
        # If the reg_id doesn't exist at all in user_registrations
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration ID is invalid or does not exist."
        )

    # --- 3. Determine Action: Claim New or Confirm Existing ---
    try:
        if registration_record.user_id == user.user_id and registration_record.status == 'claimed':
            # Scenario A: Reg_id is ALREADY claimed by THIS authenticated user
            # Just confirm successful login and registration status, no DB update needed.
            action_message = "Logged in successfully. Registration already linked to your account."
            status_code_to_return = status.HTTP_200_OK # Success, but no new claim
            
            # Re-fetch conference name for response
            stmt_conf = select(PgConference).filter(PgConference.conference_id == registration_record.conference_id)
            result_conf = await db.execute(stmt_conf)
            conference = result_conf.scalar_one_or_none()
            conference_name_for_response = conference.name if conference else "Unknown Conference"

            return AttendeeClaimRegistrationResponse(
                message=action_message,
                user_id=user.user_id,
                claimed_reg_id=request_payload.reg_id,
                claimed_conference_id=registration_record.conference_id,
                conference_name=conference_name_for_response
            )

        elif registration_record.user_id is not None:
            # Scenario B: Reg_id is claimed by ANOTHER user
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, # Conflict indicates it's taken
                detail="This registration ID has already been claimed by another account."
            )

        elif registration_record.status != 'pre_registered':
            # Scenario C: Reg_id exists but is in a state not available for claiming (e.g., 'cancelled')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This registration ID is not currently available for claiming."
            )
        
        else: # (registration_record.user_id is None and registration_record.status == 'pre_registered')
            # Scenario D: Reg_id is UNCLAIMED and 'pre_registered' - Proceed with claiming
            
            # Check if this user already has a reg_id in their users table and if you need to warn/prevent overwriting.
            # As per last discussion, we will overwrite `users.reg_id`.
            
            # Update the PgUserRegistration table: link the authenticated user to this reg_id
            registration_record.user_id = user.user_id # Link to the authenticated user
            registration_record.claimed_by_user_at = datetime.now(timezone.utc)
            registration_record.status = 'claimed'
            db.add(registration_record) # Stage the update

            # Update the PgUser table: set the user's primary reg_id field
            user.reg_id = request_payload.reg_id # Update the 'reg_id' column in the 'users' table
            db.add(user) # Stage the update

            await db.commit() # Commit all staged changes to the database
            await db.refresh(registration_record) # Refresh to get latest DB state
            await db.refresh(user) # Refresh user object

            # --- 4. Update Neo4j (Optional) ---
            stmt_conf = select(PgConference).filter(PgConference.conference_id == registration_record.conference_id)
            result_conf = await db.execute(stmt_conf)
            conference = result_conf.scalar_one_or_none()
            
            conference_name_for_response = "Unknown Conference" 
            if conference:
                await create_user_conference_registration_neo4j(
                    user_id=str(user.user_id),
                    conference_id=str(conference.conference_id),
                    reg_id=request_payload.reg_id 
                )
                conference_name_for_response = conference.name

            # --- 5. Return Success Response for New Claim ---
            return AttendeeClaimRegistrationResponse(
                message="Registration successfully claimed and account linked.",
                user_id=user.user_id,
                claimed_reg_id=request_payload.reg_id,
                claimed_conference_id=registration_record.conference_id,
                conference_name=conference_name_for_response
            )

    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions directly
    except Exception as e:
        await db.rollback() # Rollback all database changes if any other error occurs
        print(f"Error claiming registration for user {user.user_id} with reg_id {request_payload.reg_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration claim. Please try again."
        )