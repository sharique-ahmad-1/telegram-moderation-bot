#!/usr/bin/env python3
"""
Script to post and pin the official announcements to Telegram Channel and Discussion Groups.
"""

import asyncio
import os
import socket
import sys

# Windows UTF-8 console & IPv4 network patch
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
from telegram import Bot

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8987239385:AAH9HGomNJfS4nMCwnjcDfku50kbcOnk7dQ")

CHANNEL_ID = -1003908541243  # Lookism India
GROUP_GC_ID = -1004446541499  # Lookism GC

MSG_CHANNEL = """🔥 **HUGE UPDATE: NEW CHAPTER DROPPING SOON!** 🔥

Get ready everyone! The brand new chapter will be uploaded **every Thursday at sharp 7:20 PM IST**! ⏰⚡

📖 **Available in:**
• **Hinglish Translation** (For that raw, desi vibe! 🇮🇳🔥)
• **English Translation** (Clean & accurate! 🌐✨)

Set your alarms for **7:20 PM every Thursday** and don't miss a single panel! Drop your hype reactions below! 🚀💥"""

MSG_GROUP = """🇮🇳 **WELCOME TO THE OFFICIAL LOOKISM INDIAN DISCUSSION GROUP!** 🇮🇳

This is the ultimate hub exclusively for **Indian fans**! 🔥

💬 **What you can do here:**
• Discuss the **latest chapters** & wild plot twists 📖
• Share your **craziest theories**, predictions & power-scaling debates 🧠⚡
• Vibe and enjoy with fellow Indian readers! 🤝✨

*(Note: Keep the chat clean and respectful—our AI Moderation Bot @lookismchudbot is watching! 🛡️)*

Enjoy the group and let the theories begin! 👇🔥"""


async def main():
    bot = Bot(token=TOKEN)

    print("--- 1. Posting to Lookism India (Official Channel: -1003908541243) ---")
    try:
        m1 = await bot.send_message(chat_id=CHANNEL_ID, text=MSG_CHANNEL, parse_mode="Markdown")
        print(f"✅ Posted announcement in Lookism India (Message ID: {m1.message_id})")
        await bot.pin_chat_message(chat_id=CHANNEL_ID, message_id=m1.message_id)
        print("📌 Pinned announcement in Lookism India!")
    except Exception as e:
        print(f"❌ Error in Lookism India: {e}")

    print("\n--- 2. Posting to Lookism GC (Discussion Group: -1004446541499) ---")
    try:
        m2 = await bot.send_message(chat_id=GROUP_GC_ID, text=MSG_GROUP, parse_mode="Markdown")
        print(f"✅ Posted announcement in Lookism GC (Message ID: {m2.message_id})")
        await bot.pin_chat_message(chat_id=GROUP_GC_ID, message_id=m2.message_id)
        print("📌 Pinned announcement in Lookism GC!")
    except Exception as e:
        print(f"❌ Error in Lookism GC: {e}")


if __name__ == "__main__":
    asyncio.run(main())
