"""MHVI dashboard — shared data, constants and helpers.

This is the V10.1 dashboard (the version that went through the three usability
exercises), moved out of the single app.py into this package so it can run
alongside the AI-assistant, account and ticket code. The code is unchanged
apart from the import lines and the startup-year rule, which now comes from
data.py so the map and the assistant always agree on the year they show.

    core.py       data, constants, helpers   (this file)
    layout.py     the page
    callbacks.py  everything the page does
    context.py    the assistant's "answer from the dashboard's data" layer
    chat_bridge.py  how those grounded answers appear in the assistant window

Change tags such as [E1-R2] refer to the usability-study recommendation each
piece implements; see docs/change_history.
"""

import base64
import csv
import io
import json
import uuid
from pathlib import Path
from datetime import datetime

import dash
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, MATCH, Input, Output, State, dash_table, dcc, html
from dotenv import load_dotenv

load_dotenv()

from data import ALLOWED_TABLES, counties, get_db_connection, query_axis_data
import data as _data
from . import context as dctx

# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------
OVERALL = 'Overall MHVI Score'
INDEX_IND = 'Subcategory Index Score'
METRIC_SEP = '||'
OVERALL_METRIC = 'OVERALL'

# [E1-O1] "N/A" reads as missing data. Say what it actually means.
NO_INDICATOR_LABEL = 'Overall score — no indicator selection needed'
NO_INDICATOR_VALUE = 'N/A'

NON_SUBCATEGORY_TABLES = frozenset({
    'municipalities', 'sqlite_sequence', 'Data_Dictionary',
    'Overall_MHVI_Score', 'Overall_MHVI_M_Score',
})

# ---------------------------------------------------------
# Startup metadata load
# ---------------------------------------------------------
conn = get_db_connection()

_tables = pd.read_sql_query(
    "SELECT name FROM sqlite_master WHERE type='table'", conn
)['name'].tolist()

db_metadata = {}
for tbl in _tables:
    if tbl in NON_SUBCATEGORY_TABLES or tbl not in ALLOWED_TABLES:
        continue
    try:
        inds = pd.read_sql_query(
            f"SELECT DISTINCT indicator_name FROM {tbl}", conn
        )['indicator_name'].tolist()
    except Exception:
        inds = []
    if inds:
        db_metadata[tbl] = inds

try:
    muni_df = pd.read_sql_query(
        "SELECT fips_code, name FROM municipalities ORDER BY name", conn
    )
    all_counties = muni_df.to_dict('records')
except Exception:
    all_counties = []

try:
    dict_df = pd.read_sql_query("SELECT * FROM Data_Dictionary", conn)
except Exception:
    dict_df = pd.DataFrame()

conn.close()

available_subcats = sorted(db_metadata.keys())
global_categories = [OVERALL] + available_subcats
MAP_TABLES = set(available_subcats) | {'Overall_MHVI_Score'}
FIPS_TO_NAME = {c['fips_code']: c['name'] for c in all_counties}

DICT_DESC, DICT_UNITS, DICT_SOURCE, DICT_FRIENDLY = {}, {}, {}, {}
data_dictionary_records = []
if not dict_df.empty:
    for col in ('raw_name', 'category', 'friendly_name', 'description',
                'source', 'units'):
        if col not in dict_df.columns:
            dict_df[col] = ''
    dict_df = dict_df.fillna('')
    data_dictionary_records = dict_df.to_dict('records')
    for rec in data_dictionary_records:
        raw = (rec.get('raw_name') or '').strip()
        if not raw:
            continue
        DICT_DESC[raw] = (rec.get('description') or '').strip()
        DICT_UNITS[raw] = (rec.get('units') or '').strip()
        DICT_SOURCE[raw] = (rec.get('source') or '').strip()
        DICT_FRIENDLY[raw] = (rec.get('friendly_name') or '').strip()

DICT_CATEGORIES = sorted(
    {(r.get('category') or '').strip() for r in data_dictionary_records
     if (r.get('category') or '').strip()}
)


