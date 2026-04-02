"""
Skills / Slash Commands — user-invocable named prompts.

Inspired by Claude Code's skills/ system.

Users can type /cv, /letter, /translate, /summarize etc. in chat and get
a focused, pre-configured response without needing to write a long prompt.

Each skill has:
- name: the slash command (e.g. "cv")
- description: shown in /help
- prompt_template: what gets injected as the system instruction
- aliases: alternative names

Delka improvements over Claude Code:
- Skills are defined in code AND loadable from DB (dynamic, per-platform)
- Skill arguments are parsed and injected into templates
- Returns structured response with skill metadata so frontend can style it
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    description: str
    prompt_template: str
    aliases: list[str] = field(default_factory=list)
    example: str = ""


# ── Built-in Delka skills ─────────────────────────────────────────────────────

SKILLS: dict[str, Skill] = {
    "help": Skill(
        name="help",
        description="List all available skills",
        prompt_template="",  # handled specially
        example="/help",
    ),
    "summarize": Skill(
        name="summarize",
        description="Summarize a block of text",
        prompt_template=(
            "Summarize the following text clearly and concisely. "
            "Use bullet points if the content has multiple distinct parts. "
            "Keep it under 150 words unless the text is very long.\n\nText:\n{args}"
        ),
        aliases=["summary", "tldr"],
        example="/summarize [paste text here]",
    ),
    "translate": Skill(
        name="translate",
        description="Translate text to another language",
        prompt_template=(
            "Translate the following text. "
            "If a target language is specified (e.g. 'to French'), translate to that. "
            "Otherwise detect the source and translate to English.\n\nText:\n{args}"
        ),
        aliases=["tr"],
        example="/translate [text] to French",
    ),
    "explain": Skill(
        name="explain",
        description="Explain code or a concept simply",
        prompt_template=(
            "Explain the following simply and clearly. "
            "If it's code, explain what it does step by step. "
            "If it's a concept, use a real-world analogy. "
            "Assume the reader is intelligent but not a specialist.\n\n{args}"
        ),
        aliases=["what"],
        example="/explain [code or concept]",
    ),
    "improve": Skill(
        name="improve",
        description="Improve writing quality",
        prompt_template=(
            "Improve the following text. Fix grammar, clarity, and flow. "
            "Keep the original meaning and voice. "
            "Return only the improved version — no commentary.\n\nText:\n{args}"
        ),
        aliases=["fix", "polish"],
        example="/improve [your text]",
    ),
    "email": Skill(
        name="email",
        description="Draft a professional email",
        prompt_template=(
            "Draft a professional email based on the following brief. "
            "Use proper Ghanaian professional tone. Be concise. "
            "Include Subject line.\n\nBrief:\n{args}"
        ),
        aliases=["mail"],
        example="/email [who to, purpose, key points]",
    ),
    "cv": Skill(
        name="cv",
        description="Get CV writing advice",
        prompt_template=(
            "You are a professional CV coach specialising in Ghanaian job market. "
            "Help the user with their CV based on the following:\n\n{args}"
        ),
        aliases=["resume"],
        example="/cv [what you need help with]",
    ),
    "debug": Skill(
        name="debug",
        description="Debug code — find and fix the problem",
        prompt_template=(
            "Debug the following code. "
            "1. Identify the bug(s) clearly. "
            "2. Explain why it's happening. "
            "3. Provide the fixed version.\n\nCode:\n{args}"
        ),
        aliases=["fix-code"],
        example="/debug [paste your code]",
    ),
    "brainstorm": Skill(
        name="brainstorm",
        description="Generate creative ideas on a topic",
        prompt_template=(
            "Generate 5 creative, specific ideas for the following. "
            "Be practical and relevant to the Ghanaian context where applicable. "
            "No generic suggestions.\n\nTopic:\n{args}"
        ),
        aliases=["ideas"],
        example="/brainstorm [topic]",
    ),
    "roast": Skill(
        name="roast",
        description="Get brutally honest feedback",
        prompt_template=(
            "Give brutally honest, constructive feedback on the following. "
            "Don't be polite — identify the real weaknesses. "
            "End with the 3 most important things to improve.\n\n{args}"
        ),
        aliases=["critique", "feedback"],
        example="/roast [your work, idea, or text]",
    ),
}

# Build alias lookup
_ALIAS_MAP: dict[str, str] = {}
for skill_name, skill in SKILLS.items():
    for alias in skill.aliases:
        _ALIAS_MAP[alias] = skill_name


def detect_skill(message: str) -> tuple[str, str] | None:
    """
    Check if message starts with a slash command.
    Returns (skill_name, args) or None.
    """
    message = message.strip()
    if not message.startswith("/"):
        return None
    parts = message[1:].split(None, 1)
    command = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    # Resolve alias
    resolved = _ALIAS_MAP.get(command, command)
    if resolved in SKILLS:
        return resolved, args
    return None


async def run_skill(skill_name: str, args: str, platform: str) -> dict:
    """
    Execute a skill and return structured response dict.
    """
    if skill_name == "help":
        return {"type": "skill_help", "content": _build_help_text()}

    skill = SKILLS.get(skill_name)
    if not skill:
        return {"type": "error", "content": f"Unknown skill: /{skill_name}. Type /help for available skills."}

    if not args:
        return {
            "type": "skill_hint",
            "content": f"**/{skill_name}** — {skill.description}\n\nUsage: `{skill.example}`",
        }

    prompt = skill.prompt_template.format(args=args)

    try:
        from services.inference_service import generate_full_response
        response, provider, model = await generate_full_response(
            task="chat",
            system_prompt=f"You are executing the /{skill_name} skill. {prompt.split(chr(10))[0]}",
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=1024,
        )
        return {
            "type": "skill_result",
            "skill": skill_name,
            "content": response,
            "provider": provider,
        }
    except Exception as e:
        return {"type": "error", "content": f"Skill /{skill_name} failed: {str(e)[:100]}"}


def _build_help_text() -> str:
    lines = ["**Available skills** — type `/[skill] [your input]`\n"]
    for name, skill in SKILLS.items():
        if name == "help":
            continue
        aliases = f" _(also: {', '.join('/' + a for a in skill.aliases)})_" if skill.aliases else ""
        lines.append(f"- **/{name}**{aliases} — {skill.description}")
    return "\n".join(lines)
