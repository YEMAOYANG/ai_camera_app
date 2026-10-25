Backend migrations are PostgreSQL SQL files applied in filename order by:

```sh
cd backend
python3 scripts/migrate.py
```

Tables live in the schema `app` of the configured database: locally the
Docker database `mira` (see `deploy/compose.local-db.yml`), whose schema
`public` belongs to the OpenMAIC classroom runtime.

- `APP_ENV=development` uses `APP_DATABASE_URL`.
- `APP_ENV=test` uses `APP_TEST_DATABASE_URL`, which must name the database
  `mira_test` (or `mira_test_<suffix>` for a parallel run); tests drop and
  rebuild its `app` schema.
- `APP_ENV=staging` and `APP_ENV=production` require an explicit
  `APP_DATABASE_URL`.

`100`–`102` are the PostgreSQL baseline, generated on 2026-10-25 from the final
state of the 89 MySQL migrations. Those are kept unchanged in `mysql/` as
history and are no longer applied; a few SQLite unit-test fixtures still read
their table definitions. `102` adds the foreign keys separately so that a data
copy can load every table before references are validated.

`103` holds MySQL-compatible SQL functions that backend queries still call:
`JSON_EXTRACT`, `JSON_UNQUOTE`, `JSON_CONTAINS` (MySQL's containment rules,
not PostgreSQL's `@>`), `JSON_LENGTH`, `JSON_TYPE`, `JSON_VALID`,
`JSON_REMOVE`, `mysql_unsigned` (a lenient `CAST(... AS UNSIGNED)`) and the
NULL-propagating `mysql_least` / `mysql_greatest`. Add new migrations from
`104_` onwards.
