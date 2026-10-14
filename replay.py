from cassandra.cluster import Cluster
import time
from datetime import datetime, timezone

cluster = Cluster(['127.0.0.1'], port=9042)
session = cluster.connect('football')

MATCH_ID = "CzPV312a/"
SECONDES_PAR_MINUTE = 2

match = session.execute("SELECT * FROM matches WHERE id_odsp = %s", [MATCH_ID]).one()
print(f"{match.ht} vs {match.at}")

events = list(session.execute("SELECT * FROM events WHERE id_odsp = %s", [MATCH_ID]))
print(len(events), "événements")

LIVE_ID = "LIVE-" + MATCH_ID
TTL = 6000

session.execute("DELETE FROM events WHERE id_odsp = %s", [LIVE_ID])

debut = time.time()
session.execute(
    f"INSERT INTO matches (id_odsp, ht, at, match_date, season, league, country, fthg, ftag, live_start) "
    f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) USING TTL {TTL}",
    [LIVE_ID, match.ht, match.at, match.match_date, match.season,
     match.league, match.country, 0, 0, datetime.fromtimestamp(debut, timezone.utc)],
)
print("Match live créé :", LIVE_ID)

insert_event = session.prepare(
    f"INSERT INTO events (id_odsp, sort_order, id_event, time, event_type, side, event_team, "
    f"player, player_in, player_out, text, is_goal) "
    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) USING TTL {TTL}"
)
update_score = session.prepare(
    f"UPDATE matches USING TTL {TTL} SET fthg = ?, ftag = ? WHERE id_odsp = ?"
)

score_dom, score_ext = 0, 0

for e in events:
    time.sleep(max(0, debut + e.time * SECONDES_PAR_MINUTE - time.time()))
    session.execute(insert_event, [LIVE_ID, e.sort_order, e.id_event, e.time, e.event_type,
                                   e.side, e.event_team, e.player, e.player_in, e.player_out,
                                   e.text, e.is_goal])

    if e.is_goal == 1:
        if e.side == 1:
            score_dom += 1
        else:
            score_ext += 1
        session.execute(update_score, [score_dom, score_ext, LIVE_ID])

    print(f"{e.time}' [{score_dom}-{score_ext}] {e.text}")

print("Fin du match")