"""Smoke tests -- run without any network or Telegram access.

These verify that the package imports cleanly, the expected tools are
registered on the FastMCP server, and the helper functions behave sensibly.
No Telegram credentials or session file are required to run these.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Package import
# ---------------------------------------------------------------------------


def test_package_imports():
    """The telegram_mcp package and its modules must import without errors."""
    import telegram_mcp  # noqa: F401
    from telegram_mcp import client, login, server  # noqa: F401

    assert hasattr(telegram_mcp, "__version__")
    assert telegram_mcp.__version__ == "0.1.0"


# ---------------------------------------------------------------------------
# Config handling
# ---------------------------------------------------------------------------


def test_default_session_path_is_cross_platform():
    """Default session path should resolve under the user home directory."""
    from telegram_mcp.client import _default_session_path

    path = _default_session_path()
    assert isinstance(path, Path)
    assert path.name == "telegram.session"
    assert path.parent.name == "telegram-mcp"
    # Must be under the user's home directory
    assert str(Path.home()) in str(path)


def test_get_config_raises_without_credentials(monkeypatch):
    """get_config must fail clearly when credentials are missing."""
    from telegram_mcp.client import get_config

    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)

    with pytest.raises(RuntimeError, match="Missing Telegram credentials"):
        get_config()


def test_get_config_validates_api_id_is_integer(monkeypatch):
    """get_config must reject non-integer TG_API_ID values."""
    from telegram_mcp.client import get_config

    monkeypatch.setenv("TG_API_ID", "not-a-number")
    monkeypatch.setenv("TG_API_HASH", "abc123")

    with pytest.raises(RuntimeError, match="must be an integer"):
        get_config()


def test_get_config_respects_custom_session_path(monkeypatch, tmp_path):
    """TG_SESSION_PATH env var should override the default session location."""
    from telegram_mcp.client import get_config

    custom_path = tmp_path / "custom.session"
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "abc123")
    monkeypatch.setenv("TG_SESSION_PATH", str(custom_path))

    config = get_config()
    assert config["api_id"] == 12345
    assert config["api_hash"] == "abc123"
    assert config["session_path"] == custom_path


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------


async def test_server_has_expected_tools():
    """All 5 MVP tools must be registered on the FastMCP instance.

    fastmcp exposes `list_tools()` as an async method returning FunctionTool
    objects, each with a `.name` attribute.
    """
    from telegram_mcp.server import mcp

    expected = {"get_me", "list_chats", "get_chat_info", "get_messages", "search_messages"}

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}

    assert expected.issubset(tool_names), (
        f"Missing tools. Expected {expected}, found {tool_names}"
    )


# ---------------------------------------------------------------------------
# Helper functions (pure, no network)
# ---------------------------------------------------------------------------


def test_err_returns_valid_json():
    """_err() must return a valid JSON string with an 'error' key."""
    from telegram_mcp.server import _err

    out = _err("Something broke", code=42)
    data = json.loads(out)
    assert data["error"] == "Something broke"
    assert data["code"] == 42


def test_json_helper_handles_datetimes():
    """_json() should serialize datetimes via str() fallback."""
    from datetime import datetime

    from telegram_mcp.server import _json

    payload = {"when": datetime(2026, 4, 8, 22, 0, 0)}
    out = _json(payload)
    data = json.loads(out)
    assert "2026-04-08" in data["when"]


def test_parse_offset_date():
    """_parse_offset_date should parse ISO strings and return None on bad input."""
    from datetime import datetime

    from telegram_mcp.server import _parse_offset_date

    assert _parse_offset_date(None) is None
    assert _parse_offset_date("") is None
    assert _parse_offset_date("not a date") is None

    parsed = _parse_offset_date("2026-04-08")
    assert isinstance(parsed, datetime)
    assert parsed.year == 2026
    assert parsed.month == 4
    assert parsed.day == 8


# ---------------------------------------------------------------------------
# File safety checks
# ---------------------------------------------------------------------------


def test_env_example_exists_and_has_placeholders():
    """.env.example must exist and NOT contain real-looking values."""
    root = Path(__file__).parent.parent
    env_example = root / ".env.example"
    assert env_example.exists(), "Missing .env.example"

    content = env_example.read_text()
    # Require placeholder patterns rather than real values
    assert "your_api_hash_here" in content
    assert "TG_API_ID=" in content
    assert "TG_API_HASH=" in content
    assert "TG_PHONE=" in content


def test_gitignore_excludes_secrets():
    """.gitignore must exclude .env and session files."""
    root = Path(__file__).parent.parent
    gitignore = root / ".gitignore"
    assert gitignore.exists(), "Missing .gitignore"

    content = gitignore.read_text()
    assert ".env" in content
    assert "*.session" in content
