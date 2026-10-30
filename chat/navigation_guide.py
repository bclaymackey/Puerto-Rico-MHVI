"""Lightweight guided-navigation intent.

Detects "how/where do I…" questions about the dashboard and returns short
numbered UI steps instead of running the data or report flow. Templates only
reference UI that actually exists: the V10.1 dashboard in dashboard/layout.py
("Map Category", "Go to municipality", the right-hand panel with its single
indicator search box and "Values for year", Reset, the Custom Report Builder)
and the account/ticket/chat pieces in layout.py.

is_custom_report_intent() is checked by ai_service.py BEFORE the generic
report-generation keyword match, since "custom report" would otherwise be
swallowed by the bare "report" keyword and misrouted into the single-
municipality PDF flow. It is deliberately standalone (not gated by
_NAV_PHRASES_EN/ES) so it also matches statements, not just questions.
"""

import pandas as pd

from data import get_db_connection

from .data_context_builder import detect_category, find_all_municipalities


_NAV_PHRASES_EN = [
    "how can i", "how do i", "how would i", "how to ",
    "where can i", "where do i", "where is the",
    "show me where", "show me how",
    "guide me", "walk me through", "navigate to",
]

_NAV_PHRASES_ES = [
    "cómo puedo", "como puedo",
    "cómo encuentro", "como encuentro",
    "cómo veo", "como veo",
    "cómo uso", "como uso",
    "dónde puedo", "donde puedo",
    "dónde encuentro", "donde encuentro",
    "dónde veo", "donde veo",
    "dónde está", "donde esta",
    "muéstrame", "muestrame",
    "guíame", "guiame",
]


# Known-unsupported features. If a navigation question mentions one of these,
# return the "not in this dashboard yet" message instead of generic steps.
# CSV export exists (the "⬇ CSV" button under the chart and the table's
# Export), and signing in exists, so neither is listed here any more.
_UNSUPPORTED_KEYWORDS = [
    "excel", "spreadsheet",
    "dark mode", "light mode", "modo oscuro", "modo claro",
    "edit data", "modify data", "delete data",
    "editar datos", "modificar datos", "borrar datos",
]

# Support-ticket questions. Matches the real "Report an issue" modal wired to
# tickets/core.py — keep in sync with layout.py's open-ticket-btn / ticket-modal.
_TICKET_KEYWORDS_EN = [
    "ticket", "submit a ticket", "file a ticket", "report an issue",
    "report a bug", "report a problem", "contact support", "get support",
    "help desk", "support request", "file a complaint", "raise an issue",
]
_TICKET_KEYWORDS_ES = [
    "boleto", "ticket", "enviar un ticket", "reportar un problema",
    "reportar un error", "reportar un fallo", "contactar soporte",
    "solicitar soporte", "presentar una queja", "informar un problema",
]

# Sign-in / account questions (the account button in the dashboard header).
_SIGN_IN_KEYWORDS = [
    "log in", "login", "sign in", "sign up", "create an account", "my account",
    "iniciar sesión", "iniciar sesion", "crear una cuenta", "registrarme",
]

# Custom Report Builder questions (☰ hamburger menu -> Custom Reports). This
# is a DIFFERENT feature from the chat-driven single-municipality PDF (which
# _is_report_intent in ai_service.py handles via the bare "report" keyword) -
# keep these keywords specific ("custom", "builder", "my own", "elements")
# so they never swallow genuine "generate a report for X" requests.
_CUSTOM_REPORT_KEYWORDS_EN = [
    "custom report", "report builder", "build my own report",
    "build a custom report", "create my own report",
    "custom report builder", "report elements",
]
_CUSTOM_REPORT_KEYWORDS_ES = [
    "informe personalizado", "generador de informes",
    "crear mi propio informe", "constructor de informes",
]

