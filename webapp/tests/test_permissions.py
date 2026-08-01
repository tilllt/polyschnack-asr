"""Tests für die zentrale Zugriffskontrolle (Task A1)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import Recording
from app.permissions import ensure, ensure_access, get_access_level, require_level


def _rec(user_id=None):
    return Recording(id=1, uid="x", original_name="a", stored_path="p", user_id=user_id)


def test_owner_gets_full():
    assert get_access_level(None, _rec(user_id=5), uid=5) == "full"


def test_legacy_public_is_read_for_anyone():
    assert get_access_level(None, _rec(user_id=None), uid=None) == "read"


def test_no_access():
    assert get_access_level(None, _rec(user_id=5), uid=99) is None


def test_require_level_read_allows_owner_and_full():
    rec = _rec(user_id=5)
    assert require_level("read", get_access_level(None, rec, 5))
    assert require_level("write", get_access_level(None, rec, 5))  # owner = full
    assert require_level("full", get_access_level(None, rec, 5))


def test_require_level_raises_for_none():
    with pytest.raises(HTTPException) as ei:
        ensure("write", None)
    assert ei.value.status_code == 403


def test_level_ordering():
    assert require_level("read", "write") is True  # write erfüllt read
    assert require_level("write", "read") is False
    assert require_level("full", "write") is False


def test_ensure_access_owner_ok_and_foreign_forbidden():
    rec = _rec(user_id=5)
    ensure_access(None, rec, 5, "full")  # kein Raise
    with pytest.raises(HTTPException):
        ensure_access(None, rec, 99, "read")


def test_ensure_read_ok_but_write_raises():
    rec = _rec(user_id=None)  # legacy public → read
    ensure_access(None, rec, None, "read")
    with pytest.raises(HTTPException):
        ensure_access(None, rec, None, "write")
