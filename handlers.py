import re

from telegram import Update
from telegram.ext import ContextTypes

from categories import GENERAL, categorize, find_category

from db import (
    add_items,
    clear_list,
    find_item,
    get_categories,
    get_db,
    get_rules_context,
    parse_items,
    restore_items,
    set_missing,
    unquote,
)

from messages import (
    HELP_TEXT,
    build_categories_view,
    build_list,
    build_next_list,
    category_menu,
    category_pick_keyboard,
    main_keyboard,
    normalize_command,
)

BARE_COMMANDS = {
    "קטגוריה חדשה": "איך קוראים לקטגוריה? למשל: קטגוריה חדשה אפייה",
    "שנה קטגוריה": "צורה נכונה: שנה קטגוריה <ישן> ל<חדש>",
    "הסר קטגוריה": "איזו קטגוריה למחוק? למשל: הסר קטגוריה אפייה",
    "הסר כלל": "איזה כלל למחוק? למשל: הסר כלל חלב סויה",
    "הסר": "מה להסיר? למשל: הסר חלב",
    "חסר": "מה לא נמצא? למשל: חסר חלב",
    "מצאתי": "מה מצאתם? למשל: מצאתי חלב",
    "שנה": "צורה נכונה: שנה <פריט> ל<שם חדש>",
    "כמות": "צורה נכונה: כמות <פריט> <מספר>",
    "העבר": "איך ללמד אותי? למשל: העבר חלב סויה לשתייה",
    "החזר": "מה להחזיר? למשל: החזר חלב",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML", reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML", reply_markup=main_keyboard())


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    conn = get_db()
    try:
        row = conn.execute("SELECT name, qty FROM pending WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            await query.edit_message_text("אין פריט ממתין לבחירת קטגוריה.")
            return
        category_names = get_categories(conn)
        try:
            index = int(query.data.split(":", 1)[1])
        except (ValueError, IndexError):
            index = -1
        if 0 <= index < len(category_names):
            category = category_names[index]
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
        await query.edit_message_text(
            f"'{row[0]}' הוסף לקטגוריה '{category}'. אזכור את זה בפעם הבאה!"
        )
    finally:
        conn.close()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_command((update.message.text or "").strip())

    if not text:
        return

    user_id = update.effective_user.id

    if text in BARE_COMMANDS:
        await update.message.reply_text(BARE_COMMANDS[text])
        return

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
            await update.message.reply_text(build_list(conn), parse_mode="HTML")
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
            await update.message.reply_text(build_next_list(conn), parse_mode="HTML")
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
        old, new = unquote(m.group(1)), unquote(m.group(2))
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
        name, category_name = unquote(m.group(1)), unquote(m.group(2))
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
        old, new = unquote(m.group(1)), unquote(m.group(2))
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
        name, qty = unquote(m.group(1)), int(m.group(2))
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
        await update.message.reply_text(
            category_menu(pending_items[0][0], names) + extra_note,
            reply_markup=category_pick_keyboard(names),
        )
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