"""MHVI dashboard — everything the page does.

These are the V10.1 callbacks, unchanged. They are written with the usual
``@app.callback`` decorator; ``app`` here is a recorder that keeps the list,
and ``register_dashboard_callbacks(real_app)`` hands them all to the real Dash
app at startup (MHVIM_Dashboard_App.py). That keeps this file identical to the
version that was tested, instead of re-indenting it inside a function.
"""
from .core import *  # noqa: F401,F403  (constants, helpers, styles)
from .core import _map_target  # noqa: F401


class _DeferredApp:
    """Collects @app.callback / app.clientside_callback registrations."""

    def __init__(self):
        self._callbacks = []
        self._clientside = []

    def callback(self, *args, **kwargs):
        def decorator(fn):
            self._callbacks.append((args, kwargs, fn))
            return fn
        return decorator

    def clientside_callback(self, *args, **kwargs):
        self._clientside.append((args, kwargs))


app = _DeferredApp()


def register_dashboard_callbacks(real_app):
    """Attach every dashboard callback to the real Dash app."""
    for args, kwargs, fn in app._callbacks:
        real_app.callback(*args, **kwargs)(fn)
    for args, kwargs in app._clientside:
        real_app.clientside_callback(*args, **kwargs)


# =========================================================
# MAP
# =========================================================
@app.callback(
    [Output('pr-map', 'figure'), Output('map-year-store', 'data')],
    [Input('map-category', 'value'),
     Input('y-county-dropdown', 'value')]
)
def update_map(category, selected):
    selected = as_list(selected)
    df, year, info = fetch_map_data(category)
    used_mapbox = False

    if df.empty:
        try:
            fig = px.choropleth_map(geojson=counties, locations=[],
                                    map_style="carto-positron", zoom=7.5,
                                    center={"lat": 18.2208, "lon": -66.5901})
        except Exception:
            try:
                fig = px.choropleth_mapbox(geojson=counties, locations=[],
                                           mapbox_style="carto-positron",
                                           zoom=7.5,
                                           center={"lat": 18.2208,
                                                   "lon": -66.5901})
                used_mapbox = True
            except Exception:
                fig = px.scatter(title="Map Load Error")
        fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
        return fig, None

    kwargs = dict(
        geojson=counties, locations='fips_code', color='value',
        hover_name='name', color_continuous_scale="Viridis_r", zoom=7.5,
        center={"lat": 18.2208, "lon": -66.5901}, opacity=0.8,
        hover_data={'fips_code': False, 'value': ':.1f'},
        labels={'value': 'Index score'}, range_color=(0, 100),
    )
    try:
        fig = px.choropleth_map(df, map_style="carto-positron", **kwargs)
    except Exception:
        fig = px.choropleth_mapbox(df, mapbox_style="carto-positron", **kwargs)
        used_mapbox = True

    # [E1-O5] permanently label the selected municipality on the map
    try:
        pts = [(FIPS_CENTROID[f], FIPS_TO_NAME.get(f, f))
               for f in selected if f in FIPS_CENTROID]
        if pts:
            lats = [p[0][0] for p in pts]
            lons = [p[0][1] for p in pts]
            names = [p[1] for p in pts]
            trace_cls = go.Scattermapbox if used_mapbox else go.Scattermap
            fig.add_trace(trace_cls(
                lat=lats, lon=lons, mode='markers+text', text=names,
                textposition='top center',
                textfont=dict(size=14, color='#11181f'),
                marker=dict(size=16, color='#ffffff'),
                hoverinfo='text', name='Selected', showlegend=False,
            ))
    except Exception:
        pass

    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        coloraxis_colorbar=dict(title="Index<br>0–100"),
        # keep the user's zoom/pan when the map redraws on selection
        uirevision=str(category),
    )
    return fig, year


# =========================================================
# SELECTION
# =========================================================
PANEL_OPEN_STYLE = {
    'flex': '4', 'padding': '20px', 'backgroundColor': '#f8f9fa',
    'borderLeft': '1px solid #ccc', 'fontFamily': 'Arial',
    'height': '80vh', 'overflowY': 'auto',
    'display': 'flex', 'flexDirection': 'column', 'minWidth': '0'
}
PANEL_HIDDEN_STYLE = {'display': 'none'}


def _county_value(fips_list, mode):
    """Shape the dropdown value for its current `multi` setting."""
    fips_list = [f for f in (fips_list or []) if f]
    if mode == 'single':
        return fips_list[0] if fips_list else None
    return fips_list


@app.callback(
    [Output('y-county-dropdown', 'value'),
     Output('side-panel-container', 'style')],
    [Input('pr-map', 'clickData'),
     Input('muni-search', 'value'),
     Input('close-panel-btn', 'n_clicks'),
     Input('reset-btn', 'n_clicks'),
     Input({'type': 'chip-remove-muni', 'index': ALL}, 'n_clicks')],
    [State('selection-mode', 'value'),
     State('y-county-dropdown', 'value')],
    prevent_initial_call=True
)
def handle_selection(click_data, search_fips, close_clicks, reset_clicks,
                     chip_clicks, mode, current):
    trigger = dash.ctx.triggered_id
    nu = dash.no_update
    current = as_list(current)

    if trigger == 'reset-btn':
        return _county_value([], 'single'), PANEL_HIDDEN_STYLE

    if trigger == 'close-panel-btn':
        return nu, PANEL_HIDDEN_STYLE

    # [E1-O2] chip × removes one municipality
    if isinstance(trigger, dict) and trigger.get('type') == 'chip-remove-muni':
        if not any(c for c in (chip_clicks or [])):
            raise dash.exceptions.PreventUpdate
        remaining = [f for f in current if f != trigger.get('index')]
        style = PANEL_OPEN_STYLE if remaining else PANEL_HIDDEN_STYLE
        return _county_value(remaining, mode), style

    if trigger == 'muni-search':
        # also fires when Reset clears the box; nothing to do then
        if not search_fips:
            raise dash.exceptions.PreventUpdate
        if mode == 'compare' and search_fips not in current:
            return _county_value(current + [search_fips], mode), PANEL_OPEN_STYLE
        return _county_value([search_fips], mode), PANEL_OPEN_STYLE

    if trigger == 'pr-map':
        if not click_data:
            raise dash.exceptions.PreventUpdate
        fips = click_data['points'][0].get('location')
        if not fips:
            raise dash.exceptions.PreventUpdate
        if mode == 'compare' and fips not in current:
            return _county_value(current + [fips], mode), PANEL_OPEN_STYLE
        return _county_value([fips], mode), PANEL_OPEN_STYLE

    raise dash.exceptions.PreventUpdate


@app.callback(
    Output('muni-search', 'value'),
    Input('pr-map', 'clickData'),
    prevent_initial_call=True
)
def sync_search_box_with_map(click_data):
    if not click_data:
        raise dash.exceptions.PreventUpdate
    fips = click_data['points'][0].get('location')
    if not fips:
        raise dash.exceptions.PreventUpdate
    return fips


# [E2-O1] switching between one-municipality and compare mode
@app.callback(
    [Output('y-county-dropdown', 'multi'),
     Output('y-county-dropdown', 'value', allow_duplicate=True),
     Output('y-county-dropdown', 'placeholder')],
    Input('selection-mode', 'value'),
    State('y-county-dropdown', 'value'),
    prevent_initial_call=True
)
def set_selection_mode(mode, current):
    current = as_list(current)
    if mode == 'compare':
        return True, current, "Search municipalities to compare…"
    # Dropping back to one municipality keeps the first and discards the rest,
    # which is what stops stale municipalities from riding along.
    return False, (current[0] if current else None), "Search a municipality…"


