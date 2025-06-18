import asyncio
from fastapi import FastAPI
from app.api.v1.api import api_router
from app.db.database import get_db, AsyncSessionLocal, engine, Base
from app.db.neo4j import (
    get_neo4j_async_driver,
    close_neo4j_driver,
    initialize_gds,
    refresh_gds_graphs_and_similarities, # This will be called on startup
)
from app.api.v1.endpoints.people import router as people_router

from datetime import datetime, timedelta, timezone 

app = FastAPI(
    title="Your API",
    description="API for managing people and events",
    version="1.0.0",
    openapi_url="/openapi.json", # Standard
    docs_url="/docs", # Standard for Swagger UI
    redoc_url="/redoc" # Standard for ReDoc
)
app.include_router(
    api_router,
    prefix="/api/v1" # This prefix will apply to all routes nested under api_router
)
# --- GLOBAL IN-MEMORY STATE FOR GRAPH COMPUTATION TRIGGERS ---
_total_profile_updates_since_last_comp: int = 0
_last_similarity_computed_at: datetime = datetime.now(timezone.utc)
# --- END GLOBAL STATE ---

# --- IN-MEMORY STATE MANAGEMENT FUNCTIONS ---
async def increment_profile_update_count_in_memory():
    """Increments the in-memory counter for profile updates."""
    global _total_profile_updates_since_last_comp
    _total_profile_updates_since_last_comp += 1
    print(f"In-memory: Incremented profile update count to {_total_profile_updates_since_last_comp}")

async def reset_similarity_state_in_memory():
    """Resets the in-memory profile update counter and updates the last computation timestamp."""
    global _total_profile_updates_since_last_comp, _last_similarity_computed_at
    _total_profile_updates_since_last_comp = 0
    _last_similarity_computed_at = datetime.now(timezone.utc)
    print("In-memory: Graph computation state reset.")
# --- END IN-MEMORY STATE MANAGEMENT FUNCTIONS ---


# --- Background Task for Similarity Computation ---
async def background_similarity_task():
    MIN_HOURS_BETWEEN_COMPUTATIONS = 24 # Minimum 24 hours between full recomputations
    USER_UPDATE_THRESHOLD = 10         # Trigger if 10 relevant user profile updates occur
    
    # initial_gds_projected_on_first_run flag is no longer needed here
    # as startup_event guarantees the initial refresh.

    while True:
        await asyncio.sleep(60 * 60) # Check every hour

        try:
            # Access global state variables directly here as they are in the same file
            now_utc = datetime.now(timezone.utc)
            
            time_since_last_comp = now_utc - _last_similarity_computed_at
            updates_threshold_met = _total_profile_updates_since_last_comp >= USER_UPDATE_THRESHOLD
            time_condition_met = time_since_last_comp >= timedelta(hours=MIN_HOURS_BETWEEN_COMPUTATIONS)

            print(f"Similarity Check: Time since last: {time_since_last_comp}. Updates since last comp: {_total_profile_updates_since_last_comp}/{USER_UPDATE_THRESHOLD}. "
                  f"Time condition met: {time_condition_met}, Updates threshold met: {updates_threshold_met}")
            
            should_compute_similarities = False
            
            # The initial_gds_projected_on_first_run logic is removed,
            # as startup_event now guarantees the initial refresh.

            if updates_threshold_met:
                print(f"  --> User update threshold of {USER_UPDATE_THRESHOLD} met. Triggering computation.")
                should_compute_similarities = True
            elif time_condition_met:
                print(f"  --> {MIN_HOURS_BETWEEN_COMPUTATIONS} hours passed. Triggering computation.")
                should_compute_similarities = True
            else:
                print("Conditions not met for similarity computation. Waiting...")

            if should_compute_similarities:
                try:
                    print("Conditions met for similarity computation. Starting GDS refresh...")
                    await refresh_gds_graphs_and_similarities()
                    await reset_similarity_state_in_memory() 
                    print("GDS refresh completed and state reset.")
                except Exception as comp_e:
                    print(f"Error during GDS refresh: {comp_e}")
            else:
                print("Conditions not met for similarity computation. Waiting...")

        except Exception as e:
            print(f"Error in background_similarity_task: {e}")

@app.on_event("startup")
async def startup_event():
    print("Application startup...")
    
    print("Initializing PostgreSQL tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("PostgreSQL tables initialized.")

    await get_neo4j_async_driver()
    await initialize_gds()
    
    # --- HERE IS THE IMMEDIATE REFRESH ON STARTUP ---
    try:
        print("Performing initial GDS graph and similarity refresh on startup...")
        await refresh_gds_graphs_and_similarities()
        await reset_similarity_state_in_memory() # Reset state after initial refresh
        print("Initial GDS refresh completed.")
    except Exception as e:
        print(f"Initial GDS refresh failed on startup: {e}")
        # Depending on criticality, you might want to exit the app or log a critical error here.
        # For now, it will just log the error and proceed.

    asyncio.create_task(background_similarity_task())
    print("Background similarity task started.")

@app.on_event("shutdown")
async def shutdown_event():
    print("Application shutdown...")
    await close_neo4j_driver()

@app.get("/")
async def root():
    return {"message": "Welcome to the Knowledge Graph API!"}