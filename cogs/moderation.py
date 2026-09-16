import logging
from datetime import timedelta
from typing import Optional

import discord
from discord.ext import commands

from utils import database as db
from utils.helpers import format_duration, mod_embed, parse_duration

log = logging.getLogger(__name__)


async def check_and_escalate(
    bot: commands.Bot,
    guild: discord.Guild,
    member: discord.Member,
    warn_count: int,
) -> tuple[bool, Optional[discord.Embed]]:
    """Kick or ban a member if their warning count meets the configured threshold.

    Returns (triggered, embed):
      - triggered=False  → threshold not reached, no action taken
      - triggered=True, embed set  → action succeeded, embed ready to post
      - triggered=True, embed=None → action triggered but bot lacked permission
    """
    cfg = await db.get_config(guild.id)
    threshold = cfg.get("warn_threshold", 3)
    action = cfg.get("warn_action", "kick")
    if warn_count < threshold or action == "none":
        return False, None

    esc_reason = f"Auto-{action}: reached {warn_count} warning(s)"
    dm_title = (
        f"👢 You were kicked from {guild.name}"
        if action == "kick"
        else f"🔨 You were banned from {guild.name}"
    )
    await _dm(
        member,
        discord.Embed(
            title=dm_title,
            description=f"**Reason:** {esc_reason}",
            color=discord.Color.orange() if action == "kick" else discord.Color.red(),
        ),
    )
    try:
        if action == "kick":
            await member.kick(reason=esc_reason)
        elif action == "ban":
            await member.ban(reason=esc_reason)
        esc_case = await db.add_case(guild.id, action, member.id, bot.user.id, esc_reason)
        esc_embed = mod_embed(action, member, bot.user, esc_reason, esc_case)
        await _send_mod_log(bot, guild, esc_embed)
        return True, esc_embed
    except discord.Forbidden:
        log.warning(
            "Auto-escalation: missing %s permission in guild %s for member %s",
            action, guild.id, member.id,
        )
        return True, None


async def _send_mod_log(bot: commands.Bot, guild: discord.Guild, embed: discord.Embed) -> None:
    cfg = await db.get_config(guild.id)
    channel_id = cfg.get("mod_log_channel")
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def _dm(user: discord.abc.User, embed: discord.Embed) -> None:
    try:
        await user.send(embed=embed)
    except discord.HTTPException:
        # Covers Forbidden (403), non-friend DM restriction (400), and other HTTP errors
        pass


