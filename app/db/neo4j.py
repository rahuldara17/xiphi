import os
import asyncio
from neo4j import AsyncGraphDatabase, GraphDatabase # Use AsyncGraphDatabase for main ops, GraphDatabase for GDS's internal needs
from graphdatascience import GraphDataScience # GDS client
from typing import List, Dict, Any, Optional # Added Optional for biography parameter

from app.core.config import settings # Assuming settings are correctly defined here

# --- GLOBAL DRIVER INSTANCES ---
_neo4j_async_driver_instance = None # The async driver instance for general CRUD
_neo4j_sync_driver_for_gds_instance = None # A separate sync driver instance specifically for GDS
gds = None # Global GDS client instance


async def get_neo4j_driver():
    """Returns the Neo4j ASYNC driver instance, initializing if not already."""
    global _neo4j_async_driver_instance
    if _neo4j_async_driver_instance is None:
        uri = settings.NEO4J_URI
        username = settings.NEO4J_USER
        password = settings.NEO4J_PASSWORD
        if not uri or not username or not password:
            raise ValueError("Neo4j connection details are not set in app.core.config.")
        _neo4j_async_driver_instance = AsyncGraphDatabase.driver(uri, auth=(username, password))
        await _neo4j_async_driver_instance.verify_connectivity()
        print("Neo4j async driver initialized successfully!")
    return _neo4j_async_driver_instance

async def close_neo4j_driver():
    """Closes the Neo4j async driver connection AND the GDS sync driver."""
    global _neo4j_async_driver_instance, _neo4j_sync_driver_for_gds_instance
    if _neo4j_async_driver_instance:
        await _neo4j_async_driver_instance.close()
        _neo4j_async_driver_instance = None
        print("Neo4j async driver closed.")
    if _neo4j_sync_driver_for_gds_instance: # Close the sync driver for GDS as well
        _neo4j_sync_driver_for_gds_instance.close()
        _neo4j_sync_driver_for_gds_instance = None
        print("Neo4j GDS sync driver closed.")


# --- GDS Graph Names (Constants) ---
DEMO_GRAPH_NAME = "user_demographics_graph"
INTEREST_GRAPH_NAME = "user_interest_graph"
SKILL_GRAPH_NAME = "user_skill_graph"


async def initialize_gds():
    """
    Initializes the GDS client.
    This function no longer projects graphs; projection is handled by refresh_gds_graphs_and_similarities.
    """
    global gds, _neo4j_sync_driver_for_gds_instance
    
    # Create/get the SYNCHRONOUS driver instance explicitly for GDS.
    if _neo4j_sync_driver_for_gds_instance is None:
        _neo4j_sync_driver_for_gds_instance = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        _neo4j_sync_driver_for_gds_instance.verify_connectivity()
        print("Neo4j GDS sync driver initialized successfully!")
    
    gds = GraphDataScience(_neo4j_sync_driver_for_gds_instance)
    print("GDS client initialized.")


async def _try_project_gds_graph(graph_name: str, node_labels: List[str], relationship_types: Dict[str, Dict[str, str]]):
    """Helper to drop and project a GDS graph, wrapping sync GDS calls in to_thread."""
    try:
        print(f"Dropping existing GDS graph '{graph_name}'...")
        # Use asyncio.to_thread for synchronous GDS calls
        await asyncio.to_thread(gds.graph.drop, graph_name)
        print(f"Projecting GDS graph '{graph_name}'...")
        await asyncio.to_thread(gds.graph.project, graph_name, node_labels, relationship_types)
        print(f"GDS graph '{graph_name}' projected successfully.")
    except Exception as e:
        # Check for specific "does not exist" errors to handle first-time projection gracefully
        error_msg = str(e).lower()
        if "does not exist" in error_msg or "no graph exists" in error_msg:
            print(f"Graph '{graph_name}' did not exist, proceeding to project.")
            try:
                await asyncio.to_thread(gds.graph.project, graph_name, node_labels, relationship_types)
                print(f"GDS graph '{graph_name}' projected successfully (after initial drop attempt).")
            except Exception as project_e:
                print(f"Error during projection of '{graph_name}' after drop attempt: {project_e}")
                raise project_e # Re-raise serious projection errors
        else:
            print(f"Error projecting GDS graph '{graph_name}': {e}")
            raise # Re-raise unexpected errors


