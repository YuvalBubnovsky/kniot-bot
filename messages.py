import html
import re

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from categories import GENERAL

from db import get_categories

HELP_TEXT = """<b>בוט קניות</b>

<b>הוספת פריטים</b>
שלחו לי פריט ואשמור אותו לרשימה. אפשר להוסיף כמות:
• חלב
• חלב x2
• חלב 2
• 2 חלב
• כמה פריטים בשורות נפרדות

שים/י לב: אם שם הפריט נראה כמו פקודה (למשל רשמתם 'קטגוריה חדשה' כפריט), יש למחוק אותו עם מרכאות:
• הסר "קטגוריה חדשה"

<b>רשימה</b>
• <b>רשימה</b> — להציג את הרשימה הממוינת לפי קטגוריות
• <b>חסר</b> <i>פריט</i> — לסמן פריט שלא נמצא בחנות
• <b>מצאתי</b> <i>פריט</i> — להחזיר פריט שלא נמצא
• <b>הסר</b> <i>פריט</i> — להסיר פריט מהרשימה
• <b>שנה</b> <i>פריט</i> ל<i>שם חדש</i> — לשנות שם של פריט
• <b>כמות</b> <i>פריט</i> <i>מספר</i> — לקבוע כמות
• <b>נקה</b> — לרוקן את הרשימה (<i>פריטים שלא נמצאו נשמרים לרשימה הבאה!</i>)
• <b>הבא</b> — להציג את רשימת הקניות הבאה
• <b>החזר</b> <i>פריט</i> — להחזיר פריט מהרשימה הבאה לרשימה הנוכחית
• <b>החזר הכל</b> — להחזיר את כל הפריטים מהרשימה הבאה

<b>קטגוריות</b>
• <b>קטגוריות</b> — להציג את רשימת הקטגוריות
• <b>קטגוריה חדשה</b> <i>שם</i> — להוסיף קטגוריה
• <b>שנה קטגוריה</b> <i>ישן</i> ל<i>חדש</i> — לשנות שם קטגוריה
• <b>הסר קטגוריה</b> <i>שם</i> — למחוק קטגוריה (הפריטים יעברו לכללי)
• <b>העבר</b> <i>פריט</i> ל<i>קטגוריה</i> — ללמד אותי לאיזה קטגוריה פריט שייך
• <b>כללים</b> — להציג את הכללים שלמדתי
• <b>הסר כלל</b> <i>פריט</i> — למחוק כלל שלמדתי

<i>אם אני לא מזהה פריט, אשאל אתכם לאיזה קטגוריה הוא שייך — ואזכור לפעם הבאה!</i>

הרשימה משותפת — כל מי שמדבר עם הבוט רואה את אותה הרשימה.

אפשר גם להשתמש בכפתור ה<b>Menu</b> או בפקודות באנגלית (למשל /list, /add חלב, /remove חלב).
"""

COMMANDS = [
    BotCommand("list", "הצג את רשימת הקניות"),
    BotCommand("add", "הוסף פריט (או פשוט שלחו את הפריט)"),
    BotCommand("remove", "הסר פריט מהרשימה"),
    BotCommand("missing", "סמן פריט שלא נמצא בחנות"),
    BotCommand("found", "החזר פריט שאותר שוב"),
    BotCommand("qty", "קבע כמות לפריט"),
    BotCommand("rename", "שנה שם של פריט"),
    BotCommand("clear", "רוקן את הרשימה"),
    BotCommand("next", "הצג את רשימת הקניות הבאה"),
    BotCommand("return", "החזר פריט מהרשימה הבאה"),
    BotCommand("returnall", "החזר את כל הפריטים מהרשימה הבאה"),
    BotCommand("categories", "הצג את רשימת הקטגוריות"),
    BotCommand("newcat", "הוסף קטגוריה חדשה"),
    BotCommand("renamecat", "שנה שם של קטגוריה"),
    BotCommand("removecat", "מחק קטגוריה"),
    BotCommand("move", "למד את הבוט לאיזה קטגוריה פריט שייך"),
    BotCommand("rules", "הצג את הכללים שלמד הבוט"),
    BotCommand("delrule", "מחק כלל"),
    BotCommand("help", "עזרה ופקודות"),
]

CMD_MAP = {
    "list": "רשימה",
    "next": "הבא",
    "clear": "נקה",
    "categories": "קטגוריות",
    "rules": "כללים",
    "returnall": "החזר הכל",
}

CMD_PREFIX_MAP = {
    "add": "",
    "remove": "הסר ",
    "missing": "חסר ",
    "found": "מצאתי ",
    "qty": "כמות ",
    "rename": "שנה ",
    "move": "העבר ",
    "newcat": "קטגוריה חדשה ",
    "renamecat": "שנה קטגוריה ",
    "removecat": "הסר קטגוריה ",
    "delrule": "הסר כלל ",
    "return": "החזר ",
}


def normalize_command(text: str) -> str:
    """Translate latin /commands (menu / i18n) to the Hebrew phrases the bot matches."""
    if not text.startswith("/"):
        return text
    cmd, _, args = text.partition(" ")
    cmd = cmd.strip("/").lower()
    if cmd in CMD_MAP:
        return CMD_MAP[cmd]
    prefix = CMD_PREFIX_MAP.get(cmd)
    if prefix is None:
        return text
    args = re.sub(r"\s+to\s+", " ל", args.strip())
    return prefix if not args else (prefix + args).strip()


def split_by_category(rows, category_names):
    items_by_category = {}
    for name, qty, category in rows:
        items_by_category.setdefault(category, []).append((name, qty))
    lines = []
    for category in category_names:
        items = items_by_category.get(category)
        if not items:
            continue
        lines.append(f"<b><u>{html.escape(category)}:</u></b>")
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


def category_menu(name, category_names):
    lines = [f"לאיזה קטגוריה שייך '{name}'?", ""]
    for i, category in enumerate(category_names, 1):
        lines.append(f"{i}. {category}")
    lines.append(f"{len(category_names) + 1}. קטגוריה אחרת (כללי)")
    lines.append("")
    lines.append("לחצו על קטגוריה או שלחו מספר")
    return "\n".join(lines)


def category_pick_keyboard(category_names):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(category, callback_data=f"cat:{i}")]
         for i, category in enumerate(category_names)]
    )


def build_categories_view(names):
    lines = ["קטגוריות:", ""]
    for i, category in enumerate(names, 1):
        lines.append(f"{i}. {category}")
    lines.append("")
    lines.append("הוספה: קטגוריה חדשה <שם>")
    lines.append("שינוי שם: שנה קטגוריה <ישן> ל<חדש>")
    lines.append("מחיקה: הסר קטגוריה <שם>")
    return "\n".join(lines)


def main_keyboard():
    return ReplyKeyboardMarkup(
        [["רשימה", "הבא"], ["נקה", "קטגוריות"], ["עזרה"]],
        resize_keyboard=True,
    )