import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()

from log_config import setup_logging  # noqa: E402

setup_logging()

import discord  # noqa: E402
from discord import app_commands  # noqa: E402

from agent import init_agent, run_agent  # noqa: E402
from user_state import clear_history, set_timezone  # noqa: E402

log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_mention(message: discord.Message) -> str:
    """Extract message content, stripping bot mentions."""
    content = message.content
    log.debug("Raw message content: %r", content)
    is_mentioned = bot.user in message.mentions
    if is_mentioned and bot.user is not None:
        content = re.sub(rf"<@!?{bot.user.id}>", "", content).strip()
    log.debug("Stripped content: %r", content)
    return content


async def _send_chunks(send_fn, response: str) -> None:
    """Send a response, splitting into 2000-char chunks if needed."""
    if len(response) <= 2000:
        await send_fn(response)
        return
    chunks = [response[i : i + 1990] for i in range(0, len(response), 1990)]
    for chunk in chunks:
        await send_fn(chunk)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@tree.command(name="ask", description="Ask the assistant a question or give it a task")
@app_commands.describe(message="Your message to the assistant")
async def slash_ask(interaction: discord.Interaction, message: str) -> None:
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)
    log.info("Slash /ask from %s: %s", interaction.user, message[:200])
    try:
        response = await run_agent(message, user_id=user_id)
    except TimeoutError:
        log.warning("Agent timed out for slash from %s", interaction.user)
        response = "The request took too long. Please try a simpler question or try again later."
    except ConnectionError as exc:
        log.warning("Connection error in slash agent for %s: %s", interaction.user, exc)
        response = "I couldn't reach one of my services. Please try again in a moment."
    except Exception as exc:
        log.exception("Agent error for slash command from %s", interaction.user)
        error_type = type(exc).__name__
        response = f"Something went wrong (`{error_type}`). Please try again or rephrase your request."
    await _send_chunks(interaction.followup.send, response)


@tree.command(name="clear", description="Clear your conversation history")
async def slash_clear(interaction: discord.Interaction) -> None:
    user_id = str(interaction.user.id)
    clear_history(user_id)
    log.info("Slash /clear from %s", interaction.user)
    await interaction.response.send_message("Conversation history cleared.", ephemeral=True)


@tree.command(name="timezone", description="Set your timezone")
@app_commands.describe(tz_name="IANA timezone name, e.g. 'Asia/Manila', 'America/New_York'")
async def slash_timezone(interaction: discord.Interaction, tz_name: str) -> None:
    user_id = str(interaction.user.id)
    err = set_timezone(user_id, tz_name)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
    else:
        log.info("Slash /timezone from %s: %s", interaction.user, tz_name)
        await interaction.response.send_message(
            f"Timezone set to **{tz_name}**.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    assert bot.user is not None
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Syncing slash commands...")
    await tree.sync()
    log.info("Initializing agent tools...")
    await init_agent()
    log.info("Ready. Mention me or DM me to get started.")


@bot.event
async def _handle_text_command(message: discord.Message, content: str) -> bool:
    """Handle built-in text commands. Returns True if a command was handled."""
    user_id = str(message.author.id)
    lower = content.lower()

    if lower in ("forget", "clear", "clear history", "reset"):
        clear_history(user_id)
        await message.reply("Conversation history cleared.")
        return True

    if lower.startswith("set timezone "):
        tz_name = content[len("set timezone "):].strip()
        err = set_timezone(user_id, tz_name)
        await message.reply(err if err else f"Timezone set to **{tz_name}**.")
        return True

    return False


async def _run_and_reply(message: discord.Message, content: str) -> None:
    """Run the agent and send the response."""
    user_id = str(message.author.id)
    log.info("Request from %s (ID: %s): %s", message.author, message.author.id, content[:200])

    async with message.channel.typing():
        try:
            response = await run_agent(content, user_id=user_id)
        except TimeoutError:
            log.warning("Agent timed out for %s", message.author)
            response = "The request took too long. Please try a simpler question or try again later."
        except ConnectionError as exc:
            log.warning("Connection error in agent for %s: %s", message.author, exc)
            response = "I couldn't reach one of my services. Please try again in a moment."
        except Exception as exc:
            log.exception("Agent error for message from %s", message.author)
            error_type = type(exc).__name__
            response = f"Something went wrong (`{error_type}`). Please try again or rephrase your request."

    if len(response) <= 2000:
        await message.reply(response)
    else:
        chunks = [response[i : i + 1990] for i in range(0, len(response), 1990)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_dm or bot.user in message.mentions):
        return

    content = _strip_mention(message)
    if not content:
        await message.reply(
            "Hey! Mention me with a request, or use these commands:\n"
            "\u2022 `/ask` \u2014 ask me anything\n"
            "\u2022 `/clear` \u2014 clear your conversation history\n"
            "\u2022 `/timezone` \u2014 set your timezone\n"
            "Or just mention me with your request!"
        )
        return

    if not await _handle_text_command(message, content):
        await _run_and_reply(message, content)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    bot.run(token)
