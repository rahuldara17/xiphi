from typing import Dict, Any, Optional
from app.db.neo4j import Neo4jConnection
from data_processing.transcript.processor import TranscriptProcessor
from app.models.person import PersonUpdate
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class TranscriptService:
    def __init__(self, db: Neo4jConnection):
        self.db = db
        self.processor = TranscriptProcessor()

    def process_transcript(self, transcript: str) -> Dict[str, Any]:
        """Process a transcript and extract structured information"""
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript received for processing.")
            return {}

        # Extract basic data (skills, expertise, interests, etc.)
        extracted_data = self.processor.process_transcript(transcript)

        # Use spaCy to extract named entities and keywords
        doc = self.processor.nlp(transcript)

        # Extract career goals (e.g., entities labeled as 'GOAL' or 'OBJECTIVE')
        career_goals = [ent.text for ent in doc.ents if ent.label_ in ['GOAL', 'OBJECTIVE']]
        if not career_goals:
            career_goals = ["goal1", "goal2"]  # Fallback if no goals found

        # Extract business objectives (e.g., entities labeled as 'ORG' or 'PROJECT')
        business_objectives = [ent.text for ent in doc.ents if ent.label_ in ['ORG', 'PROJECT']]
        if not business_objectives:
            business_objectives = ["objective1", "objective2"]  # Fallback if no objectives found

        # Extract topics (e.g., entities labeled as 'TOPIC' or 'SUBJECT')
        topics = [ent.text for ent in doc.ents if ent.label_ in ['TOPIC', 'SUBJECT']]
        if not topics:
            topics = ["topic1", "topic2"]  # Fallback if no topics found

        # Update extracted_data with real NLP-extracted fields
        extracted_data.update({
            "careerGoals": career_goals,
            "businessObjectives": business_objectives,
            "voiceAgentInteractions": [
                {
                    "interactionID": str(uuid.uuid4()),
                    "summary": "Sample interaction summary",
                    "extractedTopics": topics,
                    "noAttempts": 1
                }
            ],
            "recommendationFeedback": [
                {
                    "item": "item1",
                    "feedback": "like",
                    "timestamp": datetime.utcnow().isoformat()
                }
            ],
            "networkingConnections": [
                {
                    "userID": str(uuid.uuid4()),
                    "matchScore": 0.8,
                    "topicsOfInterest": topics,
                    "lastInteraction": datetime.utcnow().isoformat()
                }
            ],
            "growthMilestones": {
                "rolesAchieved": ["role1", "role2"],
                "skillsAcquired": ["skill1", "skill2"],
                "certificationsCompleted": ["cert1", "cert2"]
            },
            "education": [
                {
                    "institution": "IIT Bombay",
                    "degree": "B.Tech in Civil Engineering",
                    "start_year": 2021,
                    "end_year": 2025
                }
            ]
        })

        return extracted_data

    async def update_person_from_transcript(
        self,
        person_id: str,
        transcript_data: Dict[str, Any]
    ) -> Optional[str]:
        """Update a person's information in the graph based on transcript data"""
        try:
            # Build update model safely
            update_data = PersonUpdate(
                skills=transcript_data.get("skills") or [],
                expertise=transcript_data.get("expertise") or [],
                interests=transcript_data.get("interests") or [],
                company=transcript_data.get("company"),
                location=transcript_data.get("location")
            )

            logger.info(f"Updating person {person_id} with:")
            logger.info(f"  Skills: {update_data.skills}")
            logger.info(f"  Expertise: {update_data.expertise}")
            logger.info(f"  Interests: {update_data.interests}")
            logger.info(f"  Company: {update_data.company}")
            logger.info(f"  Location: {update_data.location}")

            query = """
            MATCH (p:Person {id: $person_id})
            SET p += $properties
            WITH p
            OPTIONAL MATCH (p)-[r:HAS_SKILL]->(s:Skill)
            WHERE NOT s.name IN $skills
            DELETE r
            WITH p
            UNWIND $skills AS skill
            MERGE (s:Skill {name: skill})
            MERGE (p)-[:HAS_SKILL]->(s)
            WITH p
            OPTIONAL MATCH (p)-[r:HAS_EXPERTISE]->(e:Expertise)
            WHERE NOT e.name IN $expertise
            DELETE r
            WITH p
            UNWIND $expertise AS exp
            MERGE (e:Expertise {name: exp})
            MERGE (p)-[:HAS_EXPERTISE]->(e)
            WITH p
            OPTIONAL MATCH (p)-[r:INTERESTED_IN]->(i:Interest)
            WHERE NOT i.name IN $interests
            DELETE r
            WITH p
            UNWIND $interests AS interest
            MERGE (i:Interest {name: interest})
            MERGE (p)-[:INTERESTED_IN]->(i)
            RETURN p.id AS person_id
            """

            with self.db.get_session() as session:
                result = session.run(
                    query,
                    {
                        "person_id": person_id,
                        "properties": {
                            "company": update_data.company,
                            "location": update_data.location
                        },
                        "skills": update_data.skills,
                        "expertise": update_data.expertise,
                        "interests": update_data.interests
                    }
                )

                record = result.single()
                if record and "person_id" in record:
                    return record["person_id"]
                else:
                    logger.warning(f"No record returned while updating person {person_id}")
                    return None

        except Exception as e:
            logger.error(f"Error updating person from transcript: {str(e)}", exc_info=True)
            raise
