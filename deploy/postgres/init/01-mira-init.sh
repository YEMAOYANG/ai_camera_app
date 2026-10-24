#!/bin/sh
# Runs once, when the PostgreSQL data volume is first initialised.
# Creates the single login `mira` and the disposable test database, then
# applies the per-database layout in database-setup.psql to both databases.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v mira_pw="$MIRA_DB_PASSWORD" <<'SQL'
CREATE ROLE mira LOGIN PASSWORD :'mira_pw';
CREATE DATABASE mira_test;
SQL

for database in "$POSTGRES_DB" mira_test; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" \
    -v db="$database" -f /docker-entrypoint-initdb.d/database-setup.psql
done
