import asyncio
import discord
from discord.ext import commands

class FakeNuke(commands.Cog):
    """A cog containing a realistic-looking fake nuke command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="nuke")
    @commands.guild_only()
    async def nuke(self, ctx: commands.Context) -> None:
        """Runs a simulated server nuke sequence (restricted to specific authorized user)."""
        # Strictly restrict to the specified authorized user ID
        if ctx.author.id != 921050834521948160:
            return  # Fail silently as if the command doesn't exist

        # Phase 1: Warning Embed
        embed = discord.Embed(
            title="⚠️ CRITICAL SYSTEM ALERT ⚠️",
            description=(
                "**PROTOCOL NUKE-598 DETECTED**\n\n"
                f"**Initiated By:** {ctx.author.mention}\n"
                f"**Target Server:** `{ctx.guild.name}`\n"
                "**Authorization:** GRANTED\n\n"
                "*Decoupling security relays and preparing server purge...*"
            ),
            color=0xdd2e44,  # Dark red/crimson
        )
        embed.set_footer(text="System override in progress...")
        message = await ctx.send(embed=embed)
        await asyncio.sleep(2.5)

        # Phase 2: Countdown
        countdown_steps = [
            ("T-minus 5 seconds", "🔴 █░░░░░░░░░ 10%"),
            ("T-minus 4 seconds", "🔴 ███░░░░░░░ 30%"),
            ("T-minus 3 seconds", "🔴 █████░░░░░ 50%"),
            ("T-minus 2 seconds", "🔴 ███████░░░ 70%"),
            ("T-minus 1 second ", "🔴 █████████░ 90%"),
        ]

        for time_left, bar in countdown_steps:
            embed.title = "🚀 DETONATION INITIATED"
            embed.description = (
                "**PROTOCOL NUKE-598 DETECTED**\n\n"
                f"**Status:** `{time_left}`\n"
                f"**Core Charge:** `{bar}`\n\n"
                "*System lockout complete. Escape is impossible.*"
            )
            embed.color = 0xff4500  # Orange-red
            await message.edit(embed=embed)
            await asyncio.sleep(1.0)

        # Phase 3: Simulated Deletion Progression
        # 1. Channels Wiped
        embed.title = "💥 INITIATING OBLITERATION"
        embed.description = (
            "**DELETING SERVER ASSETS...**\n\n"
            "📁 **Channels Wiped:** `[░░░░░░░░░░] 0%`"
        )
        embed.color = 0xff0000  # Bright Red
        await message.edit(embed=embed)
        await asyncio.sleep(1.5)

        num_channels = len(ctx.guild.channels)
        embed.description = (
            "**DELETING SERVER ASSETS...**\n\n"
            f"📁 **Channels Wiped:** `[██████████] 100%` (Deleted {num_channels} channels)\n"
            "👥 **Members Banned:** `[░░░░░░░░░░] 0%`"
        )
        await message.edit(embed=embed)
        await asyncio.sleep(1.5)

        # 2. Members Banned
        num_members = ctx.guild.member_count or 100
        embed.description = (
            "**DELETING SERVER ASSETS...**\n\n"
            f"📁 **Channels Wiped:** `[██████████] 100%` (Deleted {num_channels} channels)\n"
            f"👥 **Members Banned:** `[██████████] 100%` (Banned {num_members} members)\n"
            "🛡️ **Roles Purged:** `[░░░░░░░░░░] 0%`"
        )
        await message.edit(embed=embed)
        await asyncio.sleep(1.5)

        # 3. Roles Wiped
        num_roles = len(ctx.guild.roles) - 1  # Exclude @everyone
        embed.description = (
            "**DELETING SERVER ASSETS...**\n\n"
            f"📁 **Channels Wiped:** `[██████████] 100%` (Deleted {num_channels} channels)\n"
            f"👥 **Members Banned:** `[██████████] 100%` (Banned {num_members} members)\n"
            f"🛡️ **Roles Purged:** `[██████████] 100%` (Purged {num_roles} roles)\n\n"
            "📡 **System Status:** *Overload imminent...*"
        )
        await message.edit(embed=embed)
        await asyncio.sleep(2.0)

        # Phase 4: The Climax / Punchline
        final_embed = discord.Embed(
            title="💥 SERVER OBLITERATED 💥",
            description=(
                "**Nuke Sequence Complete.**\n\n"
                f"• **Channels Deleted:** {num_channels}\n"
                f"• **Members Banned:** {num_members}\n"
                f"• **Roles Purged:** {num_roles}\n"
                "• **Time Elapsed:** 11.5 seconds\n\n"
                "*(Just kidding! 😉 No channels, members, or roles were harmed. This was a fake simulation.)*"
            ),
            color=0x2f3136,  # Dark theme color
        )
        final_embed.set_footer(text="Nuke Simulation Complete.")
        await message.edit(embed=final_embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FakeNuke(bot))
