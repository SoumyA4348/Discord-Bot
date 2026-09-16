import asyncio
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands, tasks

from utils.database import (
    create_giveaway,
    end_giveaway_db,
    get_active_giveaways,
    get_giveaway,
    get_giveaway_entries,
    get_giveaway_entry_count,
    get_guild_giveaways,
    toggle_giveaway_entry,
)
from utils.helpers import parse_duration

ALLOWED_GIVEAWAY_USERS = {
    792114446981529607,
    921050834521948160,
    1080356083329142905,
}


def is_giveaway_admin():
    """Check if command invoker is in the whitelist of authorized giveaway admins."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in ALLOWED_GIVEAWAY_USERS:
            return True
        await ctx.send("❌ You are not authorized to use giveaway commands.")
        return False

    return commands.check(predicate)


def build_giveaway_embed(
    prize: str,
    ends_at_dt: datetime,
    host: discord.abc.User,
    sponsor: Optional[str] = None,
    requirements: Optional[str] = None,
    winners_count: int = 1,
    entry_count: int = 0,
    ended: bool = False,
    winners: Optional[List[int]] = None,
) -> discord.Embed:
    """Build the standardized Giveaway embed matching the requested format."""
    end_unix = int(ends_at_dt.timestamp())
    color = 0x2f3136 if ended else 0x5865F2  # Blurple when active, dark when ended

    title = "🏁 GIVEAWAY ENDED 🏁" if ended else "🎉 GIVEAWAY TIME! 🎉"
    embed = discord.Embed(title=title, color=color)

    description_lines = []
    description_lines.append(f"🎁 **Reward:** **{prize}**")

    if not ended:
        description_lines.append(
            f"⏱️ **Duration:** Ends <t:{end_unix}:R> (<t:{end_unix}:F>)"
        )
    else:
        description_lines.append(f"⏱️ **Ended:** <t:{end_unix}:R>")

    if sponsor:
        description_lines.append(f"👑 **Sponsored by:** {sponsor}")

    if requirements and not ended:
        description_lines.append(
            f"📋 **Required invites to claim the prize:** {requirements}"
        )

    description_lines.append(f"🏆 **Winners:** `{winners_count}`")
    description_lines.append(f"👥 **Entries:** `{entry_count}`")

    if ended:
        if winners:
            winner_mentions = ", ".join(f"<@{w}>" for w in winners)
            description_lines.append(f"\n🎉 **Winner(s):** {winner_mentions}")
        else:
            description_lines.append("\n⚠️ **Winner(s):** No valid entries.")
    else:
        description_lines.append("\n*Join now for a chance to win!*")
        description_lines.append("*Click the participate button below to enter.*")

    embed.description = "\n".join(description_lines)
    embed.set_footer(
        text=f"Hosted by {host.display_name} • Ends"
    )
    embed.timestamp = ends_at_dt
    return embed


def update_giveaway_embed_entries(embed: discord.Embed, new_count: int) -> discord.Embed:
    """Update the entry count in an existing giveaway embed description."""
    if not embed.description:
        return embed
    new_desc = re.sub(
        r"👥 \*\*Entries:\*\* `?\d+`?", f"👥 **Entries:** `{new_count}`", embed.description
    )
    embed.description = new_desc
    return embed


class GiveawayView(discord.ui.View):
    """Persistent view with a single participate button for giveaways."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Participate 🎉",
        style=discord.ButtonStyle.success,
        custom_id="giveaway_participate_button",
    )
    async def participate(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.message:
            return

        giveaway = await get_giveaway(interaction.message.id)
        if not giveaway or giveaway["ended"]:
            await interaction.response.send_message(
                "❌ This giveaway has already ended!", ephemeral=True
            )
            return

        entered = await toggle_giveaway_entry(
            interaction.message.id, interaction.user.id
        )
        count = await get_giveaway_entry_count(interaction.message.id)

        if entered:
            await interaction.response.send_message(
                f"🎉 You entered the giveaway for **{giveaway['prize']}**!\n"
                f"Total entries: `{count}`",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"ℹ️ You left the giveaway for **{giveaway['prize']}**.\n"
                f"Total entries: `{count}`",
                ephemeral=True,
            )

        # Update the embed's displayed entry count
        try:
            if interaction.message.embeds:
                old_embed = interaction.message.embeds[0]
                updated_embed = update_giveaway_embed_entries(old_embed, count)
                await interaction.message.edit(embed=updated_embed)
        except Exception:
            pass


class DisabledGiveawayView(discord.ui.View):
    """View shown after a giveaway has concluded."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Giveaway Ended 🏁",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="giveaway_ended_button",
    )
    async def ended_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        pass


class GiveawayCog(commands.Cog, name="Giveaway"):
    """Automated giveaway cog with interactive buttons, persistent storage, and auto-rolling."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self) -> None:
        self.check_giveaways.cancel()

    @tasks.loop(seconds=10)
    async def check_giveaways(self) -> None:
        """Background loop to check and auto-roll expired giveaways."""
        await self.bot.wait_until_ready()
        try:
            active_giveaways = await get_active_giveaways()
            now = datetime.now(timezone.utc)
            for g in active_giveaways:
                ends_at_dt = datetime.fromisoformat(g["ends_at"])
                if ends_at_dt <= now:
                    await self._end_giveaway(g["message_id"])
        except Exception as exc:
            print(f"[GiveawayCog] Error in check_giveaways loop: {exc}")

    async def _end_giveaway(
        self, message_id: int, reroll: bool = False, reroll_winners: int = 1
    ) -> Optional[List[int]]:
        """Core logic to end/roll a giveaway."""
        giveaway = await get_giveaway(message_id)
        if not giveaway:
            return None

        if not reroll:
            await end_giveaway_db(message_id)

        channel = self.bot.get_channel(giveaway["channel_id"])
        if not channel:
            try:
                channel = await self.bot.fetch_channel(giveaway["channel_id"])
            except Exception:
                return None

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            message = None

        entries = await get_giveaway_entries(message_id)
        winners_count = reroll_winners if reroll else (giveaway["winners_count"] or 1)

        winners: List[int] = []
        if entries:
            num_to_pick = min(len(entries), winners_count)
            winners = random.sample(entries, num_to_pick)

        # Update the original message if found
        if message:
            try:
                ends_at_dt = datetime.fromisoformat(giveaway["ends_at"])
                host = self.bot.get_user(giveaway["host_id"]) or message.author
                embed = build_giveaway_embed(
                    prize=giveaway["prize"],
                    ends_at_dt=ends_at_dt,
                    host=host,
                    sponsor=giveaway["sponsor"],
                    requirements=giveaway["requirements"],
                    winners_count=giveaway["winners_count"] or 1,
                    entry_count=len(entries),
                    ended=True,
                    winners=winners if not reroll else None,
                )
                await message.edit(embed=embed, view=DisabledGiveawayView())
            except Exception:
                pass

        # Send announcement in channel
        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            sponsor_str = f" Sponsored by {giveaway['sponsor']}." if giveaway["sponsor"] else ""
            req_str = (
                f"\n*(Requirement check: `{giveaway['requirements']}`)*"
                if giveaway["requirements"]
                else ""
            )

            announcement = (
                f"🎊 {'**REROLL WINNER!**' if reroll else '**GIVEAWAY ENDED!**'} 🎊\n"
                f"Congratulations {mentions}! You won **{giveaway['prize']}**!{sponsor_str}{req_str}\n"
                f"Jump to giveaway: {message.jump_url if message else ''}"
            )
            await channel.send(announcement)
        else:
            if not reroll:
                await channel.send(
                    f"⚠️ No valid entries for **{giveaway['prize']}** ({message.jump_url if message else ''}). No winner could be drawn."
                )

        return winners

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Silence CheckFailure so no raw tracebacks are logged for unauthorized users."""
        if isinstance(error, commands.CheckFailure):
            return

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.command(name="gstart")
    @is_giveaway_admin()
    async def gstart_command(
        self,
        ctx: commands.Context,
        duration: str,
        winners: Optional[str] = "1",
        *,
        prize: str,
    ) -> None:
        """Quickly start a giveaway.

        Usage:
          `!gstart <duration> [winners] <prize>`
          e.g. `!gstart 24h 1 Nitro Classic`
          e.g. `!gstart 2d SpongeBob Rank`
        """
        winners_count = 1
        final_prize = prize

        if winners and winners.isdigit():
            winners_count = max(1, int(winners))
        elif winners:
            final_prize = f"{winners} {prize}".strip()

        td = parse_duration(duration)
        if not td:
            return await ctx.send(
                "❌ Invalid duration format! Use `10m`, `2h`, `1d`, `7d`, etc."
            )

        now = datetime.now(timezone.utc)
        ends_at_dt = now + td
        ends_at_iso = ends_at_dt.isoformat()

        embed = build_giveaway_embed(
            prize=final_prize,
            ends_at_dt=ends_at_dt,
            host=ctx.author,
            winners_count=winners_count,
            entry_count=0,
        )

        msg = await ctx.send(
            content="🎉 **GIVEAWAY TIME!** 🎉",
            embed=embed,
            view=GiveawayView(),
        )

        await create_giveaway(
            message_id=msg.id,
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            prize=final_prize,
            winners_count=winners_count,
            sponsor=None,
            requirements=None,
            ends_at=ends_at_iso,
            host_id=ctx.author.id,
        )

    @commands.command(name="gcreate")
    @is_giveaway_admin()
    async def gcreate_command(self, ctx: commands.Context, *, flags: Optional[str] = None) -> None:
        """Interactive or flag-based creation wizard for custom giveaways.

        Flags mode:
          `!gcreate --duration 7d --prize "1x SpongeBob Rank" --sponsor "@Gunstarpro" --requirements "1 invite" --winners 1 --ping everyone`

        Wizard mode:
          Run `!gcreate` with no arguments to start an interactive step-by-step wizard!
        """
        # Flag-based parsing
        if flags and "--" in flags:
            parsed: Dict[str, str] = {}
            parts = re.findall(r"--(\w+)\s+([^\-]+(?<!\s))", flags)
            for key, val in parts:
                parsed[key.lower().strip()] = val.strip().strip('"').strip("'")

            duration_str = parsed.get("duration", "24h")
            prize = parsed.get("prize", "Discord Prize")
            sponsor = parsed.get("sponsor")
            requirements = parsed.get("requirements")
            winners_count = int(parsed.get("winners", "1") if parsed.get("winners", "1").isdigit() else 1)
            ping_type = parsed.get("ping", "everyone").lower()

            td = parse_duration(duration_str)
            if not td:
                return await ctx.send("❌ Invalid duration provided in flags.")

            now = datetime.now(timezone.utc)
            ends_at_dt = now + td
            ends_at_iso = ends_at_dt.isoformat()

            ping_msg = ""
            if ping_type == "everyone":
                ping_msg = "@everyone\n"
            elif ping_type == "here":
                ping_msg = "@here\n"

            embed = build_giveaway_embed(
                prize=prize,
                ends_at_dt=ends_at_dt,
                host=ctx.author,
                sponsor=sponsor,
                requirements=requirements,
                winners_count=winners_count,
                entry_count=0,
            )

            msg = await ctx.send(
                content=f"{ping_msg}# 🎉 GIVEAWAY TIME! 🎉",
                embed=embed,
                view=GiveawayView(),
            )

            await create_giveaway(
                message_id=msg.id,
                channel_id=ctx.channel.id,
                guild_id=ctx.guild.id,
                prize=prize,
                winners_count=winners_count,
                sponsor=sponsor,
                requirements=requirements,
                ends_at=ends_at_iso,
                host_id=ctx.author.id,
            )
            return

        # Interactive Step-by-Step Wizard
        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            # Step 1: Channel
            await ctx.send("📍 **Step 1/7:** What channel should the giveaway be in? (Mention channel like `#giveaways` or type `here`)")
            msg1 = await self.bot.wait_for("message", timeout=60.0, check=check)
            if msg1.channel_mentions:
                target_channel = msg1.channel_mentions[0]
            elif msg1.content.strip().isdigit():
                chan = self.bot.get_channel(int(msg1.content.strip()))
                target_channel = chan if chan else ctx.channel
            else:
                target_channel = ctx.channel

            # Step 2: Duration
            await ctx.send("⏱️ **Step 2/7:** How long should the giveaway run? (e.g. `10m`, `2h`, `7d`)")
            msg2 = await self.bot.wait_for("message", timeout=60.0, check=check)
            td = parse_duration(msg2.content)
            if not td:
                return await ctx.send("❌ Invalid duration. Setup cancelled. Please try again.")

            # Step 3: Prize
            await ctx.send("🎁 **Step 3/7:** What is the prize/reward? (e.g. `1x SpongeBob Rank`)")
            msg3 = await self.bot.wait_for("message", timeout=60.0, check=check)
            prize = msg3.content.strip()

            # Step 4: Number of Winners
            await ctx.send("🏆 **Step 4/7:** How many winners? (e.g. `1`)")
            msg4 = await self.bot.wait_for("message", timeout=60.0, check=check)
            winners_count = int(msg4.content.strip()) if msg4.content.strip().isdigit() else 1

            # Step 5: Sponsor
            await ctx.send("👑 **Step 5/7:** Who is sponsoring this? (Mention user e.g. `<@1080356083329142905>` or type `none`)")
            msg5 = await self.bot.wait_for("message", timeout=60.0, check=check)
            sponsor = None if msg5.content.strip().lower() in ["none", "no", "n/a"] else msg5.content.strip()

            # Step 6: Requirements
            await ctx.send("📋 **Step 6/7:** What are the requirements to claim? (e.g. `1 invite` or type `none`)")
            msg6 = await self.bot.wait_for("message", timeout=60.0, check=check)
            requirements = None if msg6.content.strip().lower() in ["none", "no", "n/a"] else msg6.content.strip()

            # Step 7: Ping
            await ctx.send("📢 **Step 7/7:** Should I ping `@everyone`, `@here`, or `none`?")
            msg7 = await self.bot.wait_for("message", timeout=60.0, check=check)
            ping_choice = msg7.content.strip().lower()
            ping_content = ""
            if "everyone" in ping_choice:
                ping_content = "@everyone\n"
            elif "here" in ping_choice:
                ping_content = "@here\n"

            now = datetime.now(timezone.utc)
            ends_at_dt = now + td
            ends_at_iso = ends_at_dt.isoformat()

            embed = build_giveaway_embed(
                prize=prize,
                ends_at_dt=ends_at_dt,
                host=ctx.author,
                sponsor=sponsor,
                requirements=requirements,
                winners_count=winners_count,
                entry_count=0,
            )

            giveaway_msg = await target_channel.send(
                content=f"{ping_content}# 🎉 GIVEAWAY TIME! 🎉",
                embed=embed,
                view=GiveawayView(),
            )

            await create_giveaway(
                message_id=giveaway_msg.id,
                channel_id=target_channel.id,
                guild_id=ctx.guild.id,
                prize=prize,
                winners_count=winners_count,
                sponsor=sponsor,
                requirements=requirements,
                ends_at=ends_at_iso,
                host_id=ctx.author.id,
            )

            await ctx.send(f"✅ **Giveaway created successfully!** Jump to: {giveaway_msg.jump_url}")

        except asyncio.TimeoutError:
            await ctx.send("⏳ Giveaway creation wizard timed out (60s). Please run `!gcreate` again.")

    @commands.command(name="gend")
    @is_giveaway_admin()
    async def gend_command(self, ctx: commands.Context, message_id: int) -> None:
        """Immediately end an active giveaway and roll winners.

        Usage: `!gend <message_id>`
        """
        giveaway = await get_giveaway(message_id)
        if not giveaway:
            return await ctx.send("❌ Giveaway not found with that message ID.")
        if giveaway["ended"]:
            return await ctx.send("❌ That giveaway has already ended.")

        winners = await self._end_giveaway(message_id)
        await ctx.send(f"✅ Ended giveaway `{message_id}`.")

    @commands.command(name="greroll")
    @is_giveaway_admin()
    async def greroll_command(
        self, ctx: commands.Context, message_id: int, winners_count: Optional[int] = 1
    ) -> None:
        """Reroll winner(s) for an ended giveaway.

        Usage: `!greroll <message_id> [winners_count]`
        """
        giveaway = await get_giveaway(message_id)
        if not giveaway:
            return await ctx.send("❌ Giveaway not found with that message ID.")

        winners = await self._end_giveaway(
            message_id, reroll=True, reroll_winners=winners_count or 1
        )
        if winners:
            await ctx.send(f"✅ Rerolled {len(winners)} new winner(s) for `{message_id}`.")
        else:
            await ctx.send("⚠️ No entries available to reroll.")

    @commands.command(name="glist")
    @is_giveaway_admin()
    async def glist_command(self, ctx: commands.Context) -> None:
        """List all active giveaways in the server."""
        giveaways = await get_guild_giveaways(ctx.guild.id, active_only=True)
        if not giveaways:
            return await ctx.send("ℹ️ There are no active giveaways running in this server.")

        embed = discord.Embed(
            title="🎉 Active Giveaways",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        for g in giveaways:
            ends_at_dt = datetime.fromisoformat(g["ends_at"])
            unix_time = int(ends_at_dt.timestamp())
            sponsor_txt = f" • Sponsored by {g['sponsor']}" if g['sponsor'] else ""
            embed.add_field(
                name=f"🎁 {g['prize']}",
                value=(
                    f"**Ends:** <t:{unix_time}:R> (<t:{unix_time}:f>)\n"
                    f"**Winners:** `{g['winners_count']}`{sponsor_txt}\n"
                    f"**Channel:** <#{g['channel_id']}> • [Jump to Giveaway](https://discord.com/channels/{g['guild_id']}/{g['channel_id']}/{g['message_id']})"
                ),
                inline=False,
            )

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    # Register the persistent view so active giveaway buttons work after restart
    bot.add_view(GiveawayView())
    await bot.add_cog(GiveawayCog(bot))
