USE football;

COPY matches (id_odsp, adv_stats, match_date, league, season, country, ht, at, fthg, ftag)
FROM '/tmp/ginf.csv'
WITH HEADER = true;

COPY events (
    id_odsp, id_event, sort_order, time, text, event_type, 
    event_type2, side, event_team, opponent, player, player2, 
    player_in, player_out, shot_place, shot_outcome, is_goal, 
    location, bodypart, assist_method, situation, fast_break
)
FROM '/tmp/events.csv'
WITH HEADER = true;