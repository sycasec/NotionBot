# azzurro

> **Temporary README** — to be replaced with proper documentation.

A Discord bot that can read and write to Notion using natural language, and look up live stock prices. Powered by [llama3.2](https://ollama.com/library/llama3.2) via Ollama, with Notion access handled by the [official Notion MCP server](https://github.com/makenotion/notion-mcp-server).

## Stack

- **Discord** — `discord.py`, responds to DMs and @mentions
- **LLM** — `llama3.2` via `ollama` + `langchain-ollama`
- **Notion** — `@notionhq/notion-mcp-server` (MCP) via `langchain-mcp-adapters`
- **Stocks** — Yahoo Finance (no API key needed)
- **Runtime** — Python 3.14, Node 22 (via mise)

## Setup

### 1. Clone and install dependencies

```bash
python -m venv discord-bot-venv
source discord-bot-venv/bin/activate
pip install discord.py ollama langchain-ollama langchain-mcp-adapters langchain-core notion-client requests python-dotenv mcp
```

Node 22 is managed via mise (`mise install`).

### 2. Pull the Ollama model

```bash
ollama pull llama3.2
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `DISCORD_TOKEN` | [discord.com/developers](https://discord.com/developers/applications) → Bot → Token |
| `NOTION_TOKEN` | [notion.so/my-integrations](https://www.notion.so/my-integrations) → create an integration |
| `OLLAMA_MODEL` | defaults to `llama3.2`, change to `llama3.1` for better tool-calling |

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

Mention the bot or DM it:

```
@bot Check AAPL and if it's down more than 2% today, write a page in Notion called "AAPL Alert" explaining what happened
@bot Create a Notion database called Project Tracker with columns Name, Status, Priority, Notes
@bot Search Notion for meeting notes
@bot What's the current price of TSLA?
```

## Project structure

```
azzurro/
├── bot.py                  # Discord client
├── agent.py                # LangChain tool-calling loop
├── tools/
│   └── finance_tools.py    # Stock price lookup (Yahoo Finance)
├── .env.example
└── mise.toml               # Node 22
```