# Phrases that indicate a genuine "how do I use this dashboard" question, as
# opposed to an unrelated "how do I..." question that happens to be phrased
# the same way. Only these fall back to the generic overview steps; anything
# else with no other match is left for the LLM (which has its own scope
# guardrails) instead of guessing.
_GENERAL_DASHBOARD_PHRASES_EN = [
    "use this dashboard", "use the dashboard", "use this site",
    "use this app", "how this works", "how does this work",
    "get started", "getting started", "navigate this",
]
_GENERAL_DASHBOARD_PHRASES_ES = [
    "usar este panel", "usar el panel", "usar este sitio",
    "usar esta aplicación", "usar esta app", "cómo funciona esto",
    "como funciona esto", "empezar", "cómo navego", "como navego",
]


_TEMPLATES_EN = {
    "category_and_municipality": [
        "Step 1: At the top of the page, open the \"Map Category\" dropdown and select \"{category}\".",
        "Step 2: In the \"Go to municipality\" box next to it, type {municipality} and pick it from the list.",
        "Step 3: The right panel opens on {municipality}, already showing {category}.",
        "Step 4: Under \"Values for year\", choose the year you want — the exact numbers are listed as text, so you do not need to hover over the chart.",
        "Step 5: The table below the chart carries every value, with its raw number, its normalized 0-100 number, and whether it is observed or projected.",
    ],
    "category_only": [
        "Step 1: At the top of the page, open the \"Map Category\" dropdown and select \"{category}\".",
        "Step 2: The map recolors to show {category} across all 78 municipalities.",
        "Step 3: Type any name into \"Go to municipality\", or click the map, to open that municipality's panel.",
        "Step 4: Use \"Values for year\" in the panel to read exact numbers for a given year.",
    ],
    "municipality_only": [
        "Step 1: In the \"Go to municipality\" box at the top of the page, type {municipality} and pick it from the list. (Clicking it on the map does the same thing.)",
        "Step 2: The right panel opens on {municipality}.",
        "Step 3: To change what is shown, type any word — \"poverty\", \"rent\", \"insured\" — into the indicator box in the panel. One box searches every category.",
        "Step 4: Use \"Values for year\" to read exact numbers without hovering.",
    ],
    "general": [
        "Step 1: Pick what the map colors with \"Map Category\" at the top of the page.",
        "Step 2: Type a name into \"Go to municipality\", or click the map, to open the right panel.",
        "Step 3: In the panel, type any word into the indicator box to search every category at once; switch between \"Raw\" and \"Normalized 0-100\" to change how values are shown. Whichever is active is named in the bar across the top of the page.",
        "Step 4: Use \"Values for year\" for exact numbers, the table below the chart for everything at once, and the PNG/CSV buttons to export.",
        "Step 5: \"Reset dashboard\" at the top right clears every selection if you want to start over.",
    ],
    "sign_in": [
        "Step 1: Click the \"👤 Sign in\" button at the right-hand end of the header, next to the logos.",
        "Step 2: Enter your email and password and click \"Log in\" — or click \"Sign up\" to create an account.",
        "Step 3: Once signed in, the same button reads \"⚙ Settings\" and has Change password, Security question, Report an issue and Sign out.",
    ],
    "report_issue": [
        "Step 1: Sign in, then click the ⚙ Settings button at the right-hand end of the header.",
        "Step 2: In the panel that opens, click \"\U0001F6DF Report an issue\".",
        "Step 3: Choose a category, add a subject, and describe the issue.",
        "Step 4: Click Submit — our team will follow up by email.",
    ],
    "custom_report_builder": [
        "Step 1: The quickest way: set up the chart in the right-hand panel the way you want it, then click \"➕ Add to report\" under the chart. The exact graph, with its settings, goes into the report.",
        "Step 2: To open the report, click the ☰ menu button in the top-left of the header, then \"Custom Reports\".",
        "Step 3: In the Custom Report Builder, \"+ Add blank element\" adds another section; for each one choose Line Graph or Data Table, the municipalities, a category and indicator, and optionally \"Normalized 0–100\" or \"Include projection\".",
        "Step 4: Click \"🖨 Export report to PDF\" and choose \"Save as PDF\" in the print dialog.",
        "(This is different from asking me to generate a report for a specific municipality here in chat.)",
    ],
    "unknown": "I don't see that option in this dashboard yet.",
}

