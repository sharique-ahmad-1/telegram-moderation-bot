#!/usr/bin/env python3
"""
Production-Ready Telegram Content Moderation Bot
================================================
Bot Username: @lookismchudbot
Features:
- IPv4 network adapter enforcement for ultra-stable connection.
- Token integration from .env or hardcoded fallback.
- Local AI toxicity & harassment classification (alt-profanity-check, score > 0.75).
- Prohibited bad words and phrases matching via bad_words.txt.
- Unauthorized link and Telegram channel/group invite detection (regex & entity parsing).
- Chat Admin/Owner exemption from moderation.
- Dynamic /addword command restricted to Admins with persistence to bad_words.txt.
- Asynchronous python-telegram-bot (v20+) architecture with structured JSONL audit activity logging.
"""

import asyncio
import datetime
import json
import logging
import os
import re
import socket
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

# Reconfigure stdout/stderr to UTF-8 and line-buffering on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# NETWORK OPTIMIZATION: FORCE IPV4
# ---------------------------------------------------------------------------
# Prevents connection timeouts on environments where IPv6 routing is unsupported/blocked
_original_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


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
from telegram import ChatMember, Update
from telegram.constants import ChatMemberStatus, ChatType, MessageEntityType
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN: str = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8987239385:AAH9HGomNJfS4nMCwnjcDfku50kbcOnk7dQ",
)

# Local AI Toxicity threshold (0.0 to 1.0)
TOXICITY_THRESHOLD: float = float(os.getenv("TOXICITY_THRESHOLD", "0.75"))

# Path to the bad words file
BAD_WORDS_FILE: str = os.getenv("BAD_WORDS_FILE", "bad_words.txt")

# Path to structured activity audit log
ACTIVITY_LOG_FILE: str = os.getenv("ACTIVITY_LOG_FILE", "activity.jsonl")

# Send a short-lived warning message to the chat after deleting a violation
SEND_WARNING_MESSAGE: bool = os.getenv("SEND_WARNING_MESSAGE", "True").lower() in ("true", "1", "yes")

# Duration in seconds before the warning message auto-deletes
WARNING_DELETE_DELAY: int = int(os.getenv("WARNING_DELETE_DELAY", "5"))

# ---------------------------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("moderation_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("ModerationBot")


def log_activity(event_type: str, data: dict) -> None:
    """Appends structured JSON event to activity log for CLI queries."""
    try:
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": event_type,
            **data,
        }
        with open(ACTIVITY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Failed to record activity entry: %s", e)


# ---------------------------------------------------------------------------
# LOCAL AI TOXICITY MODEL INTEGRATION
# ---------------------------------------------------------------------------
_LOCAL_AI_READY = False
try:
    from profanity_check import predict_prob

    _LOCAL_AI_READY = True
    logger.info("Local AI model (alt-profanity-check) loaded successfully.")
except ImportError:
    logger.warning(
        "Package 'alt-profanity-check' is not installed or failed to import. "
        "Local AI toxicity classification will be disabled until installed. "
        "Rule-based filtering and link detection remain fully active."
    )


def evaluate_local_toxicity(text: str) -> Tuple[bool, float]:
    """
    Evaluates text toxicity locally without external API calls.
    Returns (is_toxic, toxicity_score).
    Skips short messages (< 4 words or < 15 characters) to avoid false positives on simple words like 'hi'.
    """
    if not _LOCAL_AI_READY or not text or not text.strip():
        return False, 0.0

    stripped = text.strip()
    words = stripped.split()
    # Do NOT run AI toxicity check on short messages (< 4 words or < 15 characters)
    # Simple words like 'hi', 'ho', 'hello' cause false positives in alt-profanity-check.
    # Bad words are still caught by bad_words.txt.
    if len(words) < 4 or len(stripped) < 15:
        return False, 0.0

    try:
        scores = predict_prob([text])
        score = float(scores[0]) if len(scores) > 0 else 0.0
        is_toxic = score >= TOXICITY_THRESHOLD
        return is_toxic, score
    except Exception as e:
        logger.error("Error during local toxicity evaluation: %s", e)
        return False, 0.0


# ---------------------------------------------------------------------------
# BAD WORDS & LINK DETECTION PATTERNS
# ---------------------------------------------------------------------------
TELEGRAM_INVITE_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:t(?:elegram)?\.(?:me|dog)|telegram\.org)\/(?:\+|joinchat\/|[a-zA-Z0-9_]+)",
    re.IGNORECASE,
)

GENERAL_LINK_REGEX = re.compile(
    r"(?:https?:\/\/|ftp:\/\/|www\.)[^\s/$.?#].[^\s]*",
    re.IGNORECASE,
)