# [E1-R7] keep the graph on the map's category unless the user unlinks it
@app.callback(
    [Output('y-metric-dropdown', 'value', allow_duplicate=True),
     Output('metric-cat-filter', 'value', allow_duplicate=True)],
    Input('map-category', 'value'),
    State('link-graph-to-map', 'value'),
    State('y-metric-dropdown', 'value'),
    prevent_initial_call=True
)
def sync_graph_to_map_category(map_cat, link, current_metrics):
    if 'link' not in (link or []):
        raise dash.exceptions.PreventUpdate
    if map_cat == OVERALL:
        return [OVERALL_METRIC], 'All'
    target = CATEGORY_INDEX_METRIC.get(map_cat)
    if not target:
        raise dash.exceptions.PreventUpdate
    if as_list(current_metrics) == [target]:
        raise dash.exceptions.PreventUpdate
    return [target], map_cat


# =========================================================
# RESET  [E1-R4] / [E2-R2]
# =========================================================
@app.callback(
    [Output('map-category', 'value'),
     Output('link-graph-to-map', 'value'),
     Output('metric-cat-filter', 'value'),
     Output('y-metric-dropdown', 'value', allow_duplicate=True),
     Output('data-mode', 'value', allow_duplicate=True),
     Output('forecast-toggle', 'value', allow_duplicate=True),
     Output('chart-layout', 'value', allow_duplicate=True),
     Output('selection-mode', 'value'),
     Output('left-menu-container', 'style', allow_duplicate=True),
     Output('table-section', 'style', allow_duplicate=True),
     Output('data-table', 'style_table', allow_duplicate=True),
     Output('expand-table-btn', 'children', allow_duplicate=True),
     Output('add-report-toast', 'children', allow_duplicate=True),
     Output('dict-category-filter', 'value'),
     Output('dict-search', 'value', allow_duplicate=True),
     Output('muni-search', 'value', allow_duplicate=True),
     Output('report-elements-container', 'children', allow_duplicate=True),
     Output('custom-reports-modal', 'style', allow_duplicate=True),
     Output('help-modal', 'style', allow_duplicate=True),
     Output('hierarchy-modal', 'style', allow_duplicate=True)],
    Input('reset-btn', 'n_clicks'),
    prevent_initial_call=True
)
def reset_dashboard(n_clicks):
    """Everything the study saw carrying over between tasks, cleared at once."""
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    return (OVERALL, ['link'], 'All', [OVERALL_METRIC], 'raw', [], 'single',
            'single', {'display': 'none'}, TABLE_STYLE_INLINE, DT_STYLE_INLINE,
            "⤢", "", 'All', '', None, [],
            dict(MODAL_WRAP, zIndex='1500'), dict(MODAL_WRAP),
            dict(MODAL_WRAP))


# =========================================================
# INDICATOR PICKER + DEFINITIONS
# =========================================================
@app.callback(
    Output('y-metric-dropdown', 'options'),
    Input('metric-cat-filter', 'value'),
    State('y-metric-dropdown', 'value'),
)
def filter_metric_options(cat_filter, selected):
    if not cat_filter or cat_filter == 'All':
        return METRIC_OPTIONS
    selected = set(as_list(selected))
    return [o for o in METRIC_OPTIONS
            if METRIC_CATEGORY.get(o['value']) == cat_filter
            or o['value'] in selected]


# [E1-O2] chips: a plain list of what is active, each with its own ×
@app.callback(
    Output('selection-chips', 'children'),
    [Input('y-county-dropdown', 'value'),
     Input('y-metric-dropdown', 'value')],
)
def render_selection_chips(counties_list, metrics):
    counties_list = as_list(counties_list)
    metrics = as_list(metrics)
    kids = []

    if counties_list:
        kids.append(html.Div([
            html.Span("Municipality: " if len(counties_list) == 1
                      else "Municipalities: ",
                      style={'fontSize': '12px', 'fontWeight': '700',
                             'marginRight': '4px'}),
            *[html.Span([
                FIPS_TO_NAME.get(f, f),
                html.Button("×", id={'type': 'chip-remove-muni', 'index': f},
                            n_clicks=0, className='chip-x',
                            title=f"Remove {FIPS_TO_NAME.get(f, f)}"),
            ], className='chip') for f in counties_list],
        ], style={'marginBottom': '4px'}))

    if metrics:
        kids.append(html.Div([
            html.Span("Indicator: " if len(metrics) == 1 else "Indicators: ",
                      style={'fontSize': '12px', 'fontWeight': '700',
                             'marginRight': '4px'}),
            *[html.Span([
                metric_label(m),
                html.Button("×", id={'type': 'chip-remove-metric', 'index': m},
                            n_clicks=0, className='chip-x',
                            title=f"Remove {metric_label(m)}"),
            ], className='chip') for m in metrics],
        ]))

    if not kids:
        return html.Div("Nothing selected yet.",
                        style={'fontSize': '12px', 'color': '#888',
                               'fontStyle': 'italic'})
    return kids


@app.callback(
    Output('y-metric-dropdown', 'value', allow_duplicate=True),
    Input({'type': 'chip-remove-metric', 'index': ALL}, 'n_clicks'),
    State('y-metric-dropdown', 'value'),
    prevent_initial_call=True
)
def remove_metric_chip(chip_clicks, metrics):
    trigger = dash.ctx.triggered_id
    if not isinstance(trigger, dict):
        raise dash.exceptions.PreventUpdate
    if not any(c for c in (chip_clicks or [])):
        raise dash.exceptions.PreventUpdate
    return [m for m in as_list(metrics) if m != trigger.get('index')]


# [E2-R6] definitions beside the selection — collapsed to one line each, so
# the panel stays scannable. Click to read; the glossary link is inside.
@app.callback(
    Output('indicator-definitions', 'children'),
    Input('y-metric-dropdown', 'value'),
)
def render_indicator_definitions(metrics):
    metrics = as_list(metrics)
    if not metrics:
        return None
    rows = []
    for m in metrics:
        raw = METRIC_RAWNAME.get(m, m)
        desc = DICT_DESC.get(raw, '')
        units = METRIC_UNITS.get(m, '') or DICT_UNITS.get(raw, '')
        source = DICT_SOURCE.get(raw, '')
        head = f"ⓘ  {metric_label(m)}"
        if units:
            head += f"  ·  {units}"
        body = [html.Div(desc if desc else
                         "No description on file for this indicator yet.",
                         style={} if desc else {'color': AMBER_FG})]
        if source:
            body.append(html.Div(f"Source: {source}",
                                 style={'color': '#777', 'marginTop': '4px'}))
        body.append(html.Button("View in Data Dictionary →",
                                id={'type': 'view-def-btn', 'index': raw},
                                n_clicks=0,
                                style={'border': 'none', 'background': 'none',
                                       'color': BLUE, 'cursor': 'pointer',
                                       'padding': '0', 'fontSize': '12px',
                                       'textDecoration': 'underline',
                                       'marginTop': '5px'}))
        rows.append(html.Details([
            html.Summary(head, title=desc or metric_label(m)),
            html.Div(body),
        ], className='def-row'))
    return rows


