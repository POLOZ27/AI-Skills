"""
title: CSEEC Source Texts
description: Look up the original wording of public-domain texts (Library of Congress Aesop fables, Project Gutenberg books) from the school's local library, reading the official site only when the library does not have it yet.
author: CSEEC
version: 0.2.1
license: MIT
"""

import asyncio
import csv
from datetime import datetime, timezone
import html
import io
import ipaddress
import json
import os
import re
import socket
import sqlite3
import ssl
import threading
import time
import unicodedata
from typing import Literal
from urllib.parse import urlsplit
from urllib.request import (
    build_opener,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
)
from urllib.robotparser import RobotFileParser

USER_AGENT = "CSEEC-Source-Reader/0.1 (+https://www.cseec.ca)"
ROBOT_AGENTS = (USER_AGENT, "ChatGPT-User", "Claude-User", "Claude-Web")
TLS = ssl.create_default_context()
LIBRARY_DIR = "/app/backend/data/source_library"
LIBRARY_DB = os.path.join(LIBRARY_DIR, "library.db")

AESOP_BASE = "https://read.gov/aesop/"
AESOP_INDEX = AESOP_BASE + "001.html"
GUTENBERG_TEXT = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
GUTENBERG_PAGE = "https://www.gutenberg.org/ebooks/{id}"
GUTENBERG_CATALOG = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
# Only these public-domain routes are ever read.
ALLOWED = {
    "read.gov": ("/aesop/",),
    "www.gutenberg.org": ("/cache/epub/",),
}
SOURCE_NAMES = {
    "loc_aesop": "Library of Congress, The Aesop for Children (read.gov/aesop)",
    "gutenberg": "Project Gutenberg",
}
PAGE_LIMIT = 2 * 1024 * 1024
BOOK_LIMIT = 12 * 1024 * 1024
CATALOG_LIMIT = 64 * 1024 * 1024
ROBOTS_TIMEOUT = 5
PAGE_TIMEOUT = 10
BOOK_TIMEOUT = 30
ROBOTS_TTL = 24 * 3600
AESOP_INDEX_TTL = 30 * 24 * 3600
# Tool output is re-read by the model on every later round; return long texts in parts.
PART_CHARS = 12000
MATCH_LIMIT = 5
NORM_VERSION = "2"
_ROBOTS = {}
_HOST_LOCKS = {}
_HOST_LOCKS_GUARD = threading.Lock()
_DB_LOCK = threading.Lock()


def host_lock(hostname):
    with _HOST_LOCKS_GUARD:
        return _HOST_LOCKS.setdefault(hostname, threading.Lock())


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize(text):
    """Lower-case, '&' as 'and', no punctuation or accents that differ between editions."""
    text = html.unescape(text or "").lower().replace("&", " and ")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"[’'`]", "", text)
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def connect():
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    db = sqlite3.connect(LIBRARY_DB, timeout=30)
    db.execute(
        "CREATE TABLE IF NOT EXISTS catalog (id TEXT PRIMARY KEY, source TEXT, title TEXT,"
        " author TEXT, language TEXT, norm TEXT)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS texts (id TEXT PRIMARY KEY, source TEXT, title TEXT,"
        " author TEXT, url TEXT, fetched_at TEXT, body TEXT)"
    )
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    row = db.execute("SELECT value FROM meta WHERE key='norm_version'").fetchone()
    if not row or row[0] != NORM_VERSION:
        # normalize() changed (accents are now stripped): recompute stored search keys once.
        with _DB_LOCK, db:
            for text_id, source, title, author in db.execute(
                "SELECT id, source, title, author FROM catalog"
            ).fetchall():
                key = title if source == "loc_aesop" else title + " " + author
                db.execute("UPDATE catalog SET norm=? WHERE id=?", (normalize(key), text_id))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('norm_version', ?)", (NORM_VERSION,))
    return db


def validate_url(url, resolve=True):
    parts = urlsplit(url)
    prefixes = ALLOWED.get(parts.hostname, ())
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.query
        or parts.fragment
        or not any(parts.path.startswith(p) for p in prefixes)
        or "%" in parts.path
        or ".." in parts.path
        or "\\" in parts.path
    ):
        raise ValueError("URL outside approved public-domain routes")
    if resolve:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(a[4][0]).is_global for a in addresses
        ):
            raise ValueError("Non-public destination blocked")
    return url


