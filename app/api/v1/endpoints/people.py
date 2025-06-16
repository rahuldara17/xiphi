from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from postgres.models import User, UserSkill, UserInterest, UserJobRole, UserCompany # Ensure UserCompany has 'joined_at'
from app.models.person import UserCreate, UserRead, UserUpdateSchema, RegistrationCategory # Make sure RegistrationCategory is imported
from app.db.database import get_db
from datetime import datetime, timezone # Use timezone for consistent UTC now
import uuid

# No direct import of increment_profile_update_count_in_memory here at the top
# It will be imported inside the functions to prevent circular dependencies.

# Import ALL your ASYNC Neo4j CRUD functions
from app.db.neo4j import (
    create_user_node, create_or_update_user_skill_neo4j,
    create_or_update_user_interest_neo4j, create_or_update_user_job_role_neo4j,
    create_or_update_user_company_neo4j, update_user_location_neo4j, get_neo4j_driver
)

# Import the entity normalization functions from process.py
from app.services.process import (
    find_or_create_skill_interest,
    find_or_create_company,
    find_or_create_job_role
)

from typing import Dict, Any, List
from services.services.person_service import PeopleService


router = APIRouter()

async def get_people_service_dependency(db: AsyncSession = Depends(get_db)):
    neo4j_driver_instance = await get_neo4j_driver()
    return PeopleService(db=db, neo4j_driver_async=neo4j_driver_instance)


# --- User CRUD Endpoints ---

