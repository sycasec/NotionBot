# azzurro

A Discord bot that interacts with Notion, looks up stock prices, checks the weather, searches the web, and more all via natural language. Supports dual LLM providers: local inference with [Ollama](https://ollama.com) or cloud via [Groq](https://groq.com).

## Stack

- **Discord** : `discord.py` with slash commands, DMs, and @mentions
- **LLM** : `qwen2.5:14b` via Ollama (default) or `llama-3.3-70b-versatile` via Groq
- **Notion** : `notion-client` (simple tools) + `@notionhq/notion-mcp-server` (MCP, Groq only)
- **Tools** : stock prices (Yahoo Finance), weather (Open-Meteo), web search (DuckDuckGo), date math
- **State** : per-user conversation history and timezone preferences (SQLite)
- **Runtime** : Python 3.14, Node 22 (via mise)

## Setup

### 1. Clone and install dependencies

```bash
python -m venv discord-bot-venv
source discord-bot-venv/bin/activate
pip install discord.py langchain-core langchain-ollama langchain-groq langchain-mcp-adapters \
    notion-client requests python-dotenv mcp httpx
```

Node 22 is managed via mise (`mise install`).

### 2. Pull the Ollama model

```bash
ollama pull qwen2.5:14b
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | [Discord Developer Portal](https://discord.com/developers/applications) → Bot → Token |
| `NOTION_TOKEN` | [Notion Integrations](https://www.notion.so/my-integrations) → create an integration |
| `NOTION_PARENT_PAGE_ID` | UUID of the Notion page to create sub-pages under |
| `OLLAMA_MODEL` | Ollama model name (default: `qwen2.5:14b`) |
| `GROQ_API_KEY` | Groq API key (only needed if using the Groq provider) |
| `LLM_PROVIDER` | `ollama` (default) or `groq` |
| `LOG_LEVEL` | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

For Notion: after creating the integration, open any page in Notion and go to **Share → Connections → your integration** to grant access.

### 4. Discord bot settings

In the Developer Portal:
- **Bot → Privileged Gateway Intents** → enable **Message Content Intent**
- **OAuth2 → URL Generator** → scope `bot`, permissions: Read Messages, Send Messages, Read Message History
- Use the generated URL to invite the bot to your server

### 5. Run

```bash
source discord-bot-venv/bin/activate
python bot.py
```

## Usage

### Slash commands

| Command | Description |
|---|---|
| `/ask <message>` | Ask the assistant a question or give it a task |
| `/clear` | Clear your conversation history |
| `/timezone <tz>` | Set your timezone (e.g. `Asia/Manila`, `America/New_York`) |

### Text commands

Mention the bot or DM it directly:

```
@bot Check AAPL and if it's down more than 2%, create a Notion page called "AAPL Alert"
@bot What's the weather in Tokyo?
@bot Search the web for latest Python 3.14 features
@bot What date is 30 days from now?
@bot Search Notion for meeting notes
clear              (resets conversation history)
set timezone US/Eastern
```

## Project structure

```
azzurro/
├── bot.py                      # Discord client, slash commands, event handlers
├── agent.py                    # Agent loop, prompt building, fake-action detection
├── llm.py                      # LLM provider abstraction (Ollama / Groq)
├── tool_utils.py               # Tool invocation, UUID fixing, error detection
├── config.py                   # Centralized config (frozen dataclass)
├── user_state.py               # Per-user SQLite state (history, timezone)
├── log_config.py               # Logging setup with custom formatter
├── system_prompt.md            # Externalized system prompt template
├── tools/
│   ├── notion_tools.py         # Notion: create page, search, append content
│   ├── finance_tools.py        # Stock price lookup (Yahoo Finance)
│   ├── weather_tools.py        # Weather conditions (Open-Meteo)
│   ├── search_tools.py         # Web search (DuckDuckGo)
│   └── date_tools.py           # Date arithmetic (e.g. "today + 30 days")
├── mise.toml                   # Node 22 version management
└── .env                        # Environment variables (not committed)
```
