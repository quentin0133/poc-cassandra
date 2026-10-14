import time
from datetime import timezone
import dash
from dash import html, dcc, dash_table, Input, Output, State, ctx
import pandas as pd
from cassandra.cluster import Cluster
import plotly.express as px

from timeline import render_timeline, tableau_score

cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('football')

events_stmt = session.prepare("""
    SELECT time, event_type, side, player, player_in, player_out, text, is_goal
    FROM events
    WHERE id_odsp = ?
""")

LIVE_ID = "LIVE-CzPV312a/"
SECONDES_PAR_MINUTE = 2

LOCATION_MAP = {
    1: "Moitié d'attaque", 2: "Moitié défensive", 3: "Centre de la surface",
    4: "Aile gauche", 5: "Aile droite", 6: "Angle fermé / long",
    7: "Angle fermé (gauche)", 8: "Angle fermé (droite)", 9: "Côté gauche de la surface de réparation",
    10: "Côté gauche de la surface de but", 11: "Côté droit de la surface de réparation", 12: "Côté gauche de la surface de but",
    13: "Près du but", 14: "Point de pénality", 15: "Hors de la surface",
    16: "Longue distance", 17: "+35 yards", 18: "+40 yards", 19: "Inconnu"
}

dropdown_options = []

def load_matches():
    """Load matches from Cassandra only the first time the tab is opened."""
    global dropdown_options
    if not dropdown_options:
        rows = session.execute("""
            SELECT id_odsp, match_date, ht, at, fthg, ftag
            FROM matches
            LIMIT 100                        
        """)
        df_matches = pd.DataFrame(list(rows))
        dropdown_options = [
            {
                'label': f"{row['match_date']} : {row['ht']} {row['fthg']} - {row['ftag']} {row['at']}",
                'value': row['id_odsp']
            }
            for _, row in df_matches.iterrows()
        ]
    return dropdown_options

app = dash.Dash(__name__)

app.layout = html.Div(className="page", children=[
    html.H1("MatchLive", className="app-title"),
    html.Div(
        html.Div(id="bench-metric", className="metric",
        children="Temps d'exécution : initialisation..."),
    ),
    
    dcc.Tabs(id="tabs-menu", value="tab-dashboard", className="tabs", children=[
        dcc.Tab(label="Dashboard", value="tab-dashboard",
                className="tab", selected_className="tab-selected"),
        dcc.Tab(label="Événements par match", value="tab-match",
                className="tab", selected_className="tab-selected"),
        dcc.Tab(label="Direct", value="tab-live",
                className="tab", selected_className="tab-selected", children=[
            html.Div(className="card", style={'marginTop': '20px'}, children=[
                html.Div(className="sb-head", children=html.Div(
                    id="live-badge", className="sb-live", style={'display': 'none'},
                    children=[html.Span(className="sb-dot"), html.Span(id="live-clock")])),
                html.Div(id="live-container"),
            ]),
            dcc.Store(id="live-start"),
            dcc.Interval(id="refresh", interval=2000),
            dcc.Interval(id="clock-tick", interval=1000),
        ]),
    ]),
    
    html.Div(id="view-dashboard", style={'paddingTop': '20px'}, children=[
        html.Div(id="dashboard-content")
    ]),
    
    html.Div(id="view-match", style={'display': 'none'}, children=[
        html.Div(className="card", style={'marginTop': '20px'}, children=[
            dcc.Dropdown(id='match-selector', options=[], value=None, clearable=False),
        ]),
        html.Div(className="card", children=[
            html.H3("Événements", className="card-title"),
            html.Div(id='events-container'),
        ]),
    ]),
])

@app.callback(
    [
        Output("view-dashboard", "style"),
        Output("view-match", "style"),
        Output("dashboard-content", "children"),
        Output("events-container", "children"),
        Output("bench-metric", "children"),
        Output("match-selector", "options"),
        Output("match-selector", "value")
    ],
    [
        Input("tabs-menu", "value"),
        Input("match-selector", "value")
    ]
)
def switch_tabs(active_tab, selected_id_odsp):
    trigger = ctx.triggered_id
    
    style_dash = {'paddingTop': '20px', 'display': 'block' if active_tab == "tab-dashboard" else 'none'}
    style_match = {'paddingTop': '20px', 'display': 'block' if active_tab == "tab-match" else 'none'}

    if active_tab == "tab-dashboard" and trigger != "match-selector":
        dash_content, metric_text = update_dashboard()
        return style_dash, style_match, dash_content, dash.no_update, metric_text, dash.no_update, dash.no_update
    
    if active_tab == "tab-match":
        opts = load_matches()
        id_odsp = selected_id_odsp or opts[0]['value']
        match_content, metric_text = update_match(id_odsp)
        return style_dash, style_match, dash.no_update, match_content, metric_text, opts, id_odsp
    
    return style_dash, style_match, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    