@router.post("/", response_model=UserRead)
async def create_user(user_create_payload: UserCreate, db: AsyncSession = Depends(get_db)): # Renamed parameter for clarity
    # Import main module inside the function to avoid circular dependency
    # This is only needed if you want to increment the counter even for basic user creation.
    # If not, you can remove this import from here.
    import main as main_app_module 

    # 1. Check for existing user
    result = await db.execute(select(User).filter(User.email == user_create_payload.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Create new User in Postgres
    new_user_uuid = uuid.uuid4()
    new_user = User(
        user_id=new_user_uuid,
        email=user_create_payload.email,
        password_hash=user_create_payload.password_hash,
        first_name=user_create_payload.first_name,
        last_name=user_create_payload.last_name,
        avatar_url=user_create_payload.avatar_url,
        biography=user_create_payload.biography,
        phone=user_create_payload.phone,
        # Ensure RegistrationCategory enum is handled correctly (use .value)
        registration_category=user_create_payload.registration_category.value
    )

    db.add(new_user)
    # Commit the new user now so its ID is available for relationships
    await db.commit()
    await db.refresh(new_user)

    # 3. Create User node in Neo4j
    await create_user_node(
        user_id=str(new_user.user_id),
        fullName=f"{new_user.first_name} {new_user.last_name}",
        email=new_user.email,
        first_name=new_user.first_name,
        last_name=new_user.last_name
    )

    # --- REVERTED: Removed all logic for user_skills, user_interests, etc. during creation ---
    # These fields are NOT part of the UserCreate schema.
    # User will need to update skills, interests, etc. via the /update endpoint.

    # Only increment the counter for the basic user creation if it counts as a profile update
    # Otherwise, remove this line too.
    await main_app_module.increment_profile_update_count_in_memory()
    
    # No further commits needed here as basic user is already committed
    return new_user


@router.post("/update")
async def update_user_data(payload: UserUpdateSchema, db: AsyncSession = Depends(get_db)):
    user_id = str(payload.user_id)
    data_was_updated = False # Flag to track if any relevant data was updated

    # Import main module inside the function to avoid circular dependency
    import main as main_app_module 

    now_utc = datetime.now(timezone.utc)
    infinity_date = datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)

    # --- Update Skills ---
    if payload.user_skills:
        for skill_payload in payload.user_skills:
            skill_info = await find_or_create_skill_interest(db, skill_payload.skill_name, entity_type='skill')
            if skill_info:
                await db.merge(UserSkill( # Update Postgres
                    user_id=user_id,
                    skill_interest_id=skill_info["skill_interest_id"],
                    assigned_at=skill_payload.assigned_at or now_utc,
                    valid_from=skill_payload.valid_from or now_utc,
                    valid_to=skill_payload.valid_to or infinity_date
                ))
                await create_or_update_user_skill_neo4j(user_id, skill_info["name"])
                data_was_updated = True

    # --- Update Interests ---
    if payload.user_interests:
        for interest_payload in payload.user_interests:
            interest_info = await find_or_create_skill_interest(db, interest_payload.interest_name, entity_type='interest')
            if interest_info:
                await db.merge(UserInterest( # Update Postgres
                    user_id=user_id,
                    skill_interest_id=interest_info["skill_interest_id"],
                    assigned_at=interest_payload.assigned_at or now_utc,
                    valid_from=interest_payload.valid_from or now_utc,
                    valid_to=interest_payload.valid_to or infinity_date
                ))
                await create_or_update_user_interest_neo4j(user_id, interest_info["name"])
                data_was_updated = True

    # --- Update Job Roles ---
    if payload.user_job_roles:
        for role_payload in payload.user_job_roles:
            job_role_info = await find_or_create_job_role(db, role_payload.job_role_title)
            if job_role_info:
                await db.merge(UserJobRole( # Update Postgres
                    user_id=user_id,
                    job_role_id=job_role_info["job_role_id"],
                    assigned_at=role_payload.valid_from or now_utc,
                    valid_from=role_payload.valid_from or now_utc,
                    valid_to=role_payload.valid_to or infinity_date
                ))
                await create_or_update_user_job_role_neo4j(user_id, job_role_info["title"])
                data_was_updated = True

    # --- Update Company ---
    if payload.user_company:
        company_payload = payload.user_company
        company_info = await find_or_create_company(db, company_payload.company_name)
        if company_info:
            await db.merge(UserCompany( # Update Postgres
                user_id=user_id,
                company_id=company_info["company_id"],
                assigned_at=company_payload.assigned_at or now_utc,
                valid_from=company_payload.valid_from or now_utc,
                valid_to=company_payload.valid_to or infinity_date,
            ))
            await create_or_update_user_company_neo4j(user_id, company_info["name"])
            data_was_updated = True

    # --- Update Location ---
    if hasattr(payload, 'current_location_name') and payload.current_location_name:
        await update_user_location_neo4j(user_id, payload.current_location_name)
        data_was_updated = True

    await db.commit() # Commit all Postgres changes for the user update

    if data_was_updated:
        await main_app_module.increment_profile_update_count_in_memory() # Increment in-memory count only if relevant data changed

    return {"msg": "User update successful"}

@router.get("/recommendations/demographics/{user_id}", response_model=Dict[str, Any])
async def get_demographics_recommendations_api(
    user_id: str,
    people_service: PeopleService = Depends(get_people_service_dependency)
):
    """
    Fetches people recommendations based primarily on demographic similarity
    (company, location, university).
    """
    try:
        recommendations = await people_service.get_demographics_based_recommendations(user_id, limit=5)
        return {
            "user_id": user_id,
            "category": "People For You (Demographics)",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching demographics recommendations: {e}")

@router.get("/recommendations/interests/{user_id}", response_model=Dict[str, Any])
async def get_interests_recommendations_api(
    user_id: str,
    people_service: PeopleService = Depends(get_people_service_dependency)
):
    """
    Fetches people recommendations based on shared interests.
    """
    try:
        recommendations = await people_service.get_similar_interests_recommendations(user_id, limit=5)
        return {
            "user_id": user_id,
            "category": "People with Similar Interests",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching interests recommendations: {e}")

@router.get("/recommendations/skills/{user_id}", response_model=Dict[str, Any])
async def get_skills_recommendations_api(
    user_id: str,
    people_service: PeopleService = Depends(get_people_service_dependency)
):
    """
    Fetches people recommendations based on shared skills.
    """
    try:
        recommendations = await people_service.get_similar_skills_recommendations(user_id, limit=5)
        return {
            "user_id": user_id,
            "category": "People with Similar Skills",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching skills recommendations: {e}")
    
#ajfadlfad

@router.get("/recommendations/unified/{user_id}", response_model=Dict[str, Any])
async def get_unified_recommendations_api(
    user_id: str,
    limit: int = 100, # Allow a higher limit for the unified list
    people_service: PeopleService = Depends(get_people_service_dependency)
):
    """
    Fetches unified recommendations by combining demographic, interest, and skill similarities
    with weighted and conditional logic, and ensures commonalities are fully populated.
    """
    try:
        # Step 1: Fetch recommendations from all specialized categories
        # Fetch more than the final limit, as some might be filtered/ranked lower
        fetch_limit_per_category = limit * 3 

        demographics_recs = await people_service.get_demographics_based_recommendations(user_id, limit=fetch_limit_per_category)
        interests_recs = await people_service.get_similar_interests_recommendations(user_id, limit=fetch_limit_per_category)
        skills_recs = await people_service.get_similar_skills_recommendations(user_id, limit=fetch_limit_per_category)

        # Step 2: Combine and Deduplicate (and store individual scores)
        combined_users: Dict[str, Dict[str, Any]] = {} # Key: UserID, Value: user_data dict

        def add_rec_data(rec_list, category_key):
            for rec in rec_list:
                uid = rec['UserID']
                if uid not in combined_users:
                    # Initialize with base data and default scores/empty commonalities
                    combined_users[uid] = {
                        'UserID': uid,
                        'RecommendedUser': rec['RecommendedUser'],
                        'Role': rec.get('Role'),
                        'YearsExperience': rec.get('YearsExperience'),
                        'Scores': { 'Demographics': 0.0, 'Interests': 0.0, 'Skills': 0.0 },
                        'CommonalityRaw': {} # Store raw commonality lists to deduplicate later
                    }
                # Update specific score
                combined_users[uid]['Scores'][category_key] = rec['SimilarityScore']
                
                # Store raw commonalities from this specific query for later deduplication
                for key in ['SharedCompanies', 'SharedLocations', 'SharedUniversities', 'CommonInterests', 'CommonSkills']:
                    if key in rec and rec[key]: # Only add if key exists and list is not empty
                        combined_users[uid]['CommonalityRaw'].setdefault(key, []).extend(rec[key])

        add_rec_data(demographics_recs, 'Demographics')
        add_rec_data(interests_recs, 'Interests')
        add_rec_data(skills_recs, 'Skills')

        # Step 3: Calculate Final Score and Process Commonalities
        final_recommendations_list = []
        for uid, user_data in combined_users.items():
            demo_score = user_data['Scores']['Demographics']
            interest_score = user_data['Scores']['Interests']
            skill_score = user_data['Scores']['Skills']

            final_weighted_score = 0.0
            
            
            final_weighted_score = (demo_score * 0.20) + \
                                       (interest_score * 0.60) + \
                                       (skill_score * 0.10)
            
            
            user_data['FinalScore'] = final_weighted_score

            # Deduplicate and finalize commonalities for display
            final_common_data = {}
            for key, raw_list in user_data['CommonalityRaw'].items():
                final_common_data[key] = list(set(raw_list)) # Use set to deduplicate

            user_data['Commonalities'] = final_common_data # Replace raw with final deduplicated
            del user_data['CommonalityRaw'] # Remove temporary raw data

            # Add to the list to be sorted
            final_recommendations_list.append(user_data)

        # Step 4: Rank and Return Top 'limit' Recommendations
        final_recommendations_list.sort(key=lambda x: x['FinalScore'], reverse=True)

        return {
            "user_id": user_id,
            "category": "Unified Recommendations",
            "recommendations": final_recommendations_list[:limit]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching unified recommendations: {e}")