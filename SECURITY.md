# Security Policy

## Supported versions

Ditto has no release branches yet. Fixes land on `main` only, so please check that a problem still happens there before reporting it.

## Scope

Ditto is built to run on a machine you trust, for one person. It has **no login**, and by design:

- the Gemini key lives in plaintext in `.env` and `backend/config/app_settings.json` (that file is written with mode `600`);
- `make up` publishes Postgres, Qdrant and the API only on `127.0.0.1`, but the frontend listens on every interface;
- `make up-local` publishes Postgres and Qdrant on every interface.

Exposing Ditto to the internet is outside its threat model. Reports are still welcome when something leaks or opens up further than the README says it does: a secret in a log or API response, a path traversal in uploads, a service bound wider than documented, and so on.

## Reporting a vulnerability

Please **do not open a public issue**. Email **samuelhs98@gmail.com** with:

- what you found and where (file, endpoint, `make` target);
- steps to reproduce;
- what an attacker could do with it.

You should get a reply within 7 days. Once a fix is on `main` you'll be credited in the commit, unless you'd rather not be.
