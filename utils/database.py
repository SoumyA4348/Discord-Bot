import aiosqlite
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "moderation.db"
)


async def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS warnings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id      INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                moderator_id  INTEGER NOT NULL,
                reason        TEXT    NOT NULL,
                timestamp     TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cases (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id      INTEGER NOT NULL,
                case_num      INTEGER NOT NULL,
                action        TEXT    NOT NULL,
                user_id       INTEGER NOT NULL,
                moderator_id  INTEGER NOT NULL,
                reason        TEXT,
                timestamp     TEXT    NOT NULL,
                UNIQUE(guild_id, case_num)
            );

            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id          INTEGER PRIMARY KEY,
                mod_log_channel   INTEGER,
                word_filter       TEXT    DEFAULT '[]',
                antiinvite        INTEGER DEFAULT 0,
                antispam          INTEGER DEFAULT 1,
                warn_threshold    INTEGER DEFAULT 3,
                warn_action       TEXT    DEFAULT 'kick'
            );

            CREATE TABLE IF NOT EXISTS giveaways (
                message_id       INTEGER PRIMARY KEY,
                channel_id       INTEGER NOT NULL,
                guild_id         INTEGER NOT NULL,
                prize            TEXT    NOT NULL,
                winners_count    INTEGER DEFAULT 1,
                sponsor          TEXT,
                requirements     TEXT,
                ends_at          TEXT    NOT NULL,
                ended            INTEGER DEFAULT 0,
                host_id          INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS giveaway_entries (
                message_id       INTEGER NOT NULL,
                user_id          INTEGER NOT NULL,
                PRIMARY KEY (message_id, user_id)
            );
        """)
        await db.commit()


# ── Warnings ─────────────────────────────────────────────────────────────────

async def add_warning(
    guild_id: int, user_id: int, moderator_id: int, reason: str
) -> int:
    ts = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, ts),
        )
        await db.commit()
        return cursor.lastrowid


async def get_warnings(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id",
            (guild_id, user_id),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def delete_warning(warning_id: int, guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM warnings WHERE id=? AND guild_id=?", (warning_id, guild_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def clear_warnings(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM warnings WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )
        await db.commit()
        return cur.rowcount


# ── Cases ─────────────────────────────────────────────────────────────────────

async def add_case(
    guild_id: int,
    action: str,
    user_id: int,
    moderator_id: int,
    reason: Optional[str],
) -> int:
    """Insert a case and return its case number.

    Retries on UNIQUE constraint violations caused by concurrent inserts
    reading the same MAX(case_num) at the same time.
    """
    ts = datetime.now(timezone.utc).isoformat()
    for _ in range(10):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT COALESCE(MAX(case_num), 0) + 1 FROM cases WHERE guild_id=?",
                    (guild_id,),
                ) as cur:
                    (case_num,) = await cur.fetchone()
                await db.execute(
                    "INSERT INTO cases "
                    "(guild_id, case_num, action, user_id, moderator_id, reason, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (guild_id, case_num, action, user_id, moderator_id, reason, ts),
                )
                await db.commit()
                return case_num
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError(f"add_case: failed to insert after 10 retries (guild {guild_id})")


async def get_case(guild_id: int, case_num: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cases WHERE guild_id=? AND case_num=?", (guild_id, case_num)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_cases(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cases WHERE guild_id=? AND user_id=? ORDER BY case_num",
            (guild_id, user_id),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


# ── Guild Config ──────────────────────────────────────────────────────────────

def _default_config(guild_id: int) -> Dict[str, Any]:
    """Return a fresh default config dict — never share a mutable list across callers."""
    return {
        "guild_id": guild_id,
        "mod_log_channel": None,
        "word_filter": [],       # new list every call — safe to mutate
        "antiinvite": 0,
        "antispam": 1,
        "warn_threshold": 3,
        "warn_action": "kick",
    }


async def _ensure_config(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,)
        )
        await db.commit()


async def get_config(guild_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                d = dict(row)
                d["word_filter"] = json.loads(d["word_filter"] or "[]")
                return d
            return _default_config(guild_id)


async def set_config(guild_id: int, **kwargs: Any) -> None:
    if "word_filter" in kwargs:
        kwargs["word_filter"] = json.dumps(kwargs["word_filter"])
    await _ensure_config(guild_id)
    if not kwargs:
        return
    set_clause = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [guild_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE guild_config SET {set_clause} WHERE guild_id=?", values
        )
        await db.commit()


# ── Giveaways ────────────────────────────────────────────────────────────────

async def create_giveaway(
    message_id: int,
    channel_id: int,
    guild_id: int,
    prize: str,
    winners_count: int,
    sponsor: Optional[str],
    requirements: Optional[str],
    ends_at: str,
    host_id: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO giveaways "
            "(message_id, channel_id, guild_id, prize, winners_count, sponsor, requirements, ends_at, ended, host_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (message_id, channel_id, guild_id, prize, winners_count, sponsor, requirements, ends_at, host_id),
        )
        await db.commit()


async def get_giveaway(message_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM giveaways WHERE message_id=?", (message_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_active_giveaways() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM giveaways WHERE ended=0 ORDER BY ends_at ASC"
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_guild_giveaways(guild_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM giveaways WHERE guild_id=?"
        if active_only:
            query += " AND ended=0"
        query += " ORDER BY ends_at ASC"
        async with db.execute(query, (guild_id,)) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def end_giveaway_db(message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE giveaways SET ended=1 WHERE message_id=?", (message_id,)
        )
        await db.commit()


async def toggle_giveaway_entry(message_id: int, user_id: int) -> bool:
    """Toggle a user's entry in a giveaway. Returns True if entered, False if left."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM giveaway_entries WHERE message_id=? AND user_id=?",
            (message_id, user_id),
        ) as cur:
            exists = await cur.fetchone()

        if exists:
            await db.execute(
                "DELETE FROM giveaway_entries WHERE message_id=? AND user_id=?",
                (message_id, user_id),
            )
            await db.commit()
            return False
        else:
            await db.execute(
                "INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)",
                (message_id, user_id),
            )
            await db.commit()
            return True


async def get_giveaway_entries(message_id: int) -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM giveaway_entries WHERE message_id=?", (message_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_giveaway_entry_count(message_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM giveaway_entries WHERE message_id=?", (message_id,)
        ) as cur:
            (count,) = await cur.fetchone()
            return count