# [E3-R5] "How this score was calculated", for index scores only.
# Figures and method wording come from MHVI Methodology Summary_Updated.docx.
@app.callback(
    Output('calc-components', 'children'),
    Input('y-metric-dropdown', 'value'),
)
def render_calc_components(metrics):
    metrics = as_list(metrics)
    index_metrics = [m for m in metrics
                     if m == OVERALL_METRIC or parse_metric(m)[1] == INDEX_IND]
    if not index_metrics:
        return None

    blocks = []
    for m in index_metrics:
        cat = METRIC_CATEGORY.get(m, OVERALL)
        if m == OVERALL_METRIC:
            head = "How the Overall MHVI Score was calculated"
            steps = [
                "1. Every indicator's raw values are ranked 0–100 across the "
                "78 municipalities. Metrics where a high value means less "
                "vulnerability (income, for example) are inverted, so 100 "
                "always means most vulnerable.",
                "2. The indicator ranks are summed within each subcategory, "
                "and that sum is percentile-ranked again to give the "
                "Subcategory Index Score.",
                "3. The subcategory ranks are summed and percentile-ranked a "
                "final time. That is the Overall MHVI Score.",
            ]
            comp_label = "Subcategories feeding the Overall Score"
            components = [pretty_category(c) for c in available_subcats]
            caveat = (f"The methodology specifies 9 subcategories. "
                      f"{len(available_subcats)} currently hold data, so the "
                      f"Overall Score is built from those "
                      f"{len(available_subcats)} only. Treat it as "
                      f"provisional until the remaining subcategories are "
                      f"loaded.")
        else:
            head = f"How the {pretty_category(cat)} index score was calculated"
            steps = [
                "1. Each indicator in this subcategory is ranked 0–100 across "
                "the 78 municipalities, inverting any metric where a high "
                "value means less vulnerability.",
                "2. Those indicator ranks are summed for the subcategory.",
                "3. The sum is percentile-ranked across municipalities to give "
                "this 0–100 score.",
            ]
            comp_label = "Indicators in this subcategory"
            components = [pretty_indicator(i) for i in db_metadata.get(cat, [])
                          if i != INDEX_IND]
            missing = [i for i in db_metadata.get(cat, [])
                       if i != INDEX_IND and not DICT_DESC.get(i)]
            caveat = ""
            if missing:
                caveat = (f"{len(missing)} of {len(components)} indicators "
                          f"here have no glossary definition on file yet.")

        blocks.append(html.Details([
            html.Summary(f"🧮  {head}",
                         title="Source: MHVI Methodology Summary"),
            html.Div([
                *[html.Div(s, style={'marginBottom': '5px'}) for s in steps],
                html.Div(f"{comp_label} ({len(components)}):",
                         style={'fontWeight': '700', 'marginTop': '7px'}),
                html.Div(", ".join(components) if components else "—",
                         style={'color': '#555'}),
                html.Div(caveat, style={'marginTop': '7px',
                                        'color': AMBER_FG}) if caveat
                else html.Span(),
                html.Div("Projections use Holt linear-trend exponential "
                         "smoothing, per the methodology document.",
                         style={'marginTop': '7px', 'color': '#777'}),
            ]),
        ], className='def-row'))
    return blocks


@app.callback(
    Output('data-mode-explainer', 'children'),
    [Input('data-mode', 'value'), Input('y-metric-dropdown', 'value')],
)
def explain_data_mode(mode, metrics):
    """One short line. The full explanation lives in the Help panel and in the
    tooltip, so the right-hand panel stays readable."""
    metrics = as_list(metrics)
    index_like = any(m == OVERALL_METRIC or parse_metric(m)[1] == INDEX_IND
                     for m in metrics)
    if mode == 'norm':
        line = [html.B("Normalized"),
                ": positions on a 0–100 scale, not real units."]
        if index_like:
            line.append(" Index scores are already 0–100 — use Raw for those.")
        tip = ("Each indicator is rescaled to 0–100 using its own lowest and "
               "highest value across the municipalities and years you "
               "selected, so indicators with different units can share one "
               "axis. MHVI index scores are already 0–100 percentile ranks, "
               "so normalizing them again changes their meaning.")
    else:
        line = [html.B("Raw"), ": each indicator in its own units."]
        if index_like:
            line.append(" Index scores are 0–100 percentile ranks.")
        else:
            line.append(" Different units should not share one axis.")
        tip = ("Raw values keep their real-world meaning (dollars, counts, "
               "rates, percentages). Two indicators with different units "
               "should not share one axis — switch to Normalized, or to split "
               "axes, to compare them. MHVI index scores are reported on a "
               "0–100 percentile scale; that is their raw unit.")
    return html.Span(line, title=tip)


# =========================================================
# YEAR SELECTOR  [E1-R2] / [E2-O5]
# =========================================================
@app.callback(
    [Output('year-selector', 'options'), Output('year-selector', 'value')],
    [Input('y-county-dropdown', 'value'),
     Input('y-metric-dropdown', 'value'),
     Input('forecast-toggle', 'value')],
    [State('year-selector', 'value'),
     State('map-year-store', 'data')],
)
def update_year_options(counties_list, metrics, forecast_opts, current_year,
                        map_year):
    counties_list = as_list(counties_list)
    metrics = as_list(metrics)
    if not counties_list or not metrics:
        return [], None
    df = build_series(counties_list, metrics)
    if df.empty:
        return [], None
    years = sorted(int(y) for y in df['year'].unique().tolist())
    opts = [{'label': str(y), 'value': int(y)} for y in years]
    if 'forecast' in (forecast_opts or []):
        last = int(max(years))
        opts += [{'label': f'{y} (predicted)', 'value': int(y)}
                 for y in range(last + 1, last + 5)]
    valid = {o['value'] for o in opts}
    if current_year in valid:
        return opts, current_year
    # Open on the year the map is colouring, so a municipality clicked on the
    # map shows the same number in the panel that its colour represents.
    if map_year is not None and int(map_year) in years:
        return opts, int(map_year)
    return opts, int(max(years))


