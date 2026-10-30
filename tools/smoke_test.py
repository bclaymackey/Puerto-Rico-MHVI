"""Pre-flight check for the MHVI dashboard. Run before pushing to main.

    python tools/smoke_test.py        (from the project folder)

It imports MHVIM_Dashboard_App.py with the real Dash installed and checks the
things that otherwise only fail when you launch the server:

  1. every component accepts the props it was given
     (this is what `dcc.Dropdown(title=...)` tripped over)
  2. every callback's component id actually exists in the layout
  3. every callback output property is a real property of that component
  4. no component id is defined twice
  5. no output is claimed by two callbacks without allow_duplicate
  6. every map category colours all 78 municipalities (no gray ones)
  7. the three logos are in assets/logos/
  8. no file other than .env contains an API key or a MongoDB password
     (the repository is public)

It also REPORTS (without failing) whether MongoDB answered, whether sign-in
is required, and which AI provider is configured.

It does NOT start a server, open a browser, or need an OpenAI key or a
database. Exit code is 0 when everything passes, 1 otherwise, so it also works
in CI.
"""
import os
import sys
import traceback
from pathlib import Path

# Run from anywhere: put the dashboard folder (this file's parent's parent)
# on the import path.
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

# The OpenAI client is built at import when LLM_PROVIDER=openai, and it refuses
# to construct without a key. Nothing here calls the API, so a placeholder is
# enough. A real key in .env is used instead if present (the .env file is read
# first), and it never leaves this process.
from dotenv import load_dotenv
load_dotenv(APP_DIR / '.env')
os.environ.setdefault("OPENAI_API_KEY", "smoke-test-placeholder")
# Do not wait long for a database that is not there.
os.environ.setdefault("MONGODB_TIMEOUT_MS", "2000")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg):
    print(f"  ok    {msg}")


# ---------------------------------------------------------------------------
print("1. Importing MHVIM_Dashboard_App.py (bad component props surface here)")
try:
    import MHVIM_Dashboard_App as M
    import dashboard.callbacks as A          # the dashboard's names
    layout = M.app.layout() if callable(M.app.layout) else M.app.layout
except Exception:
    print("\n  IMPORT FAILED — the app would not start. Traceback:\n")
    traceback.print_exc()
    sys.exit(1)
ok("the app imported and built its page, so every component accepted its props")

dash_app = M.app


# ---------------------------------------------------------------------------
def walk(node):
    """Yield every component in the layout tree."""
    if node is None or isinstance(node, (str, int, float, bool)):
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from walk(item)
        return
    yield node
    children = getattr(node, 'children', None)
    if children is not None:
        yield from walk(children)


components = list(walk(layout))
print(f"\n2. Layout contains {len(components)} components")

ids = {}
duplicates = []
for comp in components:
    cid = getattr(comp, 'id', None)
    if isinstance(cid, str):
        if cid in ids:
            duplicates.append(cid)
        ids[cid] = comp
print(f"   {len(ids)} components carry a string id")
if duplicates:
    for d in sorted(set(duplicates)):
        fail(f"component id defined more than once: {d!r}")
else:
    ok("no duplicate component ids")


# ---------------------------------------------------------------------------
print("\n3. Checking every callback against the layout")


def available_props(component):
    """Property names the component class accepts."""
    props = set(getattr(component, 'available_properties', []) or [])
    if not props:
        props = set(getattr(component, '_prop_names', []) or [])
    return props


def is_pattern_id(cid):
    """Pattern-matching ids arrive as dicts on Inputs/States but as a
    JSON-encoded string inside the callback_map output key."""
    if isinstance(cid, dict):
        return True
    return isinstance(cid, str) and cid.strip().startswith('{')


# Created inside a chat reply on purpose (the "Download report" button).
DYNAMIC_IDS = {'download-report-btn'}


def check_dep(cb_name, cid, prop, kind):
    if is_pattern_id(cid) or cid in DYNAMIC_IDS:
        return  # created inside callbacks; suppress_callback_exceptions covers them
    comp = ids.get(cid)
    if comp is None:
        fail(f"{cb_name}: {kind} {cid}.{prop} — no such id in the layout")
        return
    props = available_props(comp)
    if props and prop not in props:
        fail(f"{cb_name}: {kind} {cid}.{prop} — {type(comp).__name__} has no "
             f"property {prop!r}")


n_callbacks = 0
non_duplicate_outputs = {}

