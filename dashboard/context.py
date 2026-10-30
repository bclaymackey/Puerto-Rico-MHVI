"""Grounded question answering over the dashboard's own data and state.

WHY THIS EXISTS
---------------
Usability study Exercise 3 found the assistant answering with numbers that
disagreed with the graph on screen (61.69 for Aibonito where the chart showed
14.74), inventing an average (47.64 instead of 56.013), and asking users to
hover over the chart and read values back to it. Success rates were 0/6, 0/6,
1/6 and 2/6.

The Aibonito case is not a hallucination. `data_context_builder`'s lookups end
in `ORDER BY year DESC LIMIT 1`, with no year filter at all — so a question
about 2022 was answered with the 2024 row. 61.688 IS Aibonito's 2024 Overall
score; 14.744 is its 2022 score. The assistant was handed the wrong year and
had no way to know.

So this module answers value questions by RETRIEVAL, never generation:

* it reads the dashboard's live selection (municipalities, indicators, year,
  display mode, projection) so the user never has to restate it;
* it honours a year named in the question, which is the bug above;
* it computes averages/medians/min/max itself instead of leaving arithmetic to
  the language model;
* it returns the rows it used, so every answer can show its own evidence;
* it returns None when it cannot answer exactly, and the existing LLM path in
  ai_service.py handles the message unchanged.

It deliberately does not import app.py. The caller injects `series_fn`, so
there is exactly one implementation of the value/normalization pipeline and
this module cannot drift away from what the chart shows.
"""

import re
import unicodedata

import numpy as np

# Questions that belong to the existing report flow in ai_service.py.
_REPORT_WORDS = (
    'report', 'pdf', 'informe', 'reporte',
)

# "Export this conversation" — Exercise 3 found participants asking the
# assistant to do this and the assistant misreading it as a report request.
_EXPORT_CHAT_PATTERNS = (
    r'export (this |the |our )?(chat|conversation|transcript)',
    r'(save|download) (this |the |our )?(chat|conversation|transcript)',
    r'(chat|conversation|transcript) (to|as) (a )?pdf',
    r'export(ar)? (esta |la )?(conversaci[oó]n|charla|chat)',
    r'(descargar|guardar) (esta |la )?(conversaci[oó]n|charla|chat)',
)

_STAT_WORDS = {
    'average': ('average', 'mean', 'avg', 'promedio', 'media'),
    'median': ('median', 'mediana'),
    'max': ('maximum', 'max ', 'highest', 'largest', 'most vulnerable',
            'máximo', 'maximo', 'mayor', 'más alto', 'mas alto'),
    'min': ('minimum', 'min ', 'lowest', 'smallest', 'least',
            'mínimo', 'minimo', 'menor', 'más bajo', 'mas bajo'),
}

_VALUE_WORDS = (
    'value', 'score', 'what is', "what's", 'what was', 'how much', 'how many',
    'tell me', 'show me', 'give me', 'number', 'figure', 'rate',
    'valor', 'puntaje', 'puntuaci', 'cu[aá]l es', 'cu[aá]nto',
    'd[ií]game', 'mu[eé]strame', 'dame',
)

_RAW_WORDS = ('raw', 'actual', 'original', 'real', 'crudo', 'bruto', 'sin normalizar')
_NORM_WORDS = ('normalized', 'normalised', 'normalizado', 'normalizada',
               'escala 0-100', '0-100 scale')


def _strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(c))


def _norm(text: str) -> str:
    """Lowercase, accent-free, single-spaced — for matching only."""
    out = _strip_accents((text or '').lower())
    return ' '.join(re.sub(r'[^a-z0-9%<>\s-]', ' ', out).split())


def is_report_request(question: str) -> bool:
    q = _norm(question)
    if is_export_chat_request(question):
        return False
    return any(re.search(rf'\b{w}\b', q) for w in _REPORT_WORDS)


def is_export_chat_request(question: str) -> bool:
    """[E3-O5] 'Export this conversation' should trigger the export, not a report."""
    q = _norm(question)
    return any(re.search(p, q) for p in _EXPORT_CHAT_PATTERNS)


def extract_year(question: str, allowed=None):
    """First plausible year named in the question, or None.

    This is the fix for the Aibonito 61.69-vs-14.74 finding: a year in the
    question now wins over 'whatever row is newest'.
    """
    for match in re.finditer(r'\b(19|20)\d{2}\b', question or ''):
        year = int(match.group(0))
        if allowed is None or year in allowed:
            return year
    return None


def requested_stats(question: str):
    q = _norm(question)
    found = []
    for name, words in _STAT_WORDS.items():
        for w in words:
            if _strip_accents(w).strip() in q:
                found.append(name)
                break
    return found


def requested_mode(question: str):
    """Did the user explicitly ask for raw or normalized? [E3-R6]"""
    q = _norm(question)
    if any(w in q for w in (_strip_accents(x) for x in _NORM_WORDS)):
        return 'norm'
    if any(re.search(rf'\b{_strip_accents(w).strip()}\b', q) for w in _RAW_WORDS):
        return 'raw'
    return None