class Moderation(commands.Cog):
    """Warn, kick, ban, timeout, and case-management commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Warn ──────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warn(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Warn a member. Auto-escalates when the warning threshold is reached."""
        if member.bot:
            return await ctx.send("❌ You cannot warn a bot.")
        if member == ctx.author:
            return await ctx.send("❌ You cannot warn yourself.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ You cannot warn someone with an equal or higher role.")

        await db.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        warnings = await db.get_warnings(ctx.guild.id, member.id)
        count = len(warnings)
        case_num = await db.add_case(ctx.guild.id, "warn", member.id, ctx.author.id, reason)

        embed = mod_embed("warn", member, ctx.author, reason, case_num, extra=f"Warning #{count}")
        await ctx.send(embed=embed)
        await _send_mod_log(self.bot, ctx.guild, embed)

        await _dm(
            member,
            discord.Embed(
                title=f"⚠️ You were warned in {ctx.guild.name}",
                description=f"**Reason:** {reason}\n**Total warnings:** {count}",
                color=discord.Color.yellow(),
            ),
        )

        # Auto-escalation (shared logic with automod)
        triggered, esc_embed = await check_and_escalate(self.bot, ctx.guild, member, count)
        if triggered and esc_embed:
            await ctx.send(embed=esc_embed)
        elif triggered and esc_embed is None:
            await ctx.send("⚠️ Auto-escalation triggered but I lack the required permission.")

    @warn.error
    async def warn_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Messages** permission.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!warn @member [reason]`")

    # ── Warnings list ─────────────────────────────────────────────────────────

    @commands.command(aliases=["warns"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warnings(self, ctx: commands.Context, member: discord.Member) -> None:
        """Show all warnings for a member."""
        warns = await db.get_warnings(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(f"✅ {member.mention} has no warnings.")
        embed = discord.Embed(
            title=f"⚠️ Warnings for {member}",
            description=f"Total: **{len(warns)}**",
            color=discord.Color.yellow(),
        )
        for w in warns[-10:]:
            ts = w["timestamp"][:10]
            embed.add_field(
                name=f"#{w['id']} — {ts}",
                value=f"**Reason:** {w['reason']}\n**By:** <@{w['moderator_id']}>",
                inline=False,
            )
        if len(warns) > 10:
            embed.set_footer(text=f"Showing last 10 of {len(warns)} warnings.")
        await ctx.send(embed=embed)

    @warnings.error
    async def warnings_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!warnings @member`")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")

    # ── Clear all warnings ────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member) -> None:
        """Clear every warning for a member."""
        count = await db.clear_warnings(ctx.guild.id, member.id)
        await ctx.send(f"✅ Cleared **{count}** warning(s) for {member.mention}.")

    @clearwarnings.error
    async def clearwarnings_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!clearwarnings @member`")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")

    # ── Delete a single warning ───────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def delwarn(self, ctx: commands.Context, warn_id: int) -> None:
        """Delete a specific warning by its ID (shown in `!warnings`)."""
        deleted = await db.delete_warning(warn_id, ctx.guild.id)
        if deleted:
            await ctx.send(f"✅ Warning **#{warn_id}** deleted.")
        else:
            await ctx.send(f"❌ Warning **#{warn_id}** not found in this server.")

    @delwarn.error
    async def delwarn_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("Usage: `!delwarn <id>`  — find IDs with `!warnings @member`")

    # ── Kick ──────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Kick a member from the server."""
        if member.bot:
            return await ctx.send("❌ You cannot kick a bot.")
        if member == ctx.author:
            return await ctx.send("❌ You cannot kick yourself.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ You cannot kick someone with an equal or higher role.")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ I cannot kick someone with a higher or equal role to mine.")

        await _dm(
            member,
            discord.Embed(
                title=f"👢 You were kicked from {ctx.guild.name}",
                description=f"**Reason:** {reason}",
                color=discord.Color.orange(),
            ),
        )
        try:
            await member.kick(reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to kick that member.")

        case_num = await db.add_case(ctx.guild.id, "kick", member.id, ctx.author.id, reason)
        embed = mod_embed("kick", member, ctx.author, reason, case_num)
        await ctx.send(embed=embed)
        await _send_mod_log(self.bot, ctx.guild, embed)

    @kick.error
    async def kick_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Kick Members** permission.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!kick @member [reason]`")

    # ── Ban ───────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(
        self,
        ctx: commands.Context,
        user: discord.User,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Ban a user by mention or ID (works even if they are not in the server)."""
        member = ctx.guild.get_member(user.id)
        if member:
            if member == ctx.author:
                return await ctx.send("❌ You cannot ban yourself.")
            if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
                return await ctx.send("❌ You cannot ban someone with an equal or higher role.")
            if member.top_role >= ctx.guild.me.top_role:
                return await ctx.send(
                    "❌ I cannot ban someone with a higher or equal role to mine."
                )
            await _dm(
                member,
                discord.Embed(
                    title=f"🔨 You were banned from {ctx.guild.name}",
                    description=f"**Reason:** {reason}",
                    color=discord.Color.red(),
                ),
            )

        try:
            await ctx.guild.ban(user, reason=f"{ctx.author}: {reason}", delete_message_days=0)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to ban that user.")

        case_num = await db.add_case(ctx.guild.id, "ban", user.id, ctx.author.id, reason)
        embed = mod_embed("ban", user, ctx.author, reason, case_num)
        await ctx.send(embed=embed)
        await _send_mod_log(self.bot, ctx.guild, embed)

    @ban.error
    async def ban_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Ban Members** permission.")
        elif isinstance(error, commands.UserNotFound):
            await ctx.send("❌ User not found. Tip: use their numeric ID to ban someone not in the server.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!ban @user [reason]`")

    # ── Unban ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(
        self,
        ctx: commands.Context,
        user_id: int,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Unban a user by their numeric ID."""
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            return await ctx.send("❌ No user found with that ID.")
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except discord.NotFound:
            return await ctx.send("❌ That user is not currently banned.")
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to unban members.")

        case_num = await db.add_case(ctx.guild.id, "unban", user.id, ctx.author.id, reason)
        embed = mod_embed("unban", user, ctx.author, reason, case_num)
        await ctx.send(embed=embed)
        await _send_mod_log(self.bot, ctx.guild, embed)

    @unban.error
    async def unban_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Ban Members** permission.")
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("Usage: `!unban <user_id> [reason]`")

    # ── Timeout ───────────────────────────────────────────────────────────────

    @commands.command(aliases=["mute"])
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Timeout a member for a given duration (e.g. 10m, 2h, 7d, max 28d)."""
        if member.bot:
            return await ctx.send("❌ You cannot timeout a bot.")
        if member == ctx.author:
            return await ctx.send("❌ You cannot timeout yourself.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ You cannot timeout someone with an equal or higher role.")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send(
                "❌ I cannot timeout someone with a higher or equal role to mine."
            )

        td = parse_duration(duration)
        if td is None:
            return await ctx.send(
                "❌ Invalid duration. Examples: `10m`, `1h`, `2d`, `1w`\n"
                "Units: `s` seconds · `m` minutes · `h` hours · `d` days · `w` weeks"
            )
        if td > timedelta(days=28):
            return await ctx.send("❌ Timeout duration cannot exceed 28 days.")

        until = discord.utils.utcnow() + td
        try:
            await member.timeout(until, reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            return await ctx.send(
                "❌ I can't timeout that member. They may have Administrator or a higher role than me."
            )

        case_num = await db.add_case(ctx.guild.id, "timeout", member.id, ctx.author.id, reason)
        embed = mod_embed(
            "timeout", member, ctx.author, reason, case_num,
            extra=f"Duration: {format_duration(td)} (until {discord.utils.format_dt(until, 'R')})",
        )
        await ctx.send(embed=embed)
        await _send_mod_log(self.bot, ctx.guild, embed)

        await _dm(
            member,
            discord.Embed(
                title=f"⏱️ You were timed out in {ctx.guild.name}",
                description=(
                    f"**Duration:** {format_duration(td)}\n"
                    f"**Expires:** {discord.utils.format_dt(until, 'R')}\n"
                    f"**Reason:** {reason}"
                ),
                color=discord.Color.orange(),
            ),
        )

    @timeout.error
    async def timeout_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Moderate Members** permission.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!timeout @member <duration> [reason]`  e.g. `!timeout @user 10m Spamming`")

    # ── Remove timeout ────────────────────────────────────────────────────────

    @commands.command(aliases=["unmute", "untimeout"])
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def removetimeout(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Remove an active timeout from a member."""
        if not member.is_timed_out():
            return await ctx.send(f"❌ {member.mention} is not currently timed out.")
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        case_num = await db.add_case(ctx.guild.id, "untimeout", member.id, ctx.author.id, reason)
        embed = mod_embed("untimeout", member, ctx.author, reason, case_num)
        await ctx.send(embed=embed)
        await _send_mod_log(self.bot, ctx.guild, embed)

    @removetimeout.error
    async def removetimeout_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Moderate Members** permission.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!removetimeout @member [reason]`")

    # ── Case lookup ───────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def case(self, ctx: commands.Context, case_num: int) -> None:
        """Look up a moderation case by its number."""
        c = await db.get_case(ctx.guild.id, case_num)
        if not c:
            return await ctx.send(f"❌ Case **#{case_num}** not found.")
        ts = c["timestamp"][:19].replace("T", " ") + " UTC"
        embed = discord.Embed(title=f"📋 Case #{case_num}", color=discord.Color.blurple())
        embed.add_field(name="Action", value=c["action"].title(), inline=True)
        embed.add_field(name="Date", value=ts, inline=True)
        embed.add_field(name="User", value=f"<@{c['user_id']}> ({c['user_id']})", inline=False)
        embed.add_field(
            name="Moderator", value=f"<@{c['moderator_id']}> ({c['moderator_id']})", inline=False
        )
        embed.add_field(name="Reason", value=c["reason"] or "None", inline=False)
        await ctx.send(embed=embed)

    @case.error
    async def case_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("Usage: `!case <number>`")

    # ── All cases for a user ──────────────────────────────────────────────────

    @commands.command(aliases=["history"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def cases(self, ctx: commands.Context, member: discord.Member) -> None:
        """Show all moderation cases for a member."""
        all_cases = await db.get_user_cases(ctx.guild.id, member.id)
        if not all_cases:
            return await ctx.send(f"✅ No cases found for {member.mention}.")
        embed = discord.Embed(
            title=f"📋 Cases for {member}",
            description=f"Total: **{len(all_cases)}**",
            color=discord.Color.blurple(),
        )
        for c in all_cases[-10:]:
            ts = c["timestamp"][:10]
            embed.add_field(
                name=f"Case #{c['case_num']} — {c['action'].title()} ({ts})",
                value=f"**Reason:** {c['reason'] or 'None'}\n**By:** <@{c['moderator_id']}>",
                inline=False,
            )
        if len(all_cases) > 10:
            embed.set_footer(text=f"Showing last 10 of {len(all_cases)} cases.")
        await ctx.send(embed=embed)

    @cases.error
    async def cases_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!cases @member`")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