async def refresh_gds_graphs_and_similarities():
    """
    Orchestrates the dropping, re-projecting, and re-computing of all GDS graphs and similarities.
    This function is intended to be called by the background task based on defined criteria.
    """
    global gds

    if gds is None:
        # Defensive: If GDS client somehow isn't initialized yet, try to initialize it here.
        print("GDS client not initialized within refresh_gds_graphs_and_similarities. Attempting initialization.")
        await initialize_gds()
        if gds is None:
            print("GDS client could not be initialized. Aborting GDS refresh.")
            return

    print("Starting full GDS graph and similarity refresh process...")

    # Project all necessary graphs
    print("Projecting GDS graphs...")
    await _try_project_gds_graph(
        DEMO_GRAPH_NAME,
        ['User', 'Company', 'Location', 'University'],
        {
            'WORKS_AT': {'orientation': 'UNDIRECTED'},
            'WORKED_AT': {'orientation': 'UNDIRECTED'},
            'LIVES_IN': {'orientation': 'UNDIRECTED'},
            'STUDIED_AT': {'orientation': 'UNDIRECTED'}
        }
    )

    await _try_project_gds_graph(
        INTEREST_GRAPH_NAME,
        ['User', 'Interest'],
        {
            'HAS_INTEREST': {'orientation': 'UNDIRECTED'},
            'DESIRES_INDUSTRY': {'orientation': 'UNDIRECTED'}
        }
    )

    await _try_project_gds_graph(
        SKILL_GRAPH_NAME,
        ['User', 'Skill'],
        {
            'HAS_SKILL': {'orientation': 'UNDIRECTED'}
        }
    )
    print("All GDS graphs projected successfully.")

    # Compute all similarities
    print("Computing all GDS similarities...")

    # Ensure graphs are retrieved after projection to guarantee they are fresh
    # Wrap in try-except in case get fails (though _try_project_gds_graph should have caught it)
    try:
        demo_graph = await asyncio.to_thread(gds.graph.get, DEMO_GRAPH_NAME)
        interest_graph = await asyncio.to_thread(gds.graph.get, INTEREST_GRAPH_NAME)
        skill_graph = await asyncio.to_thread(gds.graph.get, SKILL_GRAPH_NAME)
    except Exception as e:
        print(f"Failed to retrieve projected graphs before similarity computation: {e}")
        raise # Re-raise as this is a critical failure for similarity

    # Helper to abstract similarity computation for reusability
    async def _compute_similarity(graph: Any, relationship_type: str, property_name: str):
        try:
            await asyncio.to_thread(gds.nodeSimilarity.write,
                graph,
                writeRelationshipType=relationship_type,
                writeProperty=property_name,
                topK=50,
                similarityCutoff=0.0
            )
            print(f"{relationship_type} calculation complete.")
        except Exception as e:
            print(f"Error computing {relationship_type}: {e}")
            raise # Re-raise to ensure the overall refresh knows it failed

    try:
        await _compute_similarity(demo_graph, 'SIMILAR_DEMO', 'score')
        await _compute_similarity(interest_graph, 'SIMILAR_INTEREST', 'score')
        await _compute_similarity(skill_graph, 'SIMILAR_SKILL', 'score')
        print("All GDS similarities computed.")
    except Exception as e:
        print(f"An error occurred during similarity computation: {e}")
        raise # Re-raise if any similarity computation fails

    print("Full GDS refresh process completed.")

# --- Asynchronous Neo4j CRUD functions ---
# These functions will use the AsyncGraphDatabase driver.

async def create_user_node(user_id: str, fullName: str, email: str, 
                     first_name: str, last_name: str, biography: Optional[str] = None): # ADD biography parameter
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        query = """
        MERGE (u:User {userID: $user_id})
        ON CREATE SET u.fullName = $fullName, u.email = $email,
                      u.first_name = $first_name, u.lastName = $last_name,
                      u.biography = $biography, // Set biography on create
                      u.createdAt = datetime()
        ON MATCH SET u.fullName = $fullName, u.email = $email,
                     u.first_name = $first_name, u.lastName = $last_name,
                     u.biography = $biography, // Update biography on match
                     u.updatedAt = datetime()
        RETURN u
        """
        await session.run(query, user_id=user_id, fullName=fullName, email=email,
                           first_name=first_name, last_name=last_name, biography=biography) # Pass biography
        print(f"Neo4j: Created/Updated User node for {fullName} (ID: {user_id})")