DOMAIN_LINK_REGEX = re.compile(
    r"\b(?:[a-zA-Z0-9-]+\.)+(?:com|org|net|xyz|top|info|site|online|link|click|vip|io|me|app|shop)\b(?:\/[^\s]*)?",
    re.IGNORECASE,
)


class WordFilter:
    """Manages the in-memory bad words list with persistence to file."""

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.words: Set[str] = set()
        self.regex_pattern: Optional[re.Pattern] = None
        self.load()

    def load(self) -> None:
        """Loads bad words from the text file."""
        if not self.filepath.exists():
            logger.warning("Bad words file '%s' not found. Creating empty file.", self.filepath)
            self.filepath.touch(exist_ok=True)

        loaded: Set[str] = set()
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    loaded.add(line.lower())

        self.words = loaded
        self._rebuild_regex()
        logger.info("Loaded %d prohibited word(s)/phrase(s) from '%s'.", len(self.words), self.filepath)

    def _rebuild_regex(self) -> None:
        """Builds a single compiled regex for efficient matching with word boundaries."""
        if not self.words:
            self.regex_pattern = None
            return

        sorted_words = sorted(self.words, key=len, reverse=True)
        escaped_words = [re.escape(w) for w in sorted_words]
        pattern_str = r"(?:\b" + r"\b|\b".join(escaped_words) + r"\b)"
        self.regex_pattern = re.compile(pattern_str, re.IGNORECASE)

    def add_word(self, word: str) -> bool:
        """Adds a new bad word to the list and persists it to file."""
        normalized = word.strip().lower()
        if not normalized or normalized in self.words:
            return False

        self.words.add(normalized)
        self._rebuild_regex()

        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"\n{normalized}")

        logger.info("Added new bad word: '%s'", normalized)
        return True

    def find_violation(self, text: str) -> Optional[str]:
        """Returns the first matched prohibited word/phrase in the text, or None."""
        if not self.regex_pattern or not text:
            return None
        match = self.regex_pattern.search(text)
        return match.group(0) if match else None


# Initialize bad words filter
word_filter = WordFilter(BAD_WORDS_FILE)


