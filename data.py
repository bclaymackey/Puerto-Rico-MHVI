import ssl
import json
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np
import certifi
from urllib.request import urlopen

_ssl_context = ssl.create_default_context(cafile=certifi.where())
with urlopen(
    'https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json',
    context=_ssl_context
) as _resp:
    counties = json.load(_resp)

EXCLUDED_TABLES = frozenset({'municipalities', 'sqlite_sequence', 'Overall_MHVI_Score'})
ALLOWED_TABLES = frozenset({
    'Economic_Employment', 'Education', 'Food_Water_Basic_Needs',
    'Health_Risk_Behaviors', 'Healthcare_Access', 'Housing',
    'Neighborhood_Built_Environment', 'Social_Relationships_Community',
    'Transportation_Accessibility', 'Trauma_Violence_Adversity',
    'Overall_MHVI_Score'
})


def get_db_connection() -> sqlite3.Connection:
    return sqlite3.connect(str(Path(__file__).parent / 'pr_dashboard.db'))


def load_db_metadata() -> dict:
    """Return {table_name: [indicator_name, ...]} for every subcategory table."""
    conn = get_db_connection()
    try:
        excluded = ', '.join(f"'{t}'" for t in EXCLUDED_TABLES)
        tables = pd.read_sql_query(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ({excluded})",
            conn
        )['name'].tolist()
        metadata = {}
        for tbl in tables:
            if tbl not in ALLOWED_TABLES:
                continue
            try:
                inds = pd.read_sql_query(
                    f"SELECT DISTINCT indicator_name FROM {tbl}", conn
                )['indicator_name'].tolist()
                if inds:
                    metadata[tbl] = inds
            except Exception:
                pass
        return metadata
    finally:
        conn.close()


def fetch_map_data(category: str) -> pd.DataFrame:
    """Return fips_code / name / value for the choropleth map."""
    if category == 'Overall MHVI Score':
        target_table = 'Overall_MHVI_Score'
        ind = 'Overall MHVI Score'
    else:
        target_table = category
        ind = 'Subcategory Index Score'

    if target_table not in ALLOWED_TABLES:
        return pd.DataFrame(columns=['fips_code', 'value', 'name'])

    sql = f"""
        SELECT m.fips_code, m.name, t.value
        FROM {target_table} t
        JOIN municipalities m ON t.fips_code = m.fips_code
        WHERE t.indicator_name = ?
          AND t.year = (SELECT MAX(year) FROM {target_table})
    """
    conn = get_db_connection()
    try:
        return pd.read_sql(sql, conn, params=(ind,))
    except Exception:
        return pd.DataFrame(columns=['fips_code', 'value', 'name'])
    finally:
        conn.close()


def fetch_municipality_name(fips: str) -> str:
    conn = get_db_connection()
    try:
        result = pd.read_sql_query(
            "SELECT name FROM municipalities WHERE fips_code = ?",
            conn, params=(fips,)
        )
        return result.iloc[0]['name'] if not result.empty else 'Unknown Municipality'
    except Exception:
        return 'Unknown Municipality'
    finally:
        conn.close()


def load_data_dictionary() -> pd.DataFrame:
    """Read Data_Dictionary if present; otherwise return an in-memory fallback.

    Never writes back to SQLite. Fallback rows are built from db_metadata so
    the UI has something searchable even when the DB lacks a curated table.
    """
    columns = ['raw_name', 'category', 'friendly_name', 'description', 'source']
    conn = get_db_connection()
    try:
        exists = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Data_Dictionary'",
            conn,
        )
        if not exists.empty:
            try:
                df = pd.read_sql_query("SELECT * FROM Data_Dictionary", conn)
                for col in columns:
                    if col not in df.columns:
                        df[col] = ''
                return df[columns].copy()
            except Exception:
                pass

        rows = []
        metadata = load_db_metadata()
        for category, indicators in metadata.items():
            for ind in indicators:
                if ind == 'Subcategory Index Score':
                    continue
                rows.append({
                    'raw_name': ind,
                    'category': category,
                    'friendly_name': ind.replace('_', ' ').title(),
                    'description': '',
                    'source': '',
                })
        if not rows:
            return pd.DataFrame(columns=columns)
        df = pd.DataFrame(rows)
        df.drop_duplicates(subset=['raw_name'], inplace=True)
        return df[columns]
    finally:
        conn.close()


def query_indicator_table(fips: str, category: str) -> pd.DataFrame:
    """All indicators for one municipality in one category. [indicator_name, year, value]."""
    columns = ['indicator_name', 'year', 'value']
    if category == 'Overall MHVI Score':
        target = 'Overall_MHVI_Score'
    else:
        target = category
    if target not in ALLOWED_TABLES:
        return pd.DataFrame(columns=columns)
    conn = get_db_connection()
    try:
        return pd.read_sql_query(
            f"SELECT indicator_name, year, value FROM {target} WHERE fips_code = ? ORDER BY indicator_name, year",
            conn, params=(fips,),
        )
    except Exception:
        return pd.DataFrame(columns=columns)
    finally:
        conn.close()


