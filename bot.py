import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()

from log_config import setup_logging  # noqa: E402

setup_logging()

import discord  # noqa: E402

from agent import init_agent, run_agent  # noqa: E402
from user_state import clear_history, set_timezone  # noqa: E402

log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    assert bot.user is not None
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Initializing agent tools...")
    await init_agent()
    log.info("Ready. Mention me or DM me to get started.")


def _strip_mention(message: discord.Message) -> str:
    """Extract message content, stripping bot mentions."""
    content = message.content
    log.debug("Raw message content: %r", content)
    is_mentioned = bot.user in message.mentions
    if is_mentioned and bot.user is not None:
        content = re.sub(rf"<@!?{bot.user.id}>", "", content).strip()
    log.debug("Stripped content: %r", content)
    return content


async def _send_response(message: discord.Message, response: str) -> None:
    """Reply to a message, chunking if over Discord's 2000-char limit."""
    if len(response) <= 2000:
        await message.reply(response)
        return
    chunks = [response[i : i + 1990] for i in range(0, len(response), 1990)]
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(chunk)
        else:
            await message.channel.send(chunk)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_dm or bot.user in message.mentions):
        return

    content = _strip_mention(message)
    if not content:
        await message.reply(
            "Hey! Mention me with a request, like:\n"
            "• `@Burger Check AAPL stock and if it's down 5%, write a page in Notion about it`\n"
            "• `@Burger Create a Notion table with columns Task, Status, Notes`\n"
            "• `@Burger Search Notion for meeting notes`"
        )
        return

    user_id = str(message.author.id)

    if content.lower() in ("forget", "clear", "clear history", "reset"):
        clear_history(user_id)
        await message.reply("Conversation history cleared.")
        return

    if content.lower().startswith("set timezone "):
        tz_name = content[len("set timezone "):].strip()
        err = set_timezone(user_id, tz_name)
        if err:
            await message.reply(err)
        else:
            await message.reply(f"Timezone set to **{tz_name}**.")
        return

    log.info("Request from %s (ID: %s): %s", message.author, message.author.id, content[:200])

    async with message.channel.typing():
        try:
            response = await run_agent(content, user_id=user_id)
        except Exception:
            log.exception("Agent error for message from %s", message.author)
            response = "Something went wrong while processing your request."

    await _send_response(message, response)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    bot.run(token)
