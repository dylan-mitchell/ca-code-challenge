# Consumer Reviews — WordPress to Django

A consumer-review directory with two Django services, a React/TypeScript brand listing, shared SCSS, and an installable Python authentication package. [CHALLENGE.md](CHALLENGE.md) describes the exercise; [decisions_log.md](decisions_log.md) records the approved schemas and contracts.

## Run locally

Prerequisites: Docker with Compose v2 supporting `include`, Python 3 for the standard-library helper scripts, and `make`. Application Python, Node, PostgreSQL, and MariaDB run in containers; no host Node or database installation is required.

```bash
make app-setup
```

This generates private local configuration in ignored `.env.app`, builds both service images and frontend assets, migrates both databases, imports the committed WordPress snapshot, and starts the services. Repeating setup preserves existing application records. The first build needs network access to download images and pinned dependencies.

| Address | Purpose |
|---|---|
| <http://localhost:8000/> | Django homepage |
| <http://localhost:8000/brand/> | React directory |
| <http://localhost:8000/brand/acme-insurance/> | Django brand detail |
| <http://localhost:8000/api/brands/> | Public JSON listing |
| <http://localhost:8001/api/login/> | Auth login, POST only |

```bash
make app-logs                  # Follow both application logs
make app-down                  # Stop application services; keep database volumes
make app-up                    # Start again with existing data
make app-build && make app-up  # Rebuild/recreate after Python or template changes
make app-migrate               # Apply new schema migrations
make app-import                # Rerun the content import safely
```

Ports, Django secrets, separate database passwords, the introspection service credential, and the initial demo password are configured in `.env.app`; names and defaults are documented in `.env.app.example`. `make app-env` creates this file once without printing or overwriting secrets. PostgreSQL listens locally on 55432 and the isolated source MariaDB on 53306 by default. This is a local development configuration; deployment/TLS are outside the exercise.

## Architecture and modeling

| Location | Owns |
|---|---|
| `services/main/catalog/` | Brands, industries, reviews, public reviewer profiles, content import, JSON views and rendered pages |
| `services/auth/accounts/` | Users, passwords, one reader/editor role per user, tokens, login, introspection and account import |
| `packages/shared_auth/` | Identity/role contracts, injected token verification, editor checks and common errors |
| `frontend/` | React directory, URL/request state, Vite build and shared SCSS |

Both projects use plain Django views. One local PostgreSQL server hosts separate databases and runtime roles; each application role is denied access to the other database. Main has no user/password/role tables. A local `Reviewer` references auth's stable public UUID as an ordinary unique value, while each review has real foreign keys to its local reviewer and brand.

Brand–industry is many-to-many, including zero industries. Ratings are integers 1–5; averages and counts are calculated from reviews, with `null` for an unrated brand. The stale source average is discarded. Multiple reviews from one reviewer about one brand are allowed. Referenced reviewers/brands are protected from deletion. Per-review bylines take precedence over the profile name.

`Brand.top_review` is an explicit Editor's pick that must belong to that brand. New imports leave it unset; there is no automatic fallback. Deleting the selected review clears the selection. Website, founding year, headquarters, ratings and attribution become typed fields; WordPress implementation metadata and Yoast fields are omitted rather than copied into a generic JSON bag.

Full descriptions and review bodies retain sanitized semantic HTML; presentation stays in templates/SCSS. Short descriptions and API snippets are plain text. Homepage and detail pages work without JavaScript; `/brand/` needs JavaScript and provides a no-script link to the homepage.

## Import and recovery

`make app-import` runs `scripts/import_wordpress.py`. It queries a dedicated MariaDB database restored from `db/dump.sql` on first initialization, using a SELECT-only account. The original WordPress database/volumes and committed dump are untouched. Reruns reuse that isolated source.

1. Auth's `import_wordpress_users --mapping-output PATH` creates missing users in one auth-database transaction. WordPress administrator maps to editor; subscriber maps to reader. New users receive Django password hashes from the local `AUTH_IMPORT_PASSWORD`, not imported WordPress hashes.
2. After commit, auth atomically exports source user IDs to stable public UUIDs. The wrapper uses a fresh temporary mapping file for each run.
3. Main's `import_wordpress_content --auth-map PATH` creates industries, author profiles, brands/industry links, and reviews in one main-database transaction. Original slugs, ratings, timestamps and attribution are preserved. The wrapper removes the mapping when finished.

