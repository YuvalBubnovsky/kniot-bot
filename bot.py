import logging
import os
import re
import sqlite3

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from categories import CATEGORIES, GENERAL, categorize, find_category, normalize, strip_emoji

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopping.db"))

HELP_TEXT = """אני בוט קניות!

שלחו לי פריט ואשמור אותו לרשימה. אפשר להוסיף כמות:
• חלב
• חלב x2
• חלב 2
• 2 חלב
• כמה פריטים בשורות נפרדות

פקודות:
• רשימה - להציג את הרשימה הממוינת לפי קטגוריות
• חסר <פריט> - לסמן פריט שלא נמצא בחנות
• מצאתי <פריט> - להחזיר פריט שלא נמצא
• הסר <פריט> - להסיר פריט מהרשימה
• שנה <פריט> ל<שם חדש> - לשנות שם של פריט
• כמות <פריט> <מספר> - לקבוע כמות
• נקה - לרוקן את הרשימה (פריטים שלא נמצאו נשמרים לרשימה הבאה!)
• הבא - להציג את רשימת הקניות הבאה
• החזר <פריט> - להחזיר פריט מהרשימה הבאה לרשימה הנוכחית
• החזר הכל - להחזיר את כל הפריטים מהרשימה הבאה
• קטגוריות - להציג את רשימת הקטגוריות
• קטגוריה חדשה <שם> - להוסיף קטגוריה
• שנה קטגוריה <ישן> ל<חדש> - לשנות שם קטגוריה
• הסר קטגוריה <שם> - למחוק קטגוריה (הפריטים יעברו לכללי)
• העבר <פריט> ל<קטגוריה> - ללמד אותי לאיזה קטגוריה פריט שייך
• כללים - להציג את הכללים שלמדתי
• הסר כלל <פריט> - למחוק כלל שלמדתי

אם אני לא מזהה פריט, אשאל אתכם לאיזה קטגוריה הוא שייך - ואזכור לפעם הבאה!

הרשימה משותפת - כל מי שמדבר עם הבוט רואה את אותה הרשימה.
"""


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


def parse_line(line):
    line = line.strip()
    m = re.match(r"^(\d+)\s+(.+)$", line)
    if m:
        return m.group(2).strip(), int(m.group(1))
    m = re.match(r"^(.+?)\s*[xX×*]\s*(\d+)$", line)
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(.+?)[\s-]{1,3}(\d+)$", line)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return line, 1


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


def split_by_category(rows, category_names):
    items_by_category = {}
    for name, qty, category in rows:
        items_by_category.setdefault(category, []).append((name, qty))
    lines = []
    for category in category_names:
        items = items_by_category.get(category)
        if not items:
            continue
        lines.append(f"{category}:")
        for name, qty in items:
            qty_suffix = f" x{qty}" if qty > 1 else ""
            lines.append(f"   • {name}{qty_suffix}")
        lines.append("")
    return lines


def build_list(conn):
    rows = conn.execute(
        "SELECT name, qty, category, missing FROM items ORDER BY created_at"
    ).fetchall()
    if not rows:
        return "הרשימה ריקה. שלחו לי פריטים כדי להוסיף!"

    found = [r for r in rows if not r[3]]
    missing = [r for r in rows if r[3]]

    lines = ["רשימת הקניות שלך:", ""]
    lines += split_by_category([(n, q, c) for n, q, c, _ in found], get_categories(conn))

    total = sum(r[1] for r in rows)
    if missing:
        lines.append(f"לא נמצאו: {' | '.join(n + (f' x{q}' if q > 1 else '') for n, q, _, _ in missing)}")
        lines.append("")
    lines.append(f"({total} פריטים בסך הכל)")
    return "\n".join(lines)


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


def build_next_list(conn):
    rows = conn.execute(
        "SELECT name, qty, category FROM next_items ORDER BY created_at"
    ).fetchall()
    if not rows:
        return "רשימת הקניות הבאה ריקה. (פריטים שלא נמצאו נשמרים לכאן אחרי 'נקה')"
    lines = ["לרשימת הקניות הבאה:", ""]
    lines += split_by_category(rows, get_categories(conn))
    lines.append("שלחו 'החזר <פריט>' כדי להחזיר פריט לרשימה הנוכחית, או 'החזר הכל'")
    return "\n".join(lines)


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


def category_menu(name, category_names):
    lines = [f"לאיזה קטגוריה שייך '{name}'?", ""]
    for i, category in enumerate(category_names, 1):
        lines.append(f"{i}. {category}")
    lines.append(f"{len(category_names) + 1}. קטגוריה אחרת (כללי)")
    lines.append("")
    lines.append("שלחו מספר")
    return "\n".join(lines)


