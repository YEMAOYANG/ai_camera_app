#!/bin/sh
# Runs once, when the PostgreSQL data volume is first initialised.
# Creates the single login `mira` and, when MIRA_CREATE_TEST_DATABASE=1 (local
# development only), the disposable test database; then applies the
# per-database layout in database-setup.psql to each database.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v mira_pw="$MIRA_DB_PASSWORD" <<'SQL'
CREATE ROLE mira LOGIN PASSWORD :'mira_pw';
SQL

databases="$POSTGRES_DB"
if [ "${MIRA_CREATE_TEST_DATABASE:-0}" = 1 ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -c 'CREATE DATABASE mira_test'
  databases="$databases mira_test"
fi

for database in $databases; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" \
    -v db="$database" -f /docker-entrypoint-initdb.d/database-setup.psql
done
