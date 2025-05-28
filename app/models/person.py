from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import uuid

class UserRole(str, Enum):
    ATTENDEE = "attendee"
    PRESENTER = "presenter"
    EXHIBITOR = "exhibitor"
    ORGANIZER = "organizer"

class PersonBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    bio: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
class Education(BaseModel):
    degree: str
    institution: str
    start_year: int
    end_year: int

class PersonCreate(PersonBase):
    skills: List[str] = Field(default_factory=list)
    expertise: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    education: Optional[List[Education]] = Field(default_factory=list)
    linkedin_url: Optional[str] = None

class PersonUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    skills: Optional[List[str]] = None
    expertise: Optional[List[str]] = None
    interests: Optional[List[str]] = None
    education: List[Education] = Field(default_factory=list)


class PersonInDB(PersonBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    skills: List[str] = Field(default_factory=list)
    expertise: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)

    linkedin_url: Optional[str] = None

    class Config:
        from_attributes = True

class UserProfile(BaseModel):
    userID: str = Field(default_factory=lambda: str(uuid.uuid4()))
    fullName: str
    location: Optional[str] = None
    ageGroup: Optional[str] = None
    languagePreferences: List[str] = Field(default_factory=list)
    communicationPreference: Optional[str] = None
    professionalDetails: Dict[str, Any] = Field(default_factory=dict)
    skills: List[Dict[str, str]] = Field(default_factory=list)
    goalsAndIntent: Dict[str, Any] = Field(default_factory=dict)
    engagements: List[Dict[str, Any]] = Field(default_factory=list)
    voiceAgentInteractions: List[Dict[str, Any]] = Field(default_factory=list)
    recommendationFeedback: List[Dict[str, Any]] = Field(default_factory=list)
    networkingConnections: List[Dict[str, Any]] = Field(default_factory=list)
    growthMilestones: Dict[str, List[str]] = Field(default_factory=dict)

    class Config:
        from_attributes = True

# Replace PersonResponse with UserProfile
PersonResponse = UserProfile

class RecommendationResponse(BaseModel):
    """Response model for recommendations"""
    person_id: str
    name: str
    role: UserRole
    shared_skills: List[str]
    shared_expertise: List[str]
    shared_interests: List[str]
    total_score: float 