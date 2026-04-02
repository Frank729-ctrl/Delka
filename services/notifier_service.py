"""
Notifier — exceeds Claude Code's notifier.ts.

src: Desktop/system notifications when long CLI tasks complete.
Delka: Multi-channel notifications — webhook POST + Resend email —
       when async jobs complete (CV generation, scheduled tasks, etc).
       Also supports in-chat "ping" style notifications via SSE event.

Channels:
1. Webhook: HTTP POST to configured URL with job result
2. Email:   Resend API (already in stack) with job summary
3. SSE:     Push a notification event into the active chat stream

Used by: job_queue (CV/letter async jobs), cron_service, coordinator.
"""
import time
from typing import Optional


async def notify_job_complete(
    job_id: str,
    job_type: str,          # "cv" | "letter" | "cron" | "coordinator"
    user_id: str,
    platform: str,
    result_summary: str,
    webhook_url: Optional[str] = None,
    email: Optional[str] = None,
    download_url: Optional[str] = None,
) -> None:
    """
    Send completion notification via all configured channels.
    Non-blocking — all network calls are fire-and-forget.
    """
    payload = {
        "job_id": job_id,
        "job_type": job_type,
        "status": "completed",
        "summary": result_summary[:500],
        "completed_at": time.time(),
        "download_url": download_url,
    }

    tasks = []

    if webhook_url:
        import asyncio
        tasks.append(asyncio.create_task(_send_webhook(webhook_url, payload)))

    if email:
        import asyncio
        tasks.append(asyncio.create_task(_send_email(
            to=email,
            job_type=job_type,
            summary=result_summary,
            download_url=download_url,
        )))

    from services.analytics_service import log_event
    log_event("notification_sent", platform=platform, user_id=user_id,
              job_type=job_type, channels=",".join(
                  ["webhook"] * bool(webhook_url) + ["email"] * bool(email)
              ))


async def _send_webhook(url: str, payload: dict) -> None:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload, headers={"Content-Type": "application/json"})
    except Exception:
        pass


async def _send_email(
    to: str,
    job_type: str,
    summary: str,
    download_url: Optional[str],
) -> None:
    try:
        from config import settings
        if not settings.RESEND_API_KEY:
            return

        import httpx
        job_labels = {
            "cv": "CV Generation",
            "letter": "Cover Letter",
            "cron": "Scheduled Task",
            "coordinator": "Multi-step Task",
        }
        label = job_labels.get(job_type, job_type.title())

        body = f"<p>Your {label} is ready.</p>"
        if summary:
            body += f"<p>{summary[:300]}</p>"
        if download_url:
            body += f'<p><a href="{download_url}">Download your result</a></p>'
        body += "<p>— Delka by DelkaAI</p>"

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.RESEND_FROM_EMAIL,
                    "to": [to],
                    "subject": f"✓ Your {label} is ready — DelkaAI",
                    "html": body,
                },
            )
    except Exception:
        pass


def build_completion_sse_event(job_type: str, summary: str) -> str:
    """
    Returns an SSE event to push into an active stream to notify the user
    inline that a background task completed.
    """
    import json
    return f"data: {json.dumps({'type': 'job_complete', 'job_type': job_type, 'summary': summary})}\n\n"
