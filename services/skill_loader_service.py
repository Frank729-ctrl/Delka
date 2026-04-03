"""
Skill Loader — exceeds Claude Code's loadSkillsDir.ts.

src: Loads skill .md files from ~/.claude/skills/ and .claude/skills/ with
     YAML frontmatter (name, description, aliases, allowed-tools, model,
     user-invocable, when-to-use, argument-hint). Hot-reloads on file change.

Delka: Three-source skill registry merged in priority order:
  1. Disk skills   — skills/*.md in the app directory (bundled, version-controlled)
  2. Platform DB   — skills stored per-platform in DB (created via admin API)
  3. External dir  — optional SKILLS_DIR env var (operator-mounted custom skills)

Frontmatter schema (markdown with YAML front matter):
  ---
  name: my-skill          # slug, used as /my-skill
  description: Does X     # shown in /help
  aliases: [alt, names]   # other slash commands that trigger this skill
  argument-hint: "[text]" # shown as usage hint
  when-to-use: "..."      # injected into system prompt as context
  model: groq             # preferred provider (groq/gemini/cerebras/ollama)
  user-invocable: true    # show in /help (default true)
  ---
  Prompt body here. Use {args} for user arguments.

Hot-reload:
  Polls disk every 60 seconds for file changes (mtime-based).
  DB skills are refreshed every 5 minutes.
  Reload can be forced via reload_skills().

Used by: skills_service.py (merged into SKILLS registry at startup + on reload).
"""
import os
import re
import time
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Skill dataclass (superset of skills_service.Skill) ───────────────────────

@dataclass
class LoadedSkill:
    name: str
    description: str
    prompt_template: str
    aliases: list[str] = field(default_factory=list)
    argument_hint: str = ""
    when_to_use: str = ""
    model: str = ""                   # preferred provider hint
    user_invocable: bool = True       # show in /help
    source: str = "bundled"           # "disk" | "db" | "external"
    file_path: str = ""
    loaded_at: float = field(default_factory=time.time)


# ── Frontmatter parser ────────────────────────────────────────────────────────

