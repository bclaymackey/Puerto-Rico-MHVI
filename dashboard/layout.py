"""MHVI dashboard — the page.

The V10.1 layout, unchanged except that:
  * it is a function, so the AI-CHATBOT branch's page (layout.py) can place it
    inside its login gate, and
  * the header has a slot for the account / sign-in button, and
  * the old built-in chat window is gone — the AI-CHATBOT branch's assistant
    window replaces it.
"""
from .core import *  # noqa: F401,F403  (constants, helpers, styles)
from .core import _map_target  # noqa: F401


HIERARCHY_BODY = [
    html.P("The dashboard organises the data in three levels. Every number you "
           "see sits at one of them.", style={'fontSize': '14px'}),
    html.Div([
        html.Div([
            html.Div("1 · Overall MHVI Score", style={'fontWeight': '700',
                                                      'color': PURPLE}),
            html.P("One composite score per municipality per year, reported on a "
                   "0–100 scale where higher means more vulnerable. It is built "
                   "from the category scores below, so it has no single "
                   "indicator of its own — that is why the Indicator field reads "
                   f"“{NO_INDICATOR_LABEL}”.",
                   style={'fontSize': '13px', 'margin': '4px 0 0 0'}),
        ], style={'borderLeft': f'4px solid {PURPLE}', 'paddingLeft': '12px',
                  'marginBottom': '14px'}),
        html.Div([
            html.Div("2 · Categories (also called subcategories)",
                     style={'fontWeight': '700', 'color': BLUE}),
            html.P("Domains such as Economic Employment, Education, Housing or "
                   "Healthcare Access. Each has its own Subcategory Index "
                   "Score, also 0–100, and that is what the map colours when "
                   "you choose a category.",
                   style={'fontSize': '13px', 'margin': '4px 0 0 0'}),
            html.P("Currently available: " + ", ".join(
                pretty_category(c) for c in available_subcats) or "—",
                   style={'fontSize': '12px', 'color': '#666',
                          'margin': '4px 0 0 0'}),
        ], style={'borderLeft': f'4px solid {BLUE}', 'paddingLeft': '12px',
                  'marginBottom': '14px'}),
        html.Div([
            html.Div("3 · Indicators", style={'fontWeight': '700',
                                              'color': '#1d7a4c'}),
            html.P("The individual measures inside a category — poverty rate, "
                   "labor force, total insured population, and so on. These are "
                   "in their own real-world units (dollars, people, rates, "
                   "percentages), not on a 0–100 scale. Most exist as both a "
                   "[count] and a [rate]; the dashboard tags which is which.",
                   style={'fontSize': '13px', 'margin': '4px 0 0 0'}),
        ], style={'borderLeft': '4px solid #1d7a4c', 'paddingLeft': '12px'}),
    ]),
    html.Div("Overall MHVI Score  →  Category  →  Indicator",
             style={'textAlign': 'center', 'fontWeight': '700',
                    'fontSize': '15px', 'margin': '18px 0',
                    'padding': '10px', 'background': '#f0f2f5',
                    'borderRadius': '6px'}),
    html.P("Two display modes cut across all three levels: Raw values keep each "
           "indicator in its own units, while Normalized 0–100 rescales them so "
           "indicators with different units can share one axis. The index "
           "scores at levels 1 and 2 are already 0–100.",
           style={'fontSize': '13px', 'color': '#444'}),

    html.H3("Using the right-hand panel",
            style={'fontSize': '16px', 'marginTop': '22px',
                   'borderTop': '1px solid #ddd', 'paddingTop': '16px'}),
    html.Ul([
        html.Li([html.B("One / Compare"), " — one municipality at a time by "
                 "default. Compare lets you add several and draws one line each."]),
        html.Li([html.B("Indicator box"), " — type any word to search every "
                 "category at once. The narrow dropdown beside it limits the "
                 "list to a single category if you prefer to browse."]),
        html.Li([html.B("ⓘ rows"), " — click one to read that indicator's "
                 "definition, units and source, or to open it in the Data "
                 "Dictionary."]),
        html.Li([html.B("🧮 row"), " — appears for index scores, and shows how "
                 "that score is built from its components."]),
        html.Li([html.B("Raw / Normalized 0–100"), " — Raw keeps original "
                 "units; Normalized rescales each indicator to 0–100 across "
                 "your selection so different units can share an axis. "
                 "Whichever is active is named on the chart, in the bar at the "
                 "top of the page, and in the table."]),
        html.Li([html.B("1 chart / Split axes"), " — split gives each "
                 "indicator its own vertical scale, for when one line is "
                 "squashed flat."]),
        html.Li([html.B("Values for year"), " — pick a year and read every "
                 "value as text, with averages across municipalities. No "
                 "hovering needed."]),
        html.Li([html.B("The table"), " — always carries the raw value, the "
                 "normalized value and whether the row is observed or "
                 "projected. ⤢ opens it full page."]),
    ], style={'fontSize': '13px', 'lineHeight': '1.6',
              'paddingLeft': '18px', 'margin': '0'}),
]


