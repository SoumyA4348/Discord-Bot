import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.database import init_db

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

COGS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.translator",
    "cogs.utility",
    "cogs.fake_nuke",
    "cogs.giveaway",
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True          # required for member-lookup and on_member_join

OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID", "").strip().isdigit() else None

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, owner_id=OWNER_ID)


@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="the server | !help"
        )
    )


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    """Global fallback handler — cog-level handlers take priority."""
    if hasattr(ctx.command, "on_error"):
        return
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("❌ This command cannot be used in DMs.")
        return
    if isinstance(error, commands.BotMissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await ctx.send(f"❌ I am missing the following permission(s): **{perms}**")
        return
    log.error("Unhandled command error in %s: %s", ctx.command, error, exc_info=error)


async def main() -> None:
    async with bot:
        await init_db()
        log.info("Database ready.")
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                log.info("Loaded: %s", cog)
            except Exception as exc:
                log.error("Failed to load %s: %s", cog, exc, exc_info=True)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
