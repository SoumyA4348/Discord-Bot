import discord
from discord.ext import commands

from utils import database as db


class Utility(commands.Cog):
    """Server-management and informational commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Clear ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def clear(self, ctx: commands.Context, amount: int) -> None:
        """Bulk-delete the last N messages (max 100).  Usage: `!clear <amount>`"""
        if amount <= 0:
            return await ctx.send("❌ Amount must be a positive number.", delete_after=8)
        if amount > 100:
            return await ctx.send("❌ Cannot delete more than 100 messages at once.", delete_after=8)
        deleted = await ctx.channel.purge(limit=amount + 1)
        actual = max(len(deleted) - 1, 0)
        word = "message" if actual == 1 else "messages"
        await ctx.send(f"🧹 Deleted **{actual}** {word}.", delete_after=8)

    @clear.error
    async def clear_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Messages** permission.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!clear <amount>`  e.g. `!clear 10`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Please provide a valid number.")

    # ── Slowmode ──────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def slowmode(self, ctx: commands.Context, seconds: int) -> None:
        """Set channel slowmode in seconds (0 = off, max 21600).  Usage: `!slowmode <seconds>`"""
        if not 0 <= seconds <= 21600:
            return await ctx.send("❌ Value must be between **0** and **21600** seconds.")
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send("✅ Slowmode **disabled**.")
        else:
            await ctx.send(f"✅ Slowmode set to **{seconds}** second(s).")

    @slowmode.error
    async def slowmode_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Channels** permission.")
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("Usage: `!slowmode <seconds>`  e.g. `!slowmode 5`")

    # ── Lockdown ──────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lockdown(self, ctx: commands.Context, *, reason: str = "No reason provided") -> None:
        """Prevent @everyone from sending messages in this channel."""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"**Reason:** {reason}",
            color=discord.Color.red(),
        )
        embed.set_footer(text=f"Locked by {ctx.author}")
        await ctx.send(embed=embed)

    @lockdown.error
    async def lockdown_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Channels** permission.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context) -> None:
        """Restore @everyone's ability to send messages in this channel."""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # reset to inherited default
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description="Send-message permissions restored.",
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Unlocked by {ctx.author}")
        await ctx.send(embed=embed)

    @unlock.error
    async def unlock_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Channels** permission.")

    # ── Set mod-log channel ───────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setmodlog(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the channel where all moderation actions are logged.  Usage: `!setmodlog #channel`"""
        await db.set_config(ctx.guild.id, mod_log_channel=channel.id)
        await ctx.send(f"✅ Mod-log channel set to {channel.mention}.")

    @setmodlog.error
    async def setmodlog_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Server** permission.")
        elif isinstance(error, (commands.MissingRequiredArgument, commands.ChannelNotFound)):
            await ctx.send("Usage: `!setmodlog #channel`")

    # ── User info ─────────────────────────────────────────────────────────────

    @commands.command(aliases=["ui", "whois"])
    @commands.guild_only()
    async def userinfo(
        self, ctx: commands.Context, member: discord.Member = None
    ) -> None:
        """Show detailed info about a member (defaults to yourself)."""
        member = member or ctx.author
        roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]

        warns = await db.get_warnings(ctx.guild.id, member.id)
        cases = await db.get_user_cases(ctx.guild.id, member.id)

        embed = discord.Embed(
            title=f"👤 {member}",
            color=member.color if member.color.value else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, style="D"),
            inline=True,
        )
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(member.joined_at, style="D")
            if member.joined_at
            else "Unknown",
            inline=True,
        )
        embed.add_field(name="Warnings", value=str(len(warns)), inline=True)
        embed.add_field(name="Cases", value=str(len(cases)), inline=True)
        if member.is_timed_out():
            embed.add_field(
                name="Timed Out Until",
                value=discord.utils.format_dt(member.timed_out_until, style="R"),
                inline=True,
            )
        roles_str = " ".join(roles) if roles else "None"
        embed.add_field(name=f"Roles [{len(roles)}]", value=roles_str[:1024], inline=False)
        await ctx.send(embed=embed)

    @userinfo.error
    async def userinfo_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found.")

    # ── Server info ───────────────────────────────────────────────────────────

    @commands.command(aliases=["si", "server"])
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context) -> None:
        """Show information and statistics about this server."""
        g = ctx.guild
        bots = sum(1 for m in g.members if m.bot)
        humans = g.member_count - bots

        embed = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blurple())
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown", inline=True)
        embed.add_field(name="ID", value=str(g.id), inline=True)
        embed.add_field(
            name="Created", value=discord.utils.format_dt(g.created_at, style="D"), inline=True
        )
        embed.add_field(
            name="Members", value=f"{humans:,} humans · {bots:,} bots", inline=True
        )
        embed.add_field(
            name="Channels",
            value=f"{len(g.text_channels)} text · {len(g.voice_channels)} voice",
            inline=True,
        )
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(
            name="Boosts",
            value=f"Level {g.premium_tier} · {g.premium_subscription_count} boosts",
            inline=True,
        )
        embed.add_field(
            name="Verification", value=str(g.verification_level).replace("_", " ").title(), inline=True
        )
        await ctx.send(embed=embed)

    # ── Help ──────────────────────────────────────────────────────────────────

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        """Show all available commands grouped by category."""
        embed = discord.Embed(
            title="📖 Command Reference",
            description="Prefix: `!`  —  Use `!help` anytime to see this.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="⚔️ Moderation",
            value=(
                "`!warn @user [reason]` — warn & auto-escalate\n"
                "`!warnings @user` / `!warns` — view warning history\n"
                "`!clearwarnings @user` — clear all warnings\n"
                "`!delwarn <id>` — delete one warning by ID\n"
                "`!kick @user [reason]` — kick with DM\n"
                "`!ban @user [reason]` — ban (mention or ID)\n"
                "`!unban <user_id> [reason]` — unban\n"
                "`!timeout @user <dur> [reason]` — e.g. `10m 2h 7d`\n"
                "`!removetimeout @user` / `!unmute` — remove timeout\n"
                "`!case <num>` — look up a case\n"
                "`!cases @user` / `!history` — all cases for a user"
            ),
            inline=False,
        )

        embed.add_field(
            name="🤖 Auto-Mod",
            value=(
                "`!antispam on/off` — spam detection (5 msgs / 5 s → 5 min timeout)\n"
                "`!antiinvite on/off` — block Discord invite links\n"
                "`!addword <word>` — add word to filter\n"
                "`!removeword <word>` — remove word from filter\n"
                "`!wordlist` — show filtered words\n"
                "`!warnthreshold <n> <kick|ban|none>` — auto-escalation config"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔧 Utility",
            value=(
                "`!clear <n>` — bulk-delete up to 100 messages\n"
                "`!slowmode <sec>` — set / disable slowmode (0 = off)\n"
                "`!lockdown [reason]` — lock channel for @everyone\n"
                "`!unlock` — unlock channel\n"
                "`!setmodlog #channel` — set mod-log destination\n"
                "`!userinfo [@user]` / `!whois` — member details\n"
                "`!serverinfo` / `!server` — server overview"
            ),
            inline=False,
        )

        embed.add_field(
            name="🌍 Translation",
            value=(
                "`!translate <text>` — translate to English\n"
                "`!translate to <lang> <text>` — translate to any language\n"
                "`!languages` — list supported language names\n"
                "Auto: non-English messages are translated inline automatically"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎉 Giveaways",
            value=(
                "`!gcreate` — interactive wizard / custom giveaway launcher\n"
                "`!gstart <dur> [winners] <prize>` — quick launch giveaway\n"
                "`!gend <message_id>` — end giveaway early & roll winners\n"
                "`!greroll <message_id> [winners]` — pick new winner(s)\n"
                "`!glist` — list all active giveaways"
            ),
            inline=False,
        )

        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
