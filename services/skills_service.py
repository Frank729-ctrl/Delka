"""
Skills / Slash Commands — exceeds Claude Code's loadSkillsDir.ts + bundledSkills.ts.

src: Skills loaded from ~/.claude/skills/*.md with YAML frontmatter.
     Bundled skills registered in code. Hot-reload on file change.
Delka: Three-tier registry (disk → DB → bundled) with:
     - Disk skills from skills/*.md (shipped with app, version-controlled)
     - Platform DB skills (per-platform, created via admin API at runtime)
     - External dir via SKILLS_DIR env var (operator-mounted)
     - Full YAML frontmatter: name, description, aliases, model, argument-hint,
       when-to-use, user-invocable
     - Argument substitution: {args}, named {arg1} {arg2} placeholders
     - Per-skill model preference (groq/gemini/cerebras/ollama)
     - Hot-reload: disk polled every 60s, DB every 5 min

Merged into chat_service: 'when-to-use' is injected into system prompt context
so the AI knows when to suggest skills proactively.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from services.skill_loader_service import get_registry, LoadedSkill


# ── Bundled skills (hardcoded, always available) ───────────────────────────────
# These are registered into the loader registry at startup so they merge
# cleanly with disk and DB skills (disk/DB take priority if same name).

_BUNDLED: list[dict] = [
    {
        "name": "help",
        "description": "List all available skills",
        "prompt_template": "",
        "aliases": [],
        "argument_hint": "",
    },
    {
        "name": "summarize",
        "description": "Summarize text into key points",
        "prompt_template": (
            "Summarize the following clearly and concisely. "
            "Use bullet points if the content has multiple distinct parts. "
            "Keep it under 150 words unless the text is very long.\n\nText:\n{args}"
        ),
        "aliases": ["summary", "tldr"],
        "argument_hint": "[paste text]",
    },
    {
        "name": "translate",
        "description": "Translate text to another language",
        "prompt_template": (
            "Translate the following text. If a target language is specified "
            "(e.g. 'to French'), translate to that. "
            "Otherwise detect the source and translate to English.\n\nText:\n{args}"
        ),
        "aliases": ["tr"],
        "argument_hint": "[text] to [language]",
    },
    {
        "name": "explain",
        "description": "Explain code or a concept simply",
        "prompt_template": (
            "Explain the following simply and clearly. If it's code, explain "
            "what it does step by step. If it's a concept, use a real-world "
            "analogy. Assume the reader is intelligent but not a specialist.\n\n{args}"
        ),
        "aliases": ["what"],
        "argument_hint": "[code or concept]",
    },
    {
        "name": "improve",
        "description": "Improve writing — fix grammar, clarity, and flow",
        "prompt_template": (
            "Improve the following text. Fix grammar, clarity, and flow. "
            "Keep the original meaning and voice. "
            "Return only the improved version — no commentary.\n\nText:\n{args}"
        ),
        "aliases": ["fix", "polish"],
        "argument_hint": "[your text]",
    },
    {
        "name": "email",
        "description": "Draft a professional email",
        "prompt_template": (
            "Draft a professional email based on the following brief. "
            "Use proper professional tone. Be concise. "
            "Include Subject line.\n\nBrief:\n{args}"
        ),
        "aliases": ["mail"],
        "argument_hint": "[recipient, purpose, key points]",
    },
    {
        "name": "cv",
        "description": "CV writing advice for the Ghanaian job market",
        "prompt_template": (
            "You are a professional CV coach specialising in the Ghanaian job market. "
            "Help the user with their CV based on the following:\n\n{args}"
        ),
        "aliases": ["resume"],
        "argument_hint": "[what you need help with]",
    },
    {
        "name": "debug",
        "description": "Debug code — identify and fix the problem",
        "prompt_template": (
            "Debug the following code.\n"
            "1. Identify the bug(s) clearly.\n"
            "2. Explain why it's happening.\n"
            "3. Provide the fixed version.\n\nCode:\n{args}"
        ),
        "aliases": ["fix-code"],
        "argument_hint": "[paste your code]",
    },
    {
        "name": "brainstorm",
        "description": "Generate creative ideas on a topic",
        "prompt_template": (
            "Generate 5 creative, specific ideas for the following. "
            "Be practical and relevant to the Ghanaian context where applicable. "
            "No generic suggestions.\n\nTopic:\n{args}"
        ),
        "aliases": ["ideas"],
        "argument_hint": "[topic]",
    },
    {
        "name": "roast",
        "description": "Get brutally honest, constructive feedback",
        "prompt_template": (
            "Give brutally honest, constructive feedback on the following. "
            "Don't be polite — identify the real weaknesses. "
            "End with the 3 most important things to improve.\n\n{args}"
        ),
        "aliases": ["critique", "feedback"],
        "argument_hint": "[your work, idea, or text]",
    },
]


def _register_bundled() -> None:
    """Register bundled skills into the shared registry (disk/DB takes priority)."""
    registry = get_registry()
    for b in _BUNDLED:
        # Only register if not already loaded from disk or DB
        if not registry.get(b["name"]):
            registry.register_from_dict(b, source="bundled")


# ── Argument substitution ──────────────────────────────────────────────────────

def _substitute_args(template: str, args: str) -> str:
    """
    Substitute {args} and optionally named {arg1}, {arg2} placeholders.
    Ported from src's substituteArguments() in argumentSubstitution.ts.

    Examples:
      "{args}"              → full args string
      "{arg1} vs {arg2}"    → split on "vs", "and", comma
      "{topic_clause}"      → " about {args}" if args else ""
    """
    if "{topic_clause}" in template:
        clause = f" about {args}" if args else ""
        template = template.replace("{topic_clause}", clause)

    # Named positional args: split on common delimiters
    named_pattern = re.compile(r"\{arg(\d+)\}")
    if named_pattern.search(template):
        # Split on "vs", "and", "at", comma, dash
        parts = re.split(r"\s+(?:vs\.?|and|at|@)\s+|,\s*|\s+-\s*", args, maxsplit=5)
        parts = [p.strip() for p in parts if p.strip()]

        def replace_named(m: re.Match) -> str:
            idx = int(m.group(1)) - 1
            return parts[idx] if idx < len(parts) else args

        template = named_pattern.sub(replace_named, template)

    # Finally substitute {args} with full string
    template = template.replace("{args}", args)
    return template


# ── Task → inference task mapping ─────────────────────────────────────────────

_MODEL_TO_TASK = {
    "groq": "chat",
    "gemini": "cv",        # cv chain starts with Gemini
    "cerebras": "code",
    "ollama": "chat",
    "": "chat",
}


# ── Public API ────────────────────────────────────────────────────────────────

def detect_skill(message: str) -> tuple[str, str] | None:
    """
    Check if message starts with a slash command.
    Returns (skill_name, args) or None.
    """
    message = message.strip()
    if not message.startswith("/"):
        return None
    parts = message[1:].split(None, 1)
    command = parts[0].lower().rstrip(":")
    args = parts[1].strip() if len(parts) > 1 else ""

    registry = get_registry()
    skill = registry.get(command)
    if skill:
        return skill.name, args
    return None


async def run_skill(skill_name: str, args: str, platform: str, db=None) -> dict:
    """
    Execute a skill. Looks up registry (disk → DB → bundled).
    """
    _register_bundled()   # idempotent — only registers missing ones
    registry = get_registry()

    if skill_name == "help":
        return {"type": "skill_help", "content": _build_help_text()}

    # Refresh DB skills if db provided
    if db and platform:
        await registry.refresh_db(platform, db)

    skill = registry.get(skill_name)
    if not skill:
        available = ", ".join(f"/{s.name}" for s in registry.all())
        return {
            "type": "error",
            "content": f"Unknown skill: `/{skill_name}`. Available: {available}\nType `/help` for details.",
        }

    if not args:
        hint = skill.argument_hint or "[your input]"
        return {
            "type": "skill_hint",
            "content": (
                f"**/{skill.name}** — {skill.description}\n\n"
                f"Usage: `/{skill.name} {hint}`"
                + (f"\n\nAlso available as: {', '.join('`/' + a + '`' for a in skill.aliases)}" if skill.aliases else "")
            ),
        }

    prompt = _substitute_args(skill.prompt_template, args)
    task = _MODEL_TO_TASK.get(skill.model, "chat")

    try:
        from services.inference_service import generate_full_response
        response, provider, model = await generate_full_response(
            task=task,
            system_prompt=f"You are executing the /{skill.name} skill. {skill.description}",
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=1200,
        )
        return {
            "type": "skill_result",
            "skill": skill.name,
            "content": response,
            "provider": provider,
            "source": skill.source,
        }
    except Exception as e:
        return {"type": "error", "content": f"Skill `/{skill.name}` failed: {str(e)[:100]}"}


def get_skills_context() -> str:
    """
    Build a 'when-to-use' context block for the system prompt.
    Tells the AI when to proactively suggest each skill.
    Ported from src's skill whenToUse injection.
    """
    _register_bundled()
    registry = get_registry()
    lines = []
    for skill in registry.all():
        if skill.when_to_use:
            lines.append(f"- Use `/{skill.name}` when: {skill.when_to_use}")
    if not lines:
        return ""
    return "**Available skills** (suggest when relevant):\n" + "\n".join(lines)


def _build_help_text() -> str:
    _register_bundled()
    registry = get_registry()
    lines = ["**Available skills** — type `/[skill] [your input]`\n"]
    for skill in registry.all():
        if skill.name == "help":
            continue
        aliases = (
            f" _(also: {', '.join('/' + a for a in skill.aliases)})_"
            if skill.aliases else ""
        )
        hint = f" `{skill.argument_hint}`" if skill.argument_hint else ""
        source_tag = f" [{skill.source}]" if skill.source != "bundled" else ""
        lines.append(f"- **/{skill.name}**{aliases}{hint}{source_tag} — {skill.description}")
    return "\n".join(lines)