# ---------------------------------------------------------------------------
# ADMIN EXEMPTION CHECK
# ---------------------------------------------------------------------------
async def is_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Checks if the sender of the message is a chat Administrator or Creator/Owner.
    Admins are strictly exempt from all content moderation checks.
    Also 100% exempts:
    - Messages automatically forwarded from a linked channel (is_automatic_forward)
    - Telegram Service Notifications (User ID 777000)
    - GroupAnonymousBot (User ID 1087968824)
    - Messages sent on behalf of any channel or the chat itself (sender_chat)
    """
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    if not chat or chat.type == ChatType.PRIVATE:
        return True

    # 1. Automatic forwards from linked channel into discussion group
    if message and getattr(message, "is_automatic_forward", False):
        logger.debug("Message %s is an automatic forward from linked channel. Exempt.", getattr(message, "message_id", "N/A"))
        return True

    # 2. Telegram service notifications & channel forwarder account (ID: 777000)
    if user and user.id == 777000:
        logger.debug("Message %s is from Telegram Service (777000). Exempt.", getattr(message, "message_id", "N/A"))
        return True

    # 3. Anonymous admin bot (ID: 1087968824)
    if user and user.id == 1087968824:
        logger.debug("Message %s is from GroupAnonymousBot. Exempt.", getattr(message, "message_id", "N/A"))
        return True

    # 4. Message sent on behalf of a channel or the chat itself (sender_chat is set)
    if message and message.sender_chat is not None:
        logger.debug("Message %s sent on behalf of chat/channel %s. Exempt.", getattr(message, "message_id", "N/A"), message.sender_chat.id)
        return True

    if not user:
        return False

    try:
        member: ChatMember = await context.bot.get_chat_member(chat_id=chat.id, user_id=user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception as e:
        logger.warning(
            "Failed to fetch chat member status for User ID %s in Chat %s: %s",
            getattr(user, "id", "Unknown"),
            chat.id,
            e,
        )
        return False


# ---------------------------------------------------------------------------
# MODERATION CORE ENGINE
# ---------------------------------------------------------------------------
def check_for_links(message) -> Optional[str]:
    """Scans a message for promotional links or Telegram channel invites."""
    text = (message.text or "") + " " + (message.caption or "")

    invite_match = TELEGRAM_INVITE_REGEX.search(text)
    if invite_match:
        return f"Prohibited Telegram invite link detected: '{invite_match.group(0)}'"

    link_match = GENERAL_LINK_REGEX.search(text) or DOMAIN_LINK_REGEX.search(text)
    if link_match:
        return f"Prohibited external link detected: '{link_match.group(0)}'"

    all_entities = list(message.entities or []) + list(message.caption_entities or [])
    for entity in all_entities:
        if entity.type == MessageEntityType.URL:
            return "Prohibited URL entity detected in message."
        if entity.type == MessageEntityType.TEXT_LINK and entity.url:
            return f"Prohibited hyperlinked URL detected: '{entity.url}'"

    return None


async def moderate_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main moderation handler triggered on incoming/edited messages."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat:
        return

    # Track message in activity log
    log_activity(
        "message_received",
        {
            "chat_id": chat.id,
            "chat_title": chat.title,
            "chat_type": str(chat.type),
            "user_id": user.id if user else None,
            "user_name": user.username if user else None,
            "has_caption": bool(message.caption),
            "snippet": ((message.text or message.caption or "")[:50]).strip(),
        },
    )

    if chat.type == ChatType.PRIVATE:
        return

    # Admin Exemption Check
    if await is_chat_admin(update, context):
        return

    content_text = (message.text or "") + (" " + message.caption if message.caption else "")
    if not content_text.strip():
        return

    user_id = user.id if user else "Anonymous/Channel"
    user_name = f"@{user.username}" if user and user.username else (user.first_name if user else "Unknown")
    chat_title = chat.title or str(chat.id)

    deletion_reason: Optional[str] = None

    # Link & Telegram Invite Check
    link_reason = check_for_links(message)
    if link_reason:
        deletion_reason = link_reason

    # Prohibited Bad Words Check
    if not deletion_reason:
        matched_word = word_filter.find_violation(content_text)
        if matched_word:
            deletion_reason = f"Prohibited bad word/phrase matched: '{matched_word}'"

    # Local AI Toxicity Classification Check
    if not deletion_reason:
        is_toxic, score = evaluate_local_toxicity(content_text)
        if is_toxic:
            deletion_reason = (
                f"Local AI toxicity classification triggered (Score: {score:.2f} >= {TOXICITY_THRESHOLD})"
            )

    # Enforce Deletion
    if deletion_reason:
        await enforce_deletion(
            message=message,
            chat=chat,
            user_id=user_id,
            user_name=user_name,
            chat_title=chat_title,
            reason=deletion_reason,
            snippet=content_text[:80].replace("\n", " "),
            context=context,
        )


async def enforce_deletion(
    message,
    chat,
    user_id,
    user_name: str,
    chat_title: str,
    reason: str,
    snippet: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Deletes the offending message and logs structured audit details."""
    try:
        await message.delete()

        # Structured audit log
        logger.warning(
            "MESSAGE DELETED | Chat: '%s' (ID: %s, Type: %s) | User: %s (ID: %s) | Reason: %s | Snippet: '%s'",
            chat_title,
            chat.id,
            chat.type,
            user_name,
            user_id,
            reason,
            snippet,
        )

        # Log to structured activity file
        log_activity(
            "message_deleted",
            {
                "chat_id": chat.id,
                "chat_title": chat_title,
                "chat_type": str(chat.type),
                "user_id": user_id,
                "user_name": user_name,
                "reason": reason,
                "snippet": snippet,
            },
        )

        # Send temporary warning notice
        if SEND_WARNING_MESSAGE:
            try:
                warning = await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        f"🛡️ **Moderation Action**\n"
                        f"A message from {user_name} was removed.\n"
                        f"**Reason:** {reason}"
                    ),
                    parse_mode="Markdown",
                )

                async def _delete_warning():
                    await asyncio.sleep(WARNING_DELETE_DELAY)
                    try:
                        await warning.delete()
                    except Exception:
                        pass

                asyncio.create_task(_delete_warning())
            except Exception as e:
                logger.debug("Could not send temporary warning notice: %s", e)

    except Forbidden:
        logger.error(
            "PERMISSION ERROR: Bot lacks 'Delete Messages' admin permission in Chat '%s' (ID: %s).",
            chat_title,
            chat.id,
        )
    except BadRequest as e:
        logger.error("Failed to delete message in Chat '%s': %s", chat_title, e)
    except TelegramError as e:
        logger.error("Telegram error occurred while deleting message: %s", e)