class CheckedRedirect(HTTPRedirectHandler):
    def __init__(self):
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 3:
            raise ValueError("Redirect limit reached")
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def robots_allowed(url):
    """Honour the site's robots.txt for this tool and for user-triggered AI fetchers (cached 24 hours)."""
    parts = urlsplit(url)
    cached = _ROBOTS.get(parts.hostname)
    if not cached or time.time() - cached[0] > ROBOTS_TTL:
        parser = RobotFileParser()
        try:
            opener = build_opener(ProxyHandler({}), HTTPSHandler(context=TLS))
            with opener.open(
                Request(f"https://{parts.hostname}/robots.txt", headers={"User-Agent": USER_AGENT}),
                timeout=ROBOTS_TIMEOUT,
            ) as response:
                parser.parse(response.read(512 * 1024).decode("utf-8", errors="replace").splitlines())
        except Exception as error:
            # A missing robots.txt allows reading; any other failure is treated as "do not read".
            if getattr(error, "code", None) in (404, 410):
                parser.parse([])
            else:
                parser.parse(["User-agent: *", "Disallow: /"])
        cached = _ROBOTS[parts.hostname] = (time.time(), parser)
    return all(cached[1].can_fetch(agent, url) for agent in ROBOT_AGENTS)


def fetch(url, limit=PAGE_LIMIT, timeout=PAGE_TIMEOUT):
    """Return the decoded body of an allowlisted public-domain URL."""
    lock = host_lock(urlsplit(url).hostname)
    if not lock.acquire(timeout=60):
        raise TimeoutError("Another read of this site is still running")
    try:
        validate_url(url)
        if not robots_allowed(url):
            raise PermissionError("robots.txt disallows automated reading")
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=TLS), CheckedRedirect())
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        with opener.open(request, timeout=timeout) as response:
            validate_url(response.url)
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("Response too large")
            return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    finally:
        lock.release()


def strip_tags(fragment):
    fragment = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1\s*>", " ", fragment)
    return " ".join(html.unescape(re.sub(r"(?s)<[^>]+>", " ", fragment)).split())


# ---------- Library of Congress: The Aesop for Children ----------

def aesop_index(db):
    """Store the 146 fable titles from the table of contents (refreshed monthly)."""
    row = db.execute("SELECT value FROM meta WHERE key='aesop_index_at'").fetchone()
    if row and time.time() - float(row[0]) < AESOP_INDEX_TTL:
        return
    page = fetch(AESOP_INDEX)
    entries = re.findall(r'<a\s+href="(\d{3})\.html"[^>]*>(.*?)</a>', page, flags=re.S)
    if len(entries) < 100:
        raise ValueError("Library of Congress table of contents changed; not updated")
    with _DB_LOCK, db:
        for number, title in entries:
            title = strip_tags(title)
            db.execute(
                "INSERT OR REPLACE INTO catalog VALUES (?, 'loc_aesop', ?, 'Aesop', 'en', ?)",
                (f"loc_aesop:{number}", title, normalize(title)),
            )
        db.execute("INSERT OR REPLACE INTO meta VALUES ('aesop_index_at', ?)", (str(time.time()),))


def read_aesop(number):
    url = f"{AESOP_BASE}{number}.html"
    page = fetch(url)
    body = re.search(r'(?s)<div id="page">(.*?)<!--page-->', page)
    if not body:
        raise ValueError("Fable page layout changed; text not found")
    body = body.group(1)
    title = strip_tags((re.search(r"(?s)<h1[^>]*>(.*?)</h1>", body) or [None, ""])[1])
    paragraphs = [strip_tags(p) for p in re.findall(r"(?s)<p[^>]*>(.*?)</p>", body)]
    morals = [strip_tags(m) for m in re.findall(r"(?s)<blockquote[^>]*>(.*?)</blockquote>", body)]
    paragraphs = [p for p in paragraphs if p]
    if not title or not paragraphs:
        raise ValueError("Fable page layout changed; text not found")
    text = "\n\n".join(paragraphs)
    if morals:
        text += "\n\nMoral: " + " ".join(m for m in morals if m)
    return {"title": title, "author": "Aesop", "url": url, "body": text}


