# Shopping Bot

A Telegram bot for keeping a Hebrew grocery list, sorted into categories.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Creating the bot

1. Open a chat with [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`, pick a name, and you'll get a token
3. Set the token and run:

```bash
export BOT_TOKEN="your token here"
python3 bot.py
```

## Usage

| You send | What happens |
|---|---|
| `חלב` | Adds milk (x1) to the list |
| `חלב x2` / `חלב 2` / `2 חלב` | Adds milk with quantity 2 |
| `רשימה` | Shows the full list sorted by category |
| `חסר חלב` | Marks milk as not found in the store |
| `מצאתי חלב` | Moves milk back to the main list |
| `הסר חלב` | Removes milk from the list |
| `שנה חלב ל2% חלב` | Renames an item on the list |
| `כמות חלב 3` | Sets an item's quantity |
| `נקה` | Empties the current list; items marked as not found are saved to the "next shopping list" |
| `הבא` | Shows the next shopping list (items saved from the previous trip) |
| `החזר חלב` | Moves milk from the next list back to the current list |
| `החזר הכל` | Moves all items from the next list back to the current list |
| `קטגוריות` | Lists the categories |
| `קטגוריה חדשה אפייה` | Adds a category |
| `שנה קטגוריה מוצרי חלב לחלב ומוצריו` | Renames a category (all items follow) |
| `הסר קטגוריה אפייה` | Removes a category (its items move to `כללי`) |
| `העבר חלב סויה לשתייה` | Teaches the bot a category for an item |
| `כללים` | Lists the categories the bot has learned |
| `הסר כלל חלב סויה` | Forgets a learned rule |
| `הסר "קטגוריה חדשה"` | Removes an item whose name looks like a command (use quotes) |

> **Menu & buttons**: the blue *Menu* button shows the commands with Hebrew descriptions
> (only the command names themselves must be Latin, e.g. `/list`, `/remove חלב`).
> After `/start` or `/help` you also get a quick reply-keyboard (רשימה/הבא/נקה/קטגוריות/עזרה),
> and when an unknown item needs a category, it's offered as tappable buttons instead of typing a number.

## Buttons & menu

- **Menu button** — set automatically at startup via `set_my_commands`; descriptions are in Hebrew.
- **Reply keyboard** — persistent shortcut buttons below the chat after `/start` / `/help`.
- **Inline buttons** — when the bot can't classify an item, it offers category buttons instead of a numbered reply (the numbered text flow still works).

To reset the menu/manual setup yourself, ask [@BotFather](https://t.me/BotFather) `/setcommands` (only needed if you don't run this code).

Categories are stored in the database, so you can add, rename and remove them freely.
The default ones: fruits & vegetables, bakery, dairy, eggs, meat/fish/poultry, dry goods & canned, spices & sauces, frozen, sweets & snacks, drinks, cleaning & toiletries, general.

The list is stored in `shopping.db` (SQLite) and persists across restarts.

## Smart categorization

The bot doesn't rely on rigid keyword matching:

- **Normalization** — ignores niqqud and maps Hebrew final letters (ך→כ, ם→מ, ן→נ, ף→פ, ץ→צ), so typos and plurals still match (`גבינה`, `גבינהה`, `ביצים`).
- **Token-aware scoring** — exact word matches and prefixes score higher than loose substrings.
- **Similarity fallback** — an unknown name that resembles an existing item (e.g. `טונא` for `טונה`) inherits that item's category.
- **Interactive learning** — when the bot can't classify an item, it asks you to pick a category from a numbered menu; your choice is remembered as a rule and applied automatically next time.
- **Teaching commands** — `העבר <item> ל<category>` updates the item and stores a rule; `כללים` shows learned rules; `הסר כלל <item>` deletes one.

## Shared list

The list is shared: anyone who talks to the bot (e.g. you and your wife, each on their own phone) sees and edits the same list.

## Running locally (terminal)

```bash
source venv/bin/activate
export BOT_TOKEN="your token here"
python3 bot.py
```

## Running with Docker on a VPS

```bash
# on your server:
git clone <your-repo-url> && cd <repo>
cp .env.example .env        # add your BOT_TOKEN
mkdir -p data               # persistent volume for the SQLite db
docker compose up -d --build
docker compose logs -f      # view logs
docker compose down         # stop
```

## Migrating an existing local database to the server

The whole state (items, categories, rules, next list) lives in one SQLite file (`shopping.db`). To move it:

```bash
# on the server, BEFORE first start (stop the bot if it already ran once):
docker compose down
cp /path/to/local/shopping.db data/shopping.db
docker compose up -d

# verify the old data is alive:
docker compose logs -f
# then in Telegram send: רשימה
```

Notes:

- Copy the file only while the local bot is stopped, so the DB isn't mid-write.
- Same command works the other way (backing the server up locally).
- The container's `DB_PATH` is `/app/data/shopping.db`, mapped to `./data/shopping.db` — so the copied file is picked up automatically.
- No schema version troubles: `get_db()` runs idempotent migrations (e.g. the old per-user → shared-list migration) on startup, so older DBs just work.

## Cloud deployment (Render / Fly.io)

The repo includes a `Dockerfile` suitable for direct deployment:

- **Render**: create a "Web Service" from the repo, Environment: `Docker`, environment variable: `BOT_TOKEN`. Note: the free tier sleeps the app after inactivity, which kills a polling bot — use [cron-job.org](https://cron-job.org) to ping your Web Service URL every 10 minutes to keep it awake. It's recommended to attach a Disk so the list (SQLite) survives restarts.
- **Fly.io**: `fly launch` → choose the `Dockerfile` → set the secret: `fly secrets set BOT_TOKEN=...` → `fly volumes create data --size 1` and mount it at `/app/data`.

Note: on Render's free tier the instance sleeps after ~15 minutes of no traffic, so the ping is essential for a polling bot.

## Project layout

- `bot.py` — entry point: wires up handlers and runs polling
- `handlers.py` — all message/callback handlers (commands, menu flow)
- `db.py` — SQLite access, schema migrations, parsing/quoting helpers
- `messages.py` — help text, bot commands, message/keyboard builders
- `categories.py` — category keywords (Hebrew) used for auto-categorization (seed data for new databases)
- `Dockerfile` / `docker-compose.yml` — container setup
- `.env.example` — copy to `.env` with your bot token
