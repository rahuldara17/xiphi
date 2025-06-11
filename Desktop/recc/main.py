from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import HTMLResponse # Only needed if serving HTML directly
# from fastapi.staticfiles import StaticFiles # Only needed if serving HTML directly

from neo4j_driver import get_neo4j_driver, close_neo4j_driver
from recommendations import service as rec_service

# --- FIX: Define 'app' object FIRST ---
app = FastAPI(
    title="NΞXXT Connect Recommendation API",
    description="API for personalized networking recommendations.",
    version="1.0.0"
)

# --- Add CORS Middleware ---
# Define origins that are allowed to make requests to your FastAPI app.
# For local development, '*' is the quickest way to resolve CORS issues from file:// or other local hosts.
# WARNING: Do NOT use allow_origins=["*"] in production unless you fully understand the security implications.
origins = [
    "*" # This wildcard allows any origin to make requests.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # List of allowed origins
    allow_credentials=True,      # Allow cookies to be included in cross-origin requests
    allow_methods=["*"],         # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],         # Allow all headers
)
# --- END CORS ---

# --- FastAPI Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    """Connects to Neo4j and initializes GDS on startup."""
    try:
        get_neo4j_driver() # Initialize the Neo4j driver
        rec_service.initialize_gds() # Initialize GDS client and project graphs
        rec_service.compute_all_similarities() # Compute similarities initially
    except Exception as e:
        print(f"Failed to connect to Neo4j or initialize GDS: {e}")
        # In a production environment, you might log this error more robustly
        # and perhaps have a mechanism to retry or alert.
        # For now, print error and allow app to start, but requests might fail.

@app.on_event("shutdown")
async def shutdown_event():
    """Closes the Neo4j connection on shutdown."""
    close_neo4j_driver()

# --- API Endpoints ---

@app.get("/")
async def read_root():
    return {"message": "Welcome to NΞXXT Connect Recommendation API!"}

@app.get("/recommendations/demographics/{user_id}", response_model=dict)
async def get_demographics_recommendations(user_id: str):
    """
    Fetches people recommendations based primarily on demographic similarity
    (company, location, university).
    """
    try:
        recommendations = rec_service.get_demographics_based_recommendations(user_id, limit=5)
        return {
            "user_id": user_id,
            "category": "People For You (Demographics)",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching demographics recommendations: {e}")

@app.get("/recommendations/interests/{user_id}", response_model=dict)
async def get_interests_recommendations(user_id: str):
    """
    Fetches people recommendations based on shared interests.
    """
    try:
        recommendations = rec_service.get_similar_interests_recommendations(user_id, limit=5)
        return {
            "user_id": user_id,
            "category": "People with Similar Interests",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching interests recommendations: {e}")

@app.get("/recommendations/skills/{user_id}", response_model=dict)
async def get_skills_recommendations(user_id: str):
    """
    Fetches people recommendations based on shared skills.
    """
    try:
        recommendations = rec_service.get_similar_skills_recommendations(user_id, limit=5)
        return {
            "user_id": user_id,
            "category": "People with Similar Skills",
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching skills recommendations: {e}")