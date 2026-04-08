"""Telegram MCP server.

Exposes 5 read-only Telegram tools to Claude Code via the Model Context Protocol:

    - get_me              Show current user + session health
    - list_chats          List recent dialogs (groups, DMs, channels)
    - get_chat_info       Metadata for a specific chat
    - get_messages        Message history from a chat
    - search_messages     Keyword search (per-chat or global)

Run with:
    python -m telegram_mcp.server

Requires an existing Telegram session file (run `python -m telegram_mcp.login`
first). Credentials are read from `.env` (see `.env.example`).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from telethon.errors import FloodWaitError
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import Channel, Chat, Message, User

from .client import ensure_connected, get_client

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("telegram")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json(payload: Any) -> str:
    """Serialize a dict/list to a JSON string for tool returns.

    Uses `default=str` so datetimes and other non-JSON-native types become
    their string representation instead of raising.
    """
    return json.dumps(payload, indent=2, default=str, ensure_ascii=False)


def _err(message: str, **extra: Any) -> str:
    """Return a structured error as a JSON string."""
    payload: dict[str, Any] = {"error": message}
    payload.update(extra)
    return _json(payload)


def _dialog_type(entity: Any) -> str:
    """Classify a dialog entity as 'user', 'group', 'supergroup', 'channel', or 'unknown'."""
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, Channel):
        if entity.megagroup:
            return "supergroup"
        return "channel"
    return "unknown"


def _dialog_summary(dialog: Dialog) -> dict[str, Any]:
    """Flatten a Telethon Dialog into a simple dict for JSON output."""
    entity = dialog.entity
    return {
        "id": dialog.id,
        "title": dialog.name or "",
        "type": _dialog_type(entity),
        "username": getattr(entity, "username", None),
        "unread_count": dialog.unread_count,
        "last_message_date": dialog.date.isoformat() if dialog.date else None,
        "is_pinned": dialog.pinned,
        "is_archived": dialog.archived,
    }


def _message_summary(msg: Message) -> dict[str, Any]:
    """Flatten a Telethon Message into a simple dict for JSON output."""
    sender_name = None
    sender_id = None
    if msg.sender:
        sender_id = msg.sender_id
        if isinstance(msg.sender, User):
            sender_name = (
                (msg.sender.first_name or "")
                + ((" " + msg.sender.last_name) if msg.sender.last_name else "")
            ).strip() or msg.sender.username
        else:
            sender_name = getattr(msg.sender, "title", None)

    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "text": msg.message or "",
        "has_media": bool(msg.media),
        "reply_to_msg_id": msg.reply_to_msg_id,
    }


def _parse_offset_date(offset_date: str | None) -> datetime | None:
    """Parse an ISO-format date string, or return None if blank/invalid.

    Accepts things like '2026-04-01' or '2026-04-01T12:00:00'.
    Returns None on any parse error (caller can fall back to no offset).
    """
    if not offset_date:
        return None
    try:
        return datetime.fromisoformat(offset_date)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_me() -> str:
    """Return the currently logged-in Telegram user and verify session health.

    Use this as a connectivity/sanity check before calling other tools.
    Returns the user's id, first/last name, username, and phone.
    """
    try:
        client = get_client()
        await ensure_connected(client)
        me = await client.get_me()
    except RuntimeError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Unexpected error in get_me: {exc}")

    return _json(
        {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": me.phone,
            "is_bot": me.bot,
        }
    )


@mcp.tool()
async def list_chats(limit: int = 20, include_archived: bool = False) -> str:
    """List the user's recent dialogs (chats).

    Returns recent conversations sorted by last activity. Use this to discover
    chat IDs, titles, and usernames before calling get_messages or search_messages.

    Args:
        limit: Maximum number of chats to return (default 20, max 200).
        include_archived: If True, include archived chats (default False).

    Returns:
        JSON list of dicts with id, title, type, username, unread_count,
        last_message_date, is_pinned, is_archived.
    """
    if limit < 1:
        return _err("limit must be >= 1")
    if limit > 200:
        limit = 200

    try:
        client = get_client()
        await ensure_connected(client)

        dialogs: list[dict[str, Any]] = []
        async for dialog in client.iter_dialogs(limit=limit, archived=None if include_archived else False):
            dialogs.append(_dialog_summary(dialog))
    except RuntimeError as exc:
        return _err(str(exc))
    except FloodWaitError as exc:
        return _err(f"Telegram rate limit, wait {exc.seconds}s", seconds=exc.seconds)
    except Exception as exc:
        return _err(f"Unexpected error in list_chats: {exc}")

    return _json({"count": len(dialogs), "chats": dialogs})


@mcp.tool()
async def get_chat_info(chat: str) -> str:
    """Get metadata for a specific chat.

    Args:
        chat: Chat identifier -- username (e.g. '@esn_basel'), chat ID as a
              string (e.g. '-1001234567890'), or a title/partial title (will
              be resolved by searching recent dialogs).

    Returns:
        JSON dict with id, title, type, username, member_count (if available),
        description (if available), and is_verified/is_scam flags.
    """
    try:
        client = get_client()
        await ensure_connected(client)
        entity = await _resolve_chat(client, chat)
    except RuntimeError as exc:
        return _err(str(exc))
    except FloodWaitError as exc:
        return _err(f"Telegram rate limit, wait {exc.seconds}s", seconds=exc.seconds)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Unexpected error in get_chat_info: {exc}")

    info: dict[str, Any] = {
        "id": entity.id,
        "type": _dialog_type(entity),
        "title": getattr(entity, "title", None) or getattr(entity, "first_name", None),
        "username": getattr(entity, "username", None),
    }

    if isinstance(entity, User):
        info.update(
            {
                "first_name": entity.first_name,
                "last_name": entity.last_name,
                "phone": entity.phone,
                "is_bot": entity.bot,
            }
        )
    elif isinstance(entity, Channel):
        info.update(
            {
                "participants_count": getattr(entity, "participants_count", None),
                "is_broadcast": entity.broadcast,
                "is_megagroup": entity.megagroup,
                "is_verified": entity.verified,
                "is_scam": entity.scam,
            }
        )
    elif isinstance(entity, Chat):
        info.update(
            {
                "participants_count": getattr(entity, "participants_count", None),
            }
        )

    return _json(info)


@mcp.tool()
async def get_messages(chat: str, limit: int = 50, offset_date: str | None = None) -> str:
    """Read recent messages from a chat.

    Args:
        chat: Chat identifier (username, ID, or title/partial title).
        limit: Max number of messages to return (default 50, max 500).
        offset_date: Optional ISO date string (YYYY-MM-DD or with time).
                     Only messages BEFORE this date are returned. If omitted,
                     returns the most recent messages.

    Returns:
        JSON with chat info and a list of messages (id, date, sender, text,
        has_media, reply_to_msg_id). Newest first.
    """
    if limit < 1:
        return _err("limit must be >= 1")
    if limit > 500:
        limit = 500

    parsed_offset = _parse_offset_date(offset_date)

    try:
        client = get_client()
        await ensure_connected(client)
        entity = await _resolve_chat(client, chat)

        messages: list[dict[str, Any]] = []
        async for msg in client.iter_messages(entity, limit=limit, offset_date=parsed_offset):
            if not isinstance(msg, Message):
                continue
            messages.append(_message_summary(msg))
    except RuntimeError as exc:
        return _err(str(exc))
    except FloodWaitError as exc:
        return _err(f"Telegram rate limit, wait {exc.seconds}s", seconds=exc.seconds)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Unexpected error in get_messages: {exc}")

    return _json(
        {
            "chat_id": entity.id,
            "chat_title": getattr(entity, "title", None) or getattr(entity, "first_name", None),
            "count": len(messages),
            "messages": messages,
        }
    )


@mcp.tool()
async def search_messages(query: str, chat: str | None = None, limit: int = 20) -> str:
    """Search messages by keyword, either in a specific chat or globally.

    Args:
        query: Keyword or phrase to search for.
        chat: Optional chat identifier to restrict the search. If omitted,
              searches across ALL your dialogs (slower, may rate-limit).
        limit: Max number of results (default 20, max 200).

    Returns:
        JSON with the query, match count, and a list of messages
        (id, chat_id, chat_title, date, sender, text).
    """
    if not query or not query.strip():
        return _err("query must not be empty")
    if limit < 1:
        return _err("limit must be >= 1")
    if limit > 200:
        limit = 200

    try:
        client = get_client()
        await ensure_connected(client)

        results: list[dict[str, Any]] = []

        if chat:
            entity = await _resolve_chat(client, chat)
            async for msg in client.iter_messages(entity, limit=limit, search=query):
                if not isinstance(msg, Message):
                    continue
                summary = _message_summary(msg)
                summary["chat_id"] = entity.id
                summary["chat_title"] = getattr(entity, "title", None) or getattr(entity, "first_name", None)
                results.append(summary)
        else:
            # Global search (no entity scope).
            async for msg in client.iter_messages(None, limit=limit, search=query):
                if not isinstance(msg, Message):
                    continue
                summary = _message_summary(msg)
                # Resolve the chat for each result
                chat_entity = await msg.get_chat()
                summary["chat_id"] = getattr(chat_entity, "id", None)
                summary["chat_title"] = (
                    getattr(chat_entity, "title", None)
                    or getattr(chat_entity, "first_name", None)
                )
                results.append(summary)
    except RuntimeError as exc:
        return _err(str(exc))
    except FloodWaitError as exc:
        return _err(f"Telegram rate limit, wait {exc.seconds}s", seconds=exc.seconds)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Unexpected error in search_messages: {exc}")

    return _json({"query": query, "count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Chat resolution
# ---------------------------------------------------------------------------


async def _resolve_chat(client, chat: str):
    """Resolve a user-provided chat identifier to a Telethon entity.

    Tries, in order:
        1. If `chat` parses as an int, use it as a chat ID directly.
        2. Let Telethon resolve usernames (with or without @) and phone numbers.
        3. Fall back to fuzzy title matching over recent dialogs.

    Raises:
        ValueError: If no matching chat is found.
    """
    chat = chat.strip()

    # 1. Try as an integer ID
    try:
        chat_id = int(chat)
        return await client.get_entity(chat_id)
    except ValueError:
        pass
    except Exception:
        # fall through to other strategies
        pass

    # 2. Try Telethon's direct resolution (usernames, phones, t.me links)
    try:
        return await client.get_entity(chat)
    except Exception:
        pass

    # 3. Fuzzy title match against recent dialogs
    lowered = chat.lower().lstrip("@")
    best_match = None
    async for dialog in client.iter_dialogs(limit=200):
        title = (dialog.name or "").lower()
        username = (getattr(dialog.entity, "username", None) or "").lower()
        if lowered == title or lowered == username:
            return dialog.entity
        if lowered in title or lowered in username:
            # prefer exact-start matches
            if best_match is None or title.startswith(lowered):
                best_match = dialog.entity

    if best_match is not None:
        return best_match

    raise ValueError(
        f"Could not resolve chat: {chat!r}. "
        "Try a username (@name), a numeric ID, or call list_chats() to see titles."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio (for Claude Code to launch)."""
    mcp.run()


if __name__ == "__main__":
    main()
