# 🛡️ Production-Ready Telegram Moderation Bot

A high-performance, asynchronous Telegram Content Moderation Bot built with **Python 3**, [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) (v20+), and local AI classification. It monitors Telegram channels and groups to instantly purge spam, unauthorized invite links, prohibited keywords, and toxic/harassing content without depending on third-party cloud APIs (like OpenAI or Gemini).

---

## 🚀 Key Features

1. **Local AI Toxicity & Harassment Classification**:
   - Uses `alt-profanity-check` (a fast, offline linear SVM model trained on large toxicity datasets) to score content locally.
   - Evaluates messages with zero external API calls or latency overhead.
   - Automatically deletes messages scoring **>= 0.75**.

2. **Prohibited Bad Words & Blacklist Engine**:
   - Reads keywords and phrases from `bad_words.txt`.
   - Uses regex with word-boundary awareness (`\bword\b`) to prevent false positives (e.g., won't flag `classic` for `ass`).
   - Supports multi-word phrases (e.g., `free crypto`, `join my channel`).

3. **Promotional Links & Telegram Invite Detection**:
   - Scans text, captions, and Telegram's native URL entities (`MessageEntityType.URL` and `MessageEntityType.TEXT_LINK`).
   - Detects Telegram channel/group invites (`t.me/...`, `telegram.me/...`, `telegram.dog/...`).
   - Catches raw URLs and hidden hyperlinked markdown text.

4. **Chat Admin & Owner Exemption**:
   - Automatically queries chat member permissions via `get_chat_member`.
   - Chat Administrators and Owners are strictly exempt from moderation filters.
   - Channel owners and anonymous group admins posting as the chat are also recognized and exempt.

5. **Dynamic In-Chat Admin Management**:
   - Admins can dynamically add new prohibited words with `/addword <word or phrase>`.
   - Changes update in-memory regex immediately and append to `bad_words.txt` for persistent storage.

6. **Audit Logging & Ephemeral Warnings**:
   - Detailed structured logs output to console and `moderation_bot.log` recording Chat ID, Chat Title, User ID, Username, and exact deletion reason.
   - Sends a 5-second self-destructing warning notification in chat so users understand why a message was removed without cluttering the chat history.

---

## 📁 Project Structure

```text
├── bot.py               # Main bot application and moderation logic
├── requirements.txt     # Python package dependencies
├── bad_words.txt        # Prohibited words and phrases list
├── .env                 # Environment variables & bot credentials
├── .env.example         # Example configuration template
├── moderation_bot.log   # Runtime audit and error log (auto-generated)
└── README.md            # Setup documentation & operational guide
```

---

## ⚙️ Prerequisites & Setup

### 1. Telegram Bot Father Settings (Critical!)

By default, Telegram bots cannot see regular member messages in groups due to **Group Privacy Mode**.
To allow the bot to read messages and moderate the group:

1. Open Telegram and chat with [@BotFather](https://t.me/BotFather).
2. Send `/mybots` and choose your bot.
3. Select **Bot Settings** -> **Group Privacy**.
4. Click **Turn off** (Disabled).
5. Add the bot to your group/channel and promote it to **Administrator** with **Delete Messages** permission enabled.

---

### 2. Installation

Clone or open the project folder in your terminal:

```bash
cd "d:/Antigravity/Lookism Funnel"
```

Create and activate a virtual environment (recommended):

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

---

### 3. Configuration

The bot token is already configured in `.env` and `bot.py`:

```ini
TELEGRAM_BOT_TOKEN="8987239385:AAH9HGomNJfS4nMCwnjcDfku50kbcOnk7dQ"
TOXICITY_THRESHOLD=0.75
BAD_WORDS_FILE="bad_words.txt"
SEND_WARNING_MESSAGE=True
WARNING_DELETE_DELAY=5
```

You can adjust `TOXICITY_THRESHOLD` between `0.0` and `1.0` if you want stricter or more relaxed AI moderation.

---

### 4. Running the Bot

Run the bot directly:
```bash
python bot.py
```

To run in the background on Linux/VPS:
```bash
nohup python3 bot.py > moderation_bot.log 2>&1 &
```

Or using **PM2**:
```bash
pm2 start bot.py --name "tg-moderator" --interpreter python3
```

---

## 🛠️ CLI Remote Administration & Control Tool (`cli.py`)

You can directly manage your channels and groups from the terminal using `cli.py`:

```bash
# Check bot connectivity, ID, and privacy settings
python cli.py status

# Send a message to any group, channel, or user ID (and optionally pin it)
python cli.py send --chat-id "@YourChannel" --text "Welcome to the group!" --pin

# Broadcast an announcement to your channel
python cli.py announce --channel "@YourChannel" --text "🚨 Major Announcement: New Rules Active!"

# Ban a malicious user
python cli.py ban --chat-id "-100123456789" --user-id 987654321 --revoke-messages

# Kick a user (bans and immediately unbans so they can re-enter later)
python cli.py kick --chat-id "-100123456789" --user-id 987654321

# Mute a user for 60 minutes
python cli.py mute --chat-id "-100123456789" --user-id 987654321 --minutes 60

# Unmute a user
python cli.py unmute --chat-id "-100123456789" --user-id 987654321

# Inspect chat details (member count, title, description, invite link)
python cli.py chat-info --chat-id "@YourChannel"

# View list of all administrators in a chat
python cli.py admins --chat-id "-100123456789"

# Inspect recent moderation deletions and group activity
python cli.py activity --limit 25

# Manage prohibited bad words list
python cli.py words list
python cli.py words add "new_scam_phrase"
python cli.py words del "new_scam_phrase"
```

---

## 🛠️ In-Chat Telegram Commands

| Command | Description | Permission |
| :--- | :--- | :--- |
| `/start` | Check bot status and active moderation features | All users |
| `/help` | View help guide and group configuration steps | All users |
| `/addword <word/phrase>` | Add a new prohibited word/phrase to `bad_words.txt` | **Admin Only** |
| `/delword <word/phrase>` | Remove a word from `bad_words.txt` | **Admin Only** |
| `/listwords` | View active bad words count and preview | **Admin Only** |
| `/testtoxic <text>` | Test AI toxicity score and rule triggers on any sample | **Admin Only** |

---

## 📊 Audit Log Sample

When a message is deleted, a structured log entry is recorded:

```text
2026-10-20 12:35:10,412 [WARNING] ModerationBot (bot.py:270): MESSAGE DELETED | Chat: 'Crypto Discussion' (ID: -100123456789, Type: supergroup) | User: @spammer123 (ID: 987654321) | Reason: Prohibited Telegram invite link detected: 't.me/free_crypto_airdrop' | Snippet: 'Check out my new channel: t.me/free_crypto_airdrop'
```
