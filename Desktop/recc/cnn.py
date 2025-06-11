from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

URI = "bolt://localhost:7687"  # Or your Neo4j instance URI
USERNAME = "neo4j"
PASSWORD = "87654321"

try:
    with GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD)) as driver:
        # Option 1: Use verify_connectivity()
        driver.verify_connectivity()
        print("Neo4j connection established successfully!")

        # Option 2: Run a simple query to confirm
        # with driver.session() as session:
        #     session.run("MATCH () RETURN 1 LIMIT 1")
        #     print("Neo4j connection established and a simple query executed successfully!")

except AuthError as e:
    print(f"Authentication failed: {e}")
except ServiceUnavailable as e:
    print(f"Neo4j server is unavailable or connection refused: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")