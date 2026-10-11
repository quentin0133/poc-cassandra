USE football;

CREATE TABLE IF NOT EXISTS football.matches (
    id_odsp text PRIMARY KEY,
    adv_stats boolean,
    match_date text,
    league text,
    season text,
    country text,
    ht text,
    at text,
    fthg int,
    ftag int
);

CREATE TABLE IF NOT EXISTS events (
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