Fresh counts are **9 auth accounts, 8 reviewer profiles, 5 industries, 5 brands, and 60 reviews**. A verified second import created zero records. Source IDs provide idempotency: existing records and relationships are preserved, including local edits, passwords, roles, UUIDs and Editor's picks. Identity/slug conflicts fail rather than silently merge unrelated records.

Each failed destination phase rolls back its own transaction. If main fails after auth commits, fix the reported issue and rerun: auth reuses its accounts and regenerates the mapping. A mapping-export failure likewise leaves committed accounts reusable. There is no distributed rollback and no ongoing WordPress synchronization. The importer remains for reproducibility.

## API walkthrough

```bash
curl 'http://localhost:8000/api/brands/?industry=insurance&industry=finance&sort=-review_count&page=1&page_size=2'
```

Industry parameters use OR semantics. Sorts are `average_rating`, `-average_rating`, `review_count`, and `-review_count`; the default is highest average. Pagination defaults to 20, caps at 100, and returns `count`, `next`, `previous`, `results`, and all `available_industries`. IDs are strings, timestamps are UTC, and null/empty values are deliberate mobile-friendly contract choices. React stores filters/sort/page in the URL, supports Back/Forward, and cancels stale requests.

Use the generated `AUTH_IMPORT_PASSWORD` from your private `.env.app` when prompted below. Imported `admin` is an editor; `sarah_k` is a reader. This example keeps the password and issued bearer token out of shell arguments/history and does not print either:

```bash
python3 - <<'PY'
import getpass
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

def request(url, method, data, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url, data=json.dumps(data).encode(), headers=headers, method=method)
    try:
        with urlopen(req, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        raise SystemExit(f"HTTP {error.code}: {error.read().decode()}") from None

login = request("http://localhost:8001/api/login/", "POST", {
    "username": "admin",
    "password": getpass.getpass("Imported password: "),
})
print("Authenticated:", login["user"], "Expires:", login["expires_at"])
print(request("http://localhost:8000/api/brands/acme-insurance/", "PATCH", {
    "short_description": "A helpful introduction to Acme Insurance.",
}, login["access_token"]))
PY
```

For a selection, include `"top_review_id": "<main review ID>"` in the PATCH body; send `null` to clear it. To inspect eligible local IDs:

```bash
docker compose run --rm --no-deps main python manage.py shell -c "from catalog.models import Review; print(list(Review.objects.filter(brand__slug='acme-insurance').values('id', 'title')))"
```

PATCH updates submitted fields atomically and returns the complete updated card. Omitted fields are preserved; concurrent writes to the same field use last-write-wins. Errors use `{"error":{"code":"...","message":"..."}}` with parameter/field details where relevant. Invalid payloads produce 400, missing/inactive bearer tokens 401, readers 403, missing brands/pages 404, and unsupported media types 415.

Tokens are random opaque bearer credentials with a one-hour expiry; only SHA-256 digests are stored. Main calls `POST /api/tokens/introspect/` on auth for every protected request using a separate Basic service credential and JSON `{"token":"..."}`. Active results include current identity/role/expiry; inactive tokens return `200 {"active":false}`. Invalid service credentials return 401. Auth timeouts, failures or unusable responses become main's `503 auth_unavailable`; public reads remain available. Login and introspection responses are `no-store`.

## Internal account operations

Open `docker compose run --rm --no-deps auth python manage.py shell`. Use these auth-owned helpers rather than direct field updates when lifecycle side effects are required:

```python
from getpass import getpass
from accounts.models import User
from accounts.operations import change_role, change_password, set_user_active, revoke_all_tokens, revoke_token
user = User.objects.get(username="admin")
change_role(user, "reader")          # The same token loses editor access immediately.
change_role(user, "editor")          # Restore the role for the walkthrough.
revoke_all_tokens(user)              # Login again after revocation.
# Other available operations; run only the one you intend:
# revoke_token(token_row_id)
# set_user_active(user, False)       # Disables account and revokes its tokens.
# set_user_active(user, True)        # Does not revive old tokens.
# change_password(user, getpass())   # Changes password and revokes its tokens.
```

Expiry/revocation does not delete token rows. Cleanup, logout and role-change HTTP endpoints are intentionally absent.

## Frontend and development

`make app-build` compiles TypeScript/React and Dart Sass, then collects Vite's hashed assets for WhiteNoise. Vite can be stopped when serving production assets. CSS is loaded on all pages; React is loaded only for the directory.

```bash
docker compose run --rm --no-deps frontend sh -c 'npm ci && npm run build'
```

