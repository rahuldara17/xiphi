from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.models.person import PersonCreate, PersonUpdate, UserProfile, RecommendationResponse
from app.db.neo4j import neo4j
import uuid


router = APIRouter()

@router.post("/", response_model=UserProfile)
async def create_person(person: PersonCreate):
    """Create a new person in the knowledge graph"""
    try:
        # Convert PersonCreate to UserProfile
        user_profile = UserProfile(
            userID=str(uuid.uuid4()),
            fullName=person.name,
            location=person.location,
            ageGroup=None,  # Default value
            languagePreferences=[],  # Default value
            communicationPreference=None,  # Default value
            professionalDetails={
                "currentRole": person.job_title,
                "company": person.company,
                "yearsOfExperience": None,  # Default value
                "industry": None,  # Default value
                "functionalArea": None,  # Default value
                "careerStage": None,  # Default value
                "education": person.education,
                "certifications": [],  # Default value
                "role": person.role  # Add role to professionalDetails
            },
            skills=[{
                "skillName": skill,
                "category": "General",
                "proficiency": "Intermediate"
            } for skill in person.skills],
            goalsAndIntent={
                "careerGoals": person.interests,
                "businessObjectives": [],
                "learningInterests": person.interests,
                "desiredIndustries": [],
                "openToMentor": False,
                "seekingMentorship": False
            },
            engagements=[],  # Default value
            voiceAgentInteractions=[],  # Default value
            recommendationFeedback=[],  # Default value
            networkingConnections=[],  # Default value
            growthMilestones={
                "rolesAchieved": [],
                "skillsAcquired": person.skills,
                "certificationsCompleted": []
            }
        )
        
        # Save the full UserProfile to Neo4j
        person_id = await neo4j.create_person({**user_profile.model_dump(), "role": person.role})
        return {**user_profile.model_dump(), "id": person_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{person_id}", response_model=UserProfile)
async def get_person_route(person_id: str):
    person = await neo4j.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person

@router.put("/{person_id}", response_model=UserProfile)
async def update_person(person_id: str, person: PersonUpdate):
    try:
        # Get existing person data
        existing_person = await neo4j.get_person(person_id)
        if not existing_person:
            raise HTTPException(status_code=404, detail="Person not found")

        # Convert PersonUpdate to UserProfile
        user_profile = UserProfile(
            userID=person_id,
            fullName=person.name or existing_person.get("name", ""),
            location=person.location or existing_person.get("location"),
            ageGroup=existing_person.get("ageGroup"),
            languagePreferences=existing_person.get("languagePreferences", []),
            communicationPreference=existing_person.get("communicationPreference"),
            professionalDetails={
                "currentRole": person.job_title or existing_person.get("job_title"),
                "company": person.company or existing_person.get("company"),
                "yearsOfExperience": existing_person.get("yearsOfExperience"),
                "industry": existing_person.get("industry"),
                "functionalArea": existing_person.get("functionalArea"),
                "careerStage": existing_person.get("careerStage"),
                "education": [edu.model_dump() for edu in person.education] if person.education else existing_person.get("education", []),
                "certifications": existing_person.get("certifications", [])
            },
            skills=[{
                "skillName": skill,
                "category": "General",
                "proficiency": "Intermediate"
            } for skill in (person.skills or existing_person.get("skills", []))],
            goalsAndIntent={
                "careerGoals": person.interests or existing_person.get("interests", []),
                "businessObjectives": existing_person.get("businessObjectives", []),
                "learningInterests": person.interests or existing_person.get("interests", []),
                "desiredIndustries": existing_person.get("desiredIndustries", []),
                "openToMentor": existing_person.get("openToMentor", False),
                "seekingMentorship": existing_person.get("seekingMentorship", False)
            },
            engagements=existing_person.get("engagements", []),
            voiceAgentInteractions=existing_person.get("voiceAgentInteractions", []),
            recommendationFeedback=existing_person.get("recommendationFeedback", []),
            networkingConnections=existing_person.get("networkingConnections", []),
            growthMilestones={
                "rolesAchieved": existing_person.get("rolesAchieved", []),
                "skillsAcquired": person.skills or existing_person.get("skills", []),
                "certificationsCompleted": existing_person.get("certificationsCompleted", [])
            }
        )

        # Update the full UserProfile in Neo4j
        updated_id = await neo4j.update_person(person_id, user_profile.model_dump())
        if not updated_id:
            raise HTTPException(status_code=404, detail="Person not found")
        updated_person = await neo4j.get_person(updated_id)
        return updated_person
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{person_id}")
async def delete_person(person_id: str):
    try:
        success = await neo4j.delete_person(person_id)
        if not success:
            raise HTTPException(status_code=404, detail="Person not found or already deleted")
        return {"message": "Person deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{person_id}/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(person_id: str, limit: int = 10):
    """Get recommendations for a person based on shared attributes"""
    try:
        recommendations = await neo4j.get_recommendations(person_id, limit)
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) 