# ---------------------------------------------------------
# [E1-O5] Municipality centroids, for the permanent map label
# ---------------------------------------------------------
def _build_centroids(geo):
    """Rough polygon centroids keyed by FIPS, for labelling the map."""
    out = {}
    try:
        for feat in (geo or {}).get('features', []):
            fid = str(feat.get('id') or '')
            if not fid.startswith('72'):
                continue
            xs, ys = [], []

            def walk(node):
                if not node:
                    return
                if isinstance(node[0], (int, float)):
                    xs.append(float(node[0]))
                    ys.append(float(node[1]))
                else:
                    for sub in node:
                        walk(sub)

            walk(feat.get('geometry', {}).get('coordinates'))
            if xs:
                out[fid] = (sum(ys) / len(ys), sum(xs) / len(xs))
    except Exception:
        pass
    return out


FIPS_CENTROID = _build_centroids(counties)


# ---------------------------------------------------------
# Label and formatting helpers
# ---------------------------------------------------------
def pretty_category(table_name: str) -> str:
    if table_name == OVERALL:
        return OVERALL
    return table_name.replace('_', ' ')


def pretty_indicator(name: str) -> str:
    """Scannable indicator name, with the count/rate distinction surfaced."""
    if name in (INDEX_IND, OVERALL):
        return name
    if name == NO_INDICATOR_VALUE:
        return NO_INDICATOR_LABEL
    suffix = ''
    if name.endswith('_Rate'):
        name, suffix = name[:-5], '  [rate]'
    elif name.endswith('_Cases'):
        name, suffix = name[:-6], '  [count]'
    text = name.replace('_', ' ').replace('-', ' ')
    return ' '.join(text.split()) + suffix


# [E2-R7] One number-formatting rule used by tooltips, cards, CSV and table,
# so the same value never appears as 71.42857 in one place and 71.4 in another.
def fmt_num(value) -> str:
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


def round_raw(value):
    """Numeric rounding that matches fmt_num, so sorting and display agree."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    a = abs(v)
    if a >= 10000:
        return round(v, 0)
    if a >= 100:
        return round(v, 1)
    if a >= 1:
        return round(v, 2)
    return round(v, 4)


def as_list(value):
    """[E2-O1] The municipality dropdown flips between single and multi, so its
    value is sometimes a scalar and sometimes a list. Normalise it."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v]
    return [value]


def make_metric(cat: str, ind: str) -> str:
    if cat == OVERALL:
        return OVERALL_METRIC
    return f'{cat}{METRIC_SEP}{ind}'


def parse_metric(metric: str):
    if not metric or metric == OVERALL_METRIC:
        return OVERALL, OVERALL
    if METRIC_SEP in metric:
        cat, ind = metric.split(METRIC_SEP, 1)
        return cat, ind
    return OVERALL, OVERALL


# ---------------------------------------------------------
# The flat, searchable metric list (V8 change 5)
# ---------------------------------------------------------
METRIC_OPTIONS = [{
    'label': 'Overall MHVI Score  (composite index, 0–100)',
    'value': OVERALL_METRIC,
    'title': 'Composite Mental Health Vulnerability Index across all subcategories.',
}]
METRIC_CATEGORY = {OVERALL_METRIC: OVERALL}
METRIC_LABEL = {OVERALL_METRIC: 'Overall MHVI Score'}
METRIC_UNITS = {OVERALL_METRIC: 'Index score (0–100)'}
METRIC_RAWNAME = {OVERALL_METRIC: OVERALL}

