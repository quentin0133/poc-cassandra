# MatchLive — POC Cassandra

POC réalisé dans le cadre du contrôle continu « Cassandra & CQL ».

Application web (Dash) qui stocke et affiche des matchs de football dans un cluster Cassandra : statistiques de la saison, fil des événements d'un match et rejeu d'un match « en direct ».

Données : dataset Kaggle [Football Events](https://www.kaggle.com/datasets/secareanualin/football-events), filtré sur la Ligue 1.

## Prérequis

- Docker et Docker Compose
- Python 3.12
- Un compte Kaggle pour télécharger les données

## Structure du dépôt

```
docker-compose.yaml    cluster Cassandra à 2 nœuds (cassandra-node1, cassandra-node2)
init_db.py             création du keyspace, des tables, nettoyage et chargement des données
requests/              scripts CQL de référence (keyspace, tables matches/events, import COPY)
app.py                 interface Dash (dashboard, événements par match, direct)
timeline.py            affichage de la frise des événements et du tableau de score
assets/theme.css       style de l'interface
replay.py              rejoue un match en direct dans Cassandra
requirement.txt        dépendances Python
data/                  emplacement des CSV Kaggle (non versionnés)
```

## Installation

### 1. Données

Télécharger le dataset sur Kaggle et placer `events.csv` et `ginf.csv` dans le dossier `data/`.

Aucune préparation manuelle n'est nécessaire : le filtrage sur la Ligue 1 et le nettoyage des valeurs manquantes sont faits par `init_db.py`.

### 2. Environnement Python

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirement.txt
```

Sous Mac ou Linux, activer l'environnement avec `source .venv/bin/activate`.

### 3. Cluster Cassandra

```
docker compose up -d
docker exec cassandra-node1 nodetool status
```

Attendre que les deux nœuds soient à l'état `UN` (Up / Normal), soit 2 à 3 minutes. Seul `cassandra-node1` expose le port `9042` sur la machine hôte.

### 4. Schéma et données

```
py init_db.py
```

Le script :

1. supprime puis recrée le keyspace `football` ;
2. crée les tables `matches`, `events`, `goals_by_league` et `goals_by_player` ;
3. lit les CSV de `data/`, ne garde que les matchs de Ligue 1 et nettoie les valeurs manquantes ;
4. insère les données avec des requêtes préparées exécutées en parallèle (`execute_concurrent_with_args`).

Il peut être relancé à tout moment pour repartir d'une base propre.

## Lancement

Interface :

```
py app.py
```

Puis ouvrir http://127.0.0.1:8050.

L'interface comporte trois onglets :

- **Dashboard** : top 10 des buteurs et répartition des buts par position sur le terrain ;
- **Événements par match** : choix d'un match et frise de ses événements (buts, cartons, remplacements, fautes, score à la mi-temps) ;
- **Direct** : tableau de score et frise du match en cours de rejeu, rafraîchis toutes les 2 secondes.

Le temps d'exécution des requêtes Cassandra est affiché en haut de la page.

Replay d'un match en direct, dans un second terminal :

```
py replay.py
```

Le script rejoue le match `CzPV312a/` sous l'identifiant `LIVE-CzPV312a/`, à raison de 5 secondes par minute de jeu. L'onglet « Direct » affiche le match au fur et à mesure, sans recharger la page.

Pour tout arrêter et supprimer les données : `docker compose down -v`.

## Modèle de données

Keyspace : `football`.

| Table | Clé de partition | Clé de clustering | Requête servie |
|---|---|---|---|
| `matches` | `id_odsp` | — | Infos et score d'un match |
| `events` | `id_odsp` | `sort_order` (ASC), `id_event` | Fil des événements d'un match |
| `goals_by_player` | `league` | `player`, `id_event` | Classement des buteurs |
| `goals_by_league` | `league` | `location`, `id_event` | Répartition des buts par position |

Chaque table répond à une requête précise de l'application. Les requêtes du dashboard, du fil d'un match et du direct se font par clé de partition, sans jointure. Seule la liste déroulante des matchs parcourt la table `matches` (limitée à 100 lignes).

## Mécanismes Cassandra illustrés

- **Partitionnement** : tous les événements d'un match sont dans la même partition, lue en une seule requête.
- **Clustering order** : les événements sont stockés triés par `sort_order` et renvoyés dans l'ordre du match sans `ORDER BY`.
- **Agrégation sur la clé de clustering** : `GROUP BY player` et `GROUP BY location` sont calculés à l'intérieur d'une seule partition (`league = 'Ligue 1'`).
- **Dénormalisation** : les buts sont dupliqués dans des tables dédiées (`goals_by_player`, `goals_by_league`), une par requête du dashboard.
- **TTL** : le match rejoué par `replay.py` est inséré avec `USING TTL 6000` et s'efface automatiquement 100 minutes après son écriture.
- **Upsert** : le score du direct est mis à jour par un simple `UPDATE` à chaque but, sans lecture préalable.
- **Cluster multi-nœuds** : le cluster compte 2 nœuds sur lesquels les partitions sont réparties.
