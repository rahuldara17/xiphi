# app/api/v1/api.py

from fastapi import APIRouter
from app.api.v1.endpoints import people
from app.api.v1.endpoints import events

api_router = APIRouter()

#print(f"DEBUG: Initial api_router: {api_router.routes}") # Debug statement 1

api_router.include_router(
    people.router,
    prefix="/people",
    tags=["people"]
)
#print(f"DEBUG: api_router after people: {api_router.routes}") # Debug statement 2

api_router.include_router(
    events.router,
    prefix="/events",
    tags=["Events & Conferences"]
)
#print(f"DEBUG: api_router after events: {api_router.routes}") # Debug statement 3

# Uncomment and include your other routers if they exist
# from app.api.v1.endpoints import transcripts # Example
# api_router.include_router(
#     transcripts.router,
#     prefix="/transcripts",
#     tags=["transcripts"]
# )
#print("DEBUG: app/api/v1/api.py fully loaded.") # Debug statement 4