def looks_like_value_question(question: str) -> bool:
    q = _norm(question)
    if any(re.search(_strip_accents(w), q) for w in _VALUE_WORDS):
        return True
    return bool(requested_stats(question)) or bool(extract_year(question))


def find_municipalities(question: str, municipalities):
    """Municipalities named in the question, longest name first, no overlaps."""
    q = _norm(question)
    ordered = sorted(municipalities, key=lambda m: len(m['name']), reverse=True)
    occupied = [False] * len(q)
    hits = []
    for row in ordered:
        name = _norm(row['name'])
        if not name:
            continue
        for m in re.finditer(rf'\b{re.escape(name)}\b', q):
            if any(occupied[i] for i in range(m.start(), m.end())):
                continue
            for i in range(m.start(), m.end()):
                occupied[i] = True
            hits.append((m.start(), row))
    hits.sort(key=lambda h: h[0])
    out, seen = [], set()
    for _, row in hits:
        if row['fips_code'] in seen:
            continue
        seen.add(row['fips_code'])
        out.append(row)
    return out


def find_metrics(question: str, catalog_metrics, limit=3):
    """Indicators named in the question, best match first.

    Scored on how much of the question an entry's words cover, so
    "poverty status" beats "poverty rate" when the user says "poverty status",
    and a bare "poverty" still matches something sensible.
    """
    q_words = set(_norm(question).split())
    if not q_words:
        return []
    scored = []
    for entry in catalog_metrics:
        hay = _norm(f"{entry.get('label', '')} {entry.get('raw_name', '')}")
        words = {w for w in hay.split() if len(w) > 2}
        if not words:
            continue
        overlap = words & q_words
        if not overlap:
            continue
        # Favour entries whose own words are mostly accounted for, so a long
        # ICD-range label does not win on one shared word.
        score = len(overlap) / len(words) + 0.3 * len(overlap)
        scored.append((score, len(words), entry))
    if not scored:
        return []
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [e for _, _, e in scored[:limit]]


def _fmt(value) -> str:
    if value is None:
        return '—'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return '—'
    a = abs(v)
    if a >= 10000:
        return f'{v:,.0f}'
    if a >= 100:
        return f'{v:,.1f}'
    if a >= 1:
        return f'{v:,.2f}'
    return f'{v:,.4f}'


def _label_with_mode(indicator, year, mode):
    """[E3-R6] 'Raw Poverty Status Past 12 Months, 2022' — name the value type."""
    kind = 'Normalized' if mode == 'norm' else 'Raw'
    return f'{kind} {indicator}, {year}'


