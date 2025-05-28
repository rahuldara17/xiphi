from neo4j import GraphDatabase

uri = "bolt://localhost:7687"  # Or your port
username = "neo4j"
password = "asdfghjk"  # Try what you think it is

try:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    with driver.session() as session:
        result = session.run("RETURN 1")
        print(result.single()[0])
    print("Connection successful.")
except Exception as e:
    print("Failed to connect:", e)