# ---------- Project Gutenberg ----------

def gutenberg_body(raw):
    """Drop the Project Gutenberg licence header and footer, keeping the work itself."""
    start = re.search(r"(?m)^\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG.*$", raw)
    end = re.search(r"(?m)^\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG.*$", raw)
    text = raw[start.end() if start else 0 : end.start() if end else len(raw)]
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()


def read_gutenberg(number, db):
    url = GUTENBERG_TEXT.format(id=number)
    raw = fetch(url, limit=BOOK_LIMIT, timeout=BOOK_TIMEOUT)
    title = author = ""
    row = db.execute("SELECT title, author FROM catalog WHERE id=?", (f"gutenberg:{number}",)).fetchone()
    if row:
        title, author = row
    else:
        title = (re.search(r"(?m)^Title: *(.+)$", raw) or [None, f"Gutenberg #{number}"])[1].strip()
        author = (re.search(r"(?m)^Author: *(.+)$", raw) or [None, ""])[1].strip()
    return {
        "title": title,
        "author": author,
        "url": GUTENBERG_PAGE.format(id=number),
        "body": gutenberg_body(raw),
    }


def load_gutenberg_catalog(db):
    """Store Project Gutenberg's own catalogue (title/author/language only) for local title search."""
    raw = fetch(GUTENBERG_CATALOG, limit=CATALOG_LIMIT, timeout=120)
    rows = 0
    with _DB_LOCK, db:
        for record in csv.DictReader(io.StringIO(raw)):
            if record.get("Type") != "Text" or not record.get("Text#", "").isdigit():
                continue
            title = " ".join((record.get("Title") or "").split())
            author = " ".join((record.get("Authors") or "").split())
            db.execute(
                "INSERT OR REPLACE INTO catalog VALUES (?, 'gutenberg', ?, ?, ?, ?)",
                (f"gutenberg:{record['Text#']}", title, author, record.get("Language") or "",
                 normalize(title + " " + author)),
            )
            rows += 1
        db.execute("INSERT OR REPLACE INTO meta VALUES ('gutenberg_catalog_at', ?)", (str(time.time()),))
    return rows


# ---------- Library ----------

def stored_text(db, text_id):
    row = db.execute(
        "SELECT source, title, author, url, fetched_at, body FROM texts WHERE id=?", (text_id,)
    ).fetchone()
    if row:
        return dict(zip(("source", "title", "author", "url", "fetched_at", "body"), row))
    return None


def get_text(db, text_id):
    """Return a text from the local library, reading it from its official site once if needed."""
    found = stored_text(db, text_id)
    if found:
        return found
    source, _, number = text_id.partition(":")
    if source == "loc_aesop" and re.fullmatch(r"\d{3}", number):
        item = read_aesop(number)
    elif source == "gutenberg" and re.fullmatch(r"\d{1,6}", number):
        item = read_gutenberg(number, db)
    else:
        raise ValueError("Unknown text id")
    item.update(source=source, fetched_at=now_iso())
    with _DB_LOCK, db:
        db.execute(
            "INSERT OR REPLACE INTO texts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (text_id, source, item["title"], item["author"], item["url"], item["fetched_at"], item["body"]),
        )
    return item