def answer(question, state, catalog, series_fn, language='en'):
    """Answer a value question from the dashboard's data, or return None.

    question   the user's message
    state      {'fips': [...], 'metrics': [...], 'year': int|None,
                'mode': 'raw'|'norm', 'forecast': bool}
    catalog    {'municipalities': [{'name','fips_code'}],
                'metrics': [{'value','label','raw_name','category','category_label'}]}
    series_fn  (fips_list, metric_values, include_forecast) -> DataFrame with
               columns municipality, metric, indicator, year, raw, normalized,
               is_forecast. Injected so this module uses the SAME pipeline the
               chart does and cannot drift from it.

    Returns None when it cannot answer exactly — the caller then falls through
    to the existing LLM path untouched.
    """
    state = state or {}
    if is_report_request(question):
        return None
    if not looks_like_value_question(question):
        return None

    metrics_by_value = {m['value']: m for m in catalog.get('metrics', [])}

    # --- who ---
    named = find_municipalities(question, catalog.get('municipalities', []))
    if named:
        fips = [m['fips_code'] for m in named]
        who_source = 'question'
    else:
        fips = [f for f in (state.get('fips') or []) if f]
        who_source = 'dashboard'
    if not fips:
        return None

    # --- what ---
    named_metrics = find_metrics(question, catalog.get('metrics', []))
    if named_metrics:
        metric_values = [m['value'] for m in named_metrics[:1]]
        what_source = 'question'
    else:
        metric_values = [m for m in (state.get('metrics') or []) if m]
        what_source = 'dashboard'
    if not metric_values:
        return None

    include_forecast = bool(state.get('forecast'))
    df = series_fn(fips, metric_values, include_forecast)
    if df is None or len(df) == 0:
        return None

    # --- when ---
    years = sorted(int(y) for y in df['year'].unique())
    asked_year = extract_year(question, allowed=set(years))
    if asked_year is not None:
        year, when_source = asked_year, 'question'
    elif state.get('year') in years:
        year, when_source = int(state['year']), 'dashboard'
    else:
        year, when_source = max(years), 'latest available'

    # A year named in the question that the data does not cover must be said
    # out loud rather than silently answered with a different year.
    unmatched_year = extract_year(question)
    if unmatched_year is not None and unmatched_year not in years:
        return {
            'kind': 'grounded',
            'text': (f"I don't have {unmatched_year} for that indicator. "
                     f"Stored years are {years[0]}–{years[-1]}."),
            'rows': [],
            'year': None,
            'mode': state.get('mode', 'raw'),
            'metrics': metric_values,
            'fips': fips,
            'sources': {'who': who_source, 'what': what_source,
                        'when': 'unavailable'},
            'stats': {},
            'method_note': '',
        }

    # --- raw or normalized ---
    explicit = requested_mode(question)
    mode = explicit or state.get('mode') or 'raw'
    value_col = 'normalized' if mode == 'norm' else 'raw'

    sub = df[df['year'] == year]
    if len(sub) == 0:
        return None

    rows = []
    for _, r in sub.sort_values(['indicator', 'municipality']).iterrows():
        rows.append({
            'municipality': r['municipality'],
            'indicator': r['indicator'],
            'year': int(r['year']),
            'raw': None if r['raw'] is None or not np.isfinite(r['raw'])
            else float(r['raw']),
            'normalized': None if r['normalized'] is None
            or not np.isfinite(r['normalized']) else float(r['normalized']),
            'predicted': bool(r.get('is_forecast', False)),
        })
    if not rows:
        return None

    # --- statistics, computed here rather than by the language model ---
    wanted = requested_stats(question)
    stats = {}
    series = [r[value_col] for r in rows if r[value_col] is not None]
    if wanted and len(series) > 1:
        arr = np.array(series, dtype=float)
        if 'average' in wanted:
            stats['Average'] = float(arr.mean())
        if 'median' in wanted:
            stats['Median'] = float(np.median(arr))
        if 'max' in wanted:
            stats['Max'] = float(arr.max())
        if 'min' in wanted:
            stats['Min'] = float(arr.min())
        # An average is rarely wanted alone; give the spread with it.
        if 'average' in wanted and len(wanted) == 1:
            stats['Min'] = float(arr.min())
            stats['Max'] = float(arr.max())

    # --- sentence ---
    indicators = sorted({r['indicator'] for r in rows})
    headline = _label_with_mode(
        indicators[0] if len(indicators) == 1 else f'{len(indicators)} indicators',
        year, mode)

    parts = []
    if len(rows) == 1:
        r = rows[0]
        shown = r[value_col]
        parts.append(f"{headline} — {r['municipality']}: {_fmt(shown)}.")
        other = 'normalized' if mode == 'raw' else 'raw'
        if r[other] is not None:
            other_label = 'Normalized' if other == 'normalized' else 'Raw'
            parts.append(f"({other_label} value: {_fmt(r[other])}.)")
    else:
        listed = "; ".join(f"{r['municipality']} {_fmt(r[value_col])}"
                           for r in rows)
        parts.append(f"{headline} — {listed}.")

    if stats:
        stat_txt = " · ".join(f"{k} {_fmt(v)}" for k, v in stats.items())
        parts.append(f"{stat_txt} (computed on "
                     f"{'normalized' if mode == 'norm' else 'raw'} values).")

    if any(r['predicted'] for r in rows):
        parts.append("⚠ Includes projected years — those are estimates, "
                     "not observed data.")

    if explicit and explicit != (state.get('mode') or 'raw'):
        parts.append(f"You asked for {'normalized' if explicit == 'norm' else 'raw'} "
                     f"values, so that is what I used — the dashboard is "
                     f"currently showing "
                     f"{'normalized' if state.get('mode') == 'norm' else 'raw'}.")

    method_note = ''
    if mode == 'norm':
        method_note = ("Normalized = min-max to 0–100 per indicator, on a "
                       "scale shared across the municipalities and years in "
                       "your current selection.")

    if language == 'es':
        parts.append("(Valores leídos directamente de la base de datos del "
                     "panel.)")

    return {
        'kind': 'grounded',
        'text': " ".join(parts),
        'rows': rows,
        'year': year,
        'mode': mode,
        'metrics': metric_values,
        'fips': fips,
        'sources': {'who': who_source, 'what': what_source, 'when': when_source},
        'stats': stats,
        'method_note': method_note,
    }


def state_summary(state, catalog):
    """One line describing the dashboard's current state.

    [E3-R2] Handed to the LLM path so a non-value question is at least answered
    in the context of what the user is looking at.
    """
    state = state or {}
    names = state.get('municipalities') or []
    metrics_by_value = {m['value']: m for m in catalog.get('metrics', [])}
    inds = [metrics_by_value.get(m, {}).get('label', m)
            for m in (state.get('metrics') or [])]
    bits = [
        f"municipalities: {', '.join(names) if names else 'none selected'}",
        f"indicators: {', '.join(inds) if inds else 'none selected'}",
        f"year in focus: {state.get('year') or 'none'}",
        f"display mode: {'normalized 0-100' if state.get('mode') == 'norm' else 'raw values'}",
        f"future projection: {'on' if state.get('forecast') else 'off'}",
    ]
    return "Dashboard is currently showing — " + "; ".join(bits) + "."
