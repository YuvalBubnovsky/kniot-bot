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

## Running with Docker

```bash
cp .env.example .env   # add your token
docker compose up -d --build
```

The list is stored in the `data/` directory (a persistent volume). Management:

```bash
docker compose logs -f   # view logs
docker compose down      # stop
```

## Cloud deployment (Render / Fly.io)

The repo includes a `Dockerfile` suitable for direct deployment:

- **Render**: create a "Web Service" from the repo, Environment: `Docker`, environment variable: `BOT_TOKEN`. Note: the free tier sleeps the app after inactivity, which kills a polling bot — use [cron-job.org](https://cron-job.org) to ping your Web Service URL every 10 minutes to keep it awake. It's recommended to attach a Disk so the list (SQLite) survives restarts.
- **Fly.io**: `fly launch` → choose the `Dockerfile` → set the secret: `fly secrets set BOT_TOKEN=...` → `fly volumes create data --size 1` and mount it at `/app/data`.

Note: on Render's free tier the instance sleeps after ~15 minutes of no traffic, so the ping is essential for a polling bot.

## Project layout

- `bot.py` — the Telegram bot logic
- `categories.py` — category keywords (Hebrew) used for auto-categorization (seed data for new databases)
- `Dockerfile` / `docker-compose.yml` — container setup
- `.env.example` — copy to `.env` with your bot token