def build_categories_view(names):
    lines = ["קטגוריות:", ""]
    for i, category in enumerate(names, 1):
        lines.append(f"{i}. {category}")
    lines.append("")
    lines.append("הוספה: קטגוריה חדשה <שם>")
    lines.append("שינוי שם: שנה קטגוריה <ישן> ל<חדש>")
    lines.append("מחיקה: הסר קטגוריה <שם>")
    return "\n".join(lines)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if not text:
        return

    user_id = update.effective_user.id

    if text.isdigit():
        choice = int(text)
        conn = get_db()
        try:
            row = conn.execute("SELECT name, qty FROM pending WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                category_names = get_categories(conn)
                if 1 <= choice <= len(category_names):
                    category = category_names[choice - 1]
                else:
                    category = GENERAL
                add_items(conn, [(row[0], row[1], category)])
                if category != GENERAL:
                    conn.execute(
                        "INSERT INTO rules (pattern, category) VALUES (?, ?) "
                        "ON CONFLICT(pattern) DO UPDATE SET category = excluded.category",
                        (row[0], category),
                    )
                conn.execute("DELETE FROM pending WHERE user_id = ?", (user_id,))
                conn.commit()
                await update.message.reply_text(
                    f"'{row[0]}' הוסף לקטגוריה '{category}'. אזכור את זה בפעם הבאה!"
                )
                return
        finally:
            conn.close()
        return

    if text.strip("/") in ("רשימה", "list"):
        conn = get_db()
        try:
            await update.message.reply_text(build_list(conn))
        finally:
            conn.close()
        return

    if text.strip("/") == "נקה":
        conn = get_db()
        try:
            moved = clear_list(conn)
        finally:
            conn.close()
        if moved:
            await update.message.reply_text(
                f"הרשימה נוקתה! {moved} פריטים שלא נמצאו נשמרו לרשימה הבאה. שלחו 'הבא' כדי לראות אותם."
            )
        else:
            await update.message.reply_text("הרשימה נוקתה!")
        return

    if text.strip("/") in ("הבא", "next"):
        conn = get_db()
        try:
            await update.message.reply_text(build_next_list(conn))
        finally:
            conn.close()
        return

    if text.strip("/") == "קטגוריות":
        conn = get_db()
        try:
            names = get_categories(conn)
        finally:
            conn.close()
        await update.message.reply_text(build_categories_view(names))
        return

    if text.startswith("קטגוריה חדשה "):
        name = text[len("קטגוריה חדשה "):].strip()
        if not name:
            await update.message.reply_text("איך קוראים לקטגוריה? למשל: קטגוריה חדשה אפייה")
            return
        conn = get_db()
        try:
            existing = find_category(name, get_categories(conn))
            if existing:
                await update.message.reply_text(f"הקטגוריה '{existing}' כבר קיימת.")
                return
            max_pos = conn.execute("SELECT MAX(position) FROM categories").fetchone()[0]
            conn.execute(
                "INSERT INTO categories (name, position) VALUES (?, ?)",
                (name, (max_pos or 0) + 1),
            )
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text(
            f"הקטגוריה '{name}' נוספה. למדו אותי להקצות אליה פריטים: העבר <פריט> ל{name}"
        )
        return

    if text.startswith("שנה קטגוריה "):
        m = re.match(r"^שנה קטגוריה (.+?) ל(.+)$", text)
        if not m:
            await update.message.reply_text("צורה נכונה: שנה קטגוריה <ישן> ל<חדש>")
            return
        old, new = m.group(1).strip(), m.group(2).strip()
        conn = get_db()
        try:
            names = get_categories(conn)
            current = find_category(old, names)
            target = find_category(new, names)
            if not current:
                await update.message.reply_text(f"לא נמצאה קטגוריה בשם '{old}'.")
                return
            if target and target != current:
                await update.message.reply_text(f"הקטגוריה '{new}' כבר קיימת.")
                return
            if current == GENERAL:
                await update.message.reply_text("אי אפשר לשנות את שם הקטגוריה 'כללי'.")
                return
            conn.execute("UPDATE categories SET name = ? WHERE name = ?", (new, current))
            for table in ("items", "next_items"):
                conn.execute(
                    f"UPDATE {table} SET category = ? WHERE category = ?", (new, current)
                )
            conn.execute(
                "UPDATE rules SET category = ? WHERE category = ?", (new, current)
            )
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text(
            f"הקטגוריה '{current}' שונתה ל'{new}'. כל הפריטים בה עודכנו."
        )
        return

    if text.startswith("הסר קטגוריה "):
        name = text[len("הסר קטגוריה "):].strip()
        conn = get_db()
        try:
            names = get_categories(conn)
            current = find_category(name, names)
            if not current:
                await update.message.reply_text(f"לא נמצאה קטגוריה בשם '{name}'.")
                return
            if current == GENERAL:
                await update.message.reply_text("אי אפשר למחוק את הקטגוריה 'כללי'.")
                return
            count = conn.execute(
                "SELECT COALESCE(SUM(qty), 0) FROM items WHERE category = ?", (current,)
            ).fetchone()[0]
            conn.execute("DELETE FROM categories WHERE name = ?", (current,))
            for table in ("items", "next_items"):
                conn.execute(f"UPDATE {table} SET category = ? WHERE category = ?", (GENERAL, current))
            conn.execute("DELETE FROM rules WHERE category = ?", (current,))
            conn.commit()
        finally:
            conn.close()
        msg = f"הקטגוריה '{current}' נמחקה."
        if count:
            msg += f" {count} פריטים עברו ל'כללי'."
        await update.message.reply_text(msg)
        return

    if text.strip("/") == "החזר הכל":
        conn = get_db()
        try:
            restored = restore_items(conn, [], True)
        finally:
            conn.close()
        if restored:
            await update.message.reply_text(f"{restored} פריטים הוחזרו לרשימה הנוכחית!")
        else:
            await update.message.reply_text("רשימת הקניות הבאה ריקה")
        return

    if text.startswith("החזר "):
        names = [n for n, _ in parse_items(text[5:])]
        if not names:
            await update.message.reply_text("מה להחזיר? למשל: החזר חלב")
            return
        conn = get_db()
        try:
            existing = [find_item(conn, name, "next_items") or name for name in names]
            restored = restore_items(conn, existing, False)
        finally:
            conn.close()
        if restored:
            await update.message.reply_text(f"הוחזרו לרשימה הנוכחית: {', '.join(names)}")
        else:
            await update.message.reply_text(f"לא נמצאו ברשימה הבאה: {', '.join(names)}")
        return

    if text.startswith("הסר כלל "):
        pattern = text[8:].strip()
        if not pattern:
            await update.message.reply_text("איזה כלל למחוק? למשל: הסר כלל חלב סויה")
            return
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM rules WHERE pattern = ?", (pattern,))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount:
            await update.message.reply_text(f"כלל נמחק: {pattern}")
        else:
            await update.message.reply_text(f"לא נמצא כלל בשם: {pattern}")
        return

    if text.strip("/") == "כללים":
        conn = get_db()
        try:
            rules = conn.execute("SELECT pattern, category FROM rules ORDER BY pattern").fetchall()
        finally:
            conn.close()
        if not rules:
            await update.message.reply_text(
                "אין כללים מותאמים אישית עדיין. תלמדו אותי בעזרת 'העבר <פריט> ל<קטגוריה>' "
                "או כשאשאל אתכם לאיזה קטגוריה פריט שייך."
            )
            return
        lines = ["הכללים שלמדתי:", ""]
        for pattern, category in rules:
            lines.append(f"• {pattern} → {category}")
        lines.append("")
        lines.append("למחיקה: 'הסר כלל <פריט>'")
        await update.message.reply_text("\n".join(lines))
        return

    if text.startswith("העבר "):
        m = re.match(r"^העבר (.+?) ל(?:קטגוריה)?\s*(.+)$", text)
        if not m:
            await update.message.reply_text("איך ללמד אותי? למשל: העבר חלב סויה לשתייה")
            return
        name, category_name = m.group(1).strip(), m.group(2).strip()
        conn = get_db()
        try:
            category_names = get_categories(conn)
            category = find_category(category_name, category_names)
            if not category:
                await update.message.reply_text(
                    f"לא מצאתי קטגוריה בשם '{category_name}'. שלחו 'קטגוריות' כדי לראות את הרשימה המלאה."
                )
                return
            cur = conn.execute("SELECT 1 FROM items WHERE name = ?", (name,))
            found = cur.fetchone()
            if found:
                conn.execute("UPDATE items SET category = ? WHERE name = ?", (category, name))
            conn.execute(
                "INSERT INTO rules (pattern, category) VALUES (?, ?) "
                "ON CONFLICT(pattern) DO UPDATE SET category = excluded.category",
                (name, category),
            )
            conn.commit()
        finally:
            conn.close()
        if found:
            await update.message.reply_text(
                f"'{name}' הועבר ל'{category}' ואזכור את זה בפעם הבאה!"
            )
        else:
            await update.message.reply_text(
                f"למדתי: '{name}' שייך ל'{category}'. שלחו אותו שוב ואשמור אותו בקטגוריה הנכונה."
            )
        return

    if text.startswith("שנה "):
        m = re.match(r"^שנה (.+?) ל(.+)$", text)
        if not m:
            await update.message.reply_text("צורה נכונה: שנה <פריט> ל<שם חדש>")
            return
        old, new = m.group(1).strip(), m.group(2).strip()
        conn = get_db()
        try:
            current = find_item(conn, old)
            if not current:
                await update.message.reply_text(f"לא נמצא פריט בשם '{old}' ברשימה.")
                return
            if find_item(conn, new):
                await update.message.reply_text(f"הפריט '{new}' כבר קיים ברשימה.")
                return
            conn.execute(
                "UPDATE items SET name = ? WHERE name = ?",
                (new, current),
            )
            conn.execute(
                "UPDATE next_items SET name = ? WHERE name = ?",
                (new, current),
            )
            conn.execute(
                "UPDATE rules SET pattern = ? WHERE pattern = ?", (new, current)
            )
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text(f"הפריט '{current}' שונה ל'{new}'.")
        return

    if text.startswith("כמות "):
        m = re.match(r"^כמות (.+) (\d+)$", text)
        if not m:
            await update.message.reply_text("צורה נכונה: כמות <פריט> <מספר>")
            return
        name, qty = m.group(1).strip(), int(m.group(2))
        conn = get_db()
        try:
            current = find_item(conn, name)
            if not current:
                await update.message.reply_text(f"לא נמצא פריט בשם '{name}' ברשימה.")
                return
            conn.execute("UPDATE items SET qty = ? WHERE name = ?", (qty, current))
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text(f"הכמות של '{current}' עודכנה ל{qty}.")
        return

    if text.startswith("הסר "):
        names = [n for n, _ in parse_items(text[4:])]
        if not names:
            await update.message.reply_text("מה להסיר? למשל: הסר חלב")
            return
        conn = get_db()
        try:
            resolved = [find_item(conn, n) for n in names]
            resolved = [r for r in resolved if r]
            if not resolved:
                await update.message.reply_text(f"לא נמצאו ברשימה: {', '.join(names)}")
                return
            cur = conn.execute(
                "DELETE FROM items WHERE name IN (%s)" % ",".join("?" * len(resolved)), resolved
            )
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text(f"הוסר: {', '.join(resolved)}")
        return

    if text.startswith("חסר "):
        names = [n for n, _ in parse_items(text[4:])]
        if not names:
            await update.message.reply_text("מה לא נמצא? למשל: חסר חלב")
            return
        conn = get_db()
        try:
            resolved = [find_item(conn, n) for n in names]
            resolved = [r for r in resolved if r]
            marked = set_missing(conn, resolved, True)
        finally:
            conn.close()
        if marked:
            await update.message.reply_text(f"סומן כלא נמצא: {', '.join(resolved)}")
        else:
            await update.message.reply_text(f"לא נמצאו ברשימה: {', '.join(names)}")
        return

    if text.startswith("מצאתי "):
        names = [n for n, _ in parse_items(text[5:])]
        if not names:
            await update.message.reply_text("מה מצאתם? למשל: מצאתי חלב")
            return
        conn = get_db()
        try:
            resolved = [find_item(conn, n) for n in names]
            resolved = [r for r in resolved if r]
            marked = set_missing(conn, resolved, False)
        finally:
            conn.close()
        if marked:
            await update.message.reply_text(f"הוחזר לרשימה: {', '.join(resolved)}")
        else:
            await update.message.reply_text(f"לא נמצאו ברשימה: {', '.join(names)}")
        return

    items = parse_items(text)
    if not items:
        return

    conn = get_db()
    try:
        rules, context = get_rules_context(conn)
        category_names = get_categories(conn)
        categorized = []
        pending_items = []
        for name, qty in items:
            category = categorize(name, rules, context, category_names)
            if category:
                categorized.append((name, qty, category))
                context[name] = category
            else:
                pending_items.append((name, qty))
        added, updated, restored = add_items(conn, categorized)
        if pending_items:
            first = pending_items[0]
            conn.execute(
                "INSERT INTO pending (user_id, name, qty) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET name = excluded.name, qty = excluded.qty",
                (user_id, first[0], first[1]),
            )
            conn.commit()
            extra_note = ""
            if len(pending_items) > 1:
                rest = pending_items[1:]
                add_items(conn, [(n, q, GENERAL) for n, q in rest])
                extra_note = (
                    f"\n\nהפריטים הבאים נוספו לכללי: {', '.join(n for n, _ in rest)}"
                )
    finally:
        conn.close()

    if pending_items:
        conn2 = get_db()
        try:
            names = get_categories(conn2)
        finally:
            conn2.close()
        await update.message.reply_text(category_menu(pending_items[0][0], names) + extra_note)
        return

    preview = ", ".join(f"{n} x{q}" if q > 1 else n for n, q in items)
    status = []
    if added:
        status.append(f"{added} הוספו")
    if updated:
        status.append(f"{updated} קיימים הוגדלו")
    if restored:
        status.append(f"{restored} הוחזרו לרשימה")
    await update.message.reply_text(f"{preview}\n\n({', '.join(status)}) שלחו 'רשימה' כדי לראות את הרשימה!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN environment variable")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()