for _tbl in available_subcats:
    _cat_label = pretty_category(_tbl)
    _inds = db_metadata[_tbl]
    _ordered = ([INDEX_IND] if INDEX_IND in _inds else []) + \
               sorted(i for i in _inds if i != INDEX_IND)
    for _ind in _ordered:
        _value = make_metric(_tbl, _ind)
        if _ind == INDEX_IND:
            _label = f'{_cat_label}  ›  Subcategory Index Score  (0–100)'
            _units = 'Index score (0–100)'
        else:
            _units = DICT_UNITS.get(_ind, '')
            if _units == 'Count / Rate (Not Specified)':
                _units = ''
            _label = f'{_cat_label}  ›  {pretty_indicator(_ind)}'
        METRIC_OPTIONS.append({
            'label': _label,
            'value': _value,
            'title': DICT_DESC.get(_ind) or _ind,
        })
        METRIC_CATEGORY[_value] = _tbl
        METRIC_LABEL[_value] = pretty_indicator(_ind)
        METRIC_UNITS[_value] = _units
        METRIC_RAWNAME[_value] = _ind

METRIC_OPTION_BY_VALUE = {o['value']: o for o in METRIC_OPTIONS}
# Each category's index score, for the map/graph category link [E1-R7]
CATEGORY_INDEX_METRIC = {
    tbl: make_metric(tbl, INDEX_IND)
    for tbl in available_subcats if INDEX_IND in db_metadata[tbl]
}


def metric_label(metric: str) -> str:
    return METRIC_LABEL.get(metric, metric)


def metric_category_label(metric: str) -> str:
    return pretty_category(METRIC_CATEGORY.get(metric, OVERALL))


# [E3-R1] what the assistant is allowed to look up, built once at startup
DCTX_CATALOG = {
    'municipalities': all_counties,
    'metrics': [{
        'value': v,
        'label': METRIC_LABEL.get(v, v),
        'raw_name': METRIC_RAWNAME.get(v, v),
        'category': METRIC_CATEGORY.get(v, OVERALL),
        'category_label': pretty_category(METRIC_CATEGORY.get(v, OVERALL)),
        'units': METRIC_UNITS.get(v, ''),
    } for v in METRIC_OPTION_BY_VALUE],
}


# ---------------------------------------------------------
# Data access
# ---------------------------------------------------------
_COMMON_MAP_YEAR = {'computed': False, 'year': None}


def _map_target(category):
    if category == OVERALL:
        return 'Overall_MHVI_Score', OVERALL
    return category, INDEX_IND


def common_map_year():
    """Latest year in which every map category covers all 78 municipalities.

    The rule itself lives in data.py (``data.common_map_year``) so the map and
    the AI assistant use exactly the same year. Returns None if no single year
    is complete for every category, in which case each category falls back to
    its own latest complete year.
    """
    if not _COMMON_MAP_YEAR['computed']:
        _COMMON_MAP_YEAR['year'] = _data.common_map_year()
        _COMMON_MAP_YEAR['computed'] = True
    return _COMMON_MAP_YEAR['year']


