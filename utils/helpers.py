import re
from datetime import timedelta
from typing import Optional

import discord

_DURATION_RE = re.compile(r"^(\d+)(s|m|h|d|w)$", re.IGNORECASE)
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(s: str) -> Optional[timedelta]:
    """Parse a duration string like '10m', '2h', '7d' into a timedelta."""
    match = _DURATION_RE.match(s.strip())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2).lower()
    return timedelta(seconds=value * _UNITS[unit])


def format_duration(td: timedelta) -> str:
    """Convert a timedelta to a human-readable string like '1d 2h 30m'."""
    total = int(td.total_seconds())
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not days:
        parts.append(f"{seconds}s")
    return " ".join(parts) or "0s"


_ACTION_COLORS: dict[str, discord.Color] = {
    "warn":      discord.Color.yellow(),
    "kick":      discord.Color.orange(),
    "ban":       discord.Color.red(),
    "unban":     discord.Color.green(),
    "timeout":   discord.Color.orange(),
    "untimeout": discord.Color.green(),
}

_ACTION_EMOJIS: dict[str, str] = {
    "warn":      "⚠️",
    "kick":      "👢",
    "ban":       "🔨",
    "unban":     "✅",
    "timeout":   "⏱️",
    "untimeout": "✅",
}


def mod_embed(
    action: str,
    user: discord.abc.User,
    moderator: discord.abc.User,
    reason: Optional[str] = None,
    case_num: Optional[int] = None,
    extra: Optional[str] = None,
) -> discord.Embed:
    """Build a standardised moderation action embed."""
    emoji = _ACTION_EMOJIS.get(action, "🔧")
    color = _ACTION_COLORS.get(action, discord.Color.blurple())
    embed = discord.Embed(title=f"{emoji} {action.title()}", color=color)
    embed.add_field(
        name="User",
        value=f"{user.mention} (`{user}` · {user.id})",
        inline=False,
    )
    embed.add_field(
        name="Moderator",
        value=f"{moderator.mention} (`{moderator}`)",
        inline=False,
    )
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    if extra:
        embed.add_field(name="Details", value=extra, inline=False)
    if case_num is not None:
        embed.set_footer(text=f"Case #{case_num}")
    embed.timestamp = discord.utils.utcnow()
    return embed
