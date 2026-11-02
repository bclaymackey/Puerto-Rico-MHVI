import re
import uuid
from datetime import datetime

import pandas as pd

from data import get_db_connection

from mongodb.client import is_available as mongo_available

from .chat_db import ensure_session, ensure_user
from .chat_history_manager import (
    build_llm_context,
    save_ai_response,
    save_ai_response_bilingual,
    set_last_user_message_languages,
)
from .data_context_builder import find_all_municipalities
from .llm_caller import call_llm
from .navigation_guide import (
    build_custom_report_response,
    build_navigation_response,
    is_custom_report_intent,
    is_navigation_intent,
)
from .prompt_context import build_prompt_context
from .report_data_builder import get_report_data
from .report_generator import generate_report_text
from .report_pdf import build_report_pdf
from .session_summary import maybe_update_summary


_REPORT_KEYWORDS_EN = [
    "pdf",
    "report",
    "printable report",
    "municipality report",
    "full report",
    "vulnerability report",
    "download report",
    "generate a report",
    "create a report",
    "make a report",
]
_REPORT_KEYWORDS_ES = [
    "pdf",
    "informe",
    "reporte",
    "informe municipal",
    "informe completo",
    "informe de vulnerabilidad",
    "descargar informe",
    "genera un informe",
    "generar un informe",
    "crear un informe",
    "haz un informe",
]


# ── Answers from the dashboard's own data ───────────────────────────────────
# The dashboard registers one function at startup (MHVI_Dashboard_App.py →
# dashboard/chat_bridge.py:answer_question). It is asked first, for every
# message, and returns one of:
#   {"kind": "grounded", "text": ..., "transcript": ..., "rows": [...], ...}
#       a value/statistic question answered from the same numbers the chart
#       uses, with the rows it used (usability study Exercise 3)
#   {"kind": "export_chat"}   "export this conversation"
#   None                      not for it — the normal flow below runs
# It needs neither MongoDB nor an AI key.
_DASHBOARD_ANSWERER = None


def register_dashboard_answerer(fn) -> None:
    global _DASHBOARD_ANSWERER
    _DASHBOARD_ANSWERER = fn


def _unavailable_message(language: str) -> str:
    if language == "es":
        return ("El asistente de IA no está disponible temporalmente. Las "
                "preguntas sobre valores del panel — por ejemplo, \"¿Cuál es el "
                "puntaje general de Arecibo en 2023?\" — sí funcionan.")
    return ("The AI assistant is temporarily unavailable. Questions about "
            "values on the dashboard — for example, \"What is Arecibo's "
            "overall score in 2023?\" — still work.")


def _record_turn(session_id, user_id, user_input, reply, language) -> None:
    """Save a question and its answer to the chat history, if the database is
    reachable. The answer is shown either way."""
    if not mongo_available():
        return
    try:
        ensure_user(user_id)
        ensure_session(session_id, user_id)
        build_llm_context(session_id, user_input, language=language)
        save_ai_response(session_id, reply, language)
    except Exception as e:
        print(f"[_record_turn] history not saved: {e}")


# Server-side, single-process cache. Re-readable: consume_report only pops
# when a new report replaces it (see _generate_report_response's overwrite).
# Acceptable for single-worker Dash dev; for multi-worker prod, swap for Redis.
_REPORT_CACHE: dict = {}


def _is_report_intent(text_lower: str, language: str) -> bool:
    keywords = _REPORT_KEYWORDS_ES if language == "es" else _REPORT_KEYWORDS_EN
    # Always also accept the universal English "pdf"/"report" triggers.
    extras = ["pdf", "report"]
    for kw in keywords + extras:
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            return True
    return False


def _ack_message(municipality: str, language: str, report_data: dict) -> str:
    """Ready-message plus the raw scores the PDF was built from, so the data
    behind the report is visible in chat and not only inside the download.
    """
    overall = report_data.get("overall_score")
    categories = report_data.get("categories") or {}

    year = report_data.get("year")
    in_year = f" ({year})" if year else ""
    if language == "es":
        lines = [f"Tu informe de {municipality} está listo. Datos utilizados{in_year}:"]
        overall_label = "General"
    else:
        lines = [f"Your {municipality} report is ready. Data used{in_year}:"]
        overall_label = "Overall"

    if overall is not None:
        lines.append(f"• {overall_label}: {overall}")
    for name, value in categories.items():
        lines.append(f"• {name}: {value}")

    if language == "es":
        lines.append("También puedes explorar cada categoría en el mapa usando el menú \"Map Category\".")
    else:
        lines.append("You can also explore each category on the map using the \"Map Category\" dropdown.")

    return "\n".join(lines)


def _need_municipality_message(language: str) -> str:
    if language == "es":
        return (
            "Por favor especifica un municipio para el informe. "
            "Ejemplo: \"Genera un informe para Arecibo\"."
        )
    return (
        "Please specify a municipality for the report. "
        "Example: \"Generate a report for Arecibo\"."
    )


def _no_data_message(municipality: str, language: str) -> str:
    if language == "es":
        return f"No se encontraron datos suficientes para generar un informe de {municipality}."
    return f"Not enough data was found to generate a report for {municipality}."