def normalize_series(values) -> np.ndarray:
    """Min–max scale to 0–100. Constant series returns 50.0."""
    arr = np.array(values, dtype=float)
    if arr.size == 0:
        return arr
    lo, hi = np.nanmin(arr), np.nanmax(arr)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
        return np.full_like(arr, 50.0)
    return (arr - lo) / (hi - lo) * 100.0


def forecast_series(years, values, horizon=(2025, 2026, 2027, 2028)):
    """Linear polyfit projection. Returns (years_out, values_out) or None if <2 points."""
    yrs = np.array(years, dtype=float)
    vals = np.array(values, dtype=float)
    mask = np.isfinite(yrs) & np.isfinite(vals)
    yrs, vals = yrs[mask], vals[mask]
    if yrs.size < 2:
        return None
    slope, intercept = np.polyfit(yrs, vals, 1)
    horizon_arr = np.array(horizon, dtype=float)
    return horizon_arr, slope * horizon_arr + intercept


def query_axis_data(fips: str, cat: str, ind: str) -> pd.DataFrame:
    """Return DataFrame with columns [year, val] for a given municipality/indicator."""
    conn = get_db_connection()
    if cat == 'Year':
        try:
            df = pd.read_sql(
                "SELECT DISTINCT year FROM Economic_Employment ORDER BY year", conn
            )
            df['val'] = df['year']
            return df
        except Exception:
            return pd.DataFrame({'year': [2018, 2019, 2020, 2021, 2022, 2023, 2024],
                                  'val': [2018, 2019, 2020, 2021, 2022, 2023, 2024]})
        finally:
            conn.close()
    elif cat == 'Overall MHVI Score':
        try:
            return pd.read_sql(
                "SELECT year, value as val FROM Overall_MHVI_Score WHERE fips_code = ?",
                conn, params=(fips,)
            )
        except Exception:
            return pd.DataFrame(columns=['year', 'val'])
        finally:
            conn.close()
    else:
        if cat not in ALLOWED_TABLES:
            conn.close()
            return pd.DataFrame(columns=['year', 'val'])
        try:
            return pd.read_sql(
                f"SELECT year, value as val FROM {cat} WHERE fips_code = ? AND indicator_name = ?",
                conn, params=(fips, ind)
            )
        except Exception:
            return pd.DataFrame(columns=['year', 'val'])
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Which year the map shows — shared by the dashboard and the AI assistant
# ---------------------------------------------------------------------------
# Several tables have an incomplete newest year (Overall 2024 is missing
# Florida, Education 2024 has 11 of 78 municipalities, Healthcare Access 2025
# has 52 of 78). The map therefore shows one year that is complete for every
# category, and the assistant's "latest" answers use the same year, so the two
# never disagree.

OVERALL_TABLE = 'Overall_MHVI_Score'
OVERALL_INDICATOR = 'Overall MHVI Score'
INDEX_INDICATOR = 'Subcategory Index Score'

_YEAR_CACHE = {}


def _municipality_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM municipalities").fetchone()[0]


def _complete_years(conn, table: str, indicator: str, n_munis: int) -> set:
    rows = conn.execute(
        f"""SELECT year FROM {table}
            WHERE indicator_name = ? AND value IS NOT NULL
            GROUP BY year
            HAVING COUNT(DISTINCT fips_code) >= ?""",
        (indicator, n_munis)).fetchall()
    return {int(r[0]) for r in rows}


def common_map_year():
    """Latest year in which the Overall score and every category's index score
    cover all municipalities, or None if there is no such year. Cached: the
    database is read-only while the app runs."""
    if 'common' in _YEAR_CACHE:
        return _YEAR_CACHE['common']
    shared = None
    conn = get_db_connection()
    try:
        n = _municipality_count(conn)
        targets = [(OVERALL_TABLE, OVERALL_INDICATOR)] + [
            (tbl, INDEX_INDICATOR) for tbl in sorted(load_db_metadata())]
        for tbl, ind in targets:
            if tbl not in ALLOWED_TABLES:
                continue
            years = _complete_years(conn, tbl, ind, n)
            shared = years if shared is None else (shared & years)
    except Exception:
        shared = None
    finally:
        conn.close()
    _YEAR_CACHE['common'] = max(shared) if shared else None
    return _YEAR_CACHE['common']


def map_year(table: str, indicator: str = INDEX_INDICATOR):
    """The year the map shows for one table, by the same rule as the map:
    the common year if this table is complete in it, otherwise this table's
    latest complete year, otherwise the year with the most municipalities."""
    key = (table, indicator)
    if key in _YEAR_CACHE:
        return _YEAR_CACHE[key]
    year = None
    if table in ALLOWED_TABLES:
        conn = get_db_connection()
        try:
            n = _municipality_count(conn)
            counts = conn.execute(
                f"""SELECT year, COUNT(DISTINCT fips_code) FROM {table}
                    WHERE indicator_name = ? AND value IS NOT NULL
                    GROUP BY year""", (indicator,)).fetchall()
            counts = [(int(y), int(c)) for y, c in counts]
            complete = {y for y, c in counts if c >= n}
            common = common_map_year()
            if common is not None and common in complete:
                year = common
            elif complete:
                year = max(complete)
            elif counts:
                year = max(counts, key=lambda yc: (yc[1], yc[0]))[0]
        except Exception:
            year = None
        finally:
            conn.close()
    _YEAR_CACHE[key] = year
    return year
