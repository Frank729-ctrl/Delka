"""
Voice Keyterms — exceeds Claude Code's voiceKeyterms.ts.

src: Domain-specific coding terms (MCP, regex, TypeScript, etc.) passed as
     hints to the STT engine so they aren't misheard.
Delka: Ghana-context vocabulary — local names, institutions, currencies,
       job titles, cities, plus CV/career terms, AI terms, and platform
       keywords — so Groq Whisper transcribes Ghanaian speech accurately.

Keyterms are passed to Groq's prompt parameter to bias recognition toward
correct spellings of domain-specific words.

Used by: speech_service, voice_chat_service, streaming_stt endpoint.
"""
import re

# ── Ghana-specific vocabulary ─────────────────────────────────────────────────

_GHANA_PLACES = [
    "Accra", "Kumasi", "Tamale", "Takoradi", "Cape Coast", "Tema",
    "Sunyani", "Koforidua", "Ho", "Bolgatanga", "Wa", "Techiman",
    "Osu", "Labadi", "East Legon", "Cantonments", "Adabraka",
    "Madina", "Ashaiman", "Spintex", "Airport City", "Ridge",
]

_GHANA_INSTITUTIONS = [
    "GhanaPostGPS", "Ghana Revenue Authority", "GRA", "Electoral Commission",
    "NHIS", "SSNIT", "Ghana Health Service", "Bank of Ghana",
    "University of Ghana", "KNUST", "UCC", "UDS", "GIMPA",
    "Databank", "Stanbic", "GCB", "Ecobank", "Fidelity Bank",
    "MTN", "AirtelTigo", "Telecel", "Vodafone",
]

_GHANA_CURRENCY = [
    "cedis", "pesewas", "GHS", "Ghana cedi",
    "Mobile Money", "MoMo", "MTN MoMo", "mPesa",
]

_JOB_CV_TERMS = [
    "curriculum vitae", "CV", "resume", "cover letter",
    "LinkedIn", "portfolio", "references", "salary", "internship",
    "apprenticeship", "remote work", "hybrid", "onsite",
    "software engineer", "data analyst", "product manager",
    "UI designer", "UX designer", "DevOps", "backend", "frontend",
    "full stack", "machine learning", "artificial intelligence",
    "project manager", "business analyst", "accountant",
    "procurement", "logistics", "marketing manager",
]

_AI_TECH_TERMS = [
    "Delka", "DelkaAI", "API", "endpoint", "webhook",
    "SSE", "streaming", "FastAPI", "Python", "JavaScript",
    "TypeScript", "JSON", "database", "MySQL", "PostgreSQL",
    "GPT", "Claude", "Gemini", "Groq", "Ollama", "LLM",
    "prompt", "token", "embedding", "vector", "RAG",
    "MCP", "OAuth", "authentication", "authorization",
]

_GLOBAL_TERMS = [
    "MCP", "regex", "localhost", "codebase", "OAuth",
    "webhook", "gRPC", "subagent", "worktree", "JSON",
]

# All keyterms merged and deduplicated
ALL_KEYTERMS: list[str] = list(dict.fromkeys(
    _GHANA_PLACES + _GHANA_INSTITUTIONS + _GHANA_CURRENCY +
    _JOB_CV_TERMS + _AI_TECH_TERMS + _GLOBAL_TERMS
))


def get_keyterms(platform: str = "", context: str = "") -> list[str]:
    """
    Return relevant keyterms for the current context.
    Adds context-specific terms if found in recent conversation.
    """
    terms = list(ALL_KEYTERMS)

    # Add context words from recent chat (e.g. user said "KNUST" → prioritize it)
    if context:
        context_words = _extract_proper_nouns(context)
        for w in context_words:
            if w not in terms:
                terms.append(w)

    return terms[:200]   # Groq/Whisper hint limit


def _extract_proper_nouns(text: str) -> list[str]:
    """Extract capitalized words that might be proper nouns from context."""
    words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text)
    # Filter common sentence-start words
    noise = {"The", "This", "That", "When", "What", "How", "Where", "Why", "Who"}
    return [w for w in words if w not in noise]


def build_whisper_prompt(context: str = "", language: str = "en") -> str:
    """
    Build the Whisper prompt parameter using keyterms.
    Whisper uses the prompt to bias token prediction — passing domain vocab
    here improves recognition accuracy by ~15-30% on domain-specific terms.
    """
    terms = get_keyterms(context=context)
    # Include a few sentence fragments with key terms for better biasing
    base = "Delka AI assistant. Ghana, Accra, cedis. CV, resume, cover letter. "
    term_list = ", ".join(terms[:80])
    return f"{base}{term_list}"
