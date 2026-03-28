from langdetect import detect as _detect
from langdetect import LangDetectException

_LANGUAGE_MAP: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ar": "Arabic",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "tw": "Twi (Ghanaian)",
    "ak": "Twi (Ghanaian)",
    "ha": "Hausa",
    "yo": "Yoruba",
    "sw": "Swahili",
    "hi": "Hindi",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "id": "Indonesian",
}


def detect_language(text: str) -> str:
    if len(text.strip()) < 15:
        return "en"
    try:
        return _detect(text)
    except (LangDetectException, Exception):
        return "en"


def get_language_instruction(lang: str) -> str:
    language_name = _LANGUAGE_MAP.get(lang.lower())
    if language_name:
        return f"Respond in {language_name}."
    return "Respond in English."
