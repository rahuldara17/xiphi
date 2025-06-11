import os
from neo4j import GraphDatabase
from graphdatascience import GraphDataScience

from neo4j_driver import get_neo4j_driver # Import your driver utility

# GDS client (will be initialized when driver is ready)
gds = None

# Names for our distinct GDS projected graphs
DEMO_GRAPH_NAME = "user_demographics_graph"
INTEREST_GRAPH_NAME = "user_interest_graph"
SKILL_GRAPH_NAME = "user_skill_graph"

def initialize_gds():
    """Initializes the GDS client and projects all necessary graphs."""
    global gds
    driver = get_neo4j_driver() # Ensure driver is initialized
    gds = GraphDataScience(driver)

    print("Initializing GDS graph projections...")

    # --- Project 1: Demographics Graph ---
    _try_project_gds_graph(
        DEMO_GRAPH_NAME,
        ['User', 'Company', 'Location', 'University'],
        {
            'WORKS_AT': {'orientation': 'UNDIRECTED'},
            'WORKED_AT': {'orientation': 'UNDIRECTED'},
            'LIVES_IN': {'orientation': 'UNDIRECTED'},
            'STUDIED_AT': {'orientation': 'UNDIRECTED'}
        }
    )

    # --- Project 2: Interests Graph ---
    _try_project_gds_graph(
        INTEREST_GRAPH_NAME,
        ['User', 'Interest'],
        {
            'HAS_INTEREST': {'orientation': 'UNDIRECTED'},
            'DESIRES_INDUSTRY': {'orientation': 'UNDIRECTED'} # Treat desired industry as an interest
        }
    )

    # --- Project 3: Skills Graph ---
    _try_project_gds_graph(
        SKILL_GRAPH_NAME,
        ['User', 'Skill'],
        {
            'HAS_SKILL': {'orientation': 'UNDIRECTED'}
        }
    )
    print("All GDS graphs projected successfully.")


def _try_project_gds_graph(graph_name, node_labels, relationship_types):
    """Helper to drop and project a GDS graph."""
    try:
        print(f"Dropping existing GDS graph '{graph_name}'...")
        # Removed 'failIfDoesNotExist=False' and handled error for older GDS versions
        gds.graph.drop(graph_name)
        print(f"Projecting GDS graph '{graph_name}'...")
        gds.graph.project(graph_name, node_labels, relationship_types)
        print(f"GDS graph '{graph_name}' projected successfully.")
    except Exception as e:
        # For older GDS versions, 'drop' will raise an error if graph doesn't exist.
        # We catch that specific error message if it implies "graph not found"
        # and allow the projection to proceed.
        if "does not exist" in str(e).lower() or "no graph exists" in str(e).lower():
            print(f"Graph '{graph_name}' did not exist, proceeding to project.")
            # Then try to project without re-raising an error from the drop.
            try:
                gds.graph.project(graph_name, node_labels, relationship_types)
                print(f"GDS graph '{graph_name}' projected successfully (after initial drop attempt).")
            except Exception as project_e:
                print(f"Error during projection of '{graph_name}' after drop attempt: {project_e}")
                raise project_e # Re-raise if project still fails
        else:
            print(f"Error projecting GDS graph '{graph_name}': {e}")
            raise # Re-raise the exception for other types of errors.


def compute_all_similarities():
    """
    Computes/re-computes all GDS similarities for the projected graphs.
    In a real app, this would be triggered periodically (e.g., via Celery/APScheduler).
    """
    if gds is None:
        print("GDS client not initialized. Cannot compute similarities.")
        return

    print("Computing all GDS similarities...")

    # Get graph objects before passing to write()
    demo_graph = None
    interest_graph = None
    skill_graph = None
    try:
        demo_graph = gds.graph.get(DEMO_GRAPH_NAME)
        interest_graph = gds.graph.get(INTEREST_GRAPH_NAME)
        skill_graph = gds.graph.get(SKILL_GRAPH_NAME)
    except Exception as e:
        print(f"Failed to retrieve projected graphs: {e}")
        raise # Re-raise to prevent further errors.

    # 1. Compute Demographics Similarity
    try:
        gds.nodeSimilarity.write(
            demo_graph, # Pass the graph OBJECT
            writeRelationshipType='SIMILAR_DEMO',
            writeProperty='score',
            topK=50,
            similarityCutoff=0.0
        )
        print("SIMILAR_DEMO calculation complete.")
    except Exception as e:
        print(f"Error computing SIMILAR_DEMO: {e}")

    # 2. Compute Interests Similarity
    try:
        gds.nodeSimilarity.write(
            interest_graph, # Pass the graph OBJECT
            writeRelationshipType='SIMILAR_INTEREST',
            writeProperty='score',
            topK=50,
            similarityCutoff=0.0
        )
        print("SIMILAR_INTEREST calculation complete.")
    except Exception as e:
        print(f"Error computing SIMILAR_INTEREST: {e}")

    # 3. Compute Skills Similarity
    try:
        gds.nodeSimilarity.write(
            skill_graph, # Pass the graph OBJECT
            writeRelationshipType='SIMILAR_SKILL',
            writeProperty='score',
            topK=50,
            similarityCutoff=0.0
        )
        print("SIMILAR_SKILL calculation complete.")
    except Exception as e:
        print(f"Error computing SIMILAR_SKILL: {e}")

    print("All GDS similarities computed.")


