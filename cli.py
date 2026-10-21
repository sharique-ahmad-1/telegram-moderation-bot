#!/usr/bin/env python3
"""
Telegram Bot Remote Control & Administration CLI
=================================================
Allows instant command-line execution of Telegram actions:
- Send messages & broadcast announcements (with optional pinning)
- Ban, kick, unban, mute, and unmute users
- Inspect chat information, member counts, and admin lists
- Query recent group activity and deleted messages
- Inspect bot status and connectivity

Token: 8987239385:AAH9HGomNJfS4nMCwnjcDfku50kbcOnk7dQ
"""

import argparse
import asyncio
import datetime
import json
import os
import socket
import sys
from pathlib import Path
from typing import Optional

# Reconfigure stdout/stderr to UTF-8 on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# FORCE IPV4 SOCKET RESOLUTION
# ---------------------------------------------------------------------------
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_getaddrinfo

try:
    import anyio._backends._asyncio

    _orig_anyio_getaddrinfo = anyio._backends._asyncio.AsyncIOBackend.getaddrinfo

    async def _ipv4_anyio_getaddrinfo(self, *args, **kwargs):
        kwargs["family"] = socket.AF_INET
        return await _orig_anyio_getaddrinfo(self, *args, **kwargs)

    anyio._backends._asyncio.AsyncIOBackend.getaddrinfo = _ipv4_anyio_getaddrinfo
except Exception:
    pass

from dotenv import load_dotenv
from telegram import Bot, ChatPermissions
from telegram.error import BadRequest, TelegramError

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8987239385:AAH9HGomNJfS4nMCwnjcDfku50kbcOnk7dQ")
ACTIVITY_LOG_FILE = os.getenv("ACTIVITY_LOG_FILE", "activity.jsonl")
BAD_WORDS_FILE = os.getenv("BAD_WORDS_FILE", "bad_words.txt")

# Named Chat Aliases for easy CLI reference
CHAT_ALIASES = {
    # 1. Official Channel: Lookism India
    "lookism_india": os.getenv("CHANNEL_LOOKISM_INDIA", "-1003908541243"),
    "channel": os.getenv("CHANNEL_LOOKISM_INDIA", "-1003908541243"),
    "official_channel": os.getenv("CHANNEL_LOOKISM_INDIA", "-1003908541243"),

    # 2. Linked Channel Discussion Group: Lookism GC
    "lookism_gc": os.getenv("GROUP_LOOKISM_GC", "-1004446541499"),
    "gc": os.getenv("GROUP_LOOKISM_GC", "-1004446541499"),
    "discussion": os.getenv("GROUP_LOOKISM_GC", "-1004446541499"),
    "linked_gc": os.getenv("GROUP_LOOKISM_GC", "-1004446541499"),

    # 3. Main Indian Discussion Group: Lookism Official GC India
    "lookism_official_gc": os.getenv("GROUP_LOOKISM_OFFICIAL_GC", ""),
    "official_gc": os.getenv("GROUP_LOOKISM_OFFICIAL_GC", ""),
    "main_gc": os.getenv("GROUP_LOOKISM_OFFICIAL_GC", ""),
    "main_group": os.getenv("GROUP_LOOKISM_OFFICIAL_GC", ""),
}


def resolve_chat_id(target: str) -> str:
    """Resolves named aliases like 'channel', 'gc', 'lookism_india' to numeric IDs."""
    key = target.lower().strip()
    if key in CHAT_ALIASES and CHAT_ALIASES[key]:
        return CHAT_ALIASES[key]
    return target


def get_bot() -> Bot:
    return Bot(token=TOKEN)


# ---------------------------------------------------------------------------
# ACTIONS
# ---------------------------------------------------------------------------
async def action_status() -> None:
    """Checks bot identity and connection."""
    bot = get_bot()
    me = await bot.get_me()
    print("=" * 60)
    print("TELEGRAM BOT STATUS")
    print("=" * 60)
    print(f"• Bot Name:       {me.first_name}")
    print(f"• Bot Username:   @{me.username}")
    print(f"• Bot ID:         {me.id}")
    print(f"• Can Join Groups:{me.can_join_groups}")
    print(f"• Read All Group: {not me.can_read_all_group_messages} (Privacy Mode: {'ON' if not me.can_read_all_group_messages else 'OFF/Disabled'})")
    print(f"• Supports Inline:{me.supports_inline_queries}")
    print(f"• API Status:     CONNECTED (Healthy)")
    print("=" * 60)
    print("CONFIGURED CHATS:")
    for alias, cid in [("Official Channel (Lookism India)", CHAT_ALIASES["lookism_india"]),
                       ("Linked Discussion (Lookism GC)", CHAT_ALIASES["lookism_gc"]),
                       ("Main Discussion (Lookism Official GC India)", CHAT_ALIASES["main_gc"] or "(Pending)")]:
        print(f"• {alias}: {cid}")
    print("=" * 60)


