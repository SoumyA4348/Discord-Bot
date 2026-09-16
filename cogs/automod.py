import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import discord
from discord.ext import commands

from utils import database as db
from utils.helpers import mod_embed

log = logging.getLogger(__name__)

_INVITE_RE = re.compile(
    r"discord(?:\.gg|app\.com/invite|\.com/invite)/[a-zA-Z0-9\-]+", re.IGNORECASE
)

SPAM_MAX = 5      # messages
SPAM_WINDOW = 5   # seconds
SPAM_TIMEOUT = timedelta(minutes=5)


class AutoMod(commands.Cog):
    """Automatic moderation: spam detection, word filter, and invite-link blocking."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # guild_id -> user_id -> list[datetime]
        self._msg_log: Dict[int, Dict[int, List[datetime]]] = defaultdict(
            lambda: defaultdict(list)
        )

    async def _log_to_channel(self, guild: discord.Guild, embed: discord.Embed) -> None:
        cfg = await db.get_config(guild.id)
        ch_id = cfg.get("mod_log_channel")
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        # Staff bypass — anyone who can Manage Messages is exempt from auto-mod
        if (
            isinstance(message.author, discord.Member)
            and message.author.guild_permissions.manage_messages
        ):
            return

        # Skip commands so we don't flag the prefix itself as spam
        prefix = self.bot.command_prefix
        if isinstance(prefix, str) and message.content.startswith(prefix):
            return

        cfg = await db.get_config(message.guild.id)

        if cfg.get("antispam", 1):
            await self._check_spam(message)

        word_filter: List[str] = cfg.get("word_filter", [])
        if word_filter:
            await self._check_words(message, word_filter)

        if cfg.get("antiinvite", 0):
            await self._check_invite(message)

    # ── Spam detection ────────────────────────────────────────────────────────

    async def _check_spam(self, message: discord.Message) -> None:
        now = datetime.now(timezone.utc)
        gid, uid = message.guild.id, message.author.id
        log_entry = self._msg_log[gid][uid]
        log_entry.append(now)

        cutoff = now.timestamp() - SPAM_WINDOW
        self._msg_log[gid][uid] = [t for t in log_entry if t.timestamp() > cutoff]

        if len(self._msg_log[gid][uid]) < SPAM_MAX:
            return

        # Triggered — reset immediately to prevent re-firing
        self._msg_log[gid][uid].clear()

        reason = f"Auto-mod: spam ({SPAM_MAX}+ messages in {SPAM_WINDOW}s)"

        try:
            await message.channel.purge(
                limit=SPAM_MAX * 2, check=lambda m: m.author.id == uid
            )
        except discord.Forbidden:
            pass

        try:
            until = discord.utils.utcnow() + SPAM_TIMEOUT
            await message.author.timeout(until, reason=reason)
            case_num = await db.add_case(
                gid, "timeout", uid, self.bot.user.id, reason
            )
            embed = mod_embed(
                "timeout", message.author, self.bot.user, reason, case_num,
                extra=f"Duration: 5m (auto-spam)",
            )
            await self._log_to_channel(message.guild, embed)
            try:
                await message.author.send(
                    f"⚠️ You were automatically timed out in **{message.guild.name}** "
                    f"for 5 minutes due to spam."
                )
            except discord.Forbidden:
                pass
        except discord.Forbidden:
            log.warning("AutoMod: missing Moderate Members permission in guild %s", gid)

    # ── Word filter ───────────────────────────────────────────────────────────

    async def _warn_and_escalate(
        self,
        message: discord.Message,
        reason: str,
        alert: str,
    ) -> None:
        """Add a DB warning, log it, notify the channel, then check escalation."""
        await db.add_warning(message.guild.id, message.author.id, self.bot.user.id, reason)
        warns = await db.get_warnings(message.guild.id, message.author.id)
        case_num = await db.add_case(
            message.guild.id, "warn", message.author.id, self.bot.user.id, reason
        )
        embed = mod_embed(
            "warn", message.author, self.bot.user, reason, case_num,
            extra=f"Warning #{len(warns)}",
        )
        await self._log_to_channel(message.guild, embed)

        try:
            await message.channel.send(alert, delete_after=5)
        except discord.Forbidden:
            pass

        # Reuse the same escalation logic as the manual !warn command
        from cogs.moderation import check_and_escalate
        triggered, esc_embed = await check_and_escalate(
            self.bot, message.guild, message.author, len(warns)
        )
        if triggered and esc_embed:
            await self._log_to_channel(message.guild, esc_embed)

    async def _check_words(self, message: discord.Message, word_filter: List[str]) -> None:
        content_lower = message.content.lower()
        if not any(w.lower() in content_lower for w in word_filter):
            return

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        await self._warn_and_escalate(
            message,
            reason="Auto-mod: filtered word detected",
            alert=f"⚠️ {message.author.mention}, your message contained a prohibited word.",
        )

    # ── Anti-invite ───────────────────────────────────────────────────────────

    async def _check_invite(self, message: discord.Message) -> None:
        if not _INVITE_RE.search(message.content):
            return

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        await self._warn_and_escalate(
            message,
            reason="Auto-mod: Discord invite link",
            alert=f"🚫 {message.author.mention}, posting invite links is not allowed here.",
        )

    # ── Config commands ───────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def antispam(self, ctx: commands.Context, toggle: str) -> None:
        """Enable or disable spam detection.  Usage: `!antispam on` / `!antispam off`"""
        if toggle.lower() not in ("on", "off"):
            return await ctx.send("Usage: `!antispam on` or `!antispam off`")
        val = 1 if toggle.lower() == "on" else 0
        await db.set_config(ctx.guild.id, antispam=val)
        await ctx.send(f"✅ Anti-spam is now **{'enabled' if val else 'disabled'}**.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def antiinvite(self, ctx: commands.Context, toggle: str) -> None:
        """Enable or disable invite-link filtering.  Usage: `!antiinvite on` / `!antiinvite off`"""
        if toggle.lower() not in ("on", "off"):
            return await ctx.send("Usage: `!antiinvite on` or `!antiinvite off`")
        val = 1 if toggle.lower() == "on" else 0
        await db.set_config(ctx.guild.id, antiinvite=val)
        await ctx.send(f"✅ Anti-invite is now **{'enabled' if val else 'disabled'}**.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def addword(self, ctx: commands.Context, *, word: str) -> None:
        """Add a word to the auto-mod word filter."""
        cfg = await db.get_config(ctx.guild.id)
        words: List[str] = cfg.get("word_filter", [])
        word = word.lower().strip()
        if word in words:
            return await ctx.send(f"❌ `{word}` is already in the filter.")
        words.append(word)
        await db.set_config(ctx.guild.id, word_filter=words)
        await ctx.send(f"✅ Added `{word}` to the word filter. ({len(words)} total)")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def removeword(self, ctx: commands.Context, *, word: str) -> None:
        """Remove a word from the auto-mod word filter."""
        cfg = await db.get_config(ctx.guild.id)
        words: List[str] = cfg.get("word_filter", [])
        word = word.lower().strip()
        if word not in words:
            return await ctx.send(f"❌ `{word}` is not in the filter.")
        words.remove(word)
        await db.set_config(ctx.guild.id, word_filter=words)
        await ctx.send(f"✅ Removed `{word}` from the word filter. ({len(words)} remaining)")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def wordlist(self, ctx: commands.Context) -> None:
        """Show all words currently in the word filter."""
        cfg = await db.get_config(ctx.guild.id)
        words: List[str] = cfg.get("word_filter", [])
        if not words:
            return await ctx.send("📋 The word filter is currently empty.")
        embed = discord.Embed(
            title="🚫 Word Filter",
            description=", ".join(f"`{w}`" for w in sorted(words)),
            color=discord.Color.red(),
        )
        embed.set_footer(text=f"{len(words)} word(s) in filter")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def warnthreshold(
        self, ctx: commands.Context, count: int, action: str = "kick"
    ) -> None:
        """Set warning count for auto-escalation and the action (kick/ban/none).

        Example: `!warnthreshold 3 kick`  or  `!warnthreshold 5 ban`
        """
        if count < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        if action.lower() not in ("kick", "ban", "none"):
            return await ctx.send("❌ Action must be `kick`, `ban`, or `none`.")
        await db.set_config(ctx.guild.id, warn_threshold=count, warn_action=action.lower())
        if action.lower() == "none":
            await ctx.send("✅ Auto-escalation is now **disabled**.")
        else:
            await ctx.send(
                f"✅ Members will be auto-**{action}**ed after **{count}** warning(s)."
            )

    @warnthreshold.error
    async def warnthreshold_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("Usage: `!warnthreshold <count> <kick|ban|none>`")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
