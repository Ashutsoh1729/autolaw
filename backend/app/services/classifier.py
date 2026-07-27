"""Document type classifier — uses LLM or rule-based fallback to classify document chunks."""

import logging
import re

logger = logging.getLogger(__name__)

# Known document types
DOC_TYPES = ["contract", "email", "police_report", "medical_record", "correspondence", "other"]

# Keywords for rule-based classification fallback
TYPE_KEYWORDS: dict[str, list[str]] = {
    "contract": [
        "agreement", "contract", "terms and conditions", "party of the first part",
        "hereby", "witnesseth", "indemnify", "whereas", "breach of contract",
    ],
    "email": [
        "subject:", "from:", "to:", "re:", "dear", "sincerely", "regards",
        "sent from", "original message", "--original message--",
    ],
    "police_report": [
        "police department", "incident report", "case number", "offense",
        "complaintant", "responding officer", "badge number", "police report",
    ],
    "medical_record": [
        "patient", "diagnosis", "prescription", "medical record", "doctor",
        "physician", "symptoms", "treatment", "clinical", "hospital",
    ],
    "correspondence": [
        "dear", "sincerely", "enclosed", "please find", "letter",
        "reference", "attention", "re:", "cc:",
    ],
}


def classify_by_keywords(text: str) -> str:
    """Simple rule-based keyword classifier as fallback."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for doc_type, keywords in TYPE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[doc_type] = count

    if not scores:
        return "other"

    return max(scores, key=scores.get)  # type: ignore[arg-type]


def classify_with_llm(text: str) -> str:
    """Classify document type using LLM.

    Placeholder — will be wired to OpenAI/Anthropic in Step 6.
    Falls back to keyword-based classification for now.
    """
    # TODO: Implement LLM-based classification
    return classify_by_keywords(text)


async def classify_chunk(text: str) -> tuple[str, float]:
    """Classify a text chunk by document type.

    Returns (doc_type, confidence).
    """
    doc_type = classify_with_llm(text)
    # Simple confidence heuristic based on keyword density
    keywords = TYPE_KEYWORDS.get(doc_type, [])
    if not keywords:
        return doc_type, 0.5

    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw in text_lower)
    confidence = min(matches / max(len(keywords), 1) * 2, 0.95)
    confidence = max(confidence, 0.3)

    return doc_type, confidence


async def classify_document(text: str) -> str:
    """Classify an entire document (majority vote across chunks)."""
    from app.services.chunker import chunk_document

    chunks = chunk_document(text)
    if not chunks:
        return "other"

    type_votes: dict[str, int] = {}
    for chunk in chunks:
        doc_type, _ = await classify_chunk(chunk.text)
        type_votes[doc_type] = type_votes.get(doc_type, 0) + 1

    return max(type_votes, key=type_votes.get)  # type: ignore[arg-type]
