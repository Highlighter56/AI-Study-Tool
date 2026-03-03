from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class OttoQuestion(BaseModel):
    id: str
    path: str
    question_text: str
    question_type: str
    classification: str
    options: List[str]
    context: Optional[str] = None
    answer: Optional[str] = None
    suggested_mapping: Optional[Dict[str, Any]] = None
    answer_payload: Dict[str, Any] = Field(default_factory=dict)
    model_used: Optional[str] = None
    confidence: float
    confidence_reasons: List[str] = Field(default_factory=list)