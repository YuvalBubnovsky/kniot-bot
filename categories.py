import re
import unicodedata

GENERAL = "כללי"

CATEGORIES = [
    ("פירות וירקות", [
        "עגבני", "מלפפון", "בצל", "שום", "גזר", "תפוח אדמה", "בטטה", "חסה",
        "כרוב", "פלפל", "ברוקולי", "כוסברה", "פטרוזיליה", "שמיר", "נענע",
        "קישוא", "חציל", "דלעת", "סלק", "צנון", "תירס", "אבוקדו", "לימון",
        "תפוז", "מנדרינ", "קלמנטינ", "תפוח", "אגס", "בננה", "תות", "ענבים",
        "מלון", "אבטיח", "מנגו", "אננס", "אפרסק", "נקטרינ", "שזיף", "דובדבן",
        "רימון", "קיווי", "אשכולית", "פטל", "אוכמני", "תמר", "משמש",
        "פטריות", "אספרגוס", "סלרי", "ארטישוק", "כרישה",
    ]),
    ("מאפים ולחם", [
        "לחם", "פית", "חלה", "בגט", "באגט", "לחמני", "קרואסון", "בורקס",
        "עוגה", "עוגיות", "ביסקוויט", "מאפה", "בצק", "מצה", "וופל",
    ]),
    ("חלב ומוצרי חלב", [
        "חלב", "גבינ", "קוטג", "יוגורט", "לבן", "שמנת", "חמא", "מחמיצה",
        "ריקוטה", "מוצרלה", "בולגרית", "צפתית", "מלוחה",
    ]),
    ("ביצים", [
        "ביצ",
    ]),
    ("בשר, דגים ועוף", [
        "עוף", "הודו", "בשר", "בקר", "נתח", "שניצל", "דג", "סלמון",
        "טונה", "נקניק", "המבורגר", "קבב", "כבד", "שוקיים", "פרגית", "אווז",
        "מושט", "סרדין", "מקרל",
    ]),
    ("מזון יבש ושימורים", [
        "אורז", "פסטה", "ספגטי", "אטריות", "קוסקוס", "בורגול", "קינואה",
        "עדשים", "שעועית", "חומוס", "אפונת", "שימור", "קמח", "סוכר",
        "מלח", "פתיתים", "גריסים", "שיבולת",
    ]),
    ("תבלינים ורטבים", [
        "תבלין", "קינמון", "כורכום", "כמון", "פפריקה", "פלפל שחור",
        "בזיליקום", "אורגנו", "רוטב", "קטשופ", "מיונז", "חרדל", "סחוג",
        "צ'ילי", "קוקוס", "וניל", "סויה", "בלסמי", "שמן", "חומץ",
    ]),
    ("קפואים", [
        "גליד", "פיצה", "קפוא", "ירקות מוקפאים", "שווארמה", "אגרול",
        "צ'יפס", "מקרוני",
    ]),
    ("ממתקים וחטיפים", [
        "שוקולד", "חטיף", "ביסלי", "במבה", "טורטית", "ממתק", "סוכרי",
        "מסטיק", "וספה", "קיטקט", "מרשמלו", "גומי",
    ]),
    ("שתייה", [
        "מים", "קולה", "סודה", "מיץ", "שוקו", "קפה", "נס קפה",
        "תה", "חליט", "בירה", "יין", "משקה", "ספרייט", "פאנטה", "תפוזינה",
        "טעמן", "שקד",
    ]),
    ("ניקיון וטואלטיקה", [
        "סבון", "אקונומיק", "כביס", "מרכך", "נייר טואלט", "מגבון",
        "שמפו", "מרכך שיער", "משחת שיניים", "מברשת שיניים", "דאודורנט",
        "טואלט", "אמוניה", "ספוג", "פח", "מטבח", "נוזל",
    ]),
    (GENERAL, [
    ]),
]

_FINAL_LETTERS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_TOKEN_RE = re.compile(r"[a-z0-9\u0590-\u05ff'\u2019]+")
_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\ufe0f]+")

MIN_SCORE = 60


def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.translate(_FINAL_LETTERS)
    return text.strip().lower()


def strip_emoji(text):
    return _EMOJI_RE.sub("", text).strip()


def tokens(text):
    return _TOKEN_RE.findall(normalize(text))


def match_score(name, keyword):
    n = normalize(name)
    k = normalize(keyword)
    if not n or not k:
        return 0
    if n == k:
        return 100
    if n.startswith(k):
        return 92
    for t in tokens(n):
        if t == k:
            return 95
        if t.startswith(k):
            return 88
    if k in n:
        return 60
    return 0


def best_keyword_match(name):
    best_category, best_score = None, 0
    for category, keywords in CATEGORIES:
        for keyword in keywords:
            score = match_score(name, keyword)
            if score > best_score:
                best_score = score
                best_category = category
    return best_category, best_score


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similar(a, b):
    a, b = normalize(a), normalize(b)
    if not a or not b or a[0] != b[0]:
        return False
    return 1 - levenshtein(a, b) / max(len(a), len(b)) >= 0.75


def find_category(text, category_names=None):
    """Resolve a user-typed category name against the given names (or built-ins)."""
    t = normalize(text)
    names = category_names or [c for c, _ in CATEGORIES]
    for name in names:
        n = normalize(name)
        if n == t or (t in n) or (n in t):
            return name
    return None


def categorize(name, rules=None, context=None, category_names=None):
    """Return the best category for name, or None when unsure.

    rules: iterable of (name pattern, category) learned from user input
    context: dict of existing item name -> category, used for similarity fallback
    category_names: active category names from the DB; results are limited to them
    """
    n = normalize(name)
    if not n:
        return None
    for pattern, category in rules or ():
        if normalize(pattern) in n:
            return category
    best, score = best_keyword_match(name)
    if best and score >= MIN_SCORE and (category_names is None or best in category_names):
        return best
    if context:
        for existing, category in context.items():
            if similar(existing, name):
                return category
    return None