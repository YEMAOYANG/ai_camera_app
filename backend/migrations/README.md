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
NULL-propagating `mysql_least` / `mysql_greatest`.

`105` adds `learning_textbook_review_evidence`, a content-addressed store (the
key is the SHA-256 of the bytes, enforced by a CHECK constraint; rows cannot be
updated). The review records that reuse ASR provenance (audio-audit v3 and v4)
embedded every recording three to eleven times inside
`release.audioAudit.literalAudit`: 100-200 MB each, about 30-45 MB of it
distinct audio. `scripts/split_textbook_review_evidence.py` moves those bytes
here and leaves references in `review_json`; `content/textbook_review_evidence.py`
puts them back exactly when `validate_release` runs, so no sealed digest, content
key or course identity changes. Use the tool's `plan`, `backup`, `apply`,
`verify` and `restore` steps in that order, never move `updated_at` (the archive
worker treats a changed value as a new course version), and deploy the code that
understands split records before applying: older code rejects them. Add new
migrations from `106_` onwards.
