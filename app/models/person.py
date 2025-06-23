# app/models/person.py

from pydantic import BaseModel, EmailStr, HttpUrl, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum

# --- ENUMS ---
class RegistrationCategory(str, Enum):
    attendee = "attendee"
    speaker = "speaker"
    organizer = "organizer"
    exhibitor = "exhibitor"
    presenter = "presenter"

class EventType(str, Enum):
    conference = "conference"
    presentation = "presentation"
    exhibition = "exhibition"
    workshop = "workshop"
    panel = "panel"
    keynote = "keynote"
    networking_event = "networking_event"
    product_launch = "product_launch"
    other = "other"

# --- SHARED ENTITY SCHEMAS (remain unchanged) ---
class SingleUserSkill(BaseModel):
    skill_name : str
    assigned_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

class SingleUserInterest(BaseModel):
  
    interest_name : str
    assigned_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

class SingleUserJobRole(BaseModel):
   
    job_role_title : str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

class SingleUserCompany(BaseModel):
  
    company_name: str
    assigned_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


# --- USER SCHEMAS ---
class UserCreate(BaseModel):
    email: EmailStr
    password_hash: str
    first_name: str
    last_name: str
    
    # FIX: reg_id is NOT included in UserCreate payload (it's added later)
    # reg_id: str # REMOVED from UserCreate

    avatar_url: Optional[HttpUrl] = None
    biography: Optional[str] = None
    phone: Optional[str] = None
    registration_category: RegistrationCategory = RegistrationCategory.attendee
    


class UserRead(BaseModel):
    user_id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    reg_id: Optional[str] = None # FIX: Make reg_id Optional in UserRead (as it might be null)
    registration_category: RegistrationCategory
    
    model_config = ConfigDict(from_attributes=True)


class UserUpdateSchema(BaseModel):
    user_id: UUID
    user_skills: Optional[List[SingleUserSkill]] = None
    user_job_roles: Optional[List[SingleUserJobRole]] = None
    user_interests: Optional[List[SingleUserInterest]] = None
    user_company: Optional[SingleUserCompany] = None
    location: Optional[str] = None
    
    
   

    model_config = ConfigDict(from_attributes=True)




# --- CONFERENCE & EVENT (COMPONENT) SCHEMAS (remain unchanged) ---

class ConferenceCreate(BaseModel):
    
    name: str
    description: Optional[str] = None
    start_date: datetime
    end_date: datetime
    location_name: Optional[str] = None
    organizer_id: Optional[UUID] = None
    logo_url: Optional[HttpUrl] = None
    website_url: Optional[HttpUrl] = None
    venue_details:Optional[str]=None
class ConferenceRead(ConferenceCreate):
    conference_id: UUID
    class Config:
        from_attributes = True

class EventCreate(BaseModel):
   
    conference_id: UUID 
    title: str
    description: Optional[str] = None
    event_type: EventType
    start_time: datetime
    end_time: datetime
    venue_details: Optional[str] = None
    topics: Optional[List[str]] = Field(None, description="List of topic names covered by the event.")
    #target_audience: Optional[List[str]] = Field(None, description="Tags describing the intended audience (e.g., 'Beginners', 'Developers').")
    industry_tags: Optional[List[str]] = Field(None, description="Relevant industry tags (e.g., 'FinTech', 'HealthTech').")

    presenter_user_ids: Optional[List[UUID]] = None
    exhibitor_user_ids: Optional[List[UUID]] = None
class EventRead(EventCreate):
    event_id: UUID
    class Config:
        from_attributes = True
class UserRegistrationBase(BaseModel):
    """Base model for common user registration fields.
    reg_id is the primary key in the DB.
    """
    reg_id: str = Field(..., min_length=1, max_length=100, description="Unique registration code for the attendee. This is the primary key.")
    conference_id: UUID
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    organizer_supplied_email: Optional[EmailStr] = None
    organizer_supplied_first_name: Optional[str] = None
    organizer_supplied_last_name: Optional[str] = None
    organizer_supplied_job_title: Optional[str] = None
    organizer_supplied_company_name: Optional[str] = None
    organizer_supplied_city: Optional[str] = None
    organizer_supplied_country: Optional[str] = None
    organizer_supplied_role: Optional[RegistrationCategory] = None # Their role from organizer's system

class UserRegistrationRead(UserRegistrationBase):
    """Model for reading user registration data, includes server-generated fields."""
    # registration_row_id: UUID # REMOVED: As per your instruction, this column is not used.
    user_id: Optional[UUID] = None # Matches your DB column name for the claimed attendee_user_id
    registered_by_organizer_at: datetime
    claimed_by_user_at: Optional[datetime] = None
    status: str # e.g., 'pre_registered', 'claimed', 'cancelled'

    model_config = ConfigDict(from_attributes=True)

class UserEventFeedbackCreate(BaseModel):
    user_id: UUID # Or remove and get from authenticated user
    event_id: UUID
    is_interested: bool
    comment: Optional[str] = None

class UserEventFeedbackRead(UserEventFeedbackCreate):
    feedback_id: UUID
    feedback_at: datetime
    model_config = ConfigDict(from_attributes=True)

class UserEventAttendanceCreate(BaseModel):
    user_id: UUID # Or remove and get from authenticated user
    event_id: UUID
    status: str = "attended" # e.g., 'attended', 'checked_in', 'virtual_present'
    #attended_at: Optional[datetime] = None # Will be set by system, but allow override for historical data

class UserEventAttendanceRead(UserEventAttendanceCreate):
    attendance_id: UUID
    attended_at: datetime
    model_config = ConfigDict(from_attributes=True)


class BulkRegistrationUploadResponse(BaseModel):
    conference_id: UUID
    file_name: str
    total_ids_in_file: int
    successfully_registered: int
    skipped_duplicates: int # For reg_ids that already exist
    failed_entries: List[str] = Field(default_factory=list, description="List of reg_ids that failed due to processing errors (e.g., malformed, DB errors).")
    message: str


# Request model for Attendee's combined login and claim registration API
class AttendeeClaimRegistrationRequest(BaseModel):
    email: EmailStr
    password: str
    reg_id: str = Field(..., min_length=1, max_length=100, description="The unique registration code received from the organizer.")


# Response model for successful Attendee Claim operation
class AttendeeClaimRegistrationResponse(BaseModel):
    message: str
    user_id: UUID # The ID of the user who successfully claimed
    claimed_reg_id: str
    claimed_conference_id: UUID # The conference this reg_id was for
    conference_name: str # For user-friendly feedback
    # If this endpoint also returns a JWT for subsequent authenticated calls, add it here:
    # access_token: str
    # token_type: str = "bearer"
