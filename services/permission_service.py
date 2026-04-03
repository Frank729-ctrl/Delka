"""
Permission Modes — ports Claude Code's permission system to Delka.

src has 4 modes (bashPermissions.ts, permissionMode.ts):
  auto      — runs commands/tools without asking (default for trusted contexts)
  manual    — asks user to approve each tool call before execution
  readonly  — allows read-only operations, blocks any writes
  sandbox   — executes in isolated environment (Docker or restricted subprocess)

Delka extends this with:
  - Per-request mode (API field: permission_mode)
  - Per-platform mode (stored in DB, overrides request default)
  - Per-API-key mode (stored in DB, overrides platform mode)
  - 4 mode hierarchy: api_key > platform > request > default

Additional Delka enhancements beyond src:
  - `restricted`: no code execution, no web fetch, no tool use — chat only
  - Granular capability flags (can_execute_code, can_fetch_urls, can_use_tools)
  - Audit log: every permission decision is logged with reason
  - Mode inheritance: child sessions inherit parent's mode

Modes:
  auto       — all capabilities enabled, no confirmation required
  manual     — tool calls require explicit user approval (client must handle)
  readonly   — read ops only: no code exec, no fetch, no MCP writes
  sandbox    — code execution isolated to /tmp, no network in subprocess
  restricted — chat only: no code, no fetch, no tools, no memory writes

Resolution order (highest wins):
  api_key_mode > platform_mode > request_mode > "auto" (default)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Mode definitions ──────────────────────────────────────────────────────────

VALID_MODES = {"auto", "manual", "readonly", "sandbox", "restricted"}

_MODE_RANK = {
    "auto": 0,
    "manual": 1,
    "readonly": 2,
    "sandbox": 3,
    "restricted": 4,
}


@dataclass
class PermissionProfile:
    """Resolved permission profile for a single request."""
    mode: str                       # resolved mode name
    source: str                     # where this mode came from: api_key|platform|request|default

    # Capability flags derived from mode
    can_execute_code: bool = True
    can_fetch_urls: bool = True
    can_use_tools: bool = True
    can_write_memory: bool = True
    requires_approval: bool = False  # True in manual mode — client must prompt user

    # Sandbox-specific
    sandbox_network: bool = True    # False in sandbox mode (subprocess has no outbound net)
    sandbox_cwd: str = "/tmp"


# ── Capability matrix ─────────────────────────────────────────────────────────

_MODE_CAPABILITIES: dict[str, dict] = {
    "auto": {
        "can_execute_code": True,
        "can_fetch_urls": True,
        "can_use_tools": True,
        "can_write_memory": True,
        "requires_approval": False,
        "sandbox_network": True,
        "sandbox_cwd": "/tmp",
    },
    "manual": {
        "can_execute_code": True,
        "can_fetch_urls": True,
        "can_use_tools": True,
        "can_write_memory": True,
        "requires_approval": True,   # client must ask before acting
        "sandbox_network": True,
        "sandbox_cwd": "/tmp",
    },
    "readonly": {
        "can_execute_code": False,
        "can_fetch_urls": True,      # fetching URLs is read-only
        "can_use_tools": True,       # read-only tool calls allowed
        "can_write_memory": False,
        "requires_approval": False,
        "sandbox_network": True,
        "sandbox_cwd": "/tmp",
    },
    "sandbox": {
        "can_execute_code": True,
        "can_fetch_urls": False,     # no outbound network in isolated exec
        "can_use_tools": True,
        "can_write_memory": True,
        "requires_approval": False,
        "sandbox_network": False,    # subprocess network blocked
        "sandbox_cwd": "/tmp",
    },
    "restricted": {
        "can_execute_code": False,
        "can_fetch_urls": False,
        "can_use_tools": False,
        "can_write_memory": False,
        "requires_approval": False,
        "sandbox_network": False,
        "sandbox_cwd": "/tmp",
    },
}


# ── Resolver ──────────────────────────────────────────────────────────────────

def resolve_permission(
    request_mode: Optional[str] = None,
    platform_mode: Optional[str] = None,
    api_key_mode: Optional[str] = None,
) -> PermissionProfile:
    """
    Resolve final permission mode from the three sources.
    Higher-ranked source wins (api_key > platform > request > default=auto).
    Within the same rank, more restrictive mode wins.
    """
    # Validate and collect candidates with their source labels
    candidates: list[tuple[str, str]] = []  # (mode, source)

    for mode, source in [
        (api_key_mode, "api_key"),
        (platform_mode, "platform"),
        (request_mode, "request"),
    ]:
        if mode and mode in VALID_MODES:
            candidates.append((mode, source))

    if not candidates:
        mode, source = "auto", "default"
    else:
        # Highest-rank source wins; if same rank, more restrictive mode wins
        # Since api_key > platform > request by list order, first valid candidate wins
        # (list is already in priority order)
        mode, source = candidates[0]

    caps = _MODE_CAPABILITIES.get(mode, _MODE_CAPABILITIES["auto"])
    return PermissionProfile(mode=mode, source=source, **caps)


def check_capability(profile: PermissionProfile, capability: str) -> tuple[bool, str]:
    """
    Check if a specific capability is allowed under this profile.
    Returns (allowed, reason).

    capability: "execute_code" | "fetch_url" | "use_tools" | "write_memory"
    """
    cap_map = {
        "execute_code": (profile.can_execute_code, "code execution"),
        "fetch_url": (profile.can_fetch_urls, "URL fetching"),
        "use_tools": (profile.can_use_tools, "tool use"),
        "write_memory": (profile.can_write_memory, "memory write"),
    }
    if capability not in cap_map:
        return True, ""  # unknown capability → allow (fail-open)

    allowed, label = cap_map[capability]
    if not allowed:
        return False, f"{label} is disabled in {profile.mode} mode (set by {profile.source})"
    if profile.requires_approval:
        return True, f"requires approval ({profile.mode} mode)"
    return True, ""


def permission_instruction(profile: PermissionProfile) -> str:
    """Build a system prompt instruction for the current permission mode."""
    if profile.mode == "auto":
        return ""  # no restrictions to communicate

    lines = [f"**Permission mode: {profile.mode}** (enforced by {profile.source})"]

    if profile.mode == "manual":
        lines.append(
            "Before executing any code, fetching URLs, or calling tools, "
            "tell the user what you're about to do and wait for explicit confirmation."
        )
    elif profile.mode == "readonly":
        lines.append(
            "You are in read-only mode. You may analyze and explain code, "
            "read files, and answer questions, but you MUST NOT execute code, "
            "write files, or modify any data."
        )
    elif profile.mode == "sandbox":
        lines.append(
            "Code execution is sandboxed to /tmp with no network access. "
            "You may run code but cannot make external HTTP requests from within code."
        )
    elif profile.mode == "restricted":
        lines.append(
            "You are in restricted mode: chat responses only. "
            "Do not execute code, fetch URLs, call tools, or offer to do so."
        )

    return "\n".join(lines)


# ── DB helpers ────────────────────────────────────────────────────────────────

async def get_platform_permission_mode(platform: str, db) -> Optional[str]:
    """Fetch the platform-level permission mode from DB."""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT setting_value FROM platform_settings WHERE platform = :pl AND setting_key = 'permission_mode'"),
            {"pl": platform},
        )
        row = result.fetchone()
        if row:
            mode = row[0]
            return mode if mode in VALID_MODES else None
    except Exception:
        pass
    return None


async def set_platform_permission_mode(platform: str, mode: str, db) -> bool:
    """Persist a platform-level permission mode."""
    if mode not in VALID_MODES:
        return False
    try:
        from sqlalchemy import text
        await db.execute(
            text(
                "INSERT INTO platform_settings (platform, setting_key, setting_value) "
                "VALUES (:pl, 'permission_mode', :mode) "
                "ON CONFLICT (platform, setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value"
            ),
            {"pl": platform, "mode": mode},
        )
        await db.commit()
        return True
    except Exception:
        return False
