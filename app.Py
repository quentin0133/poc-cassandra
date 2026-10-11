import dash
from dash import html, dcc, dash_table, Input, Output
import pandas as pd
from cassandra.cluster import Cluster

cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('football')

events_stmt = session.prepare("""
    SELECT time, event_team, player, text, is_goal
    FROM events
    WHERE id_odsp = ?
""")

matches_rows = session.execute("""
    SELECT id_odsp, match_date, ht, at, fthg, ftag
    FROM matches
    LIMIT 100                         
""")
df_matches = pd.DataFrame(list(matches_rows))

dropdown_options = [
    {
        'label': f"{row['match_date']} : {row['ht']} {row['fthg']} - {row['ftag']} {row['at']}",
        'value': row['id_odsp']
    }
    for _, row in df_matches.iterrows()
]

app = dash.Dash(__name__)

app.layout = html.Div(style={'fontFamily': 'sans-serif', 'padding': '20px', 'maxWidth': '1000px', 'margin': 'auto'}, children=[
    html.H2("Explorateur de Matchs & Événements Cassandra"),
    
    html.Label("Sélectionnez un match :", style={'fontWeight': 'bold'}),
    dcc.Dropdown(
        id='match-selector',
        options=dropdown_options,
        value=dropdown_options[0]['value'] if dropdown_options else None,
        clearable=False,
        style={'marginBottom': '20px'}
    ),

    html.H3("Chronologie des événements du match"),
    html.Div(id='events-container')
])

@app.callback(
    Output('events-container', 'children'),
    Input('match-selector', 'value')
)
def update_events(selected_id_odsp):
    if not selected_id_odsp:
        return html.P("Veuillez sélectionner un match.")
    
    rows = session.execute(events_stmt, [selected_id_odsp])
    df_events = pd.DataFrame(list(rows))
    
    if df_events.empty:
        return html.P("Aucun événement enregistré pour ce match.")
    
    df_events['is_goal'] = df_events['is_goal'].apply(lambda x: "⚽ BUT !" if x == 1 else "")
    
    df_events.rename(columns={
        'time': 'Minute',
        'event_team': 'Équipe',
        'player': 'Joueur',
        'text': 'Description',
        'is_goal': 'But'
    }, inplace=True)
    
    return dash_table.DataTable(
        data=df_events.to_dict('records'),
        columns=[{"name": col, "id": col} for col in df_events.columns],
        page_size=15,
        style_table={'overflowX': 'auto'},
        style_header={'backgroundColor': '#f2f2f2', 'fontWeight': 'bold'},
        style_cell={'textAlign': 'left', 'padding': '8px'},
        style_data_conditional=[
            {
                'if': {'filter_query': '{But} = "⚽ BUT !"'},
                'backgroundColor': '#d4edda',
                'fontWeight': 'bold'
            }
        ]
    )
    
if __name__ == '__main__':
    app.run(debug=True)