def search_catalog(db, title, author, source):
    words = normalize(title).split()
    author_words = normalize(author).split()
    if not words:
        return []
    sources = ("loc_aesop", "gutenberg") if source == "any" else (source,)
    # Require every title word except very short ones; rank exact titles first.
    required = [w for w in words if len(w) > 2 and w not in ("the", "and")] or words
    clauses = " AND ".join("norm LIKE ?" for _ in required + author_words)
    params = [f"%{w}%" for w in required + author_words]
    rows = db.execute(
        f"SELECT id, source, title, author, language FROM catalog WHERE source IN"
        f" ({','.join('?' * len(sources))}) AND {clauses} LIMIT 200",
        list(sources) + params,
    ).fetchall()
    wanted = " ".join(words)
    stored = {
        r[0] for r in db.execute(
            f"SELECT id FROM texts WHERE id IN ({','.join('?' * len(rows))})", [r[0] for r in rows]
        )
    } if rows else set()

    def rank(row):
        name = normalize(row[2])
        partial = bool(re.search(r"\b(part|volume|vol|book|chapter)\s+\w+", name)) and not re.search(
            r"\b(part|volume|vol|book|chapter)\b", wanted
        )
        number = int(row[0].partition(":")[2]) if row[1] == "gutenberg" else 0
        # Adaptations list the original author second; the teacher's author should be the first one.
        first_author = normalize((row[3] or "").split(";")[0])
        return (
            bool(author_words) and not all(w in first_author for w in author_words),
            # Books already in the library were chosen and checked by hand.
            row[0] not in stored,
            name != wanted,
            not name.startswith(wanted),
            partial,
            row[1] != "loc_aesop",
            row[4] not in ("en", ""),
            number,
            len(name),
        )

    return sorted(rows, key=rank)[:MATCH_LIMIT]


