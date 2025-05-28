from neo4j import GraphDatabase
from app.core.config import settings
from typing import List, Dict, Any, Optional
import logging
import uuid
import json


logger = logging.getLogger(__name__)


class Neo4jConnection:
    def __init__(self):
        self._driver = None
        logger.info(f"Initializing Neo4j connection with URI: {settings.NEO4J_URI}")
        logger.info(f"Using Neo4j user: {settings.NEO4J_USER}")
        self._connect()

    def _connect(self):
        try:
            logger.info("Attempting to connect to Neo4j...")
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            # Verify connection
            with self._driver.session() as session:
                logger.info("Testing connection with a simple query...")
                result = session.run("RETURN 1")
                logger.info(f"Connection test result: {result.single()}")
            logger.info("Successfully connected to Neo4j")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {str(e)}")
            logger.error(f"Connection details - URI: {settings.NEO4J_URI}, User: {settings.NEO4J_USER}")
            raise

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def get_session(self):
        if not self._driver:
            self._connect()
        return self._driver.session()

    async def create_constraints(self):
        """Create necessary constraints in Neo4j"""
        constraints = [
            "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT company_name IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE"
        ]
        
        with self.get_session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    logger.warning(f"Failed to create constraint: {str(e)}")

    

    async def create_person(self, person_data: Dict[str, Any]) -> str:
        person_id = str(uuid.uuid4())

        # Convert list of dicts to list of strings for Neo4j storage
        education_list = person_data.get("education", [])
        education_strings = []
        for edu in education_list:
            # Convert each dict into a JSON string (or a formatted string)
            education_strings.append(json.dumps(edu))

        properties = {
            "name": person_data["name"],
            "role": person_data["role"],
            "email": person_data["email"],
            "linkedin_url": person_data.get("linkedin_url"),
            "education": education_strings,  # This is now a list of strings
        }

        skills = person_data.get("skills", [])
        expertise = person_data.get("expertise", [])
        interests = person_data.get("interests", [])

        query = """
        MERGE (p:Person {id: $id})
        SET p += $properties
        WITH p
        UNWIND $skills as skill
        MERGE (s:Skill {name: skill})
        MERGE (p)-[:HAS_SKILL]->(s)
        WITH p
        UNWIND $expertise as exp
        MERGE (e:Expertise {name: exp})
        MERGE (p)-[:HAS_EXPERTISE]->(e)
        WITH p
        UNWIND $interests as interest
        MERGE (i:Interest {name: interest})
        MERGE (p)-[:INTERESTED_IN]->(i)
        RETURN p.id as person_id
        """

        params = {
            "id": person_id,
            "properties": properties,
            "skills": skills,
            "expertise": expertise,
            "interests": interests
        }

        with self.get_session() as session:
            result = session.run(query, params)
            return result.single()["person_id"]


    async def get_recommendations(self, person_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recommendations for a person based on shared skills, interests, and expertise"""
        query = """
        MATCH (p:Person {id: $person_id})
        MATCH (other:Person)
        WHERE other.id <> $person_id
        WITH p, other,
             [(p)-[:HAS_SKILL]->(s)<-[:HAS_SKILL]-(other) | s.name] as shared_skills,
             [(p)-[:HAS_EXPERTISE]->(e)<-[:HAS_EXPERTISE]-(other) | e.name] as shared_expertise,
             [(p)-[:INTERESTED_IN]->(i)<-[:INTERESTED_IN]-(other) | i.name] as shared_interests
        WITH other, shared_skills, shared_expertise, shared_interests,
             size(shared_skills) as skill_score,
             size(shared_expertise) as expertise_score,
             size(shared_interests) as interest_score
        WHERE skill_score > 0 OR expertise_score > 0 OR interest_score > 0
        RETURN other.id as person_id,
               other.name as name,
               other.role as role,
               shared_skills,
               shared_expertise,
               shared_interests,
               skill_score + expertise_score + interest_score as total_score
        ORDER BY total_score DESC
        LIMIT $limit
        """

        with self.get_session() as session:
            result = session.run(query, {"person_id": person_id, "limit": limit})
            return [dict(record) for record in result]
    async def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        query = """
        MATCH (p:Person {id: $person_id})
        OPTIONAL MATCH (p)-[:HAS_SKILL]->(s:Skill)
        OPTIONAL MATCH (p)-[:HAS_EXPERTISE]->(e:Expertise)
        OPTIONAL MATCH (p)-[:INTERESTED_IN]->(i:Interest)
        RETURN p, collect(DISTINCT s.name) as skills, 
            collect(DISTINCT e.name) as expertise, 
            collect(DISTINCT i.name) as interests
        """

        with self.get_session() as session:
            result = session.run(query, {"person_id": person_id})
            record = result.single()
            if not record:
                return None

            person_node = record["p"]
            education = [json.loads(e) for e in person_node.get("education", [])]

            return {
                "id": person_node["id"],
                "name": person_node["name"],
                "role": person_node["role"],
                "email": person_node["email"],
                "bio": person_node.get("bio"),
                "location": person_node.get("location"),
                "company": person_node.get("company"),
                "job_title": person_node.get("job_title"),
                "linkedin_url": person_node.get("linkedin_url"),
                "education": education,
                "skills": record["skills"],
                "expertise": record["expertise"],
                "interests": record["interests"],
            }

    async def update_person(self, person_id: str, updated_data: Dict[str, Any]) -> Optional[str]:
    # Convert education list to JSON strings
        education = updated_data.get("education", [])
        if isinstance(education, list):
            updated_data["education"] = [json.dumps(e) for e in education]

        query = """
        MATCH (p:Person {id: $person_id})
        SET p += $properties
        WITH p
        OPTIONAL MATCH (p)-[r:HAS_SKILL]->()
        DELETE r
        WITH p
        OPTIONAL MATCH (p)-[r:HAS_EXPERTISE]->()
        DELETE r
        WITH p
        OPTIONAL MATCH (p)-[r:INTERESTED_IN]->()
        DELETE r
        WITH p
        UNWIND $skills as skill
        MERGE (s:Skill {name: skill})
        MERGE (p)-[:HAS_SKILL]->(s)
        WITH p
        UNWIND $expertise as exp
        MERGE (e:Expertise {name: exp})
        MERGE (p)-[:HAS_EXPERTISE]->(e)
        WITH p
        UNWIND $interests as interest
        MERGE (i:Interest {name: interest})
        MERGE (p)-[:INTERESTED_IN]->(i)
        RETURN p.id as person_id
        """

        params = {
            "person_id": person_id,
            "properties": {
                key: updated_data[key]
                for key in ["name", "role", "email", "bio", "location", "company", "job_title", "linkedin_url", "education"]
                if key in updated_data
            },
            "skills": updated_data.get("skills", []),
            "expertise": updated_data.get("expertise", []),
            "interests": updated_data.get("interests", []),
        }

        with self.get_session() as session:
            result = session.run(query, params)
            record = result.single()
            return record["person_id"] if record else None

    async def delete_person(self, person_id: str) -> bool:
        query = """
        MATCH (p:Person {id: $person_id})
        DETACH DELETE p
        RETURN COUNT(p) AS deleted_count
        """

        with self.get_session() as session:
            result = session.run(query, {"person_id": person_id})
            record = result.single()
            return record["deleted_count"] > 0

neo4j = Neo4jConnection()
