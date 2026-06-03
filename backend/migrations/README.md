Backend migrations are SQL files applied in filename order by:

```sh
cd backend
python3 scripts/migrate.py
```

Development, test, staging, and production all use MySQL.

- `APP_ENV=development` uses `APP_DATABASE_URL`, defaulting to
  `ai_camera_app_dev`.
- `APP_ENV=test` uses `APP_TEST_DATABASE_URL`, defaulting to
  `ai_camera_app_test`.
- `APP_ENV=staging` and `APP_ENV=production` require an explicit
  `APP_DATABASE_URL`.
