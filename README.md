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

## Oracle Cloud Always Free (recommended free option)

The Always Free tier gives you a permanent ARM instance (up to 2 OCPU / 12 GB RAM, 200 GB disk) that stays awake 24/7 — no sleep timeout, unlike Render's free tier.

### 1. Create the instance

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) (card required for verification, you're never charged).
2. Console → **Compute → Instances → Create instance**:
   - Image: **Ubuntu 24.04**
   - Shape: **Edit → Ampere A1 (ARM) → `VM.Standard.A1.Flex`**, set **2 OCPUs / 12 GB memory** (the always-free envelope as of Aug 2026)
   - Boot volume: **100 GB** is fine
   - **Add your SSH public key** (download/save the private key if you let Oracle generate it)
3. **Capacity errors ("Out of host capacity") are common** — retry in another Availability Domain, or a less busy region (avoid US East/Ashburn, Frankfurt), or retry periodically with [a retry script](https://codeeasy.in/articles/oracle-cloud-free-tier-ultimate-guide/).
4. Network: the default VCN/security list is fine. **No inbound ports needed** — the bot only *polls* Telegram outbound; keep port 22 (SSH) to yourself.

### 2. Connect and install Docker

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<instance_ip>

sudo apt update && sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out (`exit`) and back in, so `docker` works without `sudo`.

### 3. Deploy the bot

```bash
git clone <your-repo-url> && cd <repo>
cp .env.example .env
nano .env                    # paste your BOT_TOKEN
mkdir -p data
docker compose up -d --build
docker compose logs -f       # expect "Bot started"; on success you'll see getUpdates activity
```

That's it — the bot runs 24/7 (the compose file already has `restart: unless-stopped`, and Docker starts on boot by default).

### 4. Migrate your current local DB (do this BEFORE the first `docker compose up`)

```bash
# on YOUR local machine, bot stopped (Ctrl+C):
scp shopping.db ubuntu@<instance_ip>:/home/ubuntu/<repo>/data/shopping.db
```

Then start the containers once, verify with `docker compose logs -f` and by sending `רשימה` in Telegram.

If the bot already ran once on the server without the DB: `docker compose down`, copy the file as above, `docker compose up -d`.

### 5. Backups (recommended, free)

```bash
# on your machine:
scp ubuntu@<instance_ip>:/home/ubuntu/<repo>/data/shopping.db ./shopping-backup.db
```

That single file is your whole state. Restoring is the same command in reverse.

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