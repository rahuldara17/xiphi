from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.services.transcript_service import TranscriptService
from app.db.neo4j import neo4j

router = APIRouter()
transcript_service = TranscriptService(neo4j)

class TranscriptRequest(BaseModel):
    """Request model for transcript processing"""
    transcript: str
    person_id: Optional[str] = None  # Optional: if provided, will update person in graph
    save_to_graph: bool = False  # Whether to save the extracted data to the graph

class TranscriptResponse(BaseModel):
    """Response model for processed transcript data"""
    extracted_data: Dict[str, Any]
    person_id: Optional[str] = None
    message: str

@router.post("/process", response_model=TranscriptResponse)
async def process_transcript(request: TranscriptRequest):
    """
    Process a transcript and optionally save the extracted data to the knowledge graph.
    
    This endpoint is for testing purposes and accepts raw transcript text.
    It uses NLP to extract structured information like skills, expertise, interests, etc.
    """
    try:
        # Process the transcript
        extracted_data = transcript_service.process_transcript(request.transcript)
        
        # If save_to_graph is True and person_id is provided, update the person in the graph
        person_id = None
        if request.save_to_graph and request.person_id:
            person_id = await transcript_service.update_person_from_transcript(
                person_id=request.person_id,
                transcript_data=extracted_data
            )
            message = "Transcript processed and data saved to knowledge graph"
        else:
            message = "Transcript processed successfully"
        
        return TranscriptResponse(
            extracted_data=extracted_data,
            person_id=person_id,
            message=message
        )
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Example transcripts for testing
EXAMPLE_TRANSCRIPTS = {
    "software_engineer": """
    I'm a senior software engineer with 8 years of experience in Python and machine learning.
    I'm particularly interested in natural language processing and computer vision.
    I graduated from Stanford University with a Master's in Computer Science in 2015.
    I'm currently working at Google where I'm proficient in cloud technologies and distributed systems.
    I'm passionate about AI and enjoy working on open-source projects.
    My expertise includes deep learning, neural networks, and big data processing.
    I'm also skilled in Docker, Kubernetes, and microservices architecture.
    """,
    
    "data_scientist": """
    As a data scientist, I specialize in predictive modeling and statistical analysis.
    I have extensive experience with R, Python, and SQL.
    I'm particularly interested in healthcare analytics and bioinformatics.
    I hold a PhD in Statistics from MIT and currently work at Pfizer.
    My expertise includes machine learning, data visualization, and experimental design.
    I'm passionate about using data to solve real-world healthcare problems.
    I'm also skilled in TensorFlow, PyTorch, and scikit-learn.
    """,
    
    "product_manager": """
    I'm a product manager with a focus on AI and machine learning products.
    I have a strong background in both technical and business aspects of product development.
    I graduated from Harvard Business School and worked at Microsoft for 5 years.
    I'm particularly interested in user experience and product strategy.
    My expertise includes agile methodologies, product roadmapping, and market analysis.
    I'm skilled in data analytics, user research, and product metrics.
    I'm passionate about building products that make a real impact.
    """
}

@router.get("/examples/{example_id}")
async def get_example_transcript(example_id: str):
    """Get an example transcript for testing purposes"""
    if example_id not in EXAMPLE_TRANSCRIPTS:
        raise HTTPException(
            status_code=404,
            detail=f"Example transcript '{example_id}' not found. Available examples: {list(EXAMPLE_TRANSCRIPTS.keys())}"
        )
    
    return {
        "transcript": EXAMPLE_TRANSCRIPTS[example_id],
        "example_id": example_id
    } 