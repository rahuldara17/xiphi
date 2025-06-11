import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Neo4j connection details
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Initialize the Neo4j driver
driver = None

def get_neo4j_driver():
    """Returns the Neo4j driver instance, initializing if not already."""
    global driver
    if driver is None:
        if not NEO4J_URI or not NEO4J_USERNAME or not NEO4J_PASSWORD:
            raise ValueError("Neo4j connection details are not set in .env file.")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity() # Test the connection
        print("Neo4j driver initialized successfully!")
    return driver

def close_neo4j_driver():
    """Closes the Neo4j driver connection."""
    global driver
    if driver:
        driver.close()
        driver = None
        print("Neo4j driver closed.")

