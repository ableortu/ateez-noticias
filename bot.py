"""Noticias de ATEEZ -> Telegram, traducidas al español.

Uso:
    python bot.py            revisa las fuentes y envía lo nuevo
    python bot.py --dry-run  muestra lo que enviaría, sin enviar ni guardar estado
    python bot.py --chat-id  muestra los chat_id que han escrito al bot

Variables de entorno: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
"""

import argparse
import html
import json
import os
import re
import sys
import time
from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

STATE_FILE = Path(__file__).with_name("seen.json")
MAX_AGE = timedelta(days=3)  # lo más viejo que esto no se envía
STATE_TTL = timedelta(days=60)  # debe ser mayor que MAX_AGE
MAX_PER_RUN = 40  # el resto queda para la siguiente ejecución
FIRST_RUN_SAMPLE = 5
HTTP_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

ATEEZ_RE = re.compile(r"ateez|atiny|에이티즈|에이티니", re.I)
TICKET_RE = re.compile(
    r"\b(?:entradas?|boletos?|preventa|conciertos?|gira|tickets?|pre-?sale|on sale|"
    r"concerts?|tour|fan ?meeting|fan-?con)\b|티켓|예매|콘서트|투어|팬미팅|팬콘",
    re.I,
)

KQ_SITE = "https://ateez.kqent.com"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
# Google News devuelve como mucho 100 resultados. En días de comeback "1d" se
# satura y "6h" no; en días normales "1d" cubre retrasos de indexación.
GOOGLE_NEWS_WINDOWS = ("6h", "1d")

# "filter": feed general del que solo interesan las entradas que mencionan a
# ATEEZ. "lang": idioma original; "es" no se traduce.
SOURCES = [
    {"name": "Web oficial ATEEZ", "kind": "kq_notices", "icon": "📢"},
    {
        "name": "YouTube ATEEZ",
        "kind": "feed",
        "icon": "🎬",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2e4Ukj5Pfr7cb3KpJAFBdQ",
    },
    {
        "name": "Google News",
        "kind": "google_news",
        "icon": "📰",
        "lang": "es",
        "query": "ATEEZ",
        "edition": {"hl": "es-419", "gl": "US", "ceid": "US:es-419"},
    },
    {
        "name": "Google News",
        "kind": "google_news",
        "icon": "📰",
        "query": "ATEEZ",
        "edition": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    },
    {
        "name": "Google News Corea",
        "kind": "google_news",
        "icon": "🇰🇷",
        "query": "에이티즈",
        "edition": {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
    },
    {"name": "Soompi", "kind": "feed", "icon": "📰", "filter": True, "url": "https://www.soompi.com/feed"},
    {"name": "Koreaboo", "kind": "feed", "icon": "📰", "filter": True, "url": "https://www.koreaboo.com/feed/"},
    {
        "name": "Reddit r/ATEEZ",
        "kind": "feed",
        "icon": "💬",
        "url": "https://www.reddit.com/r/ATEEZ/new/.rss",
    },
]


@dataclass
class Item:
    id: str
    title: str
    link: str
    source: str
    icon: str
    lang: str | None
    date: datetime | None


def http_get(url: str, params: dict | None = None) -> requests.Response:
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r


def parse_feed(src: dict, content: bytes) -> list[Item]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"feed ilegible: {feed.bozo_exception}")
    items = []
    for e in feed.entries:
        title = e.get("title", "").strip()
        link = e.get("link", "")
        if not title or not link:
            continue
        if src.get("filter"):
            tags = " ".join(t.get("term") or "" for t in e.get("tags", []))
            if not ATEEZ_RE.search(f"{title} {e.get('summary', '')} {tags}"):
                continue
        item_id = e.get("id") or link
        source = src["name"]
        publisher = e.get("source", {}).get("title")
        if publisher:  # Google News: "Titular - Medio"
            title = title.removesuffix(f" - {publisher}")
            source = f"{source} · {publisher}"
            # El mismo artículo sale con distinto guid en cada edición y ventana.
            item_id = f"gnews:{publisher}:{re.sub(r'\W+', '', title.casefold())}"
        parsed = e.get("published_parsed") or e.get("updated_parsed")
        items.append(
            Item(
                id=item_id,
                title=title,
                link=link,
                source=source,
                icon=src["icon"],
                lang=src.get("lang"),
                date=datetime.fromtimestamp(timegm(parsed), timezone.utc) if parsed else None,
            )
        )
    return items


def fetch_feed(src: dict) -> list[Item]:
    return parse_feed(src, http_get(src["url"]).content)


def fetch_google_news(src: dict) -> list[Item]:
    items = []
    for window in GOOGLE_NEWS_WINDOWS:
        params = {"q": f"{src['query']} when:{window}", **src["edition"]}
        items += parse_feed(src, http_get(GOOGLE_NEWS_URL, params).content)
    return items


