"""
Bible plugin — verse lookup via bible-api.com (free, no key).
Supports references like "John 3:16", "Psalm 23", "Romans 8:28".
"""
import re
import httpx

_VERSE_RE = re.compile(
    r"\b([1-3]?\s*[A-Za-z]+)\s+(\d+)(?::(\d+)(?:-(\d+))?)?\b",
)

_TRIGGER = re.compile(
    r"\b("
    r"bible verse|scripture|what does (the )?bible say"
    r"|read (me )?(a )?(verse|psalm|proverb|chapter)"
    r"|(?:john|psalm|psalms|proverb|proverbs|genesis|exodus|romans|matthew|mark|luke|acts|"
    r"corinthians|galatians|ephesians|philippians|colossians|thessalonians|timothy|titus|"
    r"hebrews|james|peter|revelation|isaiah|jeremiah|ezekiel|daniel|hosea|joel|amos|"
    r"obadiah|jonah|micah|nahum|habakkuk|zephaniah|haggai|zechariah|malachi|"
    r"deuteronomy|leviticus|numbers|joshua|judges|ruth|samuel|kings|chronicles|"
    r"ezra|nehemiah|esther|job|ecclesiastes|song of solomon|lamentations)"
    r"\s+\d"
    r")\b",
    re.IGNORECASE,
)

_BOOK_ABBR = {
    "gen": "Genesis", "exo": "Exodus", "lev": "Leviticus", "num": "Numbers",
    "deu": "Deuteronomy", "jos": "Joshua", "jud": "Judges", "rut": "Ruth",
    "psa": "Psalms", "pro": "Proverbs", "ecc": "Ecclesiastes",
    "isa": "Isaiah", "jer": "Jeremiah", "eze": "Ezekiel", "dan": "Daniel",
    "mat": "Matthew", "mar": "Mark", "luk": "Luke", "joh": "John",
    "act": "Acts", "rom": "Romans", "rev": "Revelation",
}


def needs_bible(message: str) -> bool:
    return bool(_TRIGGER.search(message))


def _extract_reference(message: str) -> str:
    m = _VERSE_RE.search(message)
    if not m:
        return ""
    book    = m.group(1).strip().replace(" ", "+")
    chapter = m.group(2)
    verse   = m.group(3)
    end     = m.group(4)
    ref = f"{book}+{chapter}"
    if verse:
        ref += f":{verse}"
        if end:
            ref += f"-{end}"
    return ref


async def run_bible(message: str) -> str:
    ref = _extract_reference(message)
    if not ref:
        return ""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"https://bible-api.com/{ref}")
            r.raise_for_status()
            data = r.json()

        if "error" in data:
            return ""

        reference = data.get("reference", ref.replace("+", " "))
        text      = data.get("text", "").strip()
        if not text:
            return ""

        return (
            f"--- BIBLE ({reference}) ---\n"
            f"{text}\n"
            f"Translation: World English Bible (WEB)\n"
            f"--- END ---"
        )
    except Exception:
        return ""