def fetch_map_data(category: str):
    """Choropleth values for ONE consistent year across all municipalities.

    Year choice, in order of preference:
      1. COMMON_MAP_YEAR — the latest year in which EVERY map category has a
         value for all 78 municipalities (2023 with the current data). Using
         one shared year keeps the categories comparable with each other.
      2. otherwise, this table's own latest year with all 78 municipalities;
      3. otherwise, the year with the most municipalities.

    Several tables have a partial newest year — Overall 2024 is missing
    Florida, Education 2024 has 11 of 78, Healthcare Access 2025 has 52 of
    78 — and simply showing the newest year painted those municipalities gray.

    Returns (df, year, info) where info = {'latest': int, 'missing_latest':
    [names], 'missing_shown': [names]}.
    """
    empty = pd.DataFrame(columns=['fips_code', 'name', 'value'])
    no_info = {'latest': None, 'missing_latest': [], 'missing_shown': []}
    if category == OVERALL:
        tbl, ind = 'Overall_MHVI_Score', OVERALL
    else:
        tbl, ind = category, INDEX_IND
    if tbl not in MAP_TABLES:
        return empty, None, no_info

    n_munis = len(FIPS_TO_NAME)
    conn = get_db_connection()
    try:
        counts = pd.read_sql_query(
            f"""SELECT year, COUNT(DISTINCT fips_code) AS n
                FROM {tbl}
                WHERE indicator_name = ? AND value IS NOT NULL
                GROUP BY year""",
            conn, params=(ind,),
        )
        if counts.empty:
            return empty, None, no_info
        counts['year'] = counts['year'].astype(int)
        latest = int(counts['year'].max())
        complete = counts[counts['n'] >= n_munis]
        common = common_map_year()
        if common is not None and common in set(complete['year']):
            year = common
        elif not complete.empty:
            year = int(complete['year'].max())
        else:
            best = counts.sort_values(['n', 'year'], ascending=False).iloc[0]
            year = int(best['year'])

        df = pd.read_sql_query(
            f"""SELECT m.fips_code, m.name, t.value
                FROM {tbl} t
                JOIN municipalities m ON t.fips_code = m.fips_code
                WHERE t.indicator_name = ? AND t.year = ?
                  AND t.value IS NOT NULL""",
            conn, params=(ind, year),
        )

        def missing_in(y):
            have = set(pd.read_sql_query(
                f"""SELECT DISTINCT fips_code FROM {tbl}
                    WHERE indicator_name = ? AND year = ?
                      AND value IS NOT NULL""",
                conn, params=(ind, y))['fips_code'])
            return sorted(FIPS_TO_NAME[f] for f in FIPS_TO_NAME
                          if f not in have)

        info = {
            'latest': latest,
            'missing_latest': missing_in(latest) if latest != year else [],
            'missing_shown': missing_in(year),
        }
        return df, year, info
    except Exception:
        return empty, None, no_info
    finally:
        conn.close()


def build_series(counties_list, metrics):
    """Long frame behind the chart, table, cards and CSV."""
    cols = ['municipality', 'metric', 'indicator', 'year', 'raw']
    frames = []
    for metric in metrics or []:
        cat, ind = parse_metric(metric)
        for fips in counties_list or []:
            df = query_axis_data(fips, cat, ind)
            if df is None or df.empty:
                continue
            df = df.copy()
            df['year'] = pd.to_numeric(df['year'], errors='coerce')
            df['raw'] = pd.to_numeric(df['val'], errors='coerce')
            df = df.dropna(subset=['year', 'raw'])
            if df.empty:
                continue
            frames.append(pd.DataFrame({
                'municipality': FIPS_TO_NAME.get(fips, fips),
                'metric': metric,
                'indicator': metric_label(metric),
                'year': df['year'].astype(int).values,
                'raw': df['raw'].values,
            }))
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(['indicator', 'municipality', 'year']).reset_index(drop=True)


def add_normalized(df: pd.DataFrame) -> pd.DataFrame:
    """Min-max to 0-100 per indicator on a scale SHARED by every selected
    municipality, so between-municipality comparison survives."""
    df = df.copy()
    df['normalized'] = np.nan
    if df.empty:
        return df
    for _, grp in df.groupby('metric'):
        lo, hi = grp['raw'].min(), grp['raw'].max()
        if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
            df.loc[grp.index, 'normalized'] = 50.0
        else:
            df.loc[grp.index, 'normalized'] = (grp['raw'] - lo) / (hi - lo) * 100.0
    return df