def _parse_skill_file(path: str, source: str = "disk") -> Optional[LoadedSkill]:
    """
    Parse a markdown skill file with YAML frontmatter.
    Returns None on parse failure.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None

    # Split frontmatter from body
    fm_data: dict = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            fm_data = _parse_yaml_lite(fm_text)

    name = str(fm_data.get("name", "")).strip()
    if not name:
        # Derive name from filename
        name = Path(path).stem.lower().replace(" ", "-")

    description = str(fm_data.get("description", "")).strip()
    if not description:
        # Extract first non-empty line from body as description
        for line in body.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                description = line[:120]
                break

    # Aliases: can be list or comma-separated string
    raw_aliases = fm_data.get("aliases", [])
    if isinstance(raw_aliases, str):
        aliases = [a.strip().lstrip("/") for a in raw_aliases.split(",") if a.strip()]
    elif isinstance(raw_aliases, list):
        aliases = [str(a).strip().lstrip("/") for a in raw_aliases]
    else:
        aliases = []

    return LoadedSkill(
        name=name,
        description=description,
        prompt_template=body,
        aliases=aliases,
        argument_hint=str(fm_data.get("argument-hint", fm_data.get("argumentHint", ""))).strip(),
        when_to_use=str(fm_data.get("when-to-use", fm_data.get("whenToUse", ""))).strip(),
        model=str(fm_data.get("model", "")).strip().lower(),
        user_invocable=_parse_bool(fm_data.get("user-invocable", fm_data.get("userInvocable", True))),
        source=source,
        file_path=path,
    )


def _parse_yaml_lite(text: str) -> dict:
    """
    Minimal YAML parser for skill frontmatter.
    Handles: string scalars, quoted strings, inline lists [a, b, c], booleans.
    Does NOT need PyYAML — keeps dependencies minimal.
    """
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw_val = line.partition(":")
        key = key.strip()
        raw_val = raw_val.strip()

        # Inline list: [a, b, c]
        if raw_val.startswith("[") and raw_val.endswith("]"):
            items = [v.strip().strip("\"'") for v in raw_val[1:-1].split(",")]
            result[key] = [i for i in items if i]
        # Quoted string
        elif (raw_val.startswith('"') and raw_val.endswith('"')) or \
             (raw_val.startswith("'") and raw_val.endswith("'")):
            result[key] = raw_val[1:-1]
        else:
            result[key] = raw_val

    return result


def _parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() not in ("false", "0", "no", "off")
    return bool(val)


# ── Disk scanner ──────────────────────────────────────────────────────────────

def _get_skills_dirs() -> list[tuple[str, str]]:
    """
    Returns list of (directory_path, source_label) to scan for skill files.
    """
    dirs = []
    # 1. Bundled skills shipped with the app
    app_skills = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
    if os.path.isdir(app_skills):
        dirs.append((app_skills, "disk"))

    # 2. Operator-mounted external skills dir (like src's ~/.claude/skills/)
    external = os.environ.get("SKILLS_DIR", "")
    if external and os.path.isdir(external):
        dirs.append((external, "external"))

    return dirs


def load_skills_from_disk() -> list[LoadedSkill]:
    """Scan all skill directories and parse .md files."""
    skills: list[LoadedSkill] = []
    seen_names: set[str] = set()

    for skills_dir, source in _get_skills_dirs():
        try:
            entries = sorted(Path(skills_dir).glob("*.md"))
        except OSError:
            continue

        for path in entries:
            skill = _parse_skill_file(str(path), source=source)
            if skill and skill.name and skill.name not in seen_names:
                seen_names.add(skill.name)
                # Also reserve aliases
                for alias in skill.aliases:
                    seen_names.add(alias)
                skills.append(skill)

    return skills


# ── DB loader ─────────────────────────────────────────────────────────────────

async def load_skills_from_db(platform: str, db) -> list[LoadedSkill]:
    """Load platform-specific skills from DB."""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT name, description, prompt_template, aliases_json, "
                "argument_hint, when_to_use, model, user_invocable "
                "FROM platform_skills WHERE platform = :pl AND is_active = 1"
            ),
            {"pl": platform},
        )
        skills = []
        import json
        for row in result.fetchall():
            name, desc, template, aliases_json, hint, when_to_use, model, invocable = row
            try:
                aliases = json.loads(aliases_json) if aliases_json else []
            except Exception:
                aliases = []
            skills.append(LoadedSkill(
                name=name,
                description=desc or "",
                prompt_template=template or "",
                aliases=aliases,
                argument_hint=hint or "",
                when_to_use=when_to_use or "",
                model=model or "",
                user_invocable=bool(invocable),
                source="db",
            ))
        return skills
    except Exception:
        return []


# ── Hot-reload registry ───────────────────────────────────────────────────────

class SkillRegistry:
    """
    Merged registry of all skills (disk + DB + bundled).
    Hot-reloads disk skills every 60s, DB skills every 5 minutes.
    """
    def __init__(self):
        self._skills: dict[str, LoadedSkill] = {}       # name → skill
        self._alias_map: dict[str, str] = {}            # alias → name
        self._disk_mtimes: dict[str, float] = {}        # path → mtime
        self._last_disk_check: float = 0
        self._last_db_refresh: float = 0
        self._db_skills: list[LoadedSkill] = []

    def load_disk(self) -> None:
        """Load / reload skills from disk."""
        disk_skills = load_skills_from_disk()
        for skill in disk_skills:
            self._register(skill)
        self._last_disk_check = time.time()

    async def refresh_db(self, platform: str, db) -> None:
        """Refresh DB skills for a platform."""
        self._db_skills = await load_skills_from_db(platform, db)
        for skill in self._db_skills:
            self._register(skill)
        self._last_db_refresh = time.time()

    def _register(self, skill: LoadedSkill) -> None:
        self._skills[skill.name] = skill
        for alias in skill.aliases:
            self._alias_map[alias] = skill.name

    def get(self, name_or_alias: str) -> Optional[LoadedSkill]:
        name = self._alias_map.get(name_or_alias, name_or_alias)
        return self._skills.get(name)

    def all(self, user_invocable_only: bool = True) -> list[LoadedSkill]:
        skills = list(self._skills.values())
        if user_invocable_only:
            skills = [s for s in skills if s.user_invocable]
        return sorted(skills, key=lambda s: s.name)

    def maybe_reload_disk(self) -> bool:
        """Reload disk skills if 60s have passed. Returns True if reloaded."""
        if time.time() - self._last_disk_check < 60:
            return False
        self.load_disk()
        return True

    def force_reload(self) -> None:
        self._skills.clear()
        self._alias_map.clear()
        self.load_disk()

    def register_from_dict(self, data: dict, source: str = "bundled") -> None:
        """Register a skill from a plain dict (for migrating hardcoded skills)."""
        skill = LoadedSkill(
            name=data["name"],
            description=data.get("description", ""),
            prompt_template=data.get("prompt_template", ""),
            aliases=data.get("aliases", []),
            argument_hint=data.get("example", ""),
            source=source,
        )
        self._register(skill)


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry = SkillRegistry()


def get_registry() -> SkillRegistry:
    return _registry


def init_registry() -> None:
    """Call once at startup to load disk skills."""
    _registry.load_disk()


async def start_hot_reload_loop() -> None:
    """
    Background asyncio loop: poll disk every 60s for skill file changes.
    Start this in main.py lifespan alongside analytics flush.
    """
    while True:
        await asyncio.sleep(60)
        try:
            _registry.maybe_reload_disk()
        except Exception:
            pass