async def action_send(chat_id: str, text: str, pin: bool = False, parse_mode: str = "Markdown") -> None:
    """Sends a message to a chat/channel and optionally pins it."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    msg = None
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode if parse_mode != "None" else None,
        )
    except BadRequest as e:
        if "can't parse entities" in str(e).lower():
            # Fallback to plain text if Markdown parsing fails
            msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
        else:
            print(f"❌ Failed to send message: {e}")
            sys.exit(1)
    except TelegramError as e:
        print(f"❌ Failed to send message: {e}")
        sys.exit(1)

    print(f"✅ Message sent successfully! (Message ID: {msg.message_id}, Chat: {chat_id})")

    if pin and msg:
        try:
            await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=False)
            print(f"📌 Message {msg.message_id} pinned successfully!")
        except Exception as e:
            print(f"⚠️ Message sent, but could not pin: {e}")


async def action_announce(channel: str, text: str, pin: bool = True, silent: bool = False) -> None:
    """Posts an announcement to a channel or group."""
    channel = resolve_chat_id(channel)
    bot = get_bot()
    msg = None
    try:
        msg = await bot.send_message(
            chat_id=channel,
            text=text,
            parse_mode="Markdown",
            disable_notification=silent,
        )
    except BadRequest as e:
        if "can't parse entities" in str(e).lower():
            # Fallback to unparsed text if markdown entities are malformed
            msg = await bot.send_message(chat_id=channel, text=text, parse_mode=None, disable_notification=silent)
        else:
            print(f"❌ Failed to post announcement: {e}")
            sys.exit(1)
    except TelegramError as e:
        print(f"❌ Failed to post announcement: {e}")
        sys.exit(1)

    print(f"📢 Announcement posted to {channel} (Message ID: {msg.message_id})")

    if pin and msg:
        try:
            await bot.pin_chat_message(chat_id=channel, message_id=msg.message_id, disable_notification=silent)
            print(f"📌 Announcement pinned in {channel}!")
        except Exception as e:
            print(f"⚠️ Sent announcement, but could not pin: {e}")


async def action_ban(chat_id: str, user_id: int, revoke_messages: bool = False, until_minutes: Optional[int] = None) -> None:
    """Bans a user from a chat."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    until_date = None
    if until_minutes:
        until_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=until_minutes)

    try:
        await bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date,
            revoke_messages=revoke_messages,
        )
        duration_msg = f"for {until_minutes} minutes" if until_minutes else "permanently"
        print(f"🔨 User {user_id} has been banned {duration_msg} from Chat {chat_id}.")
    except TelegramError as e:
        print(f"❌ Failed to ban user {user_id}: {e}")
        sys.exit(1)


async def action_unban(chat_id: str, user_id: int) -> None:
    """Unbans a user from a chat."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    try:
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        print(f"🕊️ User {user_id} has been unbanned in Chat {chat_id}.")
    except TelegramError as e:
        print(f"❌ Failed to unban user {user_id}: {e}")
        sys.exit(1)


async def action_kick(chat_id: str, user_id: int) -> None:
    """Kicks a user by banning and immediately unbanning."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        print(f"👢 User {user_id} kicked from Chat {chat_id}.")
    except TelegramError as e:
        print(f"❌ Failed to kick user {user_id}: {e}")
        sys.exit(1)


async def action_mute(chat_id: str, user_id: int, minutes: int = 60) -> None:
    """Mutes a user (restricts sending messages)."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    until_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date,
        )
        print(f"🔇 User {user_id} muted in Chat {chat_id} for {minutes} minutes.")
    except TelegramError as e:
        print(f"❌ Failed to mute user {user_id}: {e}")
        sys.exit(1)


async def action_unmute(chat_id: str, user_id: int) -> None:
    """Unmutes a user, restoring standard member permissions."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    try:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=permissions)
        print(f"🔊 User {user_id} unmuted in Chat {chat_id}.")
    except TelegramError as e:
        print(f"❌ Failed to unmute user {user_id}: {e}")
        sys.exit(1)


