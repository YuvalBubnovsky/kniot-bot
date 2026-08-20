import logging
import os
import re
import sqlite3

from categories import CATEGORIES, GENERAL, categorize, normalize, strip_emoji

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopping.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS items (
            name TEXT NOT NULL PRIMARY KEY,
            qty INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL,
            missing INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS next_items (
            name TEXT NOT NULL PRIMARY KEY,
            qty INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS rules (
            pattern TEXT NOT NULL PRIMARY KEY,
            category TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS pending (
            user_id INTEGER NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS categories (
            name TEXT NOT NULL PRIMARY KEY,
            position INTEGER NOT NULL
        )"""
    )
    conn.commit()
    _migrate_shared(conn)
    _seed_categories(conn)
    _sanitize_categories(conn)
    return conn


def _migrate_shared(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(items)")]
    if "user_id" not in cols:
        return
    logger.info("Migrating items table to shared list")
    conn.execute("ALTER TABLE items RENAME TO items_old")
    conn.execute(
        """CREATE TABLE items (
            name TEXT NOT NULL PRIMARY KEY,
            qty INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL,
            missing INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """INSERT INTO items (name, qty, category, created_at)
           SELECT name, SUM(qty), category, MIN(created_at) FROM items_old GROUP BY name"""
    )
    conn.execute("DROP TABLE items_old")
    conn.commit()


def _seed_categories(conn):
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]:
        return
    conn.executemany(
        "INSERT INTO categories (name, position) VALUES (?, ?)",
        [(category, i) for i, (category, _) in enumerate(CATEGORIES)],
    )
    conn.commit()


def _sanitize_categories(conn):
    for table in ("items", "next_items"):
        for (stored,) in conn.execute(f"SELECT DISTINCT category FROM {table}").fetchall():
            fixed = strip_emoji(stored)
            if fixed != stored:
                conn.execute(
                    f"UPDATE {table} SET category = ? WHERE category = ?", (fixed, stored)
                )
    conn.commit()


def get_categories(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY position")]
    if GENERAL not in names:
        names.append(GENERAL)
    return names


def get_rules_context(conn):
    rules = conn.execute("SELECT pattern, category FROM rules").fetchall()
    context = dict(conn.execute("SELECT name, category FROM items").fetchall())
    return rules, context


def find_item(conn, name, table="items"):
    n = normalize(name)
    rows = [r[0] for r in conn.execute(f"SELECT name FROM {table}").fetchall()]
    for existing in rows:
        if normalize(existing) == n:
            return existing
    return None


def add_items(conn, items):
    added, updated, restored = 0, 0, 0
    for name, qty, category in items:
        cur = conn.execute("SELECT missing FROM items WHERE name = ?", (name,))
        row = cur.fetchone()
        conn.execute(
            "INSERT INTO items (name, qty, category) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET qty = qty + excluded.qty, missing = 0",
            (name, qty, category),
        )
        if row is None:
            added += 1
        elif row[0]:
            restored += 1
        else:
            updated += 1
    conn.commit()
    return added, updated, restored


def set_missing(conn, names, missing):
    marked = 0
    for name in names:
        cur = conn.execute(
            "UPDATE items SET missing = ? WHERE name = ?", (1 if missing else 0, name)
        )
        if cur.rowcount:
            marked += 1
    conn.commit()
    return marked


def clear_list(conn):
    moved = conn.execute(
        "SELECT name, qty, category FROM items WHERE missing = 1"
    ).fetchall()
    if moved:
        conn.executemany(
            "INSERT INTO next_items (name, qty, category) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET qty = qty + excluded.qty",
            moved,
        )
    conn.execute("DELETE FROM items")
    conn.commit()
    return len(moved)


def restore_items(conn, names, restore_all):
    rules, context = get_rules_context(conn)
    category_names = get_categories(conn)
    restored = 0
    if restore_all:
        rows = conn.execute("SELECT name, qty FROM next_items").fetchall()
    else:
        rows = conn.execute(
            "SELECT name, qty FROM next_items WHERE name IN (%s)"
            % ",".join("?" * len(names)),
            names,
        ).fetchall()
    for name, qty in rows:
        category = categorize(name, rules, context, category_names) or GENERAL
        conn.execute(
            "INSERT INTO items (name, qty, category) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET qty = qty + excluded.qty",
            (name, qty, category),
        )
        conn.execute("DELETE FROM next_items WHERE name = ?", (name,))
        restored += 1
    conn.commit()
    return restored


def unquote(name):
    name = name.strip()
    if len(name) >= 2 and name[0] == name[-1] and name[0] in ('"', "'"):
        return name[1:-1].strip()
    return name


def parse_line(line):
    line = line.strip()
    m = re.match(r'^"(.+?)"(?:\s*[xX×*]\s*(\d+))?$', line)
    if m:
        return m.group(1).strip(), int(m.group(2) or 1)
    m = re.match(r"^'(.+?)'(?:\s*[xX×*]\s*(\d+))?$", line)
    if m:
        return m.group(1).strip(), int(m.group(2) or 1)
    m = re.match(r"^(\d+)\s+(.+)$", line)
    if m:
        return m.group(2).strip(), int(m.group(1))
    m = re.match(r"^(.+?)\s*[xX×*]\s*(\d+)$", line)
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(.+?)[\s-]{1,3}(\d+)$", line)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return unquote(line), 1


def parse_items(text):
    items = []
    for line in text.splitlines():
        for part in line.split(","):
            part = part.strip()
            name, qty = parse_line(part)
            if name:
                name = re.sub(r"\((\d+)\)$", "", name).strip()
                items.append((name, qty))
    return items