import pandas as pd
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args

def to_str(val):
    return None if pd.isna(val) else str(val)

def to_float(val):
    return None if pd.isna(val) else float(val)

def to_int(val, default=0):
    return default if pd.isna(val) else int(val)

cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect()

# Reset keyspace (data base)
session.execute("DROP KEYSPACE IF EXISTS football")

session.execute("""
    CREATE KEYSPACE football
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3};
""")
session.set_keyspace('football')

# Create tables
tables = [
    """
    CREATE TABLE matches (
        id_odsp text PRIMARY KEY,
        adv_stats boolean,
        match_date text,
        league text,
        season text,
        country text,
        ht text,
        at text,
        fthg int,
        ftag int,
        live_start timestamp
    );
    """,
    """
    CREATE TABLE events (
        id_odsp text,
        id_event text,
        sort_order int,
        time int,
        text text,
        event_type int,
        event_type2 double,
        side int,
        event_team text,
        opponent text,
        player text,
        player2 text,
        player_in text,
        player_out text,
        shot_place double,
        shot_outcome double,
        is_goal int,
        location double,
        bodypart double,
        assist_method int,
        situation double,
        fast_break int,
        PRIMARY KEY ((id_odsp), sort_order, id_event)
    ) WITH CLUSTERING ORDER BY (sort_order ASC);
    """,
    """
    CREATE TABLE goals_by_league (
        league text,
        location int,
        id_event text,
        id_odsp text,
        player text,
        minute int,
        PRIMARY KEY ((league), location, id_event)
    );
    """,
    """
    CREATE TABLE goals_by_player (
        league text,
        player text,
        id_event text,
        team text,
        minute int,
        PRIMARY KEY ((league), player, id_event)
    );
    """
]

for stmt in tables:
    session.execute(stmt)

df_events = pd.read_csv("data/events.csv")
df_ginf = pd.read_csv("data/ginf.csv")

# Cleaning
df_ginf = df_ginf[(df_ginf['league'] == 'F1') & (df_ginf['country'] == 'france')]
df_ginf = df_ginf[['id_odsp', 'adv_stats', 'date', 'league', 'season', 'country', 'ht', 'at', 'fthg', 'ftag']]

df_events = df_events[df_events['id_odsp'].isin(df_ginf['id_odsp'])]

# Replace empty value with None
text_cols = ['id_odsp', 'id_event', 'text', 'event_team', 'opponent', 'player', 'player2', 'player_in', 'player_out']
for col in text_cols:
    df_events[col] = df_events[col].where(df_events[col].notna(), None).astype(object)

# Replace empty value with 0 (int can't be None)
int_cols = ['sort_order', 'time', 'event_type', 'side', 'is_goal', 'assist_method', 'fast_break']
for col in int_cols:
    df_events[col] = df_events[col].fillna(0).astype(int)

# Replace empty value with None (double can be None)
float_cols = ['event_type2', 'shot_place', 'shot_outcome', 'location', 'bodypart', 'situation']
for col in float_cols:
    df_events[col] = df_events[col].where(df_events[col].notna(), None).astype(object)

# Transforming
df_events['league'] = 'Ligue 1'
df_events['location'] = df_events['location'].fillna(0).astype(int)
df_events['time'] = df_events['time'].fillna(0).astype(int)
df_events['player'] = df_events['player'].fillna('Inconnu').astype(str)
df_events['event_team'] = df_events['event_team'].fillna('Inconnu').astype(str)

# Inserting data
# Events
data_event = [
    (
        to_str(row['id_odsp']),
        to_str(row['id_event']),
        to_int(row['sort_order']),
        to_int(row['time']),
        to_str(row['text']),
        to_int(row['event_type']),
        to_float(row['event_type2']),
        to_int(row['side']),
        to_str(row['event_team']),
        to_str(row['opponent']),
        to_str(row['player']),
        to_str(row['player2']),
        to_str(row['player_in']),
        to_str(row['player_out']),
        to_float(row['shot_place']),
        to_float(row['shot_outcome']),
        to_int(row['is_goal']),
        to_float(row['location']),
        to_float(row['bodypart']),
        to_int(row['assist_method']),
        to_float(row['situation']),
        to_int(row['fast_break'])
    )
    for _, row in df_events.iterrows()
]
stmt_event = session.prepare("""
    INSERT INTO events (
        id_odsp, id_event, sort_order, time, text,
        event_type, event_type2, side, event_team, opponent,
        player, player2, player_in, player_out, shot_place,
        shot_outcome, is_goal, location, bodypart, assist_method,
        situation, fast_break
    )
    VALUES (
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?
    )
""")
execute_concurrent_with_args(session, stmt_event, data_event, concurrency=50)
print(f"Data inserted in events : {len(data_event)}")

# Matches
data_match = [
    (
        to_str(row['id_odsp']),
        to_int(row['adv_stats']),
        to_str(row['date']),
        to_str(row['league']),
        to_str(row['season']),
        to_str(row['country']),
        to_str(row['ht']),
        to_str(row['at']),
        to_int(row['fthg']),
        to_int(row['ftag'])
    )
    for _, row in df_ginf.iterrows()
]

stmt_match = session.prepare("""
    INSERT INTO matches (id_odsp, adv_stats, match_date, league, season, country, ht, at, fthg, ftag)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""")
execute_concurrent_with_args(session, stmt_match, data_match, concurrency=50)
print(f"Data inserted in matches : {len(data_match)}")

# Goals by league
df_goals = df_events[df_events['is_goal'] == 1].copy()

data_league = [
    (row['league'], row['location'], str(row['id_event']), str(row['id_odsp']), row['player'], row['time'])
    for _, row in df_goals.iterrows()
]

stmt_league = session.prepare("""
    INSERT INTO goals_by_league (league, location, id_event, id_odsp, player, minute)
    VALUES (?, ?, ?, ?, ?, ?)
""")
execute_concurrent_with_args(session, stmt_league, data_league, concurrency=50)

print(f"Data inserted in goals_by_league : {len(data_league)}")

# Goals by player
data_player = [
    (row['league'], row['player'], row['id_event'], row['event_team'], row['time'])
    for _, row in df_goals.iterrows()
]

stmt_player = session.prepare("""
    INSERT INTO goals_by_player (league, player, id_event, team, minute)
    VALUES (?, ?, ?, ?, ?)
""")
execute_concurrent_with_args(session, stmt_player, data_player, concurrency=50)
print(f"Data inserted in goal_by_player : {len(data_player)}")

print("Base de donnée prête !")