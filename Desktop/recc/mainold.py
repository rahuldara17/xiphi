from fastapi import FastAPI, HTTPException, status
from neo4j_driver import get_neo4j_driver, close_neo4j_driver
from recommendations import service as rec_service

app = FastAPI(
    title="NΞXXT Connect Recommendation API",
    description="API for personalized networking recommendations.",
    version="1.0.0"
)

# --- FastAPI Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    """Connects to Neo4j and initializes GDS on startup."""
    try:
        # NOTE: Graph data must be pre-loaded by you using Cypher scripts.
        # The initialize_graph_data() call is removed from neo4j_driver.py.
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

@app.get("/recommendations/{user_id}", response_model=dict)
async def get_all_recommendations(user_id: str):
    """
    Fetches recommendations for a given user across all categories.
    Applies exclusion logic to ensure unique users across categories.
    """
    recommended_user_ids = set() # To store IDs of users already recommended in higher-priority categories

    # Define a helper to fetch and filter
    def fetch_and_filter(fetch_func, current_user_id, limit, existing_ids_set):
        raw_recs = fetch_func(current_user_id, limit * 2) # Fetch more than needed to allow for filtering
        filtered_recs = []
        for rec in raw_recs:
            # Ensure UserID is always a string for consistent set operations
            rec_id = str(rec.get('UserID'))
            if rec_id and rec_id not in existing_ids_set:
                filtered_recs.append(rec)
                existing_ids_set.add(rec_id)
            if len(filtered_recs) >= limit:
                break
        return filtered_recs

    # --- Category 1: People For You (Demographics Based) - Highest Priority ---
    people_for_you = fetch_and_filter(rec_service.get_demographics_based_recommendations, user_id, 5, recommended_user_ids)

    # --- Category 2: People with Similar Interests ---
    similar_interests = fetch_and_filter(rec_service.get_similar_interests_recommendations, user_id, 5, recommended_user_ids)

    # --- Category 3: People with Similar Skills ---
    similar_skills = fetch_and_filter(rec_service.get_similar_skills_recommendations, user_id, 5, recommended_user_ids)

    # You can add other recommendation categories here following the same pattern.

    return {
        "user_id": user_id,
        "recommendations": {
            "People For You (Demographics)": people_for_you,
            "People with Similar Interests": similar_interests,
            "People with Similar Skills": similar_skills,
        }
    }