# ---------------------------------------------------------------------------
# ADMIN COMMANDS
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /start command."""
    await update.message.reply_text(
        "👋 **Telegram Content Moderation Bot is Active!**\n\n"
        "I protect groups and channels by automatically deleting:\n"
        "• Prohibited promotional links & Telegram channel invites\n"
        "• Blacklisted bad words and phrases\n"
        "• Toxic content, harassment, and hate speech evaluated locally via AI\n\n"
        "👑 **Admins are automatically exempt.**\n"
        "Type /help to see all available admin commands.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /help command with admin setup instructions."""
    help_text = (
        "📖 **Moderation Bot Commands & Setup Guide**\n\n"
        "**Admin Commands:**\n"
        "• `/addword <word or phrase>` - Append a new bad word to the prohibited list.\n"
        "• `/delword <word or phrase>` - Remove a word from the prohibited list.\n"
        "• `/listwords` - View the total count and list of active bad words.\n"
        "• `/testtoxic <text>` - Test the local AI toxicity score on any text sample.\n"
        "• `/help` - Show this help message.\n\n"
        "**Required Permissions for the Bot:**\n"
        "1. Add the bot (@lookismchudbot) to your Group or Channel.\n"
        "2. Promote the bot to **Administrator**.\n"
        "3. Grant the **Delete Messages** permission.\n"
        "4. In @BotFather, disable **Group Privacy Mode** (`/setprivacy -> Disable`) so the bot can inspect all incoming messages."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def cmd_addword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a new prohibited word or phrase."""
    message = update.effective_message
    if not message:
        return

    if not await is_chat_admin(update, context):
        await message.reply_text("⛔ **Access Denied**: Only chat Administrators can add prohibited words.", parse_mode="Markdown")
        return

    if not context.args:
        await message.reply_text("ℹ️ **Usage**: `/addword <word or phrase>`\nExample: `/addword scammer`", parse_mode="Markdown")
        return

    new_word = " ".join(context.args).strip()
    if len(new_word) < 2:
        await message.reply_text("⚠️ The word or phrase must be at least 2 characters long.")
        return

    success = word_filter.add_word(new_word)
    if success:
        await message.reply_text(
            f"✅ **Added to Blacklist**: `'{new_word}'`\n"
            f"Total active prohibited entries: **{len(word_filter.words)}**",
            parse_mode="Markdown",
        )
    else:
        await message.reply_text(
            f"ℹ️ `'{new_word}'` is already present in the prohibited words list.",
            parse_mode="Markdown",
        )


async def cmd_delword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes a prohibited word or phrase."""
    message = update.effective_message
    if not message:
        return

    if not await is_chat_admin(update, context):
        await message.reply_text("⛔ **Access Denied**: Only chat Administrators can remove prohibited words.", parse_mode="Markdown")
        return

    if not context.args:
        await message.reply_text("ℹ️ **Usage**: `/delword <word or phrase>`", parse_mode="Markdown")
        return

    target = " ".join(context.args).strip().lower()
    if target not in word_filter.words:
        await message.reply_text(f"⚠️ `'{target}'` was not found in the prohibited words list.", parse_mode="Markdown")
        return

    word_filter.words.remove(target)
    word_filter._rebuild_regex()

    try:
        with open(word_filter.filepath, "w", encoding="utf-8") as f:
            for w in sorted(word_filter.words):
                f.write(f"{w}\n")
        await message.reply_text(
            f"🗑️ **Removed from Blacklist**: `'{target}'`\n"
            f"Total active prohibited entries: **{len(word_filter.words)}**",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to rewrite bad words file: %s", e)
        await message.reply_text(f"❌ Error updating bad words file: {e}")


async def cmd_listwords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists active prohibited words."""
    if not await is_chat_admin(update, context):
        await update.message.reply_text("⛔ **Access Denied**: Only chat Administrators can view the blacklist.", parse_mode="Markdown")
        return

    total = len(word_filter.words)
    if total == 0:
        await update.message.reply_text("ℹ️ The prohibited words list is currently empty.")
        return

    sample = sorted(list(word_filter.words))[:50]
    preview = ", ".join(f"`{w}`" for w in sample)
    suffix = f"\n\n_...and {total - 50} more._" if total > 50 else ""

    await update.message.reply_text(
        f"📋 **Prohibited Words List** (Total: {total}):\n{preview}{suffix}",
        parse_mode="Markdown",
    )


async def cmd_testtoxic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tests sample text against moderation filters."""
    if not await is_chat_admin(update, context):
        await update.message.reply_text("⛔ **Access Denied**: Only chat Administrators can use test commands.", parse_mode="Markdown")
        return

    if not context.args:
        await update.message.reply_text("ℹ️ **Usage**: `/testtoxic <text to test>`", parse_mode="Markdown")
        return

    sample = " ".join(context.args)
    is_toxic, score = evaluate_local_toxicity(sample)
    matched_word = word_filter.find_violation(sample)
    link_violation = (
        bool(TELEGRAM_INVITE_REGEX.search(sample))
        or bool(GENERAL_LINK_REGEX.search(sample))
        or bool(DOMAIN_LINK_REGEX.search(sample))
    )

    response = (
        f"🧪 **Moderation Test Result**\n\n"
        f"**Sample:** _{sample}_\n\n"
        f"• **AI Toxicity Score:** `{score:.4f}` / 1.00 (Threshold: `{TOXICITY_THRESHOLD}`)\n"
        f"• **AI Status:** {'🚨 **VIOLATION (TOXIC)**' if is_toxic else '✅ Clean'}\n"
        f"• **Bad Word Match:** {f'🚨 Matched `{matched_word}`' if matched_word else '✅ None'}\n"
        f"• **Link/Invite Match:** {'🚨 Detected link' if link_violation else '✅ None'}\n"
    )
    await update.message.reply_text(response, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# RENDER FREE TIER CLOUD WEB SERVICE HEALTH-CHECK SERVER
# ---------------------------------------------------------------------------
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx

PORT: int = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL: Optional[str] = os.getenv("RENDER_EXTERNAL_URL")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Answers HTTP requests from Render to confirm the Web Service is healthy."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "service": "Telegram Moderation Bot", "bot": "@lookismchudbot"}')

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_server(port: int = PORT) -> None:
    """Runs a minimal HTTP server in a daemon thread for Render Cloud deployments."""
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("Cloud Health-Check HTTP server is running on 0.0.0.0:%d", port)
    except Exception as e:
        logger.warning("Could not start HTTP health server on port %d: %s", port, e)


async def keep_alive_self_ping() -> None:
    """Keeps the Render free web service alive by pinging its external URL every 10 minutes."""
    if not RENDER_EXTERNAL_URL:
        return

    logger.info("Keep-alive self-ping task active for URL: %s", RENDER_EXTERNAL_URL)
    while True:
        await asyncio.sleep(600)  # Ping every 10 minutes
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(RENDER_EXTERNAL_URL)
                logger.debug("Self-ping response: %d", res.status_code)
        except Exception as e:
            logger.debug("Self-ping attempt: %s", e)


# ---------------------------------------------------------------------------
# APPLICATION ENTRYPOINT
# ---------------------------------------------------------------------------
def main() -> None:
    """Builds and runs the Telegram moderation bot."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("YOUR_"):
        logger.critical(
            "ERROR: Telegram Bot Token is missing or invalid. "
            "Please configure TELEGRAM_BOT_TOKEN in .env or bot.py."
        )
        sys.exit(1)

    logger.info("Initializing Telegram Content Moderation Bot...")
    logger.info("Local AI Status: %s", "ENABLED (alt-profanity-check)" if _LOCAL_AI_READY else "DISABLED")
    logger.info("Toxicity Threshold: %.2f", TOXICITY_THRESHOLD)
    logger.info("Total Prohibited Words: %d", len(word_filter.words))

    # Start Cloud Health Server (Render Web Service compatibility)
    start_health_server(PORT)

    async def on_startup(application: Application) -> None:
        me = await application.bot.get_me()
        logger.info("Bot authenticated as: %s (@%s, ID: %s)", me.first_name, me.username, me.id)
        logger.info("Polling is active. Listening for messages and commands...")
        print(f"\n============================================================", flush=True)
        print(f"TELEGRAM MODERATION BOT IS LIVE! (@{me.username})", flush=True)
        print(f"Status: Polling active | Local AI: Ready | Bad Words: {len(word_filter.words)}", flush=True)
        print(f"============================================================\n", flush=True)

        # Start background keep-alive ping if deployed on Render
        if RENDER_EXTERNAL_URL:
            asyncio.create_task(keep_alive_self_ping())

    # Build Application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(on_startup).build()

    # Register Admin Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("addword", cmd_addword))
    app.add_handler(CommandHandler("delword", cmd_delword))
    app.add_handler(CommandHandler("listwords", cmd_listwords))
    app.add_handler(CommandHandler("testtoxic", cmd_testtoxic))

    # Register Content Moderation Message Handlers
    message_filter = (filters.TEXT | filters.CAPTION) & (~filters.COMMAND)
    app.add_handler(MessageHandler(message_filter, moderate_content))

    logger.info("Bot is starting polling. Ready to moderate channels and groups!")
    print(">>> TELEGRAM MODERATION BOT IS STARTING POLLING <<<", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
