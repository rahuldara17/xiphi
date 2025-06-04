from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from postgres.models import User, UserSkill, UserInterest, UserJobRole, UserCompany
from app.models.person import UserCreate, UserRead, UserUpdateSchema
from app.db.database import get_db
from app.db.neo4j import create_user_node, create_or_update_user_skill_neo4j
from app.services.process import find_closest_skill_id
from datetime import datetime
import uuid
import asyncio
from sqlalchemy.orm import Session

router = APIRouter()

from neo4j import GraphDatabase
from app.core.config import settings

neo4j_driver = GraphDatabase.driver(
    settings.NEO4J_URI,
    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
)

@router.post("/", response_model=UserRead)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.email == user.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        user_id=uuid.uuid4(),
        email=user.email,
        password_hash=user.password_hash,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        biography=user.biography,
        phone=user.phone,
        registration_category=user.registration_category
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Async fire-and-forget Neo4j node creation
    asyncio.create_task(create_user_node(
        user_id=str(new_user.user_id),
        email=new_user.email,
        first_name=new_user.first_name,
        last_name=new_user.last_name
    ))

    return new_user

@router.post("/update")

async def update_user_data(payload: UserUpdateSchema, db: AsyncSession = Depends(get_db)):
    user_id = payload.user_id

    
        # --- Update Skills ---
    if payload.user_skills:
        for skill in payload.user_skills:
            id = await find_closest_skill_id(db, skill.skill_name)

            await db.merge(UserSkill(
                user_id=user_id,
                skill_interest_id=id["skill_interest_id"],
                assigned_at=skill.assigned_at or datetime.utcnow(),
                valid_from=skill.valid_from or datetime.utcnow(),
                valid_to=skill.valid_to or datetime.max
            ))
            asyncio.create_task(create_or_update_user_skill_neo4j(str(user_id), id["name"]))
            

    # --- Update Interests ---
    if payload.user_interests:
        for interest in payload.user_interests:
            await db.merge(UserInterest(
                user_id=user_id,
                skill_interest_id=interest.skill_interest_id,
                assigned_at=interest.assigned_at or datetime.utcnow(),
                valid_from=interest.valid_from or datetime.utcnow(),
                valid_to=interest.valid_to or datetime.max
            ))

    # --- Update Job Roles ---
    if payload.user_job_roles:
        for role in payload.user_job_roles:
            await db.merge(UserJobRole(
                user_id=user_id,
                job_role_id=role.job_role_id,
                valid_from=role.valid_from or datetime.utcnow(),
                valid_to=role.valid_to or datetime.max
            ))

    # --- Update Company ---
    if payload.user_company:
        company = payload.user_company
        await db.merge(UserCompany(
            user_id=user_id,
            company_id=company.company_id,
            joined_at=company.joined_at or datetime.utcnow(),
            valid_from=company.valid_from or datetime.utcnow(),
            valid_to=company.valid_to or datetime.max
        ))

    await db.commit()
    return {"msg": "User update successful"}