def holt_linear(values, horizon):
    """Holt linear-trend exponential smoothing.

    The methodology document specifies Holt linear trend for forecasting, but
    the dashboard was projecting with `np.polyfit` — an ordinary least-squares
    straight line, which weights a 2015 observation exactly as heavily as a
    2024 one. Holt instead keeps a smoothed level and a smoothed trend and
    weights recent observations more, so it tracks a recent shift. This brings
    the dashboard in line with the documented method.

    alpha/beta are chosen by a coarse grid search on one-step-ahead squared
    error, so no extra dependency is needed.
    """
    y = np.asarray([v for v in values if v is not None and np.isfinite(v)],
                   dtype=float)
    n = len(y)
    if n < 2 or horizon < 1:
        return None
    if n < 4:
        # Too short to fit smoothing parameters; fall back to the straight line.
        try:
            slope, intercept = np.polyfit(np.arange(n, dtype=float), y, 1)
        except Exception:
            return None
        return np.array([intercept + slope * (n - 1 + h)
                         for h in range(1, horizon + 1)])

    grid = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    best = None
    for alpha in grid:
        for beta in grid:
            level, trend = y[0], y[1] - y[0]
            sse = 0.0
            for t in range(1, n):
                forecast = level + trend
                err = y[t] - forecast
                sse += err * err
                new_level = alpha * y[t] + (1 - alpha) * (level + trend)
                trend = beta * (new_level - level) + (1 - beta) * trend
                level = new_level
            if best is None or sse < best[0]:
                best = (sse, alpha, beta, level, trend)

    _, _, _, level, trend = best
    return np.array([level + h * trend for h in range(1, horizon + 1)])


def add_forecast(df: pd.DataFrame, horizon_years=4) -> pd.DataFrame:
    """Projection per (municipality, metric), for BOTH raw and normalized, so
    switching display mode does not change what is projected."""
    if df.empty:
        df = df.copy()
        df['is_forecast'] = False
        return df
    df = df.copy()
    df['is_forecast'] = False
    extra = []
    for (muni, metric), grp in df.groupby(['municipality', 'metric']):
        g = grp.dropna(subset=['raw']).sort_values('year')
        if len(g) < 3:
            continue
        last = int(g['year'].max())
        future = np.arange(last + 1, last + 1 + horizon_years, dtype=int)
        row = {'municipality': muni, 'metric': metric,
               'indicator': g['indicator'].iloc[0],
               'year': future, 'is_forecast': True}
        ok = True
        for col in ('raw', 'normalized'):
            projected = holt_linear(g[col].tolist(), horizon_years)
            if projected is None:
                row[col] = np.full(len(future), np.nan)
            else:
                row[col] = projected
        if ok:
            extra.append(pd.DataFrame(row))
    if not extra:
        return df
    return pd.concat([df] + extra, ignore_index=True)


# ---------------------------------------------------------
# [E3-R1] / [E3-R2] one pipeline shared by the chart and the assistant
# ---------------------------------------------------------
def series_for_assistant(fips_list, metric_values, include_forecast=False):
    """Exactly the frame the chart is built from.

    Injected into dashboard_context so the assistant's numbers cannot drift
    from what is plotted — the study found the two disagreeing (61.69 vs
    14.74 for Aibonito).
    """
    df = add_normalized(build_series(fips_list, metric_values))
    if include_forecast:
        return add_forecast(df)
    return df.assign(is_forecast=False)


def series_name(municipality, indicator, n_munis, n_metrics):
    if n_munis > 1 and n_metrics > 1:
        return f'{municipality} — {indicator}'
    if n_munis > 1:
        return municipality
    if n_metrics > 1:
        return indicator
    return f'{municipality} — {indicator}'


def axis_fit(df: pd.DataFrame):
    """[E1-R8] Is one indicator being squashed against the axis?

    The study's example was Employment Level vs Unemployment Level, where the
    smaller line sat compressed near the bottom. A plain magnitude ratio misses
    that (they differ by only ~5x), so the real test is how much of the shared
    vertical axis each indicator actually occupies.

    Returns (smallest axis share, magnitude ratio).
    """
    if df.empty or df['metric'].nunique() < 2:
        return 1.0, 1.0
    lo, hi = df['raw'].min(), df['raw'].max()
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return 1.0, 1.0
    span = hi - lo
    shares, mags = [], []
    for _, grp in df.groupby('metric'):
        rng = grp['raw'].max() - grp['raw'].min()
        if np.isfinite(rng):
            shares.append(float(rng) / float(span))
        med = grp['raw'].abs().median()
        if np.isfinite(med) and med > 0:
            mags.append(float(med))
    if not shares:
        return 1.0, 1.0
    ratio = (max(mags) / min(mags)) if len(mags) > 1 else 1.0
    return min(shares), ratio


