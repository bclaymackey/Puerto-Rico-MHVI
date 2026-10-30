import difflib
import re
import unicodedata

import pandas as pd

from data import (ALLOWED_TABLES, INDEX_INDICATOR, OVERALL_INDICATOR,
                  OVERALL_TABLE, get_db_connection, map_year)

from .hyperparameters import RANKING_TOP_N
from .report_data_builder import get_report_data


def _strip_accents(s: str) -> str:
    """Remove diacritics so "Mayaguez" matches "Mayagüez", "Anasco" matches
    "Añasco", etc. Precomposed accented Latin letters decompose to one base
    letter plus one combining mark under NFKD, so stripping the mark leaves
    the string the same length — matched offsets from find_all_municipalities
    still line up with the original text.
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if unicodedata.category(c) != "Mn"
    )


CATEGORY_KEYWORDS = [
    # English
    ("health care",       "Healthcare_Access",              "Healthcare"),
    ("healthcare",        "Healthcare_Access",              "Healthcare"),
    ("health risk",       "Health_Risk_Behaviors",          "Health Risk"),
    ("built environment", "Neighborhood_Built_Environment", "Neighborhood"),
    ("neighborhood",      "Neighborhood_Built_Environment", "Neighborhood"),
    ("transportation",    "Transportation_Accessibility",   "Transportation"),
    ("transit",           "Transportation_Accessibility",   "Transportation"),
    ("employment",        "Economic_Employment",            "Employment"),
    ("economic",          "Economic_Employment",            "Employment"),
    ("jobs",              "Economic_Employment",            "Employment"),
    ("education",         "Education",                      "Education"),
    ("housing",           "Housing",                        "Housing"),
    ("food",              "Food_Water_Basic_Needs",         "Food & Basic Needs"),
    ("water",             "Food_Water_Basic_Needs",         "Food & Basic Needs"),
    ("basic needs",       "Food_Water_Basic_Needs",         "Food & Basic Needs"),
    ("social",            "Social_Relationships_Community", "Social & Community"),
    ("community",         "Social_Relationships_Community", "Social & Community"),
    ("trauma",            "Trauma_Violence_Adversity",      "Trauma & Violence"),
    ("violence",          "Trauma_Violence_Adversity",      "Trauma & Violence"),
    # Spanish
    ("acceso médico",     "Healthcare_Access",              "Healthcare"),
    ("acceso medico",     "Healthcare_Access",              "Healthcare"),
    ("atención médica",   "Healthcare_Access",              "Healthcare"),
    ("atencion medica",   "Healthcare_Access",              "Healthcare"),
    ("salud",             "Healthcare_Access",              "Healthcare"),
    ("conducta de riesgo","Health_Risk_Behaviors",          "Health Risk"),
    ("riesgo de salud",   "Health_Risk_Behaviors",          "Health Risk"),
    ("entorno construido","Neighborhood_Built_Environment", "Neighborhood"),
    ("vecindario",        "Neighborhood_Built_Environment", "Neighborhood"),
    ("barrio",            "Neighborhood_Built_Environment", "Neighborhood"),
    ("transporte",        "Transportation_Accessibility",   "Transportation"),
    ("empleo",            "Economic_Employment",            "Employment"),
    ("económico",         "Economic_Employment",            "Employment"),
    ("economico",         "Economic_Employment",            "Employment"),
    ("trabajo",           "Economic_Employment",            "Employment"),
    ("educación",         "Education",                      "Education"),
    ("educacion",         "Education",                      "Education"),
    ("vivienda",          "Housing",                        "Housing"),
    ("comida",            "Food_Water_Basic_Needs",         "Food & Basic Needs"),
    ("alimentos",         "Food_Water_Basic_Needs",         "Food & Basic Needs"),
    ("agua",              "Food_Water_Basic_Needs",         "Food & Basic Needs"),
    ("necesidades básicas","Food_Water_Basic_Needs",        "Food & Basic Needs"),
    ("necesidades basicas","Food_Water_Basic_Needs",        "Food & Basic Needs"),
    ("comunidad",         "Social_Relationships_Community", "Social & Community"),
    ("relaciones sociales","Social_Relationships_Community", "Social & Community"),
    ("violencia",         "Trauma_Violence_Adversity",      "Trauma & Violence"),
    ("adversidad",        "Trauma_Violence_Adversity",      "Trauma & Violence"),
]

OVERALL_KEYWORDS = [
    "overall", "overall score", "vulnerability index", "vulnerability score",
    "vulnerable",
    "puntaje general", "puntuación general", "puntuacion general",
    "índice general", "indice general", "índice de vulnerabilidad",
    "indice de vulnerabilidad", "score general", "vulnerabilidad",
]

COMPARISON_KEYWORDS = [
    "compare", "comparison", "comparing", "compared",
    "versus", " vs ", " vs.", "side by side", "side-by-side",
    "difference between", "differences between",
    "comparar", "comparación", "comparacion", "compara", "comparado",
    "contra", "frente a", "diferencia entre", "diferencias entre",
]

AVERAGE_KEYWORDS = [
    # English
    "average", "avg", "on average", "mean score", "mean value",
    "overall average", "combined average",
    # Spanish
    "promedio", "en promedio", "media de", "promedio de",
]

RANKING_KEYWORDS = [
    "which municipalities", "what municipalities",
    "highest vulnerability", "most vulnerable",
    "top municipalities", "rank municipalities", "ranking",
    "qué municipios", "que municipios",
    "cuáles municipios", "cuales municipios",
    "cuáles son los municipios", "cuales son los municipios",
    "mayor vulnerabilidad", "más vulnerables", "mas vulnerables",
    "municipios más vulnerables", "municipios mas vulnerables",
]


def _is_comparison_query(text_lower: str) -> bool:
    padded = f" {text_lower} "
    return any(kw in padded for kw in COMPARISON_KEYWORDS)


def _is_overall_query(text_lower: str) -> bool:
    return any(kw in text_lower for kw in OVERALL_KEYWORDS)


def _is_average_query(text_lower: str) -> bool:
    return any(kw in text_lower for kw in AVERAGE_KEYWORDS)


def _is_ranking_query(text_lower: str) -> bool:
    return any(kw in text_lower for kw in RANKING_KEYWORDS)


def _detect_category(text_lower: str):
    for keyword, table, display in CATEGORY_KEYWORDS:
        if keyword in text_lower and table in ALLOWED_TABLES:
            return table, display
    return None, None


def detect_category(text_lower: str):
    """Public wrapper around _detect_category."""
    return _detect_category(text_lower)


def find_all_municipalities(text_lower: str, muni_df: pd.DataFrame) -> list:
    """Return municipalities mentioned in the message, in order of appearance.

    Longest names matched first to avoid partial overlaps (e.g. "San Juan"
    before "Juan Díaz"). Each FIPS is returned at most once. Matching is
    accent-insensitive (see _strip_accents) so a missing/wrong accent (e.g.
    typing "Mayaguez" for "Mayagüez") still resolves correctly.
    """
    sorted_munis = sorted(
        muni_df.to_dict("records"),
        key=lambda r: len(r["name"]),
        reverse=True,
    )

    text_stripped = _strip_accents(text_lower)
    occupied = [False] * len(text_stripped)
    candidates = []

    for row in sorted_munis:
        name_stripped = _strip_accents(row["name"].lower())
        pattern = r"\b" + re.escape(name_stripped) + r"\b"
        for m in re.finditer(pattern, text_stripped):
            start, end = m.start(), m.end()
            if any(occupied[i] for i in range(start, end)):
                continue
            for i in range(start, end):
                occupied[i] = True
            candidates.append((start, row["name"], row["fips_code"]))

    candidates.sort(key=lambda c: c[0])

    found = []
    seen = set()
    for _, name, fips in candidates:
        if fips in seen:
            continue
        seen.add(fips)
        found.append({"name": name, "fips_code": fips})
    return found


# Common words that must never be offered as a "did you mean" municipality
# guess, even if their edit-distance ratio happens to cross the fuzzy cutoff
# (e.g. "rico" vs "Rincón" scores 0.8 — exactly the kind of accidental match
# this list exists to block).
_FUZZY_STOPWORDS = {
    # English
    "the", "is", "of", "for", "and", "in", "on", "at", "what", "whats",
    "please", "score", "scores", "average", "overall", "compare", "report",
    "data", "puerto", "rico", "with", "about", "give", "show", "does",
    # Spanish
    "el", "la", "los", "las", "de", "del", "que", "cual", "por", "favor",
    "informe", "puntaje", "promedio", "comparar", "con", "para", "una",
    "uno", "esta", "este", "cuanto", "cuánto",
}

_FUZZY_CUTOFF = 0.78
_FUZZY_MIN_TOKEN_LEN = 4


def find_fuzzy_municipality_suggestion(text_lower: str, muni_df: pd.DataFrame):
    """Best-guess municipality for a likely misspelling, or None.

    Only meaningful to call once find_all_municipalities has already found
    nothing exact (accents included — that's handled separately). Looks at
    each word in the message and proposes the closest municipality name if a
    word is a close-enough edit-distance match — e.g. "arcibo" -> "Arecibo".
    Never applied automatically; the caller must have the user confirm it.
    """
    tokens = re.findall(r"[a-zA-Z]+", _strip_accents(text_lower))
    name_lookup = {
        _strip_accents(row["name"].lower()): row["name"]
        for row in muni_df.to_dict("records")
    }

    best_name = None
    best_ratio = 0.0
    for token in tokens:
        if len(token) < _FUZZY_MIN_TOKEN_LEN or token in _FUZZY_STOPWORDS:
            continue
        matches = difflib.get_close_matches(
            token, name_lookup.keys(), n=1, cutoff=_FUZZY_CUTOFF
        )
        if not matches:
            continue
        ratio = difflib.SequenceMatcher(None, token, matches[0]).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_name = name_lookup[matches[0]]

    return best_name


# "Latest" means the year the map shows (data.map_year) — the newest year
# that is complete for every municipality — so the assistant and the map never
# disagree. Plain ORDER BY year DESC picked incomplete newest years.

def _fetch_overall_score(conn, fips):
    """Return (value, year) for the overall score in the map's year, or None."""
    year = map_year(OVERALL_TABLE, OVERALL_INDICATOR)
    df = pd.read_sql(
        f"""
        SELECT value, year
        FROM {OVERALL_TABLE}
        WHERE fips_code = ? AND indicator_name = ? AND year = ?
        """,
        conn,
        params=(fips, OVERALL_INDICATOR, year),
    )
    if df.empty:
        return None
    return round(float(df["value"][0]), 2), int(df["year"][0])


def _fetch_category_score(conn, fips, table):
    """Return (value, year) for the category index score in the map's year, or None."""
    df = pd.read_sql(
        f"""
        SELECT value, year
        FROM {table}
        WHERE fips_code = ? AND indicator_name = ? AND year = ?
        """,
        conn,
        params=(fips, INDEX_INDICATOR, map_year(table, INDEX_INDICATOR)),
    )
    if df.empty:
        return None
    return round(float(df["value"][0]), 2), int(df["year"][0])


def _top_municipalities(conn, limit: int = 5) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT m.name, o.value, o.year
        FROM {OVERALL_TABLE} o
        JOIN municipalities m ON o.fips_code = m.fips_code
        WHERE o.indicator_name = ? AND o.year = ?
        ORDER BY o.value DESC
        LIMIT ?
        """,
        conn,
        params=(OVERALL_INDICATOR, map_year(OVERALL_TABLE, OVERALL_INDICATOR), limit),
    )


_HIGHER_NOTE = "Higher score means higher vulnerability."


def _format_multi_block(
    display: str,
    rows: list[tuple[str, float]],
    years: set | None = None,
    missing: list | None = None,
    average: float | None = None,
) -> str:
    """Render a header + one bullet per municipality, showing the raw values
    behind the answer (e.g. "Healthcare, 2022 / • Arecibo: 45.2 / ..."), so
    the LLM only has to relay real numbers rather than restate them from
    memory. A single shared year is folded into the header; mixed years are
    left off the header (not worth guessing which one to show).
    """
    year_label = None
    if years and len(years) == 1:
        year_label = str(next(iter(years)))
    header = f"{display}, {year_label}" if year_label else display

    lines = [header]
    lines += [f"• {name}: {val}" for name, val in rows]
    if average is not None:
        lines.append(f"• Average: {average}")
    if missing:
        lines.append(f"(No {display} data for {', '.join(missing)}.)")
    lines.append(_HIGHER_NOTE)
    return "\n".join(lines)


def _compute_average_context(municipalities: list, display: str, score_fn) -> str:
    """Build a data-context string with the per-municipality scores and the
    computed arithmetic average (sum of scores / count), shown explicitly so
    the LLM only has to relay it rather than do the math itself.
    """
    rows = []
    missing = []
    years = set()
    for m in municipalities:
        result = score_fn(m["fips_code"])
        if result is None:
            missing.append(m["name"])
            continue
        val, year = result
        rows.append((m["name"], val))
        years.add(year)

    if not rows:
        return f"No {display} data found for {', '.join(m['name'] for m in municipalities)}."

    avg = round(sum(v for _, v in rows) / len(rows), 2)
    return _format_multi_block(display, rows, years, missing, average=avg)


def get_breakdown_context(municipalities: list) -> str:
    """All-domain breakdown for the given municipalities (and ONLY those).

    Reuses report_data_builder.get_report_data, which returns the overall score
    plus every category sub-score for one municipality. Never fetches any
    municipality not in the provided list.
    """
    lines = []
    for m in municipalities:
        data = get_report_data(m["name"])
        if not data or not data.get("categories"):
            continue
        parts = []
        if data.get("overall_score") is not None:
            parts.append(f"Overall {data['overall_score']}")
        for display, value in data["categories"].items():
            parts.append(f"{display} {value}")
        lines.append(f"{data['municipality']} — " + " | ".join(parts))

    if not lines:
        return ""
    return "\n".join(lines) + f"\n{_HIGHER_NOTE}"


def get_data_context(
    user_input: str,
    language: str = "en",
    active_munis: list | None = None,
    active_category: tuple | None = None,
    wants_overall: bool = False,
    wants_breakdown: bool = False,
) -> str:
    """Return a plain-string snapshot of relevant data, or "" if nothing matched.

    The LLM uses this together with recent chat history to answer.

    When called from the prompt-context assembler, `active_munis` /
    `active_category` carry entities forward from earlier turns so follow-ups
    ("a full breakdown of both") still resolve to the right data. When called
    directly (legacy), these are None and behavior is unchanged.
    """
    user_input_lower = user_input.lower()
    conn = None

    try:
        conn = get_db_connection()

        muni_df = pd.read_sql(
            "SELECT name, fips_code FROM municipalities", conn,
        )
        found_munis = find_all_municipalities(user_input_lower, muni_df)

        # Entity carry-over: if the current message named no municipality, use
        # the active ones resolved from prior turns.
        if not found_munis and active_munis:
            found_munis = active_munis

        # Full-breakdown path — overall + all domains for ONLY these munis.
        if wants_breakdown and found_munis:
            breakdown = get_breakdown_context(found_munis)
            if breakdown:
                return breakdown

        # Carried-forward intent/category fallbacks (from earlier turns).
        carried_table, carried_display = active_category or (None, None)

        # AVERAGE FLOW — user wants the arithmetic average across 2+
        # municipalities (e.g. "average" / "promedio"), as opposed to a
        # side-by-side comparison. Takes priority over the comparison flow
        # below so an average request never gets answered as a comparison.
        if len(found_munis) >= 2 and _is_average_query(user_input_lower):
            cat_search = user_input_lower
            for m in found_munis:
                cat_search = cat_search.replace(m["name"].lower(), " ")

            table, display = _detect_category(cat_search)
            if not table and carried_table:
                table, display = carried_table, carried_display
            wants_overall_avg = _is_overall_query(user_input_lower) or wants_overall

            if table:
                return _compute_average_context(
                    found_munis, display,
                    lambda fips, _table=table: _fetch_category_score(conn, fips, _table),
                )
            if wants_overall_avg:
                return _compute_average_context(
                    found_munis, "Overall vulnerability",
                    lambda fips: _fetch_overall_score(conn, fips),
                )

            # No category and no "overall" specified — leave the data
            # context empty so the assistant asks which category to average
            # instead of guessing or falling back to a plain comparison.
            return ""

        # COMPARISON FLOW — two or more municipalities mentioned.
        if len(found_munis) >= 2:
            cat_search = user_input_lower
            for m in found_munis:
                cat_search = cat_search.replace(m["name"].lower(), " ")

            table, display = _detect_category(cat_search)
            if not table and carried_table:
                table, display = carried_table, carried_display
            wants_overall = (
                _is_overall_query(user_input_lower) or wants_overall
            )

            if table:
                rows, missing, years = [], [], set()
                for m in found_munis:
                    result = _fetch_category_score(conn, m["fips_code"], table)
                    if result is not None:
                        val, year = result
                        rows.append((m["name"], val))
                        years.add(year)
                    else:
                        missing.append(m["name"])
                if rows:
                    return _format_multi_block(display, rows, years, missing)
                return f"No {display} data found for {', '.join(missing)}."

            if wants_overall or _is_comparison_query(user_input_lower):
                rows, missing, years = [], [], set()
                for m in found_munis:
                    result = _fetch_overall_score(conn, m["fips_code"])
                    if result is not None:
                        val, year = result
                        rows.append((m["name"], val))
                        years.add(year)
                    else:
                        missing.append(m["name"])
                if rows:
                    return _format_multi_block("Overall vulnerability", rows, years, missing)
                return f"No overall score data found for {', '.join(missing)}."

        # RANKING — no specific municipality, ranking-style question.
        if not found_munis and _is_ranking_query(user_input_lower):
            df = _top_municipalities(conn, limit=RANKING_TOP_N)
            if not df.empty:
                rows = [
                    (row["name"], round(float(row["value"]), 2))
                    for _, row in df.iterrows()
                ]
                years = set(int(y) for y in df["year"].tolist())
                header = f"Top {RANKING_TOP_N} most vulnerable municipalities"
                if len(years) == 1:
                    header += f", {next(iter(years))}"
                header += " (ordered from most to least vulnerable)"
                lines = [header] + [f"• {name}: {val}" for name, val in rows]
                lines.append(_HIGHER_NOTE)
                return "\n".join(lines)

        # SINGLE MUNICIPALITY — overall.
        if len(found_munis) == 1 and (
            _is_overall_query(user_input_lower) or wants_overall
        ):
            m = found_munis[0]
            result = _fetch_overall_score(conn, m["fips_code"])
            if result is not None:
                val, year = result
                return (
                    f"{m['name']} overall vulnerability score ({year}): {val}. "
                    f"{_HIGHER_NOTE}"
                )
            return f"No overall score data found for {m['name']}."

        # SINGLE MUNICIPALITY — category.
        if len(found_munis) == 1:
            m = found_munis[0]
            cat_search = user_input_lower.replace(m["name"].lower(), " ")
            table, display = _detect_category(cat_search)
            if not table and carried_table:
                table, display = carried_table, carried_display
            if table:
                result = _fetch_category_score(conn, m["fips_code"], table)
                if result is not None:
                    val, year = result
                    return (
                        f"{m['name']} {display} score ({year}): {val}. {_HIGHER_NOTE}"
                    )
                return f"No {display} data found for {m['name']}."

        # LIKELY MISSPELLED MUNICIPALITY — nothing matched (even accent-
        # insensitively) anywhere above, and no active municipality carried
        # over from earlier turns either. Offer a "did you mean" guess rather
        # than silently giving up; the assistant must get user confirmation
        # before treating it as resolved (see prompt.py).
        if not found_munis:
            suggestion = find_fuzzy_municipality_suggestion(user_input_lower, muni_df)
            if suggestion:
                return (
                    "No municipality matching that name was found in this "
                    f'dashboard. The closest municipality name on record is "{suggestion}". '
                    "Ask the user in one short question whether they meant this "
                    f'municipality (e.g. "Did you mean {suggestion}?") and wait for '
                    "them to confirm before giving any score. Do not assume it silently."
                )

        return ""

    except Exception as e:
        print(e)
        return ""

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
