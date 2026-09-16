# Alteristics

A modular, asynchronous Discord community and moderation suite built with `discord.py` and SQLite. Features multi-tier moderation with persistent cases, automated spam/link filtering, interactive button-driven giveaways, and real-time multilingual translation.

## Features

### Moderation
| Command | Description |
|---|---|
| `!warn @user [reason]` | Warn a member. Auto-kicks/bans at the configured threshold. |
| `!warnings @user` | View a member's full warning history. |
| `!clearwarnings @user` | Clear all warnings for a member. |
| `!delwarn <id>` | Delete a single warning by its ID. |
| `!kick @user [reason]` | Kick a member (sends a DM with the reason). |
| `!ban @user [reason]` | Ban by mention or numeric ID (works for non-members too). |
| `!unban <user_id> [reason]` | Unban a user. |
| `!timeout @user <dur> [reason]` | Timeout a member (`10m`, `2h`, `7d`, max `28d`). |
| `!removetimeout @user` | Remove an active timeout (`!unmute` also works). |
| `!case <num>` | Look up a moderation case by number. |
| `!cases @user` | Show all cases for a member. |

### Auto-Mod (staff-exempt)
| Command | Description |
|---|---|
| `!antispam on/off` | Toggle spam detection (5+ msgs in 5 s -> 5 min timeout). |
| `!antiinvite on/off` | Block Discord invite links automatically. |
| `!addword <word>` | Add a word to the filter (auto-deletes & warns on match). |
| `!removeword <word>` | Remove a word from the filter. |
| `!wordlist` | List all filtered words. |
| `!warnthreshold <n> <kick\|ban\|none>` | Set the warning count that triggers auto-escalation. |

### Utility
| Command | Description |
|---|---|
| `!clear <n>` | Bulk-delete up to 100 messages. |
| `!slowmode <sec>` | Set channel slowmode (0 disables it). |
| `!lockdown [reason]` | Prevent @everyone from sending in the channel. |
| `!unlock` | Restore send-message permissions. |
| `!setmodlog #channel` | Set the channel where all mod actions are logged. |
| `!userinfo [@user]` | Show member info including warnings and cases. |
| `!serverinfo` | Show server statistics. |

### Translation
| Command | Description |
|---|---|
| `!translate <text>` | Translate text to English. |
| `!translate to <lang> <text>` | Translate to any supported language. |
| `!languages` | List all supported language names. |
| Auto | Every non-English message is translated inline. |

### Giveaways (staff)
| Command | Description |
|---|---|
| `!gcreate` | Interactive wizard to customize prize, sponsor, requirements, duration & pings. |
| `!gstart <dur> [winners] <prize>` | Quick launch a giveaway (e.g. `!gstart 24h 1 Nitro`). |
| `!gend <message_id>` | Manually end an active giveaway and auto-roll immediately. |
| `!greroll <message_id> [winners]` | Pick new winner(s) from previous entries. |
| `!glist` | List active giveaways running in the server. |
| Button Entry | Members click `Participate` to enter/leave; entry count updates live and persists across restarts. |

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# then edit .env and paste your bot token
```

### 3. Discord Developer Portal
In your application's **Bot** settings, enable these **Privileged Gateway Intents**:
- Server Members Intent
- Message Content Intent

### 4. Bot permissions
When generating an invite link, select at minimum:
- Read Messages / View Channels
- Send Messages
- Manage Messages
- Kick Members
- Ban Members
- Moderate Members (for timeouts)
- Manage Channels (for lockdown/slowmode)
- Read Message History

### 5. Run
```bash
python bot.py
```

### 6. First-time server config (optional)
```
!setmodlog #mod-log          # all actions will be logged here
!warnthreshold 3 kick        # auto-kick after 3 warnings (default)
!antispam on                 # enabled by default
```

## Project Structure
```
Alteristics/
├── bot.py                   # entry point & cog loader
├── cogs/
│   ├── moderation.py        # warn, kick, ban, timeout, cases
│   ├── automod.py           # spam, word filter, invite blocking
│   ├── giveaway.py          # interactive wizard, button entry, auto-roll
│   ├── translator.py        # auto-translate + manual translate
│   ├── utility.py           # clear, slowmode, lockdown, info, help
│   └── fake_nuke.py         # visual prank simulation (owner-only)
├── utils/
│   ├── database.py          # aiosqlite helpers (warnings, cases, giveaways)
│   └── helpers.py           # duration parsing, embed builder
├── data/                    # SQLite DB (auto-created, git-ignored)
├── .env.example
└── requirements.txt
```

## Tech Stack
Python 3.10+ · discord.py 2.x · aiosqlite · AsyncIO · googletrans · python-dotenv