This produces `frontend/dist/manifest.json` and bundled JS/CSS. `frontend/scss/main.scss` uses `@use` for tokens, base rules, layout, components, prose, and page styles. Shared classes work in both templates and React; `.prose` styles imported semantic HTML. `reference/theme.css` remains the original structural reference.

For live frontend development, set `VITE_DEV_SERVER_URL=http://localhost:5173` in `.env.app`, run `docker compose --profile dev up -d frontend`, then `docker compose up -d --force-recreate main`. Clear that setting and recreate main to return to built assets. Host Node 24 users can instead run `npm ci` and `npm run dev` inside `frontend/`.

Optional host Python development (Python 3.12):

```bash
python3.12 -m venv .venv
.venv/bin/pip wheel --no-deps --wheel-dir .wheels ./packages/shared_auth
.venv/bin/pip install --find-links .wheels -r requirements.txt
# With databases running and container web services stopped:
python3 scripts/manage_local.py auth runserver 8001
python3 scripts/manage_local.py main runserver 8000  # Separate terminal
```

## Tests and shared-package releases

`make test` runs shared-package tests, both Django suites against disposable PostgreSQL test databases, migration-drift checks, frontend behavior tests, TypeScript checks, and the production asset build. Runtime database roles have no test-database creation privilege; the test helper supplies separate admin credentials only to test commands.

With the imported stack running, `python3 scripts/smoke_test.py` checks the real HTTP flow, same-token role demotion, revocation, and public availability during an auth outage. It temporarily edits Acme and stops auth, then restores Acme, restarts auth, and removes its temporary user. Run it when nobody else is editing the demo. See [verification.md](verification.md) for observed results and [walkthrough.md](walkthrough.md) for a guided code tour.

Run just the shared library independently, with neither Django nor a database installed:

```bash
docker run --rm -v "$PWD/packages/shared_auth:/package:ro" -w /package -e PYTHONPATH=/package/src python:3.12-slim-bookworm python -m unittest discover -s tests -v
# Optional host service checks after the Python setup above:
python3 scripts/manage_local.py auth --test test --noinput
python3 scripts/manage_local.py main --test test --noinput
```

Both images build/install the `review-auth==0.1.0` wheel pinned in `requirements.txt`; the package version lives in `packages/shared_auth/pyproject.toml`. To release a change, update its version and the dependency pin, run independent and service contract tests, rebuild, and recreate each service. This repository updates both consumers together, but a compatible wheel can be rolled out one service at a time. For a future breaking wire change, first teach the provider/consumers to support both shapes, migrate consumers, and only then remove the old shape/version; a package bump alone does not provide protocol compatibility. No registry or simultaneous-deployment mechanism is required here.

## Tradeoffs and scope

The user deliberately chose plain Django views to avoid another framework, PostgreSQL based on prior experience and RDS suitability, live introspection for immediate role changes, and create-only import recovery over synchronization. AI-assisted proposals accepted during design include the bounded React page, small injected-lookup package, and shared SCSS organization; these were explicitly reviewed in the decisions log. Docker-first tooling, one local PostgreSQL server, the small Vite template helper, and unittest/Vitest are implementation defaults, not additional user-approved product decisions.

At 100× the data, measure importer memory/query costs, use bulk operations or bounded reads while keeping explicit recovery semantics, inspect aggregate query plans/indexes, and revisit page-number pagination for deep result sets. Consider auth availability/redundancy before introducing a cache that weakens immediate revocation. More time would add deployment configuration, operational monitoring, rate limits, token cleanup, and broader browser accessibility checks. These are future work, not claims about this build.

No editor/admin/login UI, registration/reset/social login/MFA, review submission/search/voting, image uploads, refresh tokens, automatic top-review selection, SEO/plugin parity, or AWS deployment is included. Review archive/About/Contact pages are deferred. Styling follows the reference's structure without pixel matching.

## Original WordPress reference

`make up` still starts the original site at <http://localhost:8080>, admin at `/wp-admin` (source demo credentials `admin` / `admin`), and phpMyAdmin at <http://localhost:8081>. Optional legacy overrides live in `.env` copied from `.env.example`. `make logs`, `make wp ARGS="plugin list"`, `make bootstrap`, and `make dump` remain available. The last two reseed/export the source and are unnecessary for the Django import. WordPress plugins, custom theme, schema definitions, and `db/dump.sql` remain committed; core files live in the original WordPress volume.