# =========================================================
# MAIN: chart, table, summary cards, breadcrumb, alerts
# =========================================================
@app.callback(
    [Output('county-title', 'children'),
     Output('factor-trend-graph', 'figure'),
     Output('chart-mode-banner', 'children'),
     Output('data-table', 'data'),
     Output('data-table', 'columns'),
     Output('table-mode-banner', 'children'),
     Output('table-empty-note', 'children'),
     Output('indicator-table-title', 'children'),
     Output('summary-cards', 'children'),
     Output('scale-helper', 'style'),
     Output('scale-helper-text', 'children'),
     Output('breadcrumb-bar', 'children'),
     Output('settings-alert', 'style'),
     Output('settings-alert-text', 'children'),
     Output('alert-show-raw-btn', 'style'),
     Output('alert-stop-forecast-btn', 'style'),
     Output('export-name-store', 'data'),
     Output('dashboard-state', 'data')],
    [Input('y-county-dropdown', 'value'),
     Input('y-metric-dropdown', 'value'),
     Input('data-mode', 'value'),
     Input('forecast-toggle', 'value'),
     Input('year-selector', 'value'),
     Input('chart-layout', 'value'),
     Input('map-category', 'value')]
)
def update_dashboard(counties_list, metrics, mode, forecast_opts, year,
                     chart_layout, map_cat):
    counties_list = as_list(counties_list)
    metrics = as_list(metrics)
    normalized = (mode == 'norm')
    do_forecast = 'forecast' in (forecast_opts or [])
    value_col = 'normalized' if normalized else 'raw'

    # [E3-R2] published for the assistant so the user never has to restate it
    dash_state = {
        'fips': counties_list,
        'municipalities': [FIPS_TO_NAME.get(f, f) for f in counties_list],
        'metrics': metrics,
        'year': int(year) if year is not None else None,
        'mode': mode or 'raw',
        'forecast': do_forecast,
    }

    mode_badge = html.Span(
        "NORMALIZED 0–100" if normalized else "RAW VALUES",
        className='mode-badge ' + ('mode-norm' if normalized else 'mode-raw'))

    # ----- the alert strip is independent of whether data loaded -----
    alert_bits, alert_style = [], {'display': 'none'}
    raw_btn_style = {**small_btn, 'borderColor': AMBER_FG, 'color': AMBER_FG,
                     'marginLeft': '10px', 'display': 'none'}
    fc_btn_style = {**small_btn, 'borderColor': AMBER_FG, 'color': AMBER_FG,
                    'marginLeft': '6px', 'display': 'none'}
    if normalized or do_forecast:
        msgs = []
        if normalized:
            msgs.append("Normalized values are ON — these numbers are 0–100 "
                        "positions, not real-world units.")
            raw_btn_style = {**raw_btn_style, 'display': 'inline-block'}
        if do_forecast:
            msgs.append("Future projection is ON — dashed points after the last "
                        "observed year are estimates, not data.")
            fc_btn_style = {**fc_btn_style, 'display': 'inline-block'}
        alert_bits = "⚠  " + "   ".join(msgs)
        alert_style = {'display': 'flex', 'alignItems': 'center',
                       'justifyContent': 'center', 'flexWrap': 'wrap',
                       'gap': '4px', 'padding': '8px 20px',
                       'backgroundColor': AMBER_BG, 'color': AMBER_FG,
                       'borderBottom': f'1px solid #e8d69a',
                       'fontSize': '13px'}

    def crumbs(muni_txt, cat_txt, ind_txt):
        items = [html.Span(muni_txt, className='crumb'),
                 html.Span("›", className='crumb-sep'),
                 html.Span(cat_txt, className='crumb'),
                 html.Span("›", className='crumb-sep'),
                 html.Span(ind_txt, className='crumb'),
                 html.Span("›", className='crumb-sep'),
                 html.Span("NORMALIZED 0–100" if normalized else "RAW VALUES",
                           className='crumb ' + ('crumb-norm' if normalized
                                                 else 'crumb-raw')),
                 html.Span("›", className='crumb-sep')]
        if do_forecast:
            items.append(html.Span("WITH PROJECTION", className='crumb crumb-fc'))
        else:
            items.append(html.Span("Historical only", className='crumb'))
        return items

    empty_fig = px.scatter(title="")
    try:
        empty_fig.update_layout(paper_bgcolor='#f8f9fa', plot_bgcolor='#f8f9fa',
                                margin={"r": 0, "t": 30, "l": 0, "b": 0})
    except Exception:
        pass

    # ----- [E1-O3] instructive empty states, not "No Data Found" -----
    if not counties_list:
        return ("Select a municipality", empty_fig, [mode_badge], [], [], "",
                "Pick a municipality — search at the top, or click the map.",
                "Data behind this chart", None, {'display': 'none'}, "",
                crumbs("No municipality", pretty_category(map_cat),
                       "—"),
                alert_style, alert_bits, raw_btn_style, fc_btn_style,
                'MHVI_export', dash_state)

    title = ", ".join(FIPS_TO_NAME.get(f, f) for f in counties_list)
    muni_txt = title if len(counties_list) <= 2 else \
        f"{len(counties_list)} municipalities"

    if not metrics:
        return (title, empty_fig, [mode_badge], [], [], "",
                "Pick at least one indicator — the search box covers every "
                "category at once.",
                "Data behind this chart", None, {'display': 'none'}, "",
                crumbs(muni_txt, pretty_category(map_cat), "No indicator"),
                alert_style, alert_bits, raw_btn_style, fc_btn_style,
                'MHVI_export', dash_state)

    cat_txt = metric_category_label(metrics[0]) if len(metrics) == 1 else \
        f"{len({METRIC_CATEGORY.get(m) for m in metrics})} categories"
    ind_txt = metric_label(metrics[0]) if len(metrics) == 1 else \
        f"{len(metrics)} indicators"
    crumb_items = crumbs(muni_txt, cat_txt, ind_txt)

    base = build_series(counties_list, metrics)
    if base.empty:
        return (title, empty_fig, [mode_badge], [], [], "",
                "Nothing is stored for this municipality and indicator. Try "
                "another, or check the Data Dictionary for year coverage.",
                "Data behind this chart", None, {'display': 'none'}, "",
                crumb_items, alert_style, alert_bits, raw_btn_style,
                fc_btn_style, 'MHVI_export', dash_state)

    base = add_normalized(base)
    df = add_forecast(base) if do_forecast else base.assign(is_forecast=False)

    n_munis = df['municipality'].nunique()
    n_metrics = df['metric'].nunique()
    df = df.copy()
    df['series'] = [series_name(m, i, n_munis, n_metrics)
                    for m, i in zip(df['municipality'], df['indicator'])]
    df['status'] = np.where(df['is_forecast'], 'Predicted', 'Observed')
    df = df.sort_values(['indicator', 'municipality', 'year'])

    # ----- export name, so a saved file says what it contains -----
    yr_lo, yr_hi = int(df['year'].min()), int(df['year'].max())
    safe = lambda s: "".join(ch if ch.isalnum() else '-' for ch in str(s))[:40]
    export_name = (f"MHVI_{safe(muni_txt)}_{safe(ind_txt)}_"
                   f"{'NORMALIZED' if normalized else 'RAW'}_"
                   f"{yr_lo}-{yr_hi}{'_withProjection' if do_forecast else ''}")

    # ----- chart -----
    plot_df = df.copy()
    plot_df['label_series'] = np.where(
        plot_df['is_forecast'], plot_df['series'] + ' (Forecast)',
        plot_df['series'])
    plot_df['raw_txt'] = plot_df['raw'].map(fmt_num)
    plot_df['norm_txt'] = plot_df['normalized'].map(
        lambda v: '—' if v is None or not np.isfinite(v) else f'{v:.1f}')
    # [E1-R6] the tooltip names the kind of number it is showing
    plot_df['kind_txt'] = np.where(
        plot_df['is_forecast'], '⚠ PREDICTED VALUE (estimate)', 'Observed value')

    facet = (chart_layout == 'facet' and n_metrics > 1)
    fig = px.line(
        plot_df, x='year', y=value_col, color='label_series', markers=True,
        facet_row='indicator' if facet else None,
        custom_data=['raw_txt', 'norm_txt', 'kind_txt'],
    )

    color_map = {t.name: t.line.color for t in fig.data
                 if ' (Forecast)' not in t.name}
    for t in fig.data:
        if ' (Forecast)' in t.name:
            t.line.dash = 'dash'
            base_name = t.name.replace(' (Forecast)', '')
            if base_name in color_map:
                t.line.color = color_map[base_name]
            t.showlegend = False
    try:
        fig.update_traces(
            marker=dict(size=9),  # [E1-O4] bigger hit area for tooltips
            hovertemplate=('Raw Value: %{customdata[0]}<br>'
                           'Normalized Value: %{customdata[1]}<br>'
                           '%{customdata[2]}<extra>%{fullData.name}</extra>'),
        )
    except Exception:
        pass

    y_title = 'Normalized value (0–100)' if normalized else \
        'Value (original units)'
    chart_title = (f"{'Normalized 0–100' if normalized else 'Raw values'} · "
                   f"{ind_txt} · {muni_txt}"
                   f"{' · includes projection' if do_forecast else ''}")
    try:
        fig.update_layout(
            title=dict(text=chart_title, font=dict(size=13), x=0.0),
            margin={"r": 10, "t": 54, "l": 0, "b": 0},
            paper_bgcolor='#f8f9fa', plot_bgcolor='#f8f9fa',
            xaxis=dict(title="Year", type='category',
                       categoryorder='category ascending'),
            yaxis=dict(title=y_title),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1, title=None),
            # [E1-O4] read all series at one year without pixel-hunting
            hovermode='x unified', hoverdistance=30,
            dragmode=False,
        )
        if facet:
            fig.update_yaxes(matches=None, title=None)
            fig.for_each_annotation(
                lambda a: a.update(text=a.text.split('=')[-1][:48],
                                   font=dict(size=11)))
    except Exception:
        pass

    banner = [mode_badge]
    if do_forecast:
        banner.append(html.Span("PROJECTION ON", className='mode-badge mode-fc'))
    if facet:
        banner.append(html.Span("SPLIT AXES",
                                className='mode-badge mode-raw'))

    # ----- [E1-R8] scale-mismatch helper -----
    share, ratio = axis_fit(base)
    if (not normalized) and (not facet) and share < AXIS_SHARE_FLOOR:
        scale_style = {'display': 'flex', 'alignItems': 'center',
                       'flexWrap': 'wrap', 'gap': '4px',
                       'backgroundColor': AMBER_BG, 'padding': '8px 10px',
                       'borderRadius': '4px', 'marginBottom': '10px'}
        if ratio >= 10:
            scale_text = (f"Magnitudes differ ~{ratio:,.0f}× — the smaller "
                          f"line is squashed flat.")
        else:
            scale_text = (f"One line uses only ~{share * 100:.0f}% of the "
                          f"axis height — it reads as flat.")
    else:
        scale_style = {'display': 'none'}
        scale_text = ""

    # ----- [E1-R2] / [E2-O5] summary cards for the chosen year -----
    cards = []
    if year is not None:
        yr_df = df[df['year'] == int(year)]
        if yr_df.empty:
            cards.append(html.Div(
                f"No values stored for {year}. Pick another year above.",
                style={'fontSize': '12px', 'color': '#8a6d3b',
                       'backgroundColor': AMBER_BG, 'padding': '8px 10px',
                       'borderRadius': '4px'}))
        else:
            for metric, grp in yr_df.groupby('metric', sort=False):
                predicted = bool(grp['is_forecast'].any())
                # [E3-R6] name the value type in the heading itself:
                # "Raw Poverty Status Past 12 Months, 2022"
                head = [
                    html.Span(f"{'Normalized' if normalized else 'Raw'} "
                              f"{metric_label(metric)}, {year}",
                              style={'fontWeight': '700'}),
                    html.Span("  " + ("0–100" if normalized else "own units"),
                              className='mode-badge ' +
                                        ('mode-norm' if normalized
                                         else 'mode-raw'),
                              style={'marginLeft': '6px'}),
                ]
                if predicted:
                    head.append(html.Span("  PREDICTED",
                                          className='mode-badge mode-fc',
                                          style={'marginLeft': '4px'}))
                rows = []
                for _, r in grp.sort_values('municipality').iterrows():
                    rows.append(html.Div([
                        html.Span(r['municipality'],
                                  style={'fontWeight': '600'}),
                        html.Span([
                            html.Span(f"Raw {fmt_num(r['raw'])}",
                                      style={'color': BLUE,
                                             'fontWeight': '700'
                                             if not normalized else '400'}),
                            html.Span("  ·  "),
                            html.Span(
                                "Normalized " +
                                ('—' if r['normalized'] is None
                                 or not np.isfinite(r['normalized'])
                                 else f"{r['normalized']:.1f}"),
                                style={'color': PURPLE,
                                       'fontWeight': '700' if normalized
                                       else '400'}),
                        ]),
                    ], className='sum-row'))

                # [E3-R6, delivered early] summary stats across municipalities
                vals = grp[value_col].dropna()
                if len(vals) > 1:
                    stats = (f"Average {fmt_num(vals.mean())}  ·  "
                             f"Median {fmt_num(vals.median())}  ·  "
                             f"Min {fmt_num(vals.min())}  ·  "
                             f"Max {fmt_num(vals.max())}")
                    rows.append(html.Div(
                        [html.Span("Across the selected municipalities",
                                   style={'fontWeight': '600'}),
                         html.Span(stats)],
                        className='sum-row',
                        style={'borderTop': '1px solid #dde3ea',
                               'marginTop': '4px', 'paddingTop': '6px'}))
                    rows.append(html.Div(
                        f"computed on {'normalized' if normalized else 'raw'} "
                        f"values",
                        style={'fontSize': '10.5px', 'color': '#888',
                               'textAlign': 'right'}))

                cards.append(html.Div([html.Div(head,
                                                style={'marginBottom': '6px'}),
                                       *rows], className='sum-card'))

    # ----- [E2-R1] table: year, raw, normalized, status — always all four -----
    out = pd.DataFrame({
        'municipality': df['municipality'],
        'indicator': df['indicator'],
        'year': df['year'].astype(int),
        'raw_value': [round_raw(v) for v in df['raw']],
        'norm_value': [None if v is None or not np.isfinite(v)
                       else round(float(v), 1) for v in df['normalized']],
        'status': df['status'],
    })
    columns = [
        {'id': 'municipality', 'name': 'Municipality'},
        {'id': 'indicator', 'name': 'Indicator'},
        {'id': 'year', 'name': 'Year', 'type': 'numeric'},
        {'id': 'raw_value',
         'name': ('Raw value' if not normalized else 'Raw value'),
         'type': 'numeric'},
        {'id': 'norm_value', 'name': 'Normalized (0–100)', 'type': 'numeric'},
        {'id': 'status', 'name': 'Status'},
    ]
    plotted = 'Normalized (0–100)' if normalized else 'Raw value'
    table_banner = html.Span(
        [f"{len(out):,} rows · plots ", html.B(plotted)],
        title=("Every row carries the raw value, the normalized value and its "
               "Observed / Predicted status, whichever mode the chart is in. "
               "Sort or filter any column, or use Export for a CSV."))
    title_text = ("Data behind this chart — "
                  + ('normalized 0-100' if normalized else 'raw values'))

    return (title, fig, banner, out.to_dict('records'), columns, table_banner,
            "", title_text, cards, scale_style, scale_text, crumb_items,
            alert_style, alert_bits, raw_btn_style, fc_btn_style, export_name,
            dash_state)


