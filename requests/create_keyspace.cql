CREATE KEYSPACE IF NOT EXISTS football
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};