def fetch_kq_notices(src: dict) -> list[Item]:
    data = http_get(f"{KQ_SITE}/svc/space/api/v1/notices").json()
    return [
        Item(
            id=f"kq-notice:{n['id']}",
            title=n["title"].strip(),
            link=f"{KQ_SITE}/es/notice/{n['id']}",
            source=src["name"],
            icon=src["icon"],
            lang=None,
            date=datetime.fromisoformat(n["exposedAt"].replace("Z", "+00:00")),
        )
        for n in data["items"]
    ]


FETCHERS = {"feed": fetch_feed, "google_news": fetch_google_news, "kq_notices": fetch_kq_notices}


def to_spanish(text: str) -> str:
    """Traduce con el endpoint público (no oficial) de Google; si falla, devuelve el original."""
    try:
        params = {"client": "gtx", "sl": "auto", "tl": "es", "dt": "t", "q": text}
        segments = http_get(TRANSLATE_URL, params).json()[0]
        return "".join(s[0] for s in segments)
    except (requests.RequestException, ValueError, TypeError, IndexError) as e:
        print(f"::warning::Traducción fallida, se envía el original: {e!r}")
        return text


def format_message(item: Item) -> str:
    title_es = item.title if item.lang == "es" else to_spanish(item.title)
    is_ticket = TICKET_RE.search(f"{item.title} {title_es}")
    lines = [f"{'🎫' if is_ticket else item.icon} <b>{html.escape(title_es)}</b>"]
    if title_es.casefold() != item.title.casefold():
        lines.append(f"<i>{html.escape(item.title)}</i>")
    if is_ticket:
        lines.append("#concierto_entradas")
    lines.append(html.escape(item.source))
    lines.append(html.escape(item.link))
    return "\n".join(lines)


def telegram(token: str, method: str, **params) -> dict:
    # Sin raise_for_status: su mensaje incluye la URL, que contiene el token.
    for _ in range(3):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=HTTP_TIMEOUT
        )
        body = r.json()
        if r.status_code == 429:
            time.sleep(body["parameters"]["retry_after"] + 1)
            continue
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method} {r.status_code}: {body.get('description')}")
        return body
    raise RuntimeError(f"Telegram {method}: límite de envíos tras 3 intentos")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Falta la variable de entorno {name}")
    return value


def show_chat_ids() -> None:
    updates = telegram(require_env("TELEGRAM_BOT_TOKEN"), "getUpdates")["result"]
    chats = {}
    for u in updates:
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username")
    if not chats:
        sys.exit("Sin mensajes: escribe /start a tu bot en Telegram y vuelve a ejecutar.")
    for chat_id, name in chats.items():
        print(f"TELEGRAM_CHAT_ID={chat_id}  ({name})")


def collect() -> list[Item]:
    items, failed = [], 0
    for src in SOURCES:
        try:
            found = FETCHERS[src["kind"]](src)
        except (requests.RequestException, ValueError, KeyError) as e:
            failed += 1
            print(f"::warning::Fuente caída: {src['name']}: {e!r}")
            continue
        print(f"{src['name']}: {len(found)} entradas")
        items += found
    if failed == len(SOURCES):
        sys.exit("Todas las fuentes fallaron")
    return items


def run(dry_run: bool) -> None:
    now = datetime.now(timezone.utc)
    first_run = not STATE_FILE.exists()
    seen: dict[str, str] = {} if first_run else json.loads(STATE_FILE.read_text("utf-8"))
    if not dry_run:
        token, chat_id = require_env("TELEGRAM_BOT_TOKEN"), require_env("TELEGRAM_CHAT_ID")

    fresh, batch = [], set()
    for item in sorted(collect(), key=lambda i: i.date or now):
        if item.id in seen or item.id in batch:
            continue
        if item.date and now - item.date > MAX_AGE:
            continue
        batch.add(item.id)
        fresh.append(item)

    if first_run:
        # Solo una muestra, para no mandar de golpe todo lo acumulado.
        to_send = fresh[-FIRST_RUN_SAMPLE:]
        for item in fresh[:-FIRST_RUN_SAMPLE]:
            seen[item.id] = now.isoformat()
    else:
        to_send = fresh[:MAX_PER_RUN]

    sent = 0
    try:
        for item in to_send:
            text = format_message(item)
            if dry_run:
                print(f"\n{text}")
            else:
                telegram(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")
                time.sleep(1.1)  # límite de Telegram: ~1 mensaje/segundo por chat
            seen[item.id] = now.isoformat()  # solo lo enviado; lo demás se reintenta
            sent += 1
    finally:
        print(f"\nNuevas: {len(fresh)} · enviadas: {sent}")
        if not dry_run:
            cutoff = (now - STATE_TTL).isoformat()
            kept = {k: v for k, v in seen.items() if v >= cutoff}
            STATE_FILE.write_text(json.dumps(kept, ensure_ascii=False, indent=0), "utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="no envía ni guarda estado")
    group.add_argument("--chat-id", action="store_true", help="muestra tu chat_id")
    args = parser.parse_args()
    if args.chat_id:
        show_chat_ids()
    else:
        run(args.dry_run)


if __name__ == "__main__":
    main()