# ----- one-click remedies offered by the alert and the scale helper -----
@app.callback(
    Output('data-mode', 'value'),
    [Input('alert-show-raw-btn', 'n_clicks'),
     Input('scale-normalize-btn', 'n_clicks')],
    prevent_initial_call=True
)
def quick_mode_change(raw_clicks, norm_clicks):
    trigger = dash.ctx.triggered_id
    if trigger == 'alert-show-raw-btn' and raw_clicks:
        return 'raw'
    if trigger == 'scale-normalize-btn' and norm_clicks:
        return 'norm'
    raise dash.exceptions.PreventUpdate


@app.callback(
    Output('forecast-toggle', 'value'),
    Input('alert-stop-forecast-btn', 'n_clicks'),
    prevent_initial_call=True
)
def quick_stop_forecast(n_clicks):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    return []


@app.callback(
    Output('chart-layout', 'value'),
    Input('scale-facet-btn', 'n_clicks'),
    prevent_initial_call=True
)
def quick_separate_axes(n_clicks):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    return 'facet'


# =========================================================
# EXPORTS  [E2-R4] / [E2-R5]
# =========================================================
# PNG straight from the live figure, so what is saved is what is on screen.
app.clientside_callback(
    """
    function(n_clicks, filename) {
        if (!n_clicks) { return window.dash_clientside.no_update; }
        try {
            var host = document.getElementById('factor-trend-graph');
            var gd = host ? host.querySelector('.js-plotly-plot') : null;
            if (gd && window.Plotly) {
                window.Plotly.downloadImage(gd, {
                    format: 'png', width: 1400, height: 800,
                    filename: filename || 'MHVI_graph'
                });
            }
        } catch (e) { console.log('[export-png] ' + e); }
        return window.dash_clientside.no_update;
    }
    """,
    Output('png-export-sink', 'data'),
    Input('export-png-btn', 'n_clicks'),
    State('export-name-store', 'data'),
)