_TEMPLATES_ES = {
    "category_and_municipality": [
        "Paso 1: Arriba de la página, abre el menú \"Map Category\" y selecciona \"{category}\".",
        "Paso 2: En el campo \"Go to municipality\" al lado, escribe {municipality} y selecciónalo de la lista.",
        "Paso 3: El panel derecho se abrirá en {municipality}, ya mostrando {category}.",
        "Paso 4: En \"Values for year\", elige el año que quieras — los valores exactos aparecen como texto, así que no necesitas pasar el cursor sobre la gráfica.",
        "Paso 5: La tabla debajo de la gráfica incluye cada valor, con su número crudo, su número normalizado 0-100, y si es observado o proyectado.",
    ],
    "category_only": [
        "Paso 1: Arriba de la página, abre el menú \"Map Category\" y selecciona \"{category}\".",
        "Paso 2: El mapa cambiará de color según {category} en los 78 municipios.",
        "Paso 3: Escribe cualquier nombre en \"Go to municipality\", o haz clic en el mapa, para abrir el panel de ese municipio.",
        "Paso 4: Usa \"Values for year\" en el panel para leer los números exactos de un año.",
    ],
    "municipality_only": [
        "Paso 1: En el campo \"Go to municipality\" arriba de la página, escribe {municipality} y selecciónalo. (Hacer clic en el mapa logra lo mismo.)",
        "Paso 2: El panel derecho se abrirá en {municipality}.",
        "Paso 3: Para cambiar lo que se muestra, escribe cualquier palabra — \"pobreza\", \"renta\", \"asegurado\" — en el campo de indicadores del panel. Un solo campo busca en todas las categorías.",
        "Paso 4: Usa \"Values for year\" para leer números exactos sin pasar el cursor.",
    ],
    "general": [
        "Paso 1: Elige qué colorea el mapa con \"Map Category\" arriba de la página.",
        "Paso 2: Escribe un nombre en \"Go to municipality\", o haz clic en el mapa, para abrir el panel derecho.",
        "Paso 3: En el panel, escribe cualquier palabra en el campo de indicadores para buscar en todas las categorías; cambia entre \"Raw\" y \"Normalized 0-100\" para cambiar cómo se muestran los valores. El modo activo aparece en la barra superior de la página.",
        "Paso 4: Usa \"Values for year\" para números exactos, la tabla debajo de la gráfica para verlo todo, y los botones PNG/CSV para exportar.",
        "Paso 5: \"Reset dashboard\" arriba a la derecha limpia todas las selecciones si quieres empezar de nuevo.",
    ],
    "sign_in": [
        "Paso 1: Haz clic en el botón \"👤 Sign in\" al extremo derecho del encabezado, junto a los logos.",
        "Paso 2: Escribe tu correo y contraseña y haz clic en \"Log in\" — o en \"Sign up\" para crear una cuenta.",
        "Paso 3: Ya con la sesión iniciada, el mismo botón dice \"⚙ Settings\" y tiene cambiar contraseña, pregunta de seguridad, reportar un problema y cerrar sesión.",
    ],
    "report_issue": [
        "Paso 1: Inicia sesión y haz clic en el botón ⚙ Settings al extremo derecho del encabezado.",
        "Paso 2: En el panel que se abre, haz clic en \"\U0001F6DF Report an issue\".",
        "Paso 3: Elige una categoría, agrega un asunto y describe el problema.",
        "Paso 4: Haz clic en Submit — nuestro equipo responderá por correo electrónico.",
    ],
    "custom_report_builder": [
        "Paso 1: Lo más rápido: prepara la gráfica en el panel derecho como la quieras y haz clic en \"➕ Add to report\" debajo de la gráfica. La gráfica exacta, con su configuración, pasa al informe.",
        "Paso 2: Para abrir el informe, haz clic en el botón ☰ arriba a la izquierda del encabezado y luego en \"Custom Reports\".",
        "Paso 3: En el Custom Report Builder, \"+ Add blank element\" agrega otra sección; para cada una elige Line Graph o Data Table, los municipios, una categoría y un indicador, y si quieres \"Normalized 0–100\" o \"Include projection\".",
        "Paso 4: Haz clic en \"🖨 Export report to PDF\" y elige \"Guardar como PDF\" en el diálogo de impresión.",
        "(Esto es distinto de pedirme que genere un informe para un municipio específico aquí en el chat.)",
    ],
    "unknown": "No veo esa opción en este panel todavía.",
}