# An indicator using less than this share of the axis is visually compressed.
AXIS_SHARE_FLOOR = 0.35



# ---------------------------------------------------------
# Shared styles
# ---------------------------------------------------------
PURPLE = '#4b0082'
NAVY = '#03123e'
BLUE = '#14539a'
AMBER_BG = '#fff4d6'
AMBER_FG = '#7a5a10'

menu_btn_style = {
    'width': '100%', 'padding': '10px', 'marginBottom': '10px',
    'backgroundColor': '#ffffff', 'border': '1px solid #ccc',
    'borderRadius': '4px', 'cursor': 'pointer', 'textAlign': 'left',
    'fontWeight': 'bold', 'color': '#333'
}
dropdown_style = {'width': '100%', 'marginBottom': '12px'}
label_style = {'fontWeight': 'bold', 'fontSize': '14px', 'display': 'block',
               'marginBottom': '4px'}
hint_style = {'fontSize': '12px', 'color': '#666', 'margin': '0 0 6px 0'}
small_btn = {'fontSize': '12px', 'padding': '5px 10px', 'borderRadius': '6px',
             'cursor': 'pointer', 'whiteSpace': 'nowrap',
             'border': f'1px solid {PURPLE}', 'background': 'white',
             'color': PURPLE}

TABLE_STYLE_INLINE = {'marginTop': '6px'}
TABLE_STYLE_EXPANDED = {
    'position': 'fixed', 'top': '0', 'left': '0', 'width': '100vw',
    'height': '100vh', 'backgroundColor': 'white', 'zIndex': '2500',
    'padding': '24px', 'overflowY': 'auto', 'boxSizing': 'border-box',
    'marginTop': '0',
}
DT_STYLE_INLINE = {'height': '280px', 'overflowY': 'auto', 'overflowX': 'auto'}
DT_STYLE_EXPANDED = {'height': 'calc(100vh - 170px)', 'overflowY': 'auto',
                     'overflowX': 'auto'}

MODAL_WRAP = {'display': 'none', 'position': 'fixed', 'top': '0', 'left': '0',
              'width': '100%', 'height': '100%',
              'backgroundColor': 'rgba(0,0,0,0.5)', 'zIndex': '2000',
              'justifyContent': 'center', 'alignItems': 'center'}

# [E1-I9] The Plotly toolbar and drag handlers were being triggered by accident
# (zoom, pan, right-click menu). The trend chart is now non-draggable with no
# toolbar; export has its own labelled button instead.
TREND_CONFIG = {'displayModeBar': False, 'scrollZoom': False,
                'doubleClick': False, 'displaylogo': False, 'editable': False}
MAP_CONFIG = {'displaylogo': False, 'scrollZoom': True,
              'modeBarButtonsToRemove': ['lasso2d', 'select2d', 'toImage']}



# Paths are resolved from the project folder, not from wherever the app was
# launched. Logos live in assets/logos/ (the partner branch's location); the
# older locations are still checked so a stray copy is found too.
BASE_DIR = Path(__file__).resolve().parent.parent


def encode_image(filename):
    """Logo as a base64 data URI. Looks in assets/logos/, assets/, then the
    project folder."""
    for candidate in (BASE_DIR / 'assets' / 'logos' / filename,
                      BASE_DIR / 'assets' / filename,
                      BASE_DIR / filename):
        if candidate.is_file():
            data = base64.b64encode(candidate.read_bytes()).decode('ascii')
            return f'data:image/png;base64,{data}'
    print(f"[encode_image] logo not found: {filename}")
    return ""


encoded_logo1 = encode_image('MB_Horz_3Clr.png')
encoded_logo2 = encode_image('Grupo_nexos.png')
encoded_logo3 = encode_image('aim_ahead_600x474.png')
