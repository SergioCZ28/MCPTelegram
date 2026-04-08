"""Telethon client singleton and configuration.

Exposes a single `TelegramClient` instance shared across all MCP tool calls.
Handles:

- Loading config from environment variables (via python-dotenv)
- Resolving the session file path (default: ~/.config/telegram-mcp/)
- Lazy connection and reconnection on disconnect
- Clean errors when the session file is missing (points user to `login`)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load .env from the nearest parent directory (walks up from cwd).
# Safe to call multiple times; dotenv only sets vars that aren't already set.
load_dotenv()


def _default_session_path() -> Path:
    """Return the cross-platform default session file path.

    Resolves to `~/.config/telegram-mcp/telegram.session`, which works
    on Linux, macOS, and Windows (where `Path.home()` returns `C:/Users/<name>`).
    """
    return Path.home() / ".config" / "telegram-mcp" / "telegram.session"


def get_config() -> dict:
    """Read required configuration from environment variables.

    Returns:
        Dict with keys: api_id (int), api_hash (str), phone (str|None),
        session_path (Path).

    Raises:
        RuntimeError: If TG_API_ID or TG_API_HASH are missing or invalid.
    """
    api_id_raw = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    phone = os.getenv("TG_PHONE")  # optional at server-run time
    session_path_raw = os.getenv("TG_SESSION_PATH")

    if not api_id_raw or not api_hash:
        raise RuntimeError(
            "Missing Telegram credentials. Set TG_API_ID and TG_API_HASH in your "
            ".env file. Get them from https://my.telegram.org. "
            "See .env.example for the full template."
        )

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError(
            f"TG_API_ID must be an integer, got: {api_id_raw!r}"
        ) from exc

    session_path = Path(session_path_raw).expanduser() if session_path_raw else _default_session_path()

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "session_path": session_path,
    }


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_client: TelegramClient | None = None


def ensure_session_dir(session_path: Path) -> None:
    """Create the parent directory for the session file if missing."""
    session_path.parent.mkdir(parents=True, exist_ok=True)


def get_client() -> TelegramClient:
    """Return the singleton TelegramClient, creating it on first call.

    Does NOT connect to Telegram -- that happens lazily via `ensure_connected`.
    Creates the parent directory for the session file if needed.

    Returns:
        The shared TelegramClient instance.

    Raises:
        RuntimeError: If credentials are missing or invalid.
    """
    global _client
    if _client is not None:
        return _client

    config = get_config()
    ensure_session_dir(config["session_path"])

    # Telethon accepts a path WITHOUT the `.session` extension, which it
    # appends itself. Pass the full path with extension to keep things explicit.
    _client = TelegramClient(
        str(config["session_path"]),
        config["api_id"],
        config["api_hash"],
    )
    return _client


async def ensure_connected(client: TelegramClient) -> None:
    """Connect to Telegram if not already connected.

    Idempotent -- safe to call at the start of every tool invocation.
    Telethon may disconnect on idle, so tools should call this before any API work.

    Raises:
        RuntimeError: If the session file has no valid auth (user must run login).
    """
    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        config = get_config()
        raise RuntimeError(
            f"No valid session at {config['session_path']}. "
            "Run `python -m telegram_mcp.login` to authenticate first."
        )


async def disconnect_client() -> None:
    """Disconnect the singleton client, if any. Used for clean shutdown."""
    global _client
    if _client is not None and _client.is_connected():
        await _client.disconnect()
