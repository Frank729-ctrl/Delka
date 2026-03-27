"""Tests for security/ip_blocker.py — covers all block/unblock/list branches."""
import pytest
from datetime import datetime, timedelta
from security.ip_blocker import is_ip_blocked, block_ip, unblock_ip, list_blocked
from models.blocked_ip_model import BlockedIP


async def test_unknown_ip_is_not_blocked(test_db):
    """IP with no record returns False."""
    result = await is_ip_blocked("1.2.3.4", test_db)
    assert result is False


async def test_permanent_block_returns_true(test_db):
    """IP blocked with no expiry (permanent) returns True."""
    await block_ip("10.0.0.1", "honeypot", test_db, duration_hours=None)
    result = await is_ip_blocked("10.0.0.1", test_db)
    assert result is True


async def test_active_temporary_block_returns_true(test_db):
    """IP blocked with future expiry returns True."""
    await block_ip("10.0.0.2", "rate_limit", test_db, duration_hours=24)
    result = await is_ip_blocked("10.0.0.2", test_db)
    assert result is True


async def test_expired_block_returns_false_and_deletes_record(test_db):
    """IP with past expiry returns False and the record is cleaned up."""
    # Manually insert an expired block
    expired = datetime.utcnow() - timedelta(hours=1)
    test_db.add(BlockedIP(ip_address="10.0.0.3", reason="old", expires_at=expired))
    await test_db.commit()

    result = await is_ip_blocked("10.0.0.3", test_db)
    assert result is False

    # Verify the record was deleted
    result2 = await is_ip_blocked("10.0.0.3", test_db)
    assert result2 is False


async def test_unblock_removes_record(test_db):
    """unblock_ip deletes the record and returns True."""
    await block_ip("10.0.0.5", "test", test_db)
    removed = await unblock_ip("10.0.0.5", test_db)
    assert removed is True
    assert await is_ip_blocked("10.0.0.5", test_db) is False


async def test_unblock_nonexistent_returns_false(test_db):
    """unblock_ip on an IP that isn't blocked returns False."""
    result = await unblock_ip("9.9.9.9", test_db)
    assert result is False


async def test_list_blocked_returns_all_active(test_db):
    """list_blocked returns all blocked IPs."""
    await block_ip("11.0.0.1", "reason1", test_db)
    await block_ip("11.0.0.2", "reason2", test_db)
    records = await list_blocked(test_db)
    ips = [r["ip_address"] for r in records]
    assert "11.0.0.1" in ips
    assert "11.0.0.2" in ips


async def test_block_updates_existing_record(test_db):
    """Blocking the same IP twice updates the existing record's reason."""
    await block_ip("10.0.0.9", "reason_old", test_db)
    await block_ip("10.0.0.9", "reason_new", test_db)
    records = await list_blocked(test_db)
    matching = [r for r in records if r["ip_address"] == "10.0.0.9"]
    assert len(matching) == 1
    assert matching[0]["reason"] == "reason_new"
