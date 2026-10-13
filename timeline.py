from dash import html
import re

LIBELLES = {3: "Faute", 4: "Carton jaune", 5: "Deuxième jaune", 6: "Carton rouge", 7: "Remplacement"}
ICONES = {3: "foul", 4: "yellow", 5: "second-yellow", 6: "red", 7: "sub"}
REMPLACEMENT = re.compile(r"\. (.+?) replaces (.+?)(?: because of an injury)?\.?$")

def nom(joueur):
    return (joueur or "").title()

def noms_remplacement(e):
    trouve = REMPLACEMENT.search(e.text or "")
    if trouve:
        return trouve.group(1), trouve.group(2)
    return nom(e.player_in), nom(e.player_out)


def ligne_evenement(e, dom, ext):
    classe_titre, classe_sous_titre = "tl-title", "tl-sub"

    if e.is_goal == 1:
        titre, sous_titre, icone = nom(e.player), f"But ({dom} - {ext})", "goal"
    elif e.event_type == 7:
        titre, sous_titre = noms_remplacement(e)
        icone = "sub"
        classe_titre += " tl-in"
        classe_sous_titre += " tl-out"
    else:
        titre, sous_titre = nom(e.player), LIBELLES.get(e.event_type, "")
        icone = ICONES.get(e.event_type, "")

    cote = "tl-home" if e.side == 1 else "tl-away"
    mineur = " tl-minor" if e.event_type == 3 and e.is_goal != 1 else ""
    return html.Div(className=f"tl-event {cote}{mineur}", children=[
        html.Div(f"{e.time}'", className="tl-minute"),
        html.Div(className="tl-info", children=[
            html.Span(className=f"tl-icon tl-icon-{icone}"),
            html.Div(children=[
                html.Div(titre, className=classe_titre),
                html.Div(sous_titre, className=classe_sous_titre),
            ]),
        ]),
    ])


def render_timeline(events):
    lignes = []
    dom, ext = 0, 0
    mi_temps_affichee = False

    for e in events:
        if e.time > 45 and not mi_temps_affichee:
            lignes.append(html.Div(f"MT {dom} - {ext}", className="tl-separator"))
            mi_temps_affichee = True

        if e.is_goal == 1:
            if e.side == 1:
                dom += 1
            else:
                ext += 1

        if e.is_goal == 1 or e.event_type in LIBELLES:
            lignes.append(ligne_evenement(e, dom, ext))

    if not any(e.is_goal == 1 or e.event_type in LIBELLES for e in events):
        return html.P("Aucun événement marquant pour ce match.", className="tl-empty")
    return html.Div(className="timeline", children=lignes)

def tableau_score(match, events):
    minute = events[-1].time if events else 0
    return html.Div(className="sb", children=[
        html.Div(className="sb-live", children=[
            html.Span(className="sb-dot"),
            html.Span(f"En direct · {minute}'"),
        ]),
        html.Div(className="sb-line", children=[
            html.Span(match.ht, className="sb-team sb-home"),
            html.Span(f"{match.fthg} - {match.ftag}", className="sb-score"),
            html.Span(match.at, className="sb-team"),
        ]),
    ])