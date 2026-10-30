"""MongoDB connection, collections, and low-level helpers for the chat database.

A single module-level MongoClient is used because PyMongo clients are
thread-safe and connection-pooled — there is no need for the per-call
open/close pattern SQLite required.
"""

import os
import time

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient, ReturnDocument
from pymongo.errors import PyMongoError

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "pr_chat")

# How long one MongoDB call may wait for the server before giving up. PyMongo's
# own default is 30 s, which froze the whole page whenever the database was
# unreachable. A few seconds is plenty for a hosted cluster.
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "3000"))

try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS)
except Exception as exc:  # e.g. a mongodb+srv:// address whose DNS lookup fails
    print(f"[chat-db] ❌ MONGODB_URI could not be used ({exc}). Chat history, "
          "sign-in and tickets will show as temporarily unavailable.")
    # A client that can never connect, so every call fails fast and cleanly.
    client = MongoClient("mongodb://127.0.0.1:1",
                         serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS, connect=False)
db = client[MONGODB_DB]

users = db.users
sessions = db.sessions
messages = db.messages
counters = db.counters


_logged_connection = False


def _log_connection() -> None:
    """Print a clear one-line banner confirming the chat DB backend on startup.

    Prints once per process — init_chat_mongo() may be called more than once
    (module import + explicit app startup).
    """
    global _logged_connection
    if _logged_connection:
        return
    _logged_connection = True
    try:
        info = client.server_info()  # forces a real round-trip to the server
        version = info.get("version", "?")
        host = client.address[0] if client.address else _safe_uri()
        print(
            f"[chat-db] ✅ MongoDB connected — server v{version} "
            f"@ {host}, database '{MONGODB_DB}' (chat history: users/sessions/messages)"
        )
    except PyMongoError as exc:
        print(
            f"[chat-db] ❌ MongoDB NOT reachable at {_safe_uri()} ({exc}). "
            "Locally, start it with: brew services start mongodb-community"
        )


def next_message_id() -> int:
    """Dense monotonic integer id for a new message.

    Replaces SQLite's AUTOINCREMENT `messages.id`, which is load-bearing: it is
    used for chronological ordering, history windows, and the rolling-summary
    high-water mark (`last_summarized_message_id`). ObjectId is not a dense
    integer, so we keep our own counter.
    """
    doc = counters.find_one_and_update(
        {"_id": "messages"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


# ── availability ────────────────────────────────────────────────────────────
# The dashboard must keep working when MongoDB cannot be reached. Callers ask
# is_available() first; the answer is cached for a short while so a database
# outage costs one timeout, not one per click.
_STATUS = {"ok": None, "checked": 0.0}
_RECHECK_WHEN_UP_S = 60
_RECHECK_WHEN_DOWN_S = 30
_INDEXES = {"ready": False}


def is_available() -> bool:
    """True if MongoDB answered a ping recently. Never raises."""
    now = time.monotonic()
    ttl = _RECHECK_WHEN_UP_S if _STATUS["ok"] else _RECHECK_WHEN_DOWN_S
    if _STATUS["ok"] is not None and now - _STATUS["checked"] < ttl:
        return _STATUS["ok"]
    try:
        client.admin.command("ping")
        ok = True
    except Exception:
        ok = False
    previously = _STATUS["ok"]
    _STATUS.update(ok=ok, checked=now)
    if ok and not _INDEXES["ready"]:
        try:
            _create_indexes()
        except Exception as exc:
            print(f"[chat-db] ⚠️  connected, but index setup failed: {exc}")
    if ok != previously:
        if ok:
            _log_connection()
        else:
            print(f"[chat-db] ❌ MongoDB NOT reachable ({_safe_uri()}). The dashboard "
                  "keeps running; chat history, sign-in and tickets show as "
                  "temporarily unavailable until it is back.")
    return ok


def mark_unavailable() -> None:
    """Record a failed call so the next few requests skip MongoDB at once."""
    _STATUS.update(ok=False, checked=time.monotonic())


def _safe_uri() -> str:
    """MONGODB_URI without its password, for log lines."""
    uri = MONGODB_URI
    if "@" in uri and "://" in uri:
        scheme, rest = uri.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return uri


def init_chat_mongo() -> None:
    """Create indexes and seed the message counter.

    Schemaless — no PRAGMA/ALTER migration ladder. Safe to call repeatedly.
    If MongoDB cannot be reached this prints a warning and returns instead of
    stopping the app; the indexes are created the first time it answers.
    """
    if not is_available():
        return
    _create_indexes()


def _create_indexes() -> None:
    _log_connection()
    sessions.create_index(
        [("user_id", ASCENDING), ("updated_at", DESCENDING), ("created_at", DESCENDING)]
    )
    sessions.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    messages.create_index([("session_id", ASCENDING), ("_id", ASCENDING)])
    messages.create_index(
        [("session_id", ASCENDING), ("role", ASCENDING), ("_id", ASCENDING)]
    )
    # One text index per collection, over the three content columns, for the
    # cross-session retrieval candidate fetch (lexical_search).
    messages.create_index([("content", TEXT), ("content_en", TEXT), ("content_es", TEXT)])
    counters.update_one({"_id": "messages"}, {"$setOnInsert": {"seq": 0}}, upsert=True)

    # Auth: unique email, session-token lookup, and a TTL index that auto-expires
    # sessions. Imported here (not at module top) to avoid an import cycle —
    # auth.db imports this module's `db`.
    from auth.db import ensure_auth_indexes

    ensure_auth_indexes()

    from tickets.db import ensure_ticket_indexes

    ensure_ticket_indexes()
    _INDEXES["ready"] = True