def is_navigation_intent(text_lower: str, language: str) -> bool:
    phrases = _NAV_PHRASES_ES if language == "es" else _NAV_PHRASES_EN
    return any(p in text_lower for p in phrases)


def is_custom_report_intent(text_lower: str, language: str) -> bool:
    """Standalone check for the Custom Report Builder feature.

    Not gated by _NAV_PHRASES_EN/ES so it also matches statements like
    "I need a custom report", not just "how do I..." questions. Checked by
    ai_service.py before the generic report-generation keyword match.
    """
    keywords = _CUSTOM_REPORT_KEYWORDS_ES if language == "es" else _CUSTOM_REPORT_KEYWORDS_EN
    return any(kw in text_lower for kw in keywords)


def build_custom_report_response(language: str) -> str:
    templates = _TEMPLATES_ES if language == "es" else _TEMPLATES_EN
    return "\n".join(templates["custom_report_builder"])


_muni_df_cache = None


def _muni_df():
    global _muni_df_cache
    if _muni_df_cache is None:
        conn = get_db_connection()
        try:
            _muni_df_cache = pd.read_sql(
                "SELECT name, fips_code FROM municipalities", conn,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
    return _muni_df_cache


def _dropdown_label(table_name: str) -> str:
    # Mirrors dashboard/core.py's pretty_category(): underscores become spaces.
    return table_name.replace("_", " ")


def build_navigation_response(user_input: str, language: str) -> str | None:
    """Return numbered UI steps for a confidently-matched navigation question,
    or None if the question doesn't clearly match anything this dashboard can
    do. Callers should fall back to the normal LLM turn (with its own scope
    guardrails) when this returns None, rather than showing a generic guess.
    """
    text_lower = (user_input or "").lower()
    templates = _TEMPLATES_ES if language == "es" else _TEMPLATES_EN

    if any(kw in text_lower for kw in _UNSUPPORTED_KEYWORDS):
        return templates["unknown"]

    ticket_keywords = _TICKET_KEYWORDS_ES if language == "es" else _TICKET_KEYWORDS_EN
    if any(kw in text_lower for kw in ticket_keywords):
        return "\n".join(templates["report_issue"])

    if any(kw in text_lower for kw in _SIGN_IN_KEYWORDS):
        return "\n".join(templates["sign_in"])

    table, _short = detect_category(text_lower)
    category_label = _dropdown_label(table) if table else None

    munis = find_all_municipalities(text_lower, _muni_df())
    muni_name = munis[0]["name"] if munis else None

    if category_label and muni_name:
        steps = templates["category_and_municipality"]
        return "\n".join(
            s.format(category=category_label, municipality=muni_name)
            for s in steps
        )
    if category_label:
        steps = templates["category_only"]
        return "\n".join(s.format(category=category_label) for s in steps)
    if muni_name:
        steps = templates["municipality_only"]
        return "\n".join(s.format(municipality=muni_name) for s in steps)

    general_phrases = (
        _GENERAL_DASHBOARD_PHRASES_ES if language == "es" else _GENERAL_DASHBOARD_PHRASES_EN
    )
    if any(p in text_lower for p in general_phrases):
        return "\n".join(templates["general"])

    # No confident match — let the LLM handle it (and redirect if off-topic)
    # instead of returning generic dashboard steps for an unrelated question.
    return None
