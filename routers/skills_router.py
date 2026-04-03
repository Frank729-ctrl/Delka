"""
Skills admin router — manage platform skills via API.

GET    /v1/skills                     — list all skills (disk + DB + bundled)
POST   /v1/skills                     — create a new platform skill in DB
PUT    /v1/skills/{name}              — update a skill
DELETE /v1/skills/{name}              — deactivate a skill
POST   /v1/skills/reload              — force hot-reload from disk
POST   /v1/skills/{name}/run          — test-run a skill
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from services.skill_loader_service import get_registry, init_registry

router = APIRouter(prefix="/v1/skills")


class CreateSkillRequest(BaseModel):
    platform: str
    name: str
    description: str
    prompt_template: str
    aliases: list[str] = []
    argument_hint: str = ""
    when_to_use: str = ""
    model: str = ""
    user_invocable: bool = True


class RunSkillRequest(BaseModel):
    args: str
    platform: str = ""


@router.get("")
async def api_list_skills(platform: str = "", db: AsyncSession = Depends(get_db)):
    """List all skills — disk-loaded + DB platform skills + bundled."""
    registry = get_registry()
    registry.maybe_reload_disk()

    # Also refresh DB skills if platform provided
    if platform:
        await registry.refresh_db(platform, db)

    skills = registry.all(user_invocable_only=False)
    return {
        "status": "ok",
        "count": len(skills),
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "aliases": s.aliases,
                "argument_hint": s.argument_hint,
                "when_to_use": s.when_to_use,
                "model": s.model,
                "user_invocable": s.user_invocable,
                "source": s.source,
            }
            for s in skills
        ],
    }


@router.post("")
async def api_create_skill(req: CreateSkillRequest, db: AsyncSession = Depends(get_db)):
    """Create or replace a platform skill in DB."""
    try:
        await db.execute(
            text(
                "INSERT INTO platform_skills "
                "(platform, name, description, prompt_template, aliases_json, "
                "argument_hint, when_to_use, model, user_invocable, is_active, updated_at) "
                "VALUES (:pl, :name, :desc, :tmpl, :aliases, :hint, :wtu, :model, :inv, 1, NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "description=:desc, prompt_template=:tmpl, aliases_json=:aliases, "
                "argument_hint=:hint, when_to_use=:wtu, model=:model, "
                "user_invocable=:inv, is_active=1, updated_at=NOW()"
            ),
            {
                "pl": req.platform, "name": req.name, "desc": req.description,
                "tmpl": req.prompt_template, "aliases": json.dumps(req.aliases),
                "hint": req.argument_hint, "wtu": req.when_to_use,
                "model": req.model, "inv": int(req.user_invocable),
            },
        )
        await db.commit()

        # Register into live registry immediately (no wait for next poll)
        registry = get_registry()
        await registry.refresh_db(req.platform, db)

        return {"status": "ok", "name": req.name, "platform": req.platform}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])


@router.put("/{skill_name}")
async def api_update_skill(
    skill_name: str,
    req: CreateSkillRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing platform skill."""
    req.name = skill_name
    return await api_create_skill(req, db)


@router.delete("/{skill_name}")
async def api_delete_skill(
    skill_name: str,
    platform: str,
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a skill (soft delete)."""
    try:
        await db.execute(
            text(
                "UPDATE platform_skills SET is_active = 0 "
                "WHERE name = :name AND platform = :pl"
            ),
            {"name": skill_name, "pl": platform},
        )
        await db.commit()

        # Remove from live registry
        registry = get_registry()
        registry._skills.pop(skill_name, None)

        return {"status": "ok", "deactivated": skill_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])


@router.post("/reload")
async def api_reload_skills():
    """Force hot-reload of all disk skills."""
    registry = get_registry()
    registry.force_reload()
    skills = registry.all(user_invocable_only=False)
    return {"status": "ok", "reloaded": len(skills), "skills": [s.name for s in skills]}


@router.post("/{skill_name}/run")
async def api_run_skill(skill_name: str, req: RunSkillRequest):
    """Test-run a skill directly."""
    from services.skills_service import run_skill
    result = await run_skill(skill_name, req.args, req.platform)
    return {"status": "ok", **result}
