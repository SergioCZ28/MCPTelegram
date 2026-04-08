# Telegram MCP

Read your Telegram chats directly from Claude Code.

A lean [Model Context Protocol](https://modelcontextprotocol.io) server that exposes your Telegram account to Claude as a set of read-only tools. Uses [Telethon](https://github.com/LonamiWebs/Telethon) under the hood, so it has full access to your DMs, groups, and channels (not just bot messages).

> **Why another Telegram MCP?** This one is small, auditable, read-only by default, and built specifically for Claude Code. No feature bloat, no third-party services, everything runs locally.

## Features

- **5 read-only tools** -- `list_chats`, `get_chat_info`, `get_messages`, `search_messages`, `get_me`
- **User account access** -- read your actual DMs and groups, not just bot chats
- **Secure by default** -- secrets in `.env`, session file outside the repo
- **Async** -- built on `fastmcp` + `telethon`, clean event loop integration
- **MIT licensed** -- do whatever you want with it

## Quick Start

### 1. Get Telegram API credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click **API development tools**
4. Create a new application (any name works)
5. Copy the `api_id` (integer) and `api_hash` (string)

### 2. Clone and install

```bash
git clone https://github.com/SergioCZ28/MCPTelegram.git
cd MCPTelegram

# Create a conda env (or venv)
conda create -n mcp_telegram python=3.11 -y
conda activate mcp_telegram

# Install
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` with your real `TG_API_ID`, `TG_API_HASH`, and `TG_PHONE` (international format, e.g. `+41791234567`).

### 4. Authenticate (one time)

```bash
python -m telegram_mcp.login
```

You'll be prompted for the verification code Telegram sends you. If you have 2FA enabled, you'll also be asked for your password. After this completes, a session file is created at `~/.config/telegram-mcp/telegram.session`.

### 5. Add to Claude Code

Add this to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "telegram": {
      "command": "python",
      "args": ["-m", "telegram_mcp.server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/MCPTelegram/src"
      }
    }
  }
}
```

Replace `/absolute/path/to/` with the real path where you cloned this repo. On Windows use forward slashes: `C:/Users/you/MCPTelegram/src`.

Restart Claude Code. You should now be able to ask:

> "List my recent Telegram chats"

> "Get the last 10 messages from ESN Basel"

> "Search for 'viewing' in my Telegram"

## Available Tools

| Tool | Description | Parameters |
|------|-------------|-----------|
| `get_me` | Current user info and session health check | none |
| `list_chats` | List recent dialogs (DMs, groups, channels) | `limit`, `include_archived` |
| `get_chat_info` | Details about a specific chat | `chat` (username, ID, or title) |
| `get_messages` | Read message history from a chat | `chat`, `limit`, `offset_date` |
| `search_messages` | Keyword search in a chat or globally | `query`, `chat`, `limit` |

The `chat` parameter accepts usernames (`@esn_basel`), chat IDs (`-1001234567890`), or approximate titles (resolved via `list_chats`).

## Security

**The session file is equivalent to your Telegram password.** Anyone who gets a copy can log in as you without needing your phone or code.

- Session file lives at `~/.config/telegram-mcp/telegram.session` by default (outside the repo)
- `.env` and `*.session` are in `.gitignore`
- The login script sets permissions to 600 on Unix (best effort on Windows)
- This project never sends your data anywhere except Telegram's official API endpoints

**Telegram may flag or restrict accounts for heavy automated use.** This MCP is designed for personal, interactive use via Claude Code -- not for bulk scraping. Use responsibly.

## Roadmap

- [ ] `send_message` tool (with confirmation safeguards)
- [ ] Bot API mode (safer dual-mode like [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp))
- [ ] Media download
- [ ] Rich message formatting (entities, mentions, links preserved)
- [ ] PyPI package

## Why not use [existing project X]?

| Project | Why not |
|---------|---------|
| [chigwell/telegram-mcp](https://github.com/chigwell/telegram-mcp) | Feature-bloated (groups admin, bans, polls), last commit Jan 2025 |
| [chaindead/telegram-mcp](https://github.com/chaindead/telegram-mcp) | Go + TDLib, heavier install, sends via drafts only |
| [sparfenyuk/mcp-telegram](https://github.com/sparfenyuk/mcp-telegram) | Read-only, abandoned |
| [n24q02m/better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | Actively maintained, solid choice -- but single maintainer, new, and more complex than I needed |

This one exists because I wanted something minimal, read-only first, and fully auditable in a single afternoon.

## Development

```bash
# Run tests
pytest tests/

# Lint
ruff check src/

# Run server manually (debug mode)
python -m telegram_mcp.server
```

See [CLAUDE.md](CLAUDE.md) for project architecture, conventions, and guidance for Claude agents working on this codebase.

## License

MIT -- see [LICENSE](LICENSE).

## Credits

Built with:
- [fastmcp](https://github.com/jlowin/fastmcp) by jlowin
- [Telethon](https://github.com/LonamiWebs/Telethon) by LonamiWebs
- The [Model Context Protocol](https://modelcontextprotocol.io) spec by Anthropic