async def create_or_update_user_skill_neo4j(user_id: str, skill_name: str):
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        query = """
        MATCH (u:User {userID: $user_id})
        MERGE (s:Skill {name: $skill_name})
        MERGE (u)-[r:HAS_SKILL]->(s)
        ON CREATE SET r.assigned_at = datetime()
        ON MATCH SET r.updated_at = datetime()
        RETURN u, s, r
        """
        await session.run(query, user_id=user_id, skill_name=skill_name)
        print(f"Neo4j: User {user_id} HAS_SKILL {skill_name}")

async def create_or_update_user_interest_neo4j(user_id: str, interest_name: str):
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        query = """
        MATCH (u:User {userID: $user_id})
        MERGE (i:Interest {name: $interest_name})
        MERGE (u)-[r:HAS_INTEREST]->(i)
        ON CREATE SET r.assigned_at = datetime()
        ON MATCH SET r.updated_at = datetime()
        RETURN u, i, r
        """
        await session.run(query, user_id=user_id, interest_name=interest_name)
        print(f"Neo4j: User {user_id} HAS_INTEREST {interest_name}")

async def create_or_update_user_job_role_neo4j(user_id: str, job_role_title: str):
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        query = """
        MATCH (u:User {userID: $user_id})
        MERGE (j:JobRole {title: $job_role_title})
        MERGE (u)-[r:HAS_CURRENT_ROLE]->(j)
        ON CREATE SET r.assigned_at = datetime()
        ON MATCH SET r.updated_at = datetime()
        RETURN u, j, r
        """
        await session.run(query, user_id=user_id, job_role_title=job_role_title)
        print(f"Neo4j: User {user_id} HAS_CURRENT_ROLE {job_role_title}")

async def create_or_update_user_company_neo4j(user_id: str, company_name: str, is_current: bool = True):
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        # First, remove any existing CURRENT_WORKS_AT relationships for the user
        # This ensures only one "current" company, if your logic dictates
        # This assumes your logic only tracks one current company at a time via this relation
        await session.run(
            """
            MATCH (u:User {userID: $user_id})-[r:WORKS_AT {isCurrent: TRUE}]->(c:Company)
            SET r.isCurrent = FALSE
            """,
            user_id=user_id
        )

        query = """
        MATCH (u:User {userID: $user_id})
        MERGE (c:Company {name: $company_name})
        MERGE (u)-[r:WORKS_AT]->(c)
        ON CREATE SET r.assigned_at = datetime(), r.isCurrent = $is_current
        ON MATCH SET r.updated_at = datetime(), r.isCurrent = $is_current
        RETURN u, c, r
        """
        await session.run(query, user_id=user_id, company_name=company_name, is_current=is_current)
        print(f"Neo4j: User {user_id} WORKS_AT {company_name} (isCurrent: {is_current})")

async def update_user_location_neo4j(user_id: str, location_name: str, location_type: str = 'City'):
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        # Remove any existing LIVES_IN relationship to maintain a single current location
        await session.run(
            """
            MATCH (u:User {userID: $user_id})-[old_r:LIVES_IN]->(:Location)
            DELETE old_r
            """,
            user_id=user_id
        )

        query = """
        MATCH (u:User {userID: $user_id})
        MERGE (l:Location {name: $location_name, type: $location_type})
        MERGE (u)-[r:LIVES_IN]->(l)
        ON CREATE SET r.assigned_at = datetime()
        ON MATCH SET r.updated_at = datetime()
        RETURN u, l, r
        """
        await session.run(query, user_id=user_id, location_name=location_name, location_type=location_type)
        print(f"Neo4j: User {user_id} LIVES_IN {location_name}")

# --- Recommendation Queries (FINAL FIXES) ---

#