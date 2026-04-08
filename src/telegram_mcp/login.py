"""Interactive login script -- run once to create the session file.

Run with:
    python -m telegram_mcp.login

Prompts for phone number (if not in .env), Telegram verification code,
and 2FA password if enabled. Creates a .session file at the configured path
that the MCP server can then use without any further interaction.

This script MUST be run before using the MCP server for the first time,
because the server runs over stdio and cannot prompt for a code interactively.
"""

from __future__ import annotations

import asyncio
import os
import sys
from getpass import getpass

from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from .client import ensure_session_dir, get_config, get_client


async def _run_login() -> int:
    """Interactive login flow. Returns process exit code."""
    try:
        config = get_config()
    except RuntimeError as exc:
        print(f"\n[ERROR] {exc}\n", file=sys.stderr)
        return 1

    session_path = config["session_path"]
    ensure_session_dir(session_path)

    print("Telegram MCP -- Login")
    print("-" * 40)
    print(f"Session file: {session_path}")
    print()

    client = get_client()
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already logged in as: {me.first_name} (@{me.username or 'no_username'})")
        print("Session is valid. Nothing to do.")
        await client.disconnect()
        return 0

    # Get phone number (env var first, then prompt)
    phone = config["phone"] or input("Phone number (international format, e.g. +41791234567): ").strip()
    if not phone:
        print("[ERROR] Phone number is required.", file=sys.stderr)
        await client.disconnect()
        return 1

    print(f"\nSending login code to {phone}...")
    try:
        await client.send_code_request(phone)
    except Exception as exc:
        print(f"[ERROR] Failed to send code: {exc}", file=sys.stderr)
        await client.disconnect()
        return 1

    # Prompt for the code (Telegram sends it to your Telegram app, not SMS initially)
    code = input("Enter the code you received: ").strip()
    if not code:
        print("[ERROR] Code is required.", file=sys.stderr)
        await client.disconnect()
        return 1

    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        # Account has 2FA enabled
        print("\nTwo-factor authentication is enabled on this account.")
        password = getpass("2FA password: ")
        try:
            await client.sign_in(password=password)
        except PasswordHashInvalidError:
            print("[ERROR] Incorrect 2FA password.", file=sys.stderr)
            await client.disconnect()
            return 1
    except PhoneCodeInvalidError:
        print("[ERROR] Invalid verification code.", file=sys.stderr)
        await client.disconnect()
        return 1
    except Exception as exc:
        print(f"[ERROR] Sign-in failed: {exc}", file=sys.stderr)
        await client.disconnect()
        return 1

    me = await client.get_me()
    print()
    print("Login successful!")
    print(f"  User: {me.first_name} {me.last_name or ''}".rstrip())
    print(f"  Username: @{me.username or 'no_username'}")
    print(f"  ID: {me.id}")
    print(f"  Session saved: {session_path}")
    print()
    print("You can now use the MCP server. Add it to your Claude Code settings.json")
    print("and restart Claude Code. See README.md for details.")

    await client.disconnect()

    # Best-effort: restrict session file permissions on Unix-like systems.
    # On Windows this is effectively a no-op, which is fine.
    try:
        os.chmod(session_path, 0o600)
    except (OSError, NotImplementedError):
        pass

    return 0


def main() -> None:
    """Entry point for the `telegram-mcp-login` script."""
    try:
        exit_code = asyncio.run(_run_login())
    except KeyboardInterrupt:
        print("\nCancelled.")
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
