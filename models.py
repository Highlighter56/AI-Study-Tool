from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class OttoQuestion(BaseModel):
    id: str
    path: str
    question_text: str
    classification: str
    options: List[str]
    context: Optional[str] = None
    answer: Optional[str] = None
    suggested_mapping: Optional[Dict[str, Any]] = None
    confidence: float