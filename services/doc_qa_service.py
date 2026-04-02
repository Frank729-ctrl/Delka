"""
Document Q&A — inspired by Claude Code's MagicDocs service.

Allows users to upload a PDF or paste raw text and ask questions about it.
Extracts text, chunks it, and answers questions grounded in the document.

Endpoint: POST /v1/doc/ask
- document_text: raw text (if already extracted)
- document_base64: base64-encoded PDF (uses OCR service to extract)
- question: what to ask about the document
- session_id: to maintain document context across turns
"""
import base64
import hashlib
from typing import Optional

# In-memory document store per session (evicted after 2 hours of inactivity)
import time
_DOC_STORE: dict[str, dict] = {}  # session_id → {text, hash, last_access}
_DOC_TTL_SECONDS = 7200


def _evict_stale():
    now = time.time()
    stale = [k for k, v in _DOC_STORE.items() if now - v["last_access"] > _DOC_TTL_SECONDS]
    for k in stale:
        del _DOC_STORE[k]


def store_document(session_id: str, text: str) -> str:
    """Store document text for a session. Returns content hash."""
    _evict_stale()
    doc_hash = hashlib.sha256(text[:500].encode()).hexdigest()[:8]
    _DOC_STORE[session_id] = {
        "text": text,
        "hash": doc_hash,
        "last_access": time.time(),
        "char_count": len(text),
        "word_count": len(text.split()),
    }
    return doc_hash


def get_document(session_id: str) -> Optional[str]:
    """Retrieve stored document text for a session."""
    entry = _DOC_STORE.get(session_id)
    if not entry:
        return None
    entry["last_access"] = time.time()
    return entry["text"]


def get_document_stats(session_id: str) -> Optional[dict]:
    entry = _DOC_STORE.get(session_id)
    if not entry:
        return None
    return {
        "hash": entry["hash"],
        "char_count": entry["char_count"],
        "word_count": entry["word_count"],
    }


def _chunk_text(text: str, max_chars: int = 8000, overlap: int = 400) -> list[str]:
    """Split text into overlapping chunks for long documents."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def build_doc_qa_system_prompt(doc_text: str, question: str) -> str:
    """
    Builds the system prompt for document Q&A.
    For long documents, picks the most relevant chunk.
    """
    chunks = _chunk_text(doc_text)

    if len(chunks) == 1:
        context = doc_text
    else:
        # Use the first + most question-relevant chunk (simple keyword overlap)
        q_words = set(question.lower().split())
        scored = []
        for chunk in chunks:
            c_words = set(chunk.lower().split())
            score = len(q_words & c_words)
            scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        context = scored[0][1]
        if len(chunks) > 2 and scored[0][0] != scored[-1][0]:
            # Append beginning of document for context
            context = chunks[0][:2000] + "\n...\n" + context

    return f"""You are answering questions about a document.
Answer ONLY based on the document content below.
If the answer is not in the document, say so clearly.
Do not guess or use outside knowledge.

DOCUMENT:
{context}
"""


async def answer_question(
    question: str,
    session_id: str,
    document_text: Optional[str] = None,
    document_base64: Optional[str] = None,
) -> dict:
    """
    Main entry point for document Q&A.
    Returns: {answer, doc_hash, word_count, is_new_document}
    """
    is_new_document = False

    # Upload new document if provided
    if document_text:
        doc_hash = store_document(session_id, document_text)
        is_new_document = True
    elif document_base64:
        # Decode and extract text via OCR service
        try:
            from services.ocr_service import extract_text
            image_bytes = base64.b64decode(document_base64)
            extracted = await extract_text(image_bytes)
            doc_hash = store_document(session_id, extracted)
            is_new_document = True
        except Exception as e:
            return {"error": f"Could not extract document text: {e}"}

    # Retrieve document for this session
    doc_text = get_document(session_id)
    if not doc_text:
        return {"error": "No document found for this session. Please upload a document first."}

    stats = get_document_stats(session_id)
    system_prompt = build_doc_qa_system_prompt(doc_text, question)

    try:
        from services.inference_service import generate_full_response
        answer, provider, model = await generate_full_response(
            task="chat",
            system_prompt=system_prompt,
            user_prompt=question,
            temperature=0.1,    # Low temperature for grounded answers
            max_tokens=1024,
        )
        return {
            "answer": answer,
            "provider": provider,
            "model": model,
            "doc_hash": stats["hash"],
            "doc_word_count": stats["word_count"],
            "is_new_document": is_new_document,
        }
    except Exception as e:
        return {"error": str(e)}