def dashboard_children(header_extras=()):
    """Everything on the dashboard page, as a list of components.

    header_extras: components placed at the right-hand end of the header
    (the account / sign-in button).
    """
    return [


        dcc.Store(id='export-name-store', data='MHVI_export'),
        # the year the map is showing, so the panel opens on the same year
        dcc.Store(id='map-year-store', data=None),
        # Sinks for the two clientside callbacks. Writing to a button's
        # `n_clicks_timestamp` is the old idiom for "this callback has no real
        # output", but that prop is deprecated and its availability varies by
        # Dash version — a throwaway Store is version-proof.
        dcc.Store(id='png-export-sink'),
        dcc.Store(id='print-sink'),
        # [E3-R2] the dashboard's live selection, read by the assistant
        dcc.Store(id='dashboard-state', data={}),
        dcc.Store(id='dict-copy-store', data=''),
        dcc.Download(id='download-graph-csv'),

        # ---------- Header ----------
        html.Div([
            html.Div([
                html.Button("☰", id="left-menu-btn", style={
                    'fontSize': '24px', 'backgroundColor': 'transparent',
                    'border': 'none', 'cursor': 'pointer', 'padding': '10px',
                    'marginRight': '15px'}),
                html.H1("Puerto Rico Mental Health Vulnerability Index",
                        style={'margin': '0', 'fontFamily': 'Arial',
                               'fontSize': '25px'}),
                # [E1-O8] / [E2-R6] hierarchy explainer
                html.Button("🧭 How this dashboard is organized",
                            id='open-hierarchy-btn', style={
                                'marginLeft': '18px', 'backgroundColor': '#f0f2f5',
                                'border': '1px solid #ccc', 'padding': '5px 10px',
                                'borderRadius': '4px', 'cursor': 'pointer',
                                'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                html.Button("ℹ️ Data Dictionary", id='open-help-btn', style={
                    'marginLeft': '10px', 'backgroundColor': '#f0f2f5',
                    'border': '1px solid #ccc', 'padding': '5px 10px',
                    'borderRadius': '4px', 'cursor': 'pointer',
                    'fontWeight': 'bold', 'whiteSpace': 'nowrap'})
            ], style={'display': 'flex', 'alignItems': 'center',
                      'flexWrap': 'wrap', 'gap': '4px'}),

            html.Div([
                html.Img(src=encoded_logo1, style={'height': '46px',
                                                   'objectFit': 'contain'}),
                html.Span(" | ", style={'fontSize': '28px', 'color': '#ccc',
                                        'margin': '0 12px'}),
                html.Img(src=encoded_logo2, style={'height': '46px',
                                                   'objectFit': 'contain'}),
                # account / sign-in button from the AI-CHATBOT branch
                *header_extras,
            ], style={'display': 'flex', 'alignItems': 'center'})
        ], style={'display': 'flex', 'alignItems': 'center',
                  'justifyContent': 'space-between', 'padding': '10px 20px',
                  'borderBottom': '1px solid #ccc'}),

        # ---------- Top control bar ----------
        html.Div([
            # [E1-R7] explicitly named "Map Category", with an opt-out link to the graph
            html.Div([
                html.Label("Map Category:", style={'fontWeight': 'bold',
                                                   'marginRight': '8px',
                                                   'whiteSpace': 'nowrap'}),
                dcc.Dropdown(
                    id='map-category',
                    options=[{'label': pretty_category(c), 'value': c}
                             for c in global_categories],
                    value=OVERALL, clearable=False, searchable=True,
                    style={'width': '300px'}
                ),
                dcc.Checklist(
                    id='link-graph-to-map',
                    options=[{'label': '  keep the graph on this category',
                              'value': 'link'}],
                    value=['link'],
                    style={'fontSize': '12px', 'marginLeft': '10px',
                           'whiteSpace': 'nowrap'},
                ),
            ], style={'display': 'flex', 'alignItems': 'center',
                      'marginRight': '20px'}),

            html.Div([
                html.Label("Go to municipality:", style={'fontWeight': 'bold',
                                                         'marginRight': '8px',
                                                         'whiteSpace': 'nowrap'}),
                dcc.Dropdown(
                    id='muni-search',
                    options=[{'label': c['name'], 'value': c['fips_code']}
                             for c in all_counties],
                    value=None,
                    placeholder=f"Type a name… ({len(all_counties)} municipalities)",
                    searchable=True, clearable=True, style={'width': '260px'}
                )
            ], style={'display': 'flex', 'alignItems': 'center',
                      'marginRight': '20px'}),

            html.Button("↺  Reset dashboard", id='reset-btn', n_clicks=0,
                        title="Clear every selection — municipalities, category, "
                              "indicators, year, display mode, projection, custom "
                              "report — and return to the starting state",
                        style={'padding': '8px 16px', 'backgroundColor': 'white',
                               'border': '2px solid #b3202c', 'color': '#b3202c',
                               'borderRadius': '6px', 'cursor': 'pointer',
                               'fontWeight': 'bold', 'marginLeft': 'auto',
                               'whiteSpace': 'nowrap'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'padding': '10px 20px',
                  'backgroundColor': '#f0f2f5', 'borderBottom': '1px solid #ccc',
                  'fontFamily': 'Arial', 'flexWrap': 'wrap', 'gap': '8px'}),

        # [E1-R5] / [E2-R3] persistent active-settings breadcrumb
        html.Div(id='breadcrumb-bar', className='crumb-bar', children=[]),

        # [E2-O3] / [E2-O4] loud, always-visible alert while a sticky setting is on
        html.Div(id='settings-alert',
                 style={'display': 'none'},
                 children=[
                     html.Span(id='settings-alert-text',
                               style={'fontWeight': '600'}),
                     html.Button("Show raw values", id='alert-show-raw-btn',
                                 n_clicks=0,
                                 style={**small_btn, 'borderColor': AMBER_FG,
                                        'color': AMBER_FG, 'marginLeft': '10px'}),
                     html.Button("Turn off projection", id='alert-stop-forecast-btn',
                                 n_clicks=0,
                                 style={**small_btn, 'borderColor': AMBER_FG,
                                        'color': AMBER_FG, 'marginLeft': '6px'}),
                 ]),

        # ---------- Main content ----------
        html.Div([

            html.Div(
                id='left-menu-container', style={'display': 'none'},
                children=[
                    html.H3("Navigation", style={'borderBottom': '2px solid #ccc',
                                                 'paddingBottom': '10px'}),
                    html.Button("Custom Reports", id='open-reports-btn',
                                style=menu_btn_style),
                    html.Button("Publication", style=menu_btn_style),
                    html.Button("Data Sources", style=menu_btn_style),
                    html.Button("Source Code", style=menu_btn_style)
                ]
            ),

            html.Div([
                dcc.Graph(id='pr-map', style={'height': '72vh'}, config=MAP_CONFIG)
            ], style={'flex': '7', 'padding': '10px', 'minWidth': '0'}),

            html.Div(
                id='side-panel-container', style={'display': 'none'},
                children=[
                    # ----- panel header: title, help, close -----
                    html.Div([
                        html.H2(id='county-title',
                                style={'margin': '0', 'fontSize': '20px',
                                       'flex': '1', 'minWidth': '0'}),
                        html.Button("?", id='open-panel-help-btn', n_clicks=0,
                                    title="How to read this panel",
                                    style={**small_btn, 'width': '26px',
                                           'padding': '3px 0', 'fontWeight': '700'}),
                        html.Button("✖", id="close-panel-btn", title="Close panel",
                                    style={'backgroundColor': '#ff4d4d',
                                           'color': 'white', 'border': 'none',
                                           'padding': '4px 9px',
                                           'borderRadius': '4px',
                                           'cursor': 'pointer'}),
                    ], style={'display': 'flex', 'alignItems': 'center',
                              'gap': '6px', 'borderBottom': '2px solid #ccc',
                              'paddingBottom': '8px', 'marginBottom': '8px'}),

                    # [E1-O2] removable chips for everything currently selected
                    html.Div(id='selection-chips', style={'marginBottom': '8px'}),

                    # ----- selection block -----
                    html.Div([
                        # [E2-O1] single selection by default, compare is opt-in
                        dcc.RadioItems(
                            id='selection-mode',
                            options=[{'label': ' One', 'value': 'single'},
                                     {'label': ' Compare', 'value': 'compare'}],
                            value='single', className='seg-toggle seg-mini',
                            style={'marginBottom': '6px'},
                        ),
                        dcc.Dropdown(
                            id='y-county-dropdown',
                            options=[{'label': c['name'], 'value': c['fips_code']}
                                     for c in all_counties],
                            value=None, multi=False, searchable=True,
                            placeholder="Municipality — type to search…",
                            style={'marginBottom': '8px'}
                        ),
                        html.Div([
                            dcc.Dropdown(
                                id='y-metric-dropdown',
                                options=METRIC_OPTIONS, value=[OVERALL_METRIC],
                                multi=True, searchable=True, optionHeight=52,
                                placeholder="Indicator — type to search any category…",
                                style={'flex': '1', 'minWidth': '0'}
                            ),
                            # dcc.Dropdown has no `title` prop, so the tooltip goes
                            # on a wrapping Div (an HTML element, which does).
                            html.Div(
                                dcc.Dropdown(
                                    id='metric-cat-filter',
                                    options=[{'label': 'All', 'value': 'All'}] +
                                            [{'label': pretty_category(c),
                                              'value': c}
                                             for c in available_subcats],
                                    value='All', clearable=False, searchable=True,
                                    style={'width': '130px'}
                                ),
                                title="Narrow the indicator list to one category",
                                style={'flex': '0 0 130px'}
                            ),
                        ], style={'display': 'flex', 'gap': '6px',
                                  'alignItems': 'flex-start'}),
                    ], style={'marginBottom': '8px'}),

                    # [E2-R6] one collapsed line per indicator; expand for the
                    # definition. Kept closed so the panel stays scannable.
                    html.Div(id='indicator-definitions',
                             style={'marginBottom': '8px'}),

                    # [E3-R5] how an index score is built, only when one is selected
                    html.Div(id='calc-components', style={'marginBottom': '8px'}),

                    # ----- display block: three compact toggles on two rows -----
                    html.Div([
                        html.Div([
                            dcc.RadioItems(
                                id='data-mode',
                                options=[{'label': ' Raw', 'value': 'raw'},
                                         {'label': ' Normalized 0–100',
                                          'value': 'norm'}],
                                value='raw', className='seg-toggle seg-mini',
                            ),
                            dcc.RadioItems(
                                id='chart-layout',
                                options=[{'label': ' 1 chart', 'value': 'single'},
                                         {'label': ' Split axes', 'value': 'facet'}],
                                value='single', className='seg-toggle seg-mini',
                            ),
                        ], style={'display': 'flex', 'gap': '10px',
                                  'flexWrap': 'wrap', 'marginBottom': '6px'}),
                        dcc.Checklist(
                            id='forecast-toggle',
                            options=[{'label': '  Project 4 future years',
                                      'value': 'forecast'}],
                            value=[], style={'fontSize': '12px'}
                        ),
                        # One short line, not a paragraph. Full text in the tooltip
                        # and in the Help panel.
                        html.Div(id='data-mode-explainer', className='mode-note'),
                    ], style={'marginBottom': '8px'}),

                    # [E1-R8] scale-mismatch helper with one-click remedies
                    html.Div(id='scale-helper', style={'display': 'none'},
                             children=[
                                 html.Span(id='scale-helper-text',
                                           style={'fontSize': '12px',
                                                  'color': AMBER_FG}),
                                 html.Button("Normalize",
                                             id='scale-normalize-btn', n_clicks=0,
                                             style={**small_btn,
                                                    'borderColor': AMBER_FG,
                                                    'color': AMBER_FG,
                                                    'marginLeft': '8px'}),
                                 html.Button("Split axes", id='scale-facet-btn',
                                             n_clicks=0,
                                             style={**small_btn,
                                                    'borderColor': AMBER_FG,
                                                    'color': AMBER_FG,
                                                    'marginLeft': '6px'}),
                             ]),

                    # [E1-R2] / [E2-O5] year selector + no-hover summary cards
                    html.Div([
                        html.Div([
                            html.Label("Values for year",
                                       style={'fontWeight': 'bold',
                                              'fontSize': '13px',
                                              'whiteSpace': 'nowrap'}),
                            dcc.Dropdown(id='year-selector', options=[], value=None,
                                         clearable=False, searchable=True,
                                         style={'width': '120px'}),
                        ], style={'display': 'flex', 'alignItems': 'center',
                                  'gap': '8px', 'marginBottom': '6px',
                                  'flexWrap': 'wrap'}),
                        html.Div(id='summary-cards'),
                    ], style={'marginBottom': '10px'}),

                    html.Hr(),

                    html.Div([
                        html.Div(id='chart-mode-banner',
                                 style={'marginBottom': '4px', 'display': 'flex',
                                        'alignItems': 'center', 'gap': '8px',
                                        'flexWrap': 'wrap'}),
                        dcc.Graph(id='factor-trend-graph', config=TREND_CONFIG,
                                  style={'height': '38vh', 'marginBottom': '6px'}),
                        # [E2-R4] / [E2-R5] one clearly labelled export group
                        html.Div([
                            html.Button("⬇ PNG", id='export-png-btn', n_clicks=0,
                                        title="Export the chart exactly as shown",
                                        style=small_btn),
                            html.Button("⬇ CSV", id='export-csv-btn', n_clicks=0,
                                        title="Export every value behind this "
                                              "chart, with the current settings "
                                              "recorded in the file",
                                        style=small_btn),
                            html.Button("➕ Add to report",
                                        id='add-to-custom-report-btn', n_clicks=0,
                                        title="Send this exact graph to the Custom "
                                              "Report Builder",
                                        style={'backgroundColor': '#28a745',
                                               'color': 'white', 'border': 'none',
                                               'padding': '5px 10px',
                                               'borderRadius': '6px',
                                               'cursor': 'pointer',
                                               'fontWeight': 'bold',
                                               'fontSize': '12px'}),
                        ], style={'display': 'flex', 'justifyContent': 'center',
                                  'flexWrap': 'wrap', 'gap': '6px'}),
                        html.Div(id='add-report-toast',
                                 style={'textAlign': 'center', 'color': 'green',
                                        'marginTop': '4px', 'fontSize': '12px',
                                        'minHeight': '14px'})
                    ], style={'marginBottom': '10px'}),

                    html.Div(
                        id='table-section', style=TABLE_STYLE_INLINE,
                        children=[
                            html.Div([
                                html.H4("Data behind this chart",
                                        id='indicator-table-title',
                                        style={'margin': '0', 'fontSize': '15px'}),
                                html.Span(id='table-mode-banner',
                                          style={'fontSize': '12px',
                                                 'color': '#555', 'flex': '1',
                                                 'textAlign': 'right'}),
                                html.Button("⤢", id='expand-table-btn', n_clicks=0,
                                            title="Expand the table to full page",
                                            style={**small_btn, 'width': '28px',
                                                   'padding': '3px 0'}),
                            ], style={'display': 'flex',
                                      'alignItems': 'center',
                                      'marginBottom': '6px', 'gap': '8px'}),
                            dash_table.DataTable(
                                id='data-table', data=[], columns=[],
                                page_action='none', fixed_rows={'headers': True},
                                sort_action='native', filter_action='native',
                                export_format='csv', export_headers='display',
                                style_table=DT_STYLE_INLINE,
                                style_cell={'textAlign': 'left',
                                            'padding': '6px 8px',
                                            'fontFamily': 'Arial',
                                            'fontSize': '13px', 'minWidth': '90px',
                                            'maxWidth': '320px',
                                            'whiteSpace': 'normal',
                                            'height': 'auto'},
                                style_header={'fontWeight': 'bold',
                                              'backgroundColor': '#f0f2f5',
                                              'position': 'sticky', 'top': 0},
                                style_data_conditional=[
                                    {'if': {'row_index': 'odd'},
                                     'backgroundColor': '#fafbfc'},
                                    {'if': {'filter_query':
                                            '{status} = "Predicted"'},
                                     'fontStyle': 'italic', 'color': '#7a5aa8'},
                                ],
                            ),
                            html.Div(id='table-empty-note',
                                     style={'fontSize': '12px', 'color': '#888',
                                            'fontStyle': 'italic',
                                            'marginTop': '6px'}),
                        ]
                    )
                ]
            )
        ], style={'display': 'flex', 'flexDirection': 'row'}),

        # ---------- Footer ----------
        html.Div([
            html.Div([
                html.Img(src=encoded_logo3,
                         style={'height': '40px', 'objectFit': 'contain',
                                'marginRight': '15px'}) if encoded_logo3
                else html.Span(),
                html.P("The research was supported by AIM-AHEAD Coordinating Center "
                       "at the University of North Texas Health Science Center at "
                       "Fort Worth. This research was, in part, funded by the "
                       "National Institutes of Health (NIH) Agreement No. "
                       "1OT2OD032581. The views and conclusions contained in this "
                       "document are those of the authors and should not be "
                       "interpreted as representing the official policies, either "
                       "expressed or implied, of the NIH",
                       style={'textAlign': 'left', 'color': '#888',
                              'fontSize': '11px', 'margin': '0'})
            ], style={'display': 'flex', 'alignItems': 'center',
                      'justifyContent': 'center', 'maxWidth': '800px',
                      'margin': '0 auto'})
        ], style={'padding': '15px 20px', 'borderTop': '1px solid #ccc',
                  'backgroundColor': '#f9f9f9'}),

        # ---------- Hierarchy modal ----------
        html.Div(
            id='hierarchy-modal', style=dict(MODAL_WRAP),
            children=[html.Div(
                style={'backgroundColor': 'white', 'padding': '30px',
                       'borderRadius': '8px', 'width': '70%', 'maxWidth': '760px',
                       'maxHeight': '82%', 'overflowY': 'auto',
                       'position': 'relative'},
                children=[
                    html.Button("✖ Close", id="close-hierarchy-btn", style={
                        'position': 'absolute', 'top': '15px', 'right': '15px',
                        'backgroundColor': '#ff4d4d', 'color': 'white',
                        'border': 'none', 'padding': '8px 12px',
                        'borderRadius': '4px', 'cursor': 'pointer'}),
                    html.H2("How this dashboard is organized",
                            style={'marginTop': '0',
                                   'borderBottom': '2px solid #ccc',
                                   'paddingBottom': '10px'}),
                    *HIERARCHY_BODY,
                ]
            )]
        ),

        # ---------- Data dictionary modal ----------
        html.Div(
            id='help-modal', style=dict(MODAL_WRAP),
            children=[html.Div(
                style={'backgroundColor': 'white', 'padding': '26px',
                       'borderRadius': '8px', 'width': '86%', 'height': '86%',
                       'overflowY': 'auto', 'position': 'relative'},
                children=[
                    html.Button("✖ Close", id="close-help-btn", style={
                        'position': 'absolute', 'top': '15px', 'right': '15px',
                        'backgroundColor': '#ff4d4d', 'color': 'white',
                        'border': 'none', 'padding': '8px 12px',
                        'borderRadius': '4px', 'cursor': 'pointer'}),
                    html.H2("Data Dictionary & Glossary",
                            style={'marginTop': '0',
                                   'borderBottom': '2px solid #ccc',
                                   'paddingBottom': '10px'}),
                    html.P("This glossary is curated separately from the indicator "
                           "tables and does not yet cover every indicator in the "
                           "dashboard. Entries with no description are listed as "
                           "such rather than hidden.",
                           style={'fontSize': '12px', 'color': '#8a6d3b',
                                  'backgroundColor': '#fcf8e3',
                                  'padding': '8px 10px', 'borderRadius': '4px'}),
                    # [E2-R6] prominent search over names AND definitions
                    html.Div([
                        dcc.Input(
                            id='dict-search', type='text', debounce=False,
                            placeholder="🔍  Search indicator names and definitions "
                                        "(e.g. \"occupied housing\", \"insured\")…",
                            style={'flex': '1', 'minWidth': '260px',
                                   'padding': '10px 12px', 'fontSize': '14px',
                                   'border': '2px solid #c3cdd8',
                                   'borderRadius': '6px'}),
                        dcc.Dropdown(
                            id='dict-category-filter',
                            options=[{'label': 'All categories', 'value': 'All'}] +
                                    [{'label': c.replace('_', ' '), 'value': c}
                                     for c in DICT_CATEGORIES],
                            value='All', clearable=False,
                            style={'width': '280px'}),
                    ], style={'display': 'flex', 'gap': '10px',
                              'alignItems': 'center', 'marginBottom': '6px',
                              'flexWrap': 'wrap'}),
                    html.Div(id='dict-result-count',
                             style={'fontSize': '12px', 'color': '#666',
                                    'marginBottom': '8px'}),
                    dash_table.DataTable(
                        id='dict-data-table',
                        data=data_dictionary_records,
                        columns=[
                            {'id': 'friendly_name', 'name': 'Indicator Name'},
                            {'id': 'category', 'name': 'Category'},
                            {'id': 'units', 'name': 'Units'},
                            {'id': 'description', 'name': 'Description'},
                            {'id': 'source', 'name': 'Data Source'}
                        ],
                        row_selectable='single', selected_rows=[],
                        page_size=15, sort_action='native',
                        export_format='csv', export_headers='display',
                        # [E2-R6] freeze the name column, wrap the descriptions
                        fixed_columns={'headers': True, 'data': 1},
                        style_table={'minWidth': '100%', 'overflowX': 'auto'},
                        style_cell={'textAlign': 'left', 'padding': '9px',
                                    'fontFamily': 'Arial', 'fontSize': '13px',
                                    'whiteSpace': 'normal', 'height': 'auto',
                                    'minWidth': '110px', 'maxWidth': '420px'},
                        style_cell_conditional=[
                            {'if': {'column_id': 'friendly_name'},
                             'width': '230px', 'minWidth': '230px',
                             'fontWeight': '600', 'backgroundColor': '#fbfcfe'},
                            {'if': {'column_id': 'description'}, 'width': '420px'},
                        ],
                        style_header={'fontWeight': 'bold',
                                      'backgroundColor': '#f0f2f5'},
                    ),
                    # [E2-R6] copy control lives in the layout, not inside the
                    # generated card, so its callback always has a target
                    html.Div([
                        html.Button("⧉ Copy definition", id='dict-copy-btn',
                                    n_clicks=0,
                                    style={**small_btn, 'display': 'none'}),
                        html.Span(id='dict-copy-toast',
                                  style={'fontSize': '12px', 'color': 'green',
                                         'marginLeft': '10px'}),
                    ], style={'display': 'flex', 'alignItems': 'center',
                              'marginTop': '14px', 'minHeight': '20px'}),
                    html.Div(id='dict-detail-card', style={'marginTop': '8px'}),
                ]
            )]
        ),

        # ---------- Custom report modal ----------
        html.Div(
            id='custom-reports-modal',
            style={**MODAL_WRAP, 'zIndex': '1500'},
            children=[html.Div(
                style={'backgroundColor': 'white', 'padding': '30px',
                       'borderRadius': '8px', 'width': '100%',
                       'maxWidth': '850px', 'height': '90%', 'overflowY': 'auto',
                       'position': 'relative', 'margin': '0 auto'},
                children=[
                    html.Button("✖ Close", id="close-modal-btn",
                                className="no-print", style={
                                    'position': 'absolute', 'top': '15px',
                                    'right': '15px', 'backgroundColor': '#ff4d4d',
                                    'color': 'white', 'border': 'none',
                                    'padding': '8px 12px', 'borderRadius': '4px',
                                    'cursor': 'pointer'}),
                    html.H2("Custom Report Builder",
                            style={'marginTop': '0',
                                   'borderBottom': '2px solid #ccc',
                                   'paddingBottom': '10px'}),
                    html.P("Elements added with “Add to Custom Report” arrive "
                           "carrying the exact municipalities, indicators, display "
                           "mode and projection setting that were active on the "
                           "graph.",
                           className="no-print",
                           style={'fontSize': '12px', 'color': '#555'}),
                    html.Div(id='report-elements-container', children=[],
                             style={'marginBottom': '20px'}),
                    html.Div([
                        html.Button("+ Add blank element",
                                    id='add-report-element-btn',
                                    className="no-print", style={
                                        'padding': '10px 15px',
                                        'backgroundColor': '#4CAF50',
                                        'color': 'white', 'border': 'none',
                                        'borderRadius': '4px', 'cursor': 'pointer',
                                        'marginRight': '10px'}),
                        html.Button("🖨 Export report to PDF", id='export-pdf-btn',
                                    className="no-print", style={
                                        'padding': '10px 15px',
                                        'backgroundColor': '#008CBA',
                                        'color': 'white', 'border': 'none',
                                        'borderRadius': '4px',
                                        'cursor': 'pointer'})
                    ], className="no-print",
                       style={'borderTop': '1px solid #eee', 'paddingTop': '20px'})
                ]
            )]
        ),
    ]