for key, cb in dash_app.callback_map.items():
    n_callbacks += 1
    name = getattr(cb.get('callback'), '__name__', None) or key[:48]

    for dep in cb.get('inputs', []):
        check_dep(name, dep.get('id'), dep.get('property'), 'Input')
    for dep in cb.get('state', []):
        check_dep(name, dep.get('id'), dep.get('property'), 'State')

    for out in cb.get('output', '').split('...'):
        out = out.strip('.')
        if not out or '.' not in out:
            continue
        cid, _, prop = out.rpartition('.')
        allow_dup = '@' in prop
        prop = prop.split('@')[0]
        check_dep(name, cid, prop, 'Output')
        if not allow_dup and not is_pattern_id(cid):
            non_duplicate_outputs.setdefault((cid, prop), []).append(name)

print(f"   {n_callbacks} callbacks registered")
if not FAILURES:
    ok("every callback id and property resolves")

clashes = {k: v for k, v in non_duplicate_outputs.items() if len(v) > 1}
if clashes:
    for (cid, prop), names in clashes.items():
        fail(f"{cid}.{prop} claimed without allow_duplicate by {names}")
else:
    ok("no output claimed twice without allow_duplicate")


# ---------------------------------------------------------------------------
print("\n4. Spot-checking the data layer against the database")
try:
    print(f"   municipalities loaded : {len(A.all_counties)}")
    print(f"   map categories        : {len(A.global_categories)}")
    print(f"   searchable indicators : {len(A.METRIC_OPTIONS)}")
    print(f"   glossary entries      : {len(A.data_dictionary_records)}")
    if len(A.all_counties) != 78:
        fail(f"expected 78 municipalities, found {len(A.all_counties)}")
    else:
        ok("all 78 municipalities loaded from pr_dashboard.db")
    fig, map_year = A.update_map(A.OVERALL, [])
    if map_year is None:
        fail("the map callback did not return the year it is showing")
    else:
        ok(f"map callback runs — showing {map_year}")

    # A municipality with no value for the map's year is painted gray.
    n_total = len(A.all_counties)
    for cat in A.global_categories:
        df, year, _info = A.fetch_map_data(cat)
        coloured = int(df['value'].notna().sum()) if len(df) else 0
        if coloured < n_total:
            fail(f"map '{cat}' would show {n_total - coloured} gray "
                 f"municipalities for {year}")
    ok(f"every map category colours all {n_total} municipalities")

    # The header and footer logos (including the funder's) must be present.
    missing_logos = [name for name, data in (
        ('MB_Horz_3Clr.png', A.encoded_logo1),
        ('Grupo_nexos.png', A.encoded_logo2),
        ('aim_ahead_600x474.png', A.encoded_logo3)) if not data]
    if missing_logos:
        fail(f"logo(s) not found in assets/logos/: {', '.join(missing_logos)}")
    else:
        ok("all three logos found")
except Exception:
    print()
    traceback.print_exc()
    fail("the data layer raised while being exercised")


# ---------------------------------------------------------------------------
print("\n5. Looking for API keys and database passwords outside .env")
import re as _re
# an OpenAI key, or a MongoDB address with a real password in it
KEY_PATTERN = _re.compile(
    rb'sk-[A-Za-z0-9_-]{20,}|mongodb(?:\+srv)?://[^:/\s"\']+:(?!PASSWORD@)[^@\s"\']{3,}@')
SKIP_DIRS = {'__pycache__', '.git', '.ipynb_checkpoints', 'venv', '.venv',
             'tests'}
SKIP_EXT = {'.db', '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.pyc'}
leaks = []
for path in APP_DIR.rglob('*'):
    if not path.is_file() or path.name == '.env':
        continue
    if SKIP_DIRS & set(path.parts) or path.suffix.lower() in SKIP_EXT:
        continue
    try:
        if KEY_PATTERN.search(path.read_bytes()):
            leaks.append(path.relative_to(APP_DIR))
    except OSError:
        pass
if leaks:
    for leak in leaks:
        fail(f"'{leak}' contains what looks like an API key or database "
             f"password — remove it before publishing; only .env (and the "
             f"Space's secrets) should hold them")
else:
    ok("no API keys or database passwords outside .env")


# ---------------------------------------------------------------------------
print("\n6. Settings (for information — these do not fail the check)")
from auth.policy import login_required
from mongodb.client import is_available
from chat.hyperparameters import LLM_PROVIDER, LLM_MODEL
print(f"   sign-in required (REQUIRE_LOGIN) : {'yes' if login_required() else 'no'}")
print(f"   AI provider / model              : {LLM_PROVIDER} / {LLM_MODEL}")
if is_available():
    print("   MongoDB                          : connected")
else:
    print("   MongoDB                          : NOT reachable — the dashboard "
          "runs, but chat history, sign-in and tickets will show as "
          "temporarily unavailable (check MONGODB_URI and Atlas Network Access)")


# ---------------------------------------------------------------------------
print()
print("=" * 68)
if FAILURES:
    print(f"{len(FAILURES)} PROBLEM(S) — fix before running or publishing:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("ALL PRE-FLIGHT CHECKS PASSED — safe to run the app.")
sys.exit(0)