def _safe_filename_stem(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_").lower()
    return cleaned or "municipality"


def _generate_report_response(user_input: str, language: str, session_id: str) -> dict:
    """Detect municipality, build report, cache PDF, return report dict."""
    conn = get_db_connection()
    try:
        muni_df = pd.read_sql("SELECT name, fips_code FROM municipalities", conn)
    finally:
        conn.close()

    found = find_all_municipalities(user_input.lower(), muni_df)
    if not found:
        msg = _need_municipality_message(language)
        save_ai_response(session_id, msg, language)
        return {"kind": "text", "text": msg}

    # v1: single municipality only — take the first mention if multiple.
    municipality = found[0]["name"]
    report_data = get_report_data(municipality)
    if not report_data or not report_data.get("categories"):
        msg = _no_data_message(municipality, language)
        save_ai_response(session_id, msg, language)
        return {"kind": "text", "text": msg}

    try:
        report_text = generate_report_text(report_data, language)
        pdf_bytes = build_report_pdf(report_text, municipality, language)
    except Exception as e:
        print(f"[_generate_report_response] error: {e}")
        msg = _no_data_message(municipality, language)
        save_ai_response(session_id, msg, language)
        return {"kind": "text", "text": msg}

    token = uuid.uuid4().hex
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"{_safe_filename_stem(municipality)}_vulnerability_report_{timestamp}.pdf"
    _REPORT_CACHE[token] = (pdf_bytes, filename)

    ack = _ack_message(municipality, language, report_data)
    save_ai_response(session_id, ack, language)
    return {
        "kind": "report",
        "message": ack,
        "report_token": token,
        "filename": filename,
        "municipality": municipality,
    }


def consume_report(token: str):
    """Return (pdf_bytes, filename) for a token, or None if missing.

    Does not evict the entry — the report button allows repeated downloads
    (with a confirmation) of the same pinned report, per v1's "one
    outstanding report at a time" design.
    """
    return _REPORT_CACHE.get(token)


def process_chat_message(
    user_input: str,
    language: str = "en",
    session_id: str = "default",
    user_id: str | None = None,
    dashboard_state: dict | None = None,
) -> dict:
    """Return a structured response dict.

    Shapes:
        {"kind": "text",     "text": str}
        {"kind": "report",   "message": str, "report_token": str, "filename": str, ...}
        {"kind": "grounded", "text": str, "rows": [...], ...}   (see above)
        {"kind": "export_chat", "text": str}

    dashboard_state: what the dashboard is showing (municipalities, indicators,
    year, display mode), used to answer value questions about it.
    """
    # Value questions and "export this chat" first — answered from the
    # dashboard's data, so they work even without MongoDB or an AI key.
    if _DASHBOARD_ANSWERER is not None:
        try:
            special = _DASHBOARD_ANSWERER(user_input, language, dashboard_state)
        except Exception as e:
            print(f"[process_chat_message] dashboard answer failed: {e}")
            special = None
        if special and special.get("kind") == "export_chat":
            text = ("Exportando esta conversación como PDF." if language == "es"
                    else "Exporting this conversation as a PDF.")
            _record_turn(session_id, user_id, user_input, text, language)
            return {"kind": "export_chat", "text": text}
        if special and special.get("kind") == "grounded":
            _record_turn(session_id, user_id, user_input,
                         special.get("transcript") or special.get("text", ""),
                         language)
            return special

    # Everything below keeps its history in MongoDB.
    if not mongo_available():
        return {"kind": "text", "text": _unavailable_message(language)}

    # Make sure parent rows exist before any message INSERT.
    ensure_user(user_id)
    ensure_session(session_id, user_id)

    text_lower = (user_input or "").lower()

    if is_custom_report_intent(text_lower, language):
        # Checked before _is_report_intent: "custom report" would otherwise
        # be swallowed by the bare "report" keyword and misrouted into the
        # single-municipality PDF flow below.
        steps = build_custom_report_response(language)
        build_llm_context(session_id, user_input, language=language)
        save_ai_response(session_id, steps, language)
        return {"kind": "text", "text": steps}

    if _is_report_intent(text_lower, language):
        # Record the user message in history so the report flow shows up there.
        build_llm_context(session_id, user_input, language=language)
        return _generate_report_response(user_input, language, session_id)

    if is_navigation_intent(text_lower, language):
        steps = build_navigation_response(user_input, language)
        if steps is not None:
            build_llm_context(session_id, user_input, language=language)
            save_ai_response(session_id, steps, language)
            return {"kind": "text", "text": steps}
        # No confident navigation match (e.g. an unrelated "how do I..."
        # question) — fall through to the normal LLM turn below, which
        # applies the system prompt's scope-control / redirect rules.

    ctx = build_prompt_context(session_id, user_id, user_input, language)
    reply = call_llm(
        ctx["history"],
        ctx["data_context"],
        language,
        user_name=ctx["user_name"],
        memory_context=ctx["memory_context"],
        summary_context=ctx["summary_context"],
    )
    # One call returns the answer, title, AND the user query — all bilingual.
    # Backfill the just-saved user message so its Spanish/English copies are ready
    # (no lazy translation on switch), then save the assistant reply + title.
    set_last_user_message_languages(
        session_id, reply.get("query_en"), reply.get("query_es")
    )
    text_en, text_es = reply["en"], reply["es"]
    save_ai_response_bilingual(
        session_id, text_en, text_es, language,
        title_en=reply.get("title_en"), title_es=reply.get("title_es"),
    )
    maybe_update_summary(session_id)
    active_text = text_es if language == "es" else text_en
    return {"kind": "text", "text": active_text}