def update_dashboard():
    graphic_functions = [get_top_10_player, get_goal_by_position]
    total_query_time = 0
    
    dashboard_layout = html.Div(className="dashboard-grid", children=[])
    
    for graphic_function in graphic_functions:
        (comp, query_time) = graphic_function()
        total_query_time += query_time
        dashboard_layout.children = dashboard_layout.children + [comp]

    metric_text = f"Temps d'exécution : {round(total_query_time, 2)} ms"
    
    return dashboard_layout, metric_text

def get_goal_by_position():
    start_time = time.perf_counter()
    rows = session.execute("""
        SELECT location, count(*) as count 
        FROM goals_by_league 
        WHERE league = 'Ligue 1' 
        GROUP BY location
    """)
    df = pd.DataFrame(list(rows))
    query_time = round((time.perf_counter() - start_time) * 1000, 2)

    df['position'] = df['location'].map(LOCATION_MAP).fillna("Autre")
    
    total_goals = df['count'].sum()
    df['pct'] = (df['count'] / total_goals) * 100
    
    df_main = df[df['pct'] >= 3].copy().sort_values('count', ascending=False)
    df_sub = df[df['pct'] < 3].copy().sort_values('count', ascending=False)
    
    if not df_sub.empty:
        other_count = df_sub['count'].sum()

        df_other = pd.DataFrame([{
            'position': 'Autre',
            'count': other_count
        }])
        
        df_final = pd.concat([df_main, df_other], ignore_index=True)
    else:
        df_final = df_main

    fig = px.pie(
        df_final,
        names='position',
        values='count',
        title=f"Buts par Position",
        hole=0.4
    )
    fig.update_traces(textinfo='none', hovertemplate="<b>%{label}</b><br>Buts : %{value}<br>Part : %{percent}")

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_family="Barlow, sans-serif",
        title=None,
        margin=dict(t=10, b=10, l=10, r=10),
    )
    
    component = html.Div(className="card", children=[
        html.H3("Buts par position", className="card-title"),
        dcc.Graph(figure=fig, config={'displayModeBar': False}),
    ])
    
    return component, query_time

def get_top_10_player():
    start_time = time.perf_counter()
    rows = session.execute("""
        SELECT player, count(*) as total_goals 
        FROM goals_by_player 
        WHERE league = 'Ligue 1' 
        GROUP BY player
    """)
    df = pd.DataFrame(list(rows))
    query_time = round((time.perf_counter() - start_time) * 1000, 2)

    top_10 = df.nlargest(10, 'total_goals')
    
    top_10['player'] = top_10['player'].str.title()

    component = html.Div(className="card", children=[
        html.H3("Top 10 des buteurs", className="card-title"),
        dash_table.DataTable(
            data=top_10.to_dict('records'),
            columns=[
                {"name": "Joueur", "id": "player"},
                {"name": "Buts", "id": "total_goals"}
            ],
            style_as_list_view=True,
            style_header={'backgroundColor': '#1d1d1d', 'color': '#9a9a9a',
                          'fontWeight': '600', 'border': 'none',
                          'borderBottom': '1px solid #333333'},
            style_cell={'backgroundColor': '#1d1d1d', 'color': '#f5f5f5',
                        'fontFamily': 'Barlow, sans-serif', 'fontSize': '15px',
                        'textAlign': 'left', 'padding': '10px', 'border': 'none',
                        'borderBottom': '1px solid #333333'},
        )
    ])
    
    return component, query_time

def update_match(selected_id_odsp):
    if not selected_id_odsp:
        return html.P("Veuillez sélectionner un match."), "Temps d'exécution : -- ms"

    start_time = time.perf_counter()
    rows = list(session.execute(events_stmt, [selected_id_odsp]))
    query_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

    metric_text = f"Temps d'exécution : {query_time_ms} ms"
    return render_timeline(rows), metric_text

@app.callback(Output("live-container", "children"), Output("live-start", "data"),
              Input("refresh", "n_intervals"))
def afficher_direct(n_intervals):
    match = session.execute("SELECT ht, at, fthg, ftag, live_start FROM matches WHERE id_odsp = %s",
                            [LIVE_ID]).one()
    if match is None:
        return html.P("Aucun match en direct. Lance replay.py.", className="tl-empty"), None

    rows = list(session.execute(events_stmt, [LIVE_ID]))
    debut = match.live_start.replace(tzinfo=timezone.utc).timestamp() * 1000 if match.live_start else None
    return [tableau_score(match), render_timeline(rows)], {"start": debut, "spm": SECONDES_PAR_MINUTE}

app.clientside_callback(
    """
    function(n, live) {
        if (!live) { return ["", {display: "none"}]; }
        if (!live.start) { return ["En direct", {}]; }
        const m = Math.floor((Date.now() - live.start) / 1000 / live.spm);
        return ["En direct · " + (m > 90 ? "90'+" : Math.max(0, m) + "'"), {}];
    }
    """,
    Output("live-clock", "children"),
    Output("live-badge", "style"),
    Input("clock-tick", "n_intervals"),
    State("live-start", "data"),
)
    
if __name__ == '__main__':
    app.run(debug=True)