@app.callback(
    Output('download-graph-csv', 'data'),
    Input('export-csv-btn', 'n_clicks'),
    [State('y-county-dropdown', 'value'),
     State('y-metric-dropdown', 'value'),
     State('data-mode', 'value'),
     State('forecast-toggle', 'value'),
     State('export-name-store', 'data')],
    prevent_initial_call=True
)
def export_graph_csv(n_clicks, counties_list, metrics, mode, forecast_opts,
                     export_name):
    """CSV of exactly what the chart is showing, with the settings recorded in
    a header block so the file cannot be misread later."""
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    counties_list = as_list(counties_list)
    metrics = as_list(metrics)
    if not counties_list or not metrics:
        raise dash.exceptions.PreventUpdate

    normalized = (mode == 'norm')
    do_forecast = 'forecast' in (forecast_opts or [])
    df = build_series(counties_list, metrics)
    if df.empty:
        raise dash.exceptions.PreventUpdate
    df = add_normalized(df)
    df = add_forecast(df) if do_forecast else df.assign(is_forecast=False)
    df = df.sort_values(['indicator', 'municipality', 'year'])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['# Puerto Rico MHVI dashboard export'])
    w.writerow(['# Exported', datetime.now().strftime('%Y-%m-%d %H:%M')])
    w.writerow(['# Municipalities',
                '; '.join(FIPS_TO_NAME.get(f, f) for f in counties_list)])
    w.writerow(['# Indicators',
                '; '.join(f'{metric_category_label(m)} > {metric_label(m)}'
                          for m in metrics)])
    w.writerow(['# Chart was displaying',
                'Normalized 0-100' if normalized else 'Raw values'])
    w.writerow(['# Future projection',
                'ON (4 years, Holt linear-trend exponential smoothing)'
                if do_forecast else 'OFF'])
    w.writerow(['# Normalization method',
                'min-max to 0-100 per indicator, shared across the selected '
                'municipalities and years'])
    w.writerow([])
    w.writerow(['Municipality', 'Category', 'Indicator', 'Year', 'Raw value',
                'Normalized (0-100)', 'Status'])
    for _, r in df.iterrows():
        w.writerow([
            r['municipality'],
            metric_category_label(r['metric']),
            metric_label(r['metric']),
            int(r['year']),
            '' if r['raw'] is None or not np.isfinite(r['raw'])
            else round_raw(r['raw']),
            '' if r['normalized'] is None or not np.isfinite(r['normalized'])
            else round(float(r['normalized']), 1),
            'Predicted' if r['is_forecast'] else 'Observed',
        ])
    return dcc.send_string(buf.getvalue(),
                           filename=f"{export_name or 'MHVI_export'}.csv")


# =========================================================
# TABLE EXPAND / COLLAPSE
# =========================================================
@app.callback(
    [Output('table-section', 'style'),
     Output('data-table', 'style_table'),
     Output('expand-table-btn', 'children')],
    Input('expand-table-btn', 'n_clicks'),
    State('table-section', 'style'),
)
def toggle_table_expand(n_clicks, current_style):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    expanded = bool(current_style) and current_style.get('position') == 'fixed'
    if expanded:
        return TABLE_STYLE_INLINE, DT_STYLE_INLINE, "⤢"
    return TABLE_STYLE_EXPANDED, DT_STYLE_EXPANDED, "⤡"


# =========================================================
# PANELS AND MODALS
# =========================================================
@app.callback(
    Output('left-menu-container', 'style'),
    Input('left-menu-btn', 'n_clicks'),
    State('left-menu-container', 'style')
)
def toggle_left_menu(n_clicks, current_style):
    if n_clicks is None:
        raise dash.exceptions.PreventUpdate
    open_style = {'flex': '2', 'padding': '20px', 'backgroundColor': '#f0f2f5',
                  'borderRight': '1px solid #ccc', 'fontFamily': 'Arial',
                  'height': '68vh', 'display': 'flex',
                  'flexDirection': 'column', 'minWidth': '0'}
    if current_style and current_style.get('display') == 'none':
        return open_style
    return {'display': 'none'}


@app.callback(
    Output('hierarchy-modal', 'style'),
    [Input('open-hierarchy-btn', 'n_clicks'),
     Input('open-panel-help-btn', 'n_clicks'),
     Input('close-hierarchy-btn', 'n_clicks')],
    State('hierarchy-modal', 'style')
)
def toggle_hierarchy_modal(open_clicks, panel_clicks, close_clicks, style):
    """The panel's "?" and the header's explainer open the same document —
    the hierarchy and the panel guide belong together."""
    style = dict(style or MODAL_WRAP)
    trigger = dash.ctx.triggered_id
    if trigger in ('open-hierarchy-btn', 'open-panel-help-btn'):
        style['display'] = 'flex'
    elif trigger == 'close-hierarchy-btn':
        style['display'] = 'none'
    return style


@app.callback(
    Output('help-modal', 'style'),
    [Input('open-help-btn', 'n_clicks'),
     Input('close-help-btn', 'n_clicks'),
     Input({'type': 'view-def-btn', 'index': ALL}, 'n_clicks')],
    State('help-modal', 'style')
)
def toggle_help_modal(open_clicks, close_clicks, view_clicks, style):
    style = dict(style or MODAL_WRAP)
    trigger = dash.ctx.triggered_id
    if trigger == 'close-help-btn':
        style['display'] = 'none'
    elif trigger == 'open-help-btn':
        style['display'] = 'flex'
    elif isinstance(trigger, dict) and trigger.get('type') == 'view-def-btn':
        if not any(c for c in (view_clicks or [])):
            raise dash.exceptions.PreventUpdate
        style['display'] = 'flex'
    return style


