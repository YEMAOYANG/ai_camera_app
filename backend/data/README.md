This directory is not the backend runtime database location.

Development, test, staging, and production all use MySQL through
`APP_DATABASE_URL` or `APP_TEST_DATABASE_URL`.

Do not place local database files in this directory.

Development ONVIF pairing may create an ignored `.device-secret.key` and
`device-secrets/` directory here. Credential payloads are encrypted and the
runtime configuration stores only a `secret_ref`. Production should provide a
stable key through `APP_DEVICE_SECRET_KEY` and mount access-controlled durable
secret storage, or replace the local store with a managed secret service.
