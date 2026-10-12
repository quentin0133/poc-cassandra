import time
import dash
from dash import html, dcc, dash_table, Input, Output, ctx
import pandas as pd
from cassandra.cluster import Cluster
import plotly.express as px

cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('football')

events_stmt = session.prepare("""
    SELECT time, event_team, player, text, is_goal
    FROM events
    WHERE id_odsp = ?
""")

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

app.layout = html.Div(style={'fontFamily': 'sans-serif', 'maxWidth': '1100px', 'margin': 'auto', 'padding': '20px'}, children=[
    html.Div(
        id="bench-metric",
        style={
            'display': 'inline-block',
            'padding': '10px 18px',
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #ced4da',
            'borderRadius': '6px',
            'fontWeight': 'bold',
            'marginBottom': '20px',
            'color': '#495057'
        },
        children="Temps d'exécution : initialisation..."
    ),
    
    dcc.Tabs(id="tabs-menu", value="tab-dashboard", children=[
        dcc.Tab(label="Dashboard", value="tab-dashboard"),
        dcc.Tab(label="Événements par match", value="tab-match")
    ]),
    
    html.Div(id="view-dashboard", style={'paddingTop': '20px'}, children=[
        html.H2("Vue globale"),
        html.Div(id="dashboard-content")
    ]),
    
    html.Div(id="view-match", style={'paddingTop': '20px', 'display': 'none'}, children=[
        html.Label("Sélectionnez un match :", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id='match-selector',
            options=[],
            value=None,
            clearable=False,
            style={'marginBottom': '20px'}
        ),
        html.H3("Chronologie des événements"),
        html.Div(id='events-container')
    ])
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
        if not dropdown_options:
            opts = load_matches()
            id_odsp = opts[0]['value'] if opts else None
            match_content, metric_text = update_match(id_odsp)
            return style_dash, style_match, dash.no_update, match_content, metric_text, opts, id_odsp

        id_odsp = selected_id_odsp or dropdown_options[0]['value']
        match_content, metric_text = update_match(id_odsp)
        return style_dash, style_match, dash.no_update, match_content, metric_text, dash.no_update, dash.no_update
    
    return style_dash, style_match, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    

def update_dashboard():
    graphic_functions = [get_top_10_player, get_goal_by_position]
    total_query_time = 0
    
    dashboard_layout = html.Div(
        style={
            'display': 'grid',
            'gridTemplateColumns': '1fr 1fr',
            'gap': '20px',
            'alignItems': 'start'
        },
        children=[]
    )
    
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
    
    component = html.Div(children=[
        dcc.Graph(figure=fig)
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
    
    component = html.Div(children=[
        html.H3("Top 10 des joueurs"),
        dash_table.DataTable(
            data=top_10.to_dict('records'),
            columns=[
                {"name": "Joueur", "id": "player"},
                {"name": "Total Buts", "id": "total_goals"}
            ],
            style_header={'backgroundColor': '#f2f2f2', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'left', 'padding': '8px'}
        )
    ])
    
    return component, query_time

def update_match(selected_id_odsp):
    if not selected_id_odsp:
        return html.P("Veuillez sélectionner un match."), "Temps d'exécution : -- ms"

    start_time = time.perf_counter()
    rows = session.execute(events_stmt, [selected_id_odsp])
    query_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

    df_events = pd.DataFrame(list(rows))

    metric_text = f"Temps d'exécution : {round(query_time_ms, 2)} ms"

    if df_events.empty:
        return html.P("Aucun événement pour ce match."), metric_text

    df_events['is_goal'] = df_events['is_goal'].apply(lambda x: "⚽ BUT !" if x == 1 else "")
    df_events.rename(columns={
        'time': 'Minute',
        'event_team': 'Équipe',
        'player': 'Joueur',
        'text': 'Description',
        'is_goal': 'But'
    }, inplace=True)

    table = dash_table.DataTable(
        data=df_events.to_dict('records'),
        columns=[{"name": col, "id": col} for col in df_events.columns],
        page_size=15,
        style_table={'overflowX': 'auto'}
    )

    return table, metric_text
    
if __name__ == '__main__':
    app.run(debug=True)