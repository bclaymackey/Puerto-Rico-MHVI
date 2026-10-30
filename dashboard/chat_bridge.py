"""How the dashboard's grounded answers reach the AI assistant.

The AI-CHATBOT branch owns the assistant window (callbacks.py) and the routing
of every message (chat/ai_service.py). This module gives that routing one
extra first step, registered at startup with
``chat.register_dashboard_answerer(answer_question)``:

  1. "export this conversation"  -> the assistant downloads the chat PDF
                                    instead of trying to build a report [E3-O5]
  2. a value / statistic question -> answered from the dashboard's own data,
                                    with the rows it used shown underneath
                                    [E3-R1, E3-R2, E3-R3]
  3. anything else                -> None, and the partner's flow runs unchanged

It needs no database connection and no AI key, so these answers keep working
when MongoDB or OpenAI cannot be reached.
"""
from .core import *  # noqa: F401,F403  (constants, helpers, styles)


def answer_question(question, language='en', dashboard_state=None):
    """Hook called by chat.ai_service.process_chat_message before its own
    routing. Returns a dict, or None to let the normal flow handle it."""
    if dctx.is_export_chat_request(question or ''):
        return {'kind': 'export_chat'}
    state = dict(dashboard_state or {})
    if not state.get('year'):
        # Nothing in focus on the dashboard: use the year the map shows, so the
        # assistant and the map agree (the same rule chat/ uses for "latest").
        state['year'] = common_map_year()
    try:
        result = dctx.answer(question, state, DCTX_CATALOG,
                             series_for_assistant, language or 'en')
    except Exception as e:  # never let this step break the assistant
        print(f"[dashboard answer] {e}")
        return None
    if not result:
        return None
    result = dict(result)
    result['kind'] = 'grounded'
    result['transcript'] = _grounded_transcript_text(result)
    return result


def grounded_bubble(result, language):
    """[E3-R3] An answer that shows the rows it was computed from.

    The study found users could not tell whether a number came from the
    dashboard's data, from earlier conversation, or from nowhere. A grounded
    answer is stamped, lists its own evidence, and offers to put those exact
    values on the chart.
    """
    rows = result.get('rows') or []
    mode = result.get('mode', 'raw')
    value_col = 'normalized' if mode == 'norm' else 'raw'
    chip_text = ('✓ Leído de los datos del panel' if language == 'es'
                 else '✓ Read from dashboard data')

    body = [
        html.Div(chip_text,
                 style={'fontSize': '10.5px', 'fontWeight': '700',
                        'color': '#1d7a4c', 'background': '#e8f6ed',
                        'border': '1px solid #bfe3cd', 'borderRadius': '10px',
                        'padding': '1px 7px', 'display': 'inline-block',
                        'marginBottom': '6px'}),
        html.Div(result.get('text', ''), style={'marginBottom': '6px'}),
    ]

    if rows:
        header = ['Municipality', 'Year',
                  'Normalized' if mode == 'norm' else 'Raw']
        if language == 'es':
            header = ['Municipio', 'Año',
                      'Normalizado' if mode == 'norm' else 'Crudo']
        cells = [html.Tr([html.Th(h, style={'textAlign': 'left',
                                            'padding': '2px 6px',
                                            'borderBottom': '1px solid #ddd'})
                          for h in header])]
        for r in rows:
            label = r['municipality']
            if len({x['indicator'] for x in rows}) > 1:
                label = f"{r['municipality']} · {r['indicator']}"
            val = fmt_num(r.get(value_col))
            if r.get('predicted'):
                val += ' ⚠'
            cells.append(html.Tr([
                html.Td(label, style={'padding': '2px 6px'}),
                html.Td(r['year'], style={'padding': '2px 6px'}),
                html.Td(val, style={'padding': '2px 6px',
                                    'fontWeight': '600'}),
            ]))
        body.append(html.Table(cells, style={'fontSize': '11.5px',
                                             'borderCollapse': 'collapse',
                                             'marginBottom': '6px',
                                             'width': '100%'}))

    if result.get('method_note'):
        body.append(html.Div(result['method_note'],
                             style={'fontSize': '10.5px', 'color': '#777',
                                    'marginBottom': '6px'}))

    # [E3-R3] the two links the document asked for
    actions = []
    if rows:
        payload = json.dumps({'fips': result.get('fips') or [],
                              'metrics': result.get('metrics') or [],
                              'year': result.get('year'),
                              'mode': mode})
        actions.append(html.Button(
            'Ver en la gráfica' if language == 'es'
            else 'View these values in the graph',
            id={'type': 'chat-apply-btn', 'index': payload}, n_clicks=0,
            style={'fontSize': '11px', 'padding': '4px 8px',
                   'border': f'1px solid {PURPLE}', 'borderRadius': '6px',
                   'background': PURPLE, 'color': 'white',
                   'cursor': 'pointer', 'marginRight': '4px'}))
        first_metric = (result.get('metrics') or [None])[0]
        raw_name = METRIC_RAWNAME.get(first_metric)
        if raw_name:
            actions.append(html.Button(
                'Ver definición' if language == 'es'
                else 'Open indicator definition',
                id={'type': 'view-def-btn', 'index': raw_name}, n_clicks=0,
                style={'fontSize': '11px', 'padding': '4px 8px',
                       'border': f'1px solid {PURPLE}', 'borderRadius': '6px',
                       'background': 'white', 'color': PURPLE,
                       'cursor': 'pointer'}))
    if actions:
        body.append(html.Div(actions, style={'display': 'flex',
                                             'flexWrap': 'wrap', 'gap': '4px'}))

    return html.Div(
        html.Div(body, style={'backgroundColor': '#f0f7f2', 'color': '#222',
                              'padding': '9px 12px',
                              'border': '1px solid #cfe6d9',
                              'borderRadius': '16px 16px 16px 4px',
                              'maxWidth': '95%', 'wordWrap': 'break-word'}),
        style={'display': 'flex', 'justifyContent': 'flex-start',
               'marginBottom': '6px'}
    )


def _grounded_transcript_text(result):
    """Plain-text form of a grounded answer, for history and the PDF export."""
    lines = [result.get('text', '')]
    mode = result.get('mode', 'raw')
    col = 'normalized' if mode == 'norm' else 'raw'
    for r in result.get('rows') or []:
        lines.append(f"  - {r['municipality']} · {r['indicator']} · "
                     f"{r['year']}: {fmt_num(r.get(col))}"
                     f"{' (predicted)' if r.get('predicted') else ''}")
    if result.get('method_note'):
        lines.append(result['method_note'])
    return "\n".join(lines)