# [E2-R6] "View definition" jumps into the glossary with the search pre-filled
@app.callback(
    Output('dict-search', 'value'),
    Input({'type': 'view-def-btn', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def prefill_dict_search(view_clicks):
    trigger = dash.ctx.triggered_id
    if not isinstance(trigger, dict):
        raise dash.exceptions.PreventUpdate
    if not any(c for c in (view_clicks or [])):
        raise dash.exceptions.PreventUpdate
    raw = trigger.get('index') or ''
    friendly = DICT_FRIENDLY.get(raw) or pretty_indicator(raw)
    return friendly


# [E2-R6] search covers names AND definitions, independent of the category filter
@app.callback(
    [Output('dict-data-table', 'data'),
     Output('dict-result-count', 'children'),
     Output('dict-data-table', 'selected_rows')],
    [Input('dict-search', 'value'),
     Input('dict-category-filter', 'value')],
)
def filter_dictionary(search, category_filter):
    rows = data_dictionary_records
    if category_filter and category_filter != 'All':
        rows = [r for r in rows
                if (r.get('category') or '').strip() == category_filter]
    term = (search or '').strip().lower()
    if term:
        words = [w for w in term.split() if w]

        def matches(rec):
            hay = ' '.join(str(rec.get(k, '')) for k in
                           ('friendly_name', 'raw_name', 'description',
                            'category', 'units', 'source')).lower()
            return all(w in hay for w in words)

        rows = [r for r in rows if matches(r)]

    if term and not rows:
        msg = (f"No glossary entry matches “{search}”. The glossary does not "
               f"yet cover every indicator in the dashboard.")
    elif term:
        msg = (f"{len(rows):,} of {len(data_dictionary_records):,} entries match "
               f"“{search}”. Select a row to read the full definition.")
    else:
        msg = (f"{len(rows):,} entries. Type above to search names and "
               f"definitions, or select a row to read the full definition.")
    return rows, msg, []


# [E2-R6] expandable definition card with a copy button
@app.callback(
    [Output('dict-detail-card', 'children'),
     Output('dict-copy-store', 'data'),
     Output('dict-copy-btn', 'style'),
     Output('dict-copy-toast', 'children')],
    [Input('dict-data-table', 'selected_rows')],
    State('dict-data-table', 'data'),
)
def show_dict_detail(selected_rows, rows):
    hidden = {**small_btn, 'display': 'none'}
    shown = {**small_btn, 'display': 'inline-block'}
    if not selected_rows or not rows:
        return None, '', hidden, ''
    idx = selected_rows[0]
    if idx >= len(rows):
        return None, '', hidden, ''
    r = rows[idx]
    name = r.get('friendly_name') or r.get('raw_name') or '—'
    desc = (r.get('description') or '').strip() or \
        'No description on file for this indicator yet.'
    copy_text = (f"{name}\nCategory: {r.get('category') or '—'}\n"
                 f"Units: {r.get('units') or '—'}\n"
                 f"Source: {r.get('source') or '—'}\n\n{desc}")
    card = html.Div([
        html.H3(name, style={'margin': '0 0 6px 0', 'fontSize': '18px'}),
        html.Div([
            html.Span(f"Category: {r.get('category') or '—'}",
                      style={'marginRight': '16px'}),
            html.Span(f"Units: {r.get('units') or '—'}",
                      style={'marginRight': '16px'}),
            html.Span(f"Source: {r.get('source') or '—'}"),
        ], style={'fontSize': '12px', 'color': '#666',
                  'margin': '0 0 10px 0'}),
        html.P(desc, style={'fontSize': '14px', 'lineHeight': '1.5',
                            'margin': '0', 'whiteSpace': 'pre-wrap'}),
        html.Div(f"Database name: {r.get('raw_name') or '—'}",
                 style={'fontSize': '11px', 'color': '#999',
                        'marginTop': '10px'}),
    ], style={'border': f'2px solid {BLUE}', 'borderRadius': '8px',
              'padding': '16px', 'backgroundColor': '#fbfcfe'})
    return card, copy_text, shown, ''


app.clientside_callback(
    """
    function(n_clicks, text) {
        if (!n_clicks || !text) { return ''; }
        try {
            if (navigator.clipboard) { navigator.clipboard.writeText(text); }
            else {
                var ta = document.createElement('textarea');
                ta.value = text; document.body.appendChild(ta);
                ta.select(); document.execCommand('copy');
                document.body.removeChild(ta);
            }
            return 'Definition copied to the clipboard.';
        } catch (e) { return 'Could not copy — select the text manually.'; }
    }
    """,
    Output('dict-copy-toast', 'children', allow_duplicate=True),
    Input('dict-copy-btn', 'n_clicks'),
    State('dict-copy-store', 'data'),
    prevent_initial_call=True
)


# =========================================================
# REPORT BUILDER
# =========================================================
def _report_element(idx, counties_val, cat_val, ind_val, opts_val):
    ind_options = [{'label': NO_INDICATOR_LABEL, 'value': NO_INDICATOR_VALUE}] \
        if cat_val == OVERALL else \
        [{'label': pretty_indicator(i), 'value': i}
         for i in db_metadata.get(cat_val, [])]
    return html.Div(
        id={'type': 'report-block', 'index': idx},
        className='print-page-break',
        style={'border': '1px solid #ddd', 'padding': '15px',
               'marginBottom': '15px', 'borderRadius': '5px'},
        children=[
            html.Div(className='no-print', children=[
                html.Label("Element Type:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id={'type': 'report-type', 'index': idx},
                    options=[{'label': 'Line Graph', 'value': 'Graph'},
                             {'label': 'Data Table', 'value': 'Table'}],
                    value='Graph', clearable=False,
                    style={'marginBottom': '10px'}),
                html.Label("Municipalities:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id={'type': 'report-county', 'index': idx},
                    options=[{'label': c['name'], 'value': c['fips_code']}
                             for c in all_counties],
                    value=counties_val, multi=True,
                    placeholder="Search municipalities…",
                    style={'marginBottom': '10px'}),
                html.Label("Category:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id={'type': 'report-cat', 'index': idx},
                    options=[{'label': pretty_category(c), 'value': c}
                             for c in global_categories],
                    value=cat_val, clearable=False,
                    style={'marginBottom': '10px'}),
                html.Label("Indicator:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id={'type': 'report-ind', 'index': idx},
                    options=ind_options, value=ind_val, clearable=False,
                    style={'marginBottom': '10px'}),
                dcc.Checklist(
                    id={'type': 'report-options', 'index': idx},
                    options=[{'label': ' Normalized 0–100', 'value': 'normalize'},
                             {'label': ' Include projection', 'value': 'forecast'}],
                    value=opts_val,
                    style={'fontSize': '13px', 'marginBottom': '10px'}),
                html.Button("✖ Remove Element",
                            id={'type': 'remove-element-btn', 'index': idx},
                            style={'backgroundColor': '#ff4d4d',
                                   'color': 'white', 'border': 'none',
                                   'padding': '5px 10px', 'borderRadius': '4px',
                                   'cursor': 'pointer', 'marginTop': '10px'}),
                html.Hr()
            ]),
            html.Div(id={'type': 'report-output', 'index': idx})
        ]
    )


@app.callback(
    [Output('report-elements-container', 'children'),
     Output('add-report-toast', 'children')],
    [Input('add-report-element-btn', 'n_clicks'),
     Input('add-to-custom-report-btn', 'n_clicks')],
    [State('report-elements-container', 'children'),
     State('y-county-dropdown', 'value'),
     State('y-metric-dropdown', 'value'),
     State('data-mode', 'value'),
     State('forecast-toggle', 'value')],
    prevent_initial_call=True
)
def handle_report_buttons(add_empty_clicks, add_custom_clicks, children,
                          right_counties, right_metrics, mode, forecast_opts):
    """[E2-R5] The study found the report builder opening with stale or default
    settings. One element is now created per selected indicator, each carrying
    the municipalities, display mode and projection state that were live."""
    trigger_id = dash.ctx.triggered_id
    if not trigger_id:
        raise dash.exceptions.PreventUpdate

    children = list(children or [])
    base_idx = (add_empty_clicks or 0) * 100 + (add_custom_clicks or 0) * 7 + 1000

    if trigger_id == 'add-report-element-btn':
        children.append(_report_element(base_idx, [], OVERALL,
                                        NO_INDICATOR_VALUE, []))
        return children, ""

    counties_val = as_list(right_counties)
    metrics = as_list(right_metrics)
    if not counties_val or not metrics:
        return children, ("Select a municipality and at least one indicator "
                          "first.")
    opts_val = (['normalize'] if mode == 'norm' else []) + \
               (['forecast'] if 'forecast' in (forecast_opts or []) else [])

    for offset, metric in enumerate(metrics):
        cat_val, ind_val = parse_metric(metric)
        if cat_val == OVERALL:
            ind_val = NO_INDICATOR_VALUE
        children.append(_report_element(base_idx + offset, counties_val,
                                        cat_val, ind_val, opts_val))

    mode_txt = 'normalized 0–100' if mode == 'norm' else 'raw values'
    n = len(metrics)
    return children, (f"Added {n} element{'s' if n > 1 else ''} to Custom "
                      f"Reports, using {mode_txt}"
                      f"{' with projection' if 'forecast' in (forecast_opts or []) else ''}"
                      f". Open it from the ☰ menu.")


@app.callback(
    Output('custom-reports-modal', 'style'),
    [Input('open-reports-btn', 'n_clicks'), Input('close-modal-btn', 'n_clicks')],
    State('custom-reports-modal', 'style'),
    prevent_initial_call=True
)
def toggle_reports_modal(open_clicks, close_clicks, style):
    style = dict(style or MODAL_WRAP)
    trigger = dash.ctx.triggered_id
    if trigger == 'open-reports-btn':
        style['display'] = 'flex'
    elif trigger == 'close-modal-btn':
        style['display'] = 'none'
    return style


@app.callback(
    Output({'type': 'report-block', 'index': MATCH}, 'style'),
    Input({'type': 'remove-element-btn', 'index': MATCH}, 'n_clicks'),
    State({'type': 'report-block', 'index': MATCH}, 'style')
)
def remove_element(n_clicks, style):
    style = dict(style or {})
    if n_clicks:
        style['display'] = 'none'
    return style


@app.callback(
    [Output({'type': 'report-ind', 'index': MATCH}, 'options'),
     Output({'type': 'report-ind', 'index': MATCH}, 'value'),
     Output({'type': 'report-ind', 'index': MATCH}, 'disabled')],
    Input({'type': 'report-cat', 'index': MATCH}, 'value'),
    State({'type': 'report-ind', 'index': MATCH}, 'value'),
)
def update_report_indicator(cat, current_ind):
    # [E1-O1] no bare "N/A"; and keep the incoming indicator if it is valid,
    # which is what used to clobber the handed-over selection.
    if cat in (NO_INDICATOR_VALUE, OVERALL):
        return ([{'label': NO_INDICATOR_LABEL, 'value': NO_INDICATOR_VALUE}],
                NO_INDICATOR_VALUE, True)
    indicators = db_metadata.get(cat, [])
    options = [{'label': pretty_indicator(i), 'value': i} for i in indicators]
    if current_ind in indicators:
        return options, current_ind, False
    return options, (indicators[0] if indicators else NO_INDICATOR_VALUE), False


@app.callback(
    Output({'type': 'report-output', 'index': MATCH}, 'children'),
    [Input({'type': 'report-type', 'index': MATCH}, 'value'),
     Input({'type': 'report-county', 'index': MATCH}, 'value'),
     Input({'type': 'report-cat', 'index': MATCH}, 'value'),
     Input({'type': 'report-ind', 'index': MATCH}, 'value'),
     Input({'type': 'report-options', 'index': MATCH}, 'value')]
)
def render_report_element(rtype, counties_list, cat, ind, options):
    counties_list = as_list(counties_list)
    if not counties_list:
        return html.P("Select at least one municipality for this element.",
                      style={'fontStyle': 'italic', 'color': '#666'})

    options = options or []
    do_normalize = 'normalize' in options
    do_forecast = 'forecast' in options

    metric = make_metric(cat, ind)
    df = build_series(counties_list, [metric])
    if df.empty:
        return html.P("No data available for the selected parameters.")

    df = add_normalized(df)
    value_col = 'normalized' if do_normalize else 'raw'
    df = add_forecast(df) if do_forecast else df.assign(is_forecast=False)
    df = df.sort_values(['municipality', 'year'])

    label = OVERALL if cat == OVERALL else pretty_indicator(ind)
    mode_txt = "normalized 0–100" if do_normalize else "raw values"
    df['series'] = np.where(df['is_forecast'],
                            df['municipality'] + ' (Forecast)',
                            df['municipality'])

    if rtype == 'Graph':
        fig = px.line(df, x='year', y=value_col, color='series', markers=True,
                      title=f"{label} — {mode_txt}")
        color_map = {t.name: t.line.color for t in fig.data
                     if ' (Forecast)' not in t.name}
        for t in fig.data:
            if ' (Forecast)' in t.name:
                t.line.dash = 'dash'
                base = t.name.replace(' (Forecast)', '')
                if base in color_map:
                    t.line.color = color_map[base]
                t.showlegend = False
        try:
            fig.update_layout(
                xaxis=dict(title="Year", type='category',
                           categoryorder='category ascending'),
                yaxis=dict(title='Normalized value (0–100)' if do_normalize
                           else 'Value (original units)'),
                paper_bgcolor='white', plot_bgcolor='white')
        except Exception:
            pass
        return dcc.Graph(figure=fig, config={'displayModeBar': False})

    pivot = df.pivot_table(index='year', columns='series', values=value_col,
                           aggfunc='first').reset_index()
    for c in pivot.columns:
        if c != 'year':
            pivot[c] = pivot[c].map(round_raw)
    return html.Div([
        html.H3(f"Data Table: {label} — {mode_txt}"),
        dash_table.DataTable(
            data=pivot.to_dict('records'),
            columns=[{'id': str(c), 'name': str(c)} for c in pivot.columns],
            style_cell={'textAlign': 'center', 'padding': '5px'},
            style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f2f5'})
    ])


app.clientside_callback(
    """
    function(n_clicks) {
        if(n_clicks > 0) { window.print(); }
        return window.dash_clientside.no_update;
    }
    """,
    Output('print-sink', 'data'),
    Input("export-pdf-btn", "n_clicks")
)




# =========================================================
# ASSISTANT → DASHBOARD
# =========================================================
# [E3-R3] "View these values in the graph" — put the answer on the dashboard
@app.callback(
    [Output('y-county-dropdown', 'value', allow_duplicate=True),
     Output('y-metric-dropdown', 'value', allow_duplicate=True),
     Output('year-selector', 'value', allow_duplicate=True),
     Output('data-mode', 'value', allow_duplicate=True),
     Output('selection-mode', 'value', allow_duplicate=True),
     Output('side-panel-container', 'style', allow_duplicate=True)],
    Input({'type': 'chat-apply-btn', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def apply_chat_answer_to_dashboard(clicks):
    trigger = dash.ctx.triggered_id
    if not isinstance(trigger, dict) or not any(c for c in (clicks or [])):
        raise dash.exceptions.PreventUpdate
    try:
        payload = json.loads(trigger.get('index') or '{}')
    except Exception:
        raise dash.exceptions.PreventUpdate
    fips = [f for f in (payload.get('fips') or []) if f]
    metrics = [m for m in (payload.get('metrics') or []) if m]
    if not fips or not metrics:
        raise dash.exceptions.PreventUpdate
    mode = 'compare' if len(fips) > 1 else 'single'
    return (_county_value(fips, mode), metrics, payload.get('year'),
            payload.get('mode') or 'raw', mode, PANEL_OPEN_STYLE)