async def action_chat_info(chat_id: str) -> None:
    """Displays information about a chat or channel."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    try:
        chat = await bot.get_chat(chat_id=chat_id)
        member_count = None
        try:
            member_count = await bot.get_chat_member_count(chat_id=chat_id)
        except Exception:
            pass

        print("=" * 60)
        print(f"CHAT INFORMATION: {chat.title or chat.username or chat.id}")
        print("=" * 60)
        print(f"• Title:        {chat.title}")
        print(f"• ID:           {chat.id}")
        print(f"• Type:         {chat.type}")
        print(f"• Username:     @{chat.username}" if chat.username else "• Username:     None (Private)")
        print(f"• Members:      {member_count if member_count is not None else 'N/A'}")
        print(f"• Description:  {chat.description or 'None'}")
        print(f"• Invite Link:  {chat.invite_link or 'None'}")
        print("=" * 60)
    except TelegramError as e:
        print(f"❌ Failed to fetch chat info for {chat_id}: {e}")
        sys.exit(1)


async def action_admins(chat_id: str) -> None:
    """Lists all administrators for a chat."""
    chat_id = resolve_chat_id(chat_id)
    bot = get_bot()
    try:
        admins = await bot.get_chat_administrators(chat_id=chat_id)
        print("=" * 60)
        print(f"ADMINISTRATORS IN CHAT {chat_id} (Total: {len(admins)})")
        print("=" * 60)
        for idx, adm in enumerate(admins, start=1):
            u = adm.user
            status = adm.status
            custom_title = getattr(adm, "custom_title", None)
            title_str = f" [{custom_title}]" if custom_title else ""
            print(f"{idx}. {u.first_name} (@{u.username or 'NoUsername'}, ID: {u.id}) - {status.upper()}{title_str}")
        print("=" * 60)
    except TelegramError as e:
        print(f"❌ Failed to fetch admins for {chat_id}: {e}")
        sys.exit(1)


def action_activity(limit: int = 20, event_filter: Optional[str] = None) -> None:
    """Reads recent moderation activity from activity.jsonl or logs."""
    log_file = Path(ACTIVITY_LOG_FILE)
    if not log_file.exists():
        # Fallback to moderation_bot.log
        mod_log = Path("moderation_bot.log")
        if mod_log.exists():
            print(f"Recent lines from moderation_bot.log:")
            lines = mod_log.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-limit:]:
                print(line)
        else:
            print("ℹ️ No activity log entries recorded yet.")
        return

    records = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    if event_filter:
        records = [r for r in records if r.get("event") == event_filter]

    records = records[-limit:]

    print("=" * 70)
    print(f"RECENT GROUP ACTIVITY & MODERATION EVENTS (Showing last {len(records)})")
    print("=" * 70)
    for r in records:
        ts = r.get("timestamp", "")
        ev = r.get("event", "event")
        chat = r.get("chat_title", r.get("chat_id", "Unknown Chat"))
        user = r.get("user_name", r.get("user_id", "Unknown User"))

        if ev == "message_deleted":
            reason = r.get("reason", "N/A")
            snippet = r.get("snippet", "")
            print(f"[{ts[:19]}] 🚨 DELETED in '{chat}' | User: {user} | Reason: {reason} | Text: '{snippet}'")
        elif ev == "message_received":
            snippet = r.get("snippet", "")
            print(f"[{ts[:19]}] 💬 Message in '{chat}' | From: {user} | '{snippet}'")
        else:
            print(f"[{ts[:19]}] {ev} | {r}")
    print("=" * 70)


def action_words(subcmd: str, word: Optional[str] = None) -> None:
    """Manages the bad words list."""
    filepath = Path(BAD_WORDS_FILE)
    words = []
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            words = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]

    if subcmd == "list":
        print(f"📋 Total prohibited words: {len(words)}")
        for idx, w in enumerate(sorted(words), start=1):
            print(f"{idx:3d}. {w}")
    elif subcmd == "add":
        if not word:
            print("❌ Please specify a word to add.")
            sys.exit(1)
        w_clean = word.strip().lower()
        if w_clean in words:
            print(f"ℹ️ '{w_clean}' is already in {BAD_WORDS_FILE}")
            return
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"\n{w_clean}")
        print(f"✅ Added '{w_clean}' to {BAD_WORDS_FILE} (Total: {len(words) + 1})")
    elif subcmd == "del":
        if not word:
            print("❌ Please specify a word to remove.")
            sys.exit(1)
        w_clean = word.strip().lower()
        if w_clean not in words:
            print(f"⚠️ '{w_clean}' was not found in {BAD_WORDS_FILE}")
            return
        words.remove(w_clean)
        with open(filepath, "w", encoding="utf-8") as f:
            for item in sorted(words):
                f.write(f"{item}\n")
        print(f"🗑️ Removed '{w_clean}' from {BAD_WORDS_FILE} (Total: {len(words)})")


# ---------------------------------------------------------------------------
# CLI PARSER
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Telegram Bot Control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="Check bot connection and identity")

    # send
    p_send = subparsers.add_parser("send", help="Send a message to a chat/channel")
    p_send.add_argument("--chat-id", required=True, help="Target chat ID or @channelusername")
    p_send.add_argument("--text", required=True, help="Message text to send")
    p_send.add_argument("--pin", action="store_true", help="Pin the message after sending")
    p_send.add_argument("--parse-mode", default="Markdown", choices=["Markdown", "HTML", "None"], help="Parse mode")

    # announce
    p_ann = subparsers.add_parser("announce", help="Broadcast an announcement and optionally pin")
    p_ann.add_argument("--channel", required=True, help="Channel ID (e.g. -100...) or @username")
    p_ann.add_argument("--text", required=True, help="Announcement text")
    p_ann.add_argument("--no-pin", action="store_true", help="Do not pin the announcement")
    p_ann.add_argument("--silent", action="store_true", help="Send silently without notification")

    # ban
    p_ban = subparsers.add_parser("ban", help="Ban a user from a chat")
    p_ban.add_argument("--chat-id", required=True, help="Chat ID")
    p_ban.add_argument("--user-id", type=int, required=True, help="User ID to ban")
    p_ban.add_argument("--revoke-messages", action="store_true", help="Delete all past messages of user")
    p_ban.add_argument("--minutes", type=int, default=None, help="Ban duration in minutes (default: permanent)")

    # unban
    p_unban = subparsers.add_parser("unban", help="Unban a user")
    p_unban.add_argument("--chat-id", required=True, help="Chat ID")
    p_unban.add_argument("--user-id", type=int, required=True, help="User ID")

    # kick
    p_kick = subparsers.add_parser("kick", help="Kick a user (ban and unban)")
    p_kick.add_argument("--chat-id", required=True, help="Chat ID")
    p_kick.add_argument("--user-id", type=int, required=True, help="User ID to kick")

    # mute
    p_mute = subparsers.add_parser("mute", help="Mute/restrict a user")
    p_mute.add_argument("--chat-id", required=True, help="Chat ID")
    p_mute.add_argument("--user-id", type=int, required=True, help="User ID to mute")
    p_mute.add_argument("--minutes", type=int, default=60, help="Mute duration in minutes (default: 60)")

    # unmute
    p_unmute = subparsers.add_parser("unmute", help="Unmute a user")
    p_unmute.add_argument("--chat-id", required=True, help="Chat ID")
    p_unmute.add_argument("--user-id", type=int, required=True, help="User ID")

    # chat-info
    p_info = subparsers.add_parser("chat-info", help="Get chat metadata")
    p_info.add_argument("--chat-id", required=True, help="Chat ID or @channel")

    # admins
    p_adm = subparsers.add_parser("admins", help="Get list of chat administrators")
    p_adm.add_argument("--chat-id", required=True, help="Chat ID")

    # activity
    p_act = subparsers.add_parser("activity", help="Show recent moderation/group activity")
    p_act.add_argument("--limit", type=int, default=20, help="Number of entries")
    p_act.add_argument("--event", default=None, choices=["message_deleted", "message_received"], help="Filter by event")

    # words
    p_words = subparsers.add_parser("words", help="Manage prohibited words")
    p_words.add_argument("action", choices=["list", "add", "del"], help="Action to perform")
    p_words.add_argument("word", nargs="?", default=None, help="Word to add or delete")

    args = parser.parse_args()

    if args.command == "status":
        asyncio.run(action_status())
    elif args.command == "send":
        asyncio.run(action_send(args.chat_id, args.text, pin=args.pin, parse_mode=args.parse_mode))
    elif args.command == "announce":
        asyncio.run(action_announce(args.channel, args.text, pin=not args.no_pin, silent=args.silent))
    elif args.command == "ban":
        asyncio.run(action_ban(args.chat_id, args.user_id, revoke_messages=args.revoke_messages, until_minutes=args.minutes))
    elif args.command == "unban":
        asyncio.run(action_unban(args.chat_id, args.user_id))
    elif args.command == "kick":
        asyncio.run(action_kick(args.chat_id, args.user_id))
    elif args.command == "mute":
        asyncio.run(action_mute(args.chat_id, args.user_id, minutes=args.minutes))
    elif args.command == "unmute":
        asyncio.run(action_unmute(args.chat_id, args.user_id))
    elif args.command == "chat-info":
        asyncio.run(action_chat_info(args.chat_id))
    elif args.command == "admins":
        asyncio.run(action_admins(args.chat_id))
    elif args.command == "activity":
        action_activity(limit=args.limit, event_filter=args.event)
    elif args.command == "words":
        action_words(args.action, args.word)


if __name__ == "__main__":
    main()