# --- Recommendation Retrieval Functions ---

def get_demographics_based_recommendations(user_id: str, limit: int = 5):
    """Recommends people based on strong demographic similarity (company, location, university)."""
    driver = get_neo4j_driver()
    results = []
    with driver.session() as session:
        query = f"""
        MATCH (me:User {{userID: $user_id}})
        MATCH (me)-[s:SIMILAR_DEMO]-(other:User)
        WHERE other.userID <> me.userID AND s.score > 0.0 // Filter out self and 0.0 scores

        OPTIONAL MATCH (other)-[:HAS_CURRENT_ROLE]->(jobRole:JobRole)

        // For demographic explainability: find common company/location/university
        OPTIONAL MATCH (me)-[:WORKS_AT]->(myCompany:Company)<-[:WORKS_AT]-(other)
        OPTIONAL MATCH (other)-[:WORKS_AT]->(otherCompany:Company)
        OPTIONAL MATCH (me)-[:LIVES_IN]->(myLocation:Location)<-[:LIVES_IN]-(other)
        OPTIONAL MATCH (other)-[:LIVES_IN]->(otherLocation:Location)
        OPTIONAL MATCH (me)-[:STUDIED_AT]->(myUniversity:University)<-[:STUDIED_AT]-(other)
        OPTIONAL MATCH (other)-[:STUDIED_AT]->(otherUniversity:University)


        RETURN DISTINCT other.userID AS UserID,
               other.fullName AS RecommendedUser,
               jobRole.title AS Role,
               other.yearsOfExperience AS YearsExperience,
               s.score AS SimilarityScore,
               COLLECT(DISTINCT CASE WHEN myCompany IS NOT NULL AND myCompany = otherCompany THEN otherCompany.name END) AS SharedCompanies,
               COLLECT(DISTINCT CASE WHEN myLocation IS NOT NULL AND myLocation = otherLocation THEN otherLocation.name END) AS SharedLocations,
               COLLECT(DISTINCT CASE WHEN myUniversity IS NOT NULL AND myUniversity = otherUniversity THEN otherUniversity.name END) AS SharedUniversities,
               'People For You (Demographics)' AS Category
        ORDER BY s.score DESC
        LIMIT $limit
        """
        records = session.run(query, user_id=user_id, limit=limit)
        for record in records:
            results.append(record.data())
    return results


def get_similar_interests_recommendations(user_id: str, limit: int = 5):
    """Recommends people based on shared interests."""
    driver = get_neo4j_driver()
    results = []
    with driver.session() as session:
        query = f"""
        MATCH (me:User {{userID: $user_id}})
        MATCH (me)-[s:SIMILAR_INTEREST]-(other:User)
        WHERE other.userID <> me.userID AND s.score > 0.0

        OPTIONAL MATCH (other)-[:HAS_CURRENT_ROLE]->(jobRole:JobRole)
        OPTIONAL MATCH (me)-[:HAS_INTEREST]->(commonInterest:Interest)<-[:HAS_INTEREST]-(other)

        RETURN DISTINCT other.userID AS UserID,
               other.fullName AS RecommendedUser,
               jobRole.title AS Role,
               other.yearsOfExperience AS YearsExperience,
               s.score AS SimilarityScore,
               COLLECT(DISTINCT commonInterest.name) AS CommonInterests,
               'People with Similar Interests' AS Category
        ORDER BY s.score DESC
        LIMIT $limit
        """
        records = session.run(query, user_id=user_id, limit=limit)
        for record in records:
            results.append(record.data())
    return results

def get_similar_skills_recommendations(user_id: str, limit: int = 5):
    """Recommends people based on shared skills."""
    driver = get_neo4j_driver()
    results = []
    with driver.session() as session:
        query = f"""
        MATCH (me:User {{userID: $user_id}})
        MATCH (me)-[s:SIMILAR_SKILL]-(other:User)
        WHERE other.userID <> me.userID AND s.score > 0.0

        OPTIONAL MATCH (other)-[:HAS_CURRENT_ROLE]->(jobRole:JobRole)
        OPTIONAL MATCH (me)-[:HAS_SKILL]->(commonSkill:Skill)<-[:HAS_SKILL]-(other)

        RETURN DISTINCT other.userID AS UserID,
               other.fullName AS RecommendedUser,
               jobRole.title AS Role,
               other.yearsOfExperience AS YearsExperience,
               s.score AS SimilarityScore,
               COLLECT(DISTINCT commonSkill.name) AS CommonSkills,
               'People with Similar Skills' AS Category
        ORDER BY s.score DESC
        LIMIT $limit
        """
        records = session.run(query, user_id=user_id, limit=limit)
        for record in records:
            results.append(record.data())
    return results