def part_of(item, part):
    body = item["body"]
    total = max(1, -(-len(body) // PART_CHARS))
    part = min(max(1, part), total)
    return body[(part - 1) * PART_CHARS : part * PART_CHARS], part, total


def citation(item):
    return f'"{item["title"]}", {SOURCE_NAMES[item["source"]]}, {item["url"]} (retrieved {item["fetched_at"]})'


def find(title, author, source):
    db = connect()
    try:
        notes = []
        if source in ("any", "loc_aesop"):
            try:
                aesop_index(db)
            except Exception as error:
                notes.append(f"Library of Congress list not refreshed: {type(error).__name__}")
        if source in ("any", "gutenberg") and not db.execute(
            "SELECT 1 FROM meta WHERE key='gutenberg_catalog_at'"
        ).fetchone():
            notes.append("Project Gutenberg catalogue not installed yet; Gutenberg titles cannot be searched.")
        matches = search_catalog(db, title, author, source)
        result = {
            "matches": [
                {
                    "text_id": row[0],
                    "title": row[2],
                    "author": row[3],
                    "source": SOURCE_NAMES[row[1]],
                    "in_local_library": bool(stored_text(db, row[0])),
                }
                for row in matches
            ]
        }
        if not matches:
            result["status"] = "not_found"
            result["instruction"] = (
                "Not in the public-domain library. Tell the teacher and ask them to paste or upload the original text. "
                "Do not write the text from memory."
            )
        elif normalize(matches[0][2]) == normalize(title) and matches[0][1] == "loc_aesop":
            # A fable is short: return it whole so no second call is needed.
            item = get_text(db, matches[0][0])
            result["text"] = {"text_id": matches[0][0], "cite": citation(item), "body": item["body"]}
            result["instruction"] = "Use this exact wording. Put the cite line under the passage title."
        else:
            result["instruction"] = (
                "Pick the match the teacher meant (ask if unclear), then call read_source_text with its text_id."
            )
        if notes:
            result["notes"] = notes
        return result
    finally:
        db.close()


class Tools:
    async def find_source_text(
        self,
        title: str,
        author: str = "",
        source: Literal["any", "loc_aesop", "gutenberg"] = "any",
    ) -> str:
        """Look up a public-domain text by title in the school's library (Library of Congress Aesop fables, Project Gutenberg). Call ONLY when the teacher explicitly asks you to look up / find / use a specific published text or edition (e.g. "use the Library of Congress version of The Mother and the Wolf", "查一下……原文"). Never call it on your own initiative. A short fable comes back whole; for books, call read_source_text next.

        :param title: Title of the work as the teacher wrote it, e.g. "The Mother and the Wolf".
        :param author: Optional author, e.g. "Dickens".
        :param source: loc_aesop for the Library of Congress Aesop fables, gutenberg for Project Gutenberg books, any if unsure.
        """
        try:
            data = await asyncio.to_thread(find, str(title)[:200], str(author)[:100], source)
        except Exception as error:
            data = {
                "status": "error",
                "message": type(error).__name__,
                "instruction": "Tell the teacher the library could not be read and ask for the original text. Do not write it from memory.",
            }
        return json.dumps(data, ensure_ascii=False)

    async def read_source_text(self, text_id: str, part: int = 1) -> str:
        """Read the exact text of a work found with find_source_text, in parts of about 12,000 characters. Use the wording as is and cite it.

        :param text_id: The text_id from find_source_text, e.g. "gutenberg:1400".
        :param part: Which part to read, starting at 1.
        """

        def run():
            db = connect()
            try:
                item = get_text(db, str(text_id))
                body, number, total = part_of(item, int(part))
                return {
                    "text_id": text_id,
                    "cite": citation(item),
                    "part": number,
                    "total_parts": total,
                    "body": body,
                }
            finally:
                db.close()

        try:
            data = await asyncio.to_thread(run)
        except Exception as error:
            data = {
                "status": "error",
                "message": type(error).__name__,
                "instruction": "Tell the teacher the text could not be read and ask for the original. Do not write it from memory.",
            }
        return json.dumps(data, ensure_ascii=False)

    async def search_in_source_text(self, text_id: str, phrase: str) -> str:
        """Find which parts of a long work contain a chapter heading, poem title or phrase, so you read only that part.

        :param text_id: The text_id from find_source_text.
        :param phrase: Words to look for, e.g. "CHAPTER III" or "The Tyger".
        """

        def run():
            db = connect()
            try:
                item = get_text(db, str(text_id))
                body = item["body"]
                needle = str(phrase).strip().lower()
                hits = []
                start = 0
                while needle and len(hits) < 10:
                    index = body.lower().find(needle, start)
                    if index < 0:
                        break
                    snippet = " ".join(body[max(0, index - 80) : index + 160].split())
                    hits.append({"part": index // PART_CHARS + 1, "snippet": snippet})
                    start = index + len(needle)
                return {"text_id": text_id, "cite": citation(item), "hits": hits}
            finally:
                db.close()

        try:
            data = await asyncio.to_thread(run)
        except Exception as error:
            data = {"status": "error", "message": type(error).__name__}
        return json.dumps(data, ensure_ascii=False)


def seed(aesop=True, gutenberg_catalog=True, delay=1.0):
    """Fill the local library: all Library of Congress fables, and the Gutenberg title catalogue."""
    db = connect()
    report = {}
    try:
        if aesop:
            aesop_index(db)
            ids = [row[0] for row in db.execute("SELECT id FROM catalog WHERE source='loc_aesop' ORDER BY id")]
            stored = failed = 0
            for text_id in ids:
                if stored_text(db, text_id):
                    stored += 1
                    continue
                try:
                    get_text(db, text_id)
                    stored += 1
                except Exception:
                    failed += 1
                time.sleep(delay)
            report["loc_aesop"] = {"fables": len(ids), "stored": stored, "failed": failed}
        if gutenberg_catalog:
            report["gutenberg_catalog_titles"] = load_gutenberg_catalog(db)
    finally:
        db.close()
    return report


def prefetch_list(path, delay=2.0):
    """Download each "title | author" line from Project Gutenberg into the library once."""
    db = connect()
    report = {"stored": [], "already": [], "not_found": [], "failed": []}
    try:
        with open(path, encoding="utf-8") as handle:
            lines = [l.strip() for l in handle if l.strip() and not l.startswith("#")]
        for line in lines:
            title, _, author = (part.strip() for part in line.partition("|"))
            matches = [row for row in search_catalog(db, title, author, "gutenberg") if row[4] in ("en", "")]
            if not matches:
                report["not_found"].append(line)
                continue
            text_id = matches[0][0]
            if stored_text(db, text_id):
                report["already"].append(text_id)
                continue
            try:
                get_text(db, text_id)
                report["stored"].append(f"{text_id} {matches[0][2]}")
            except Exception as error:
                report["failed"].append(f"{text_id} {type(error).__name__}")
            time.sleep(delay)
    finally:
        db.close()
    return report
