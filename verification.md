# Verification record

Local verification on November 19, 2026. No commits were pushed.

## Automated checks

- Shared library: 14 standalone tests passed, without either Django project.
- Auth service: 25 PostgreSQL tests passed.
- Main service: 42 PostgreSQL tests passed, covering models, aggregation, filters/pagination,
  atomic writes, auth failures, import recovery, content handling and pages.
- Frontend: 23 Vitest tests passed, including stale-response races,
  URL/history behavior, pagination focus and error recovery.
- TypeScript checking and the Vite/Dart Sass production build passed.
- Both Django migration-drift checks passed.
- Runtime credentials were denied access to the other service's database.
  MariaDB rejected a write attempted with the source-reader credential.

The full container command is `make test`. After the final snippet regression
was added, the updated main suite was rerun separately.

## Real data and fresh setup

The committed dump was restored into a new, isolated MariaDB volume. Import
produced 9 auth accounts, 8 reviewers, 5 industries, 5 brands and 60 reviews.
A second import created zero records. The Docker mapping-file wrapper also
completed and removed its temporary handoff.

A second Compose project, `ca-challenge-verify`, ran `make app-setup` from empty
application/source volumes with separate ports, DEBUG disabled and no Vite
server. Actual database counts matched the expected import. A rerun created
zero records. Acme's API card returned a derived average of 3.92, twelve reviews,
and no selected review. Production CSS loaded on homepage and directory;
React JavaScript loaded only on the directory. All fetched assets returned 200.
Only this disposable verification project's containers/volumes were removed.

## Live service integration

`python3 scripts/smoke_test.py` passed against the running Docker services:

- Login and separately authenticated introspection.
- Editor selection/clearing of a top review.
- Atomic rejection of an invalid multi-field PATCH.
- Immediate editor-to-reader demotion with the same unexpired token: 403.
- Revocation: 401.
- Auth outage: protected writes return 503 without changing the brand.
- Homepage, directory, both detail types and public API stay available.

The test restored the original brand, restarted auth and deleted its temporary
account. Unit tests separately exercise expiry, disable/re-enable behavior,
password-change revocation, transactional import failure and mapping recovery.

## Review

Browser observations completed against the production assets with Vite stopped:
desktop homepage and 375px mobile homepage, directory, brand and review pages
were visually inspected, with no horizontal overflow. Keyboard industry
selection used OR filtering; pagination used real links and focused results;
Back restored filters. Invalid-industry reset and missing-page recovery worked.
With JavaScript disabled, the directory showed its fallback without a permanent
loading message, and brand content/reviews remained rendered and styled.
Screenshots are local, ignored artifacts under `output/playwright/`.

Each implementation chunk received an independent agent review. Findings about
malformed text/JSON, snippet boundaries, filter focus, query consistency and the
legacy reset command were fixed and verified. The final whole-repository code
review found no outstanding actionable issues.

These checks cover the local challenge configuration. They do not claim a
production deployment, load test, exhaustive accessibility audit or support for
every browser. The original WordPress source, SQL dump and reference CSS remain
unchanged.

## 2026-11-20 — Gunicorn concurrency regression

Both service images now explicitly use two `gthread` workers with four threads
per worker. The worker-health timeout remains at its default of 30 seconds;
this is not a per-request deadline with threaded workers.

- A disposable Gunicorn process using the old single synchronous worker
  reproduced the stall: a valid GET timed out while idle connections stayed open.
- After rebuilding and starting both services, `python3 scripts/check_http_concurrency.py`
  passed all four cases: main and auth with two idle connections, then with two
  incomplete HTTP requests. Each case completed three ordinary requests while
  the held connections remained open; the slowest response was 0.127 seconds.
- The existing `python3 scripts/smoke_test.py` passed again, including login,
  introspection, editor writes, immediate role demotion, revocation, atomic
  validation, auth-outage behavior and public pages. It restored Acme's previous
  values, restarted auth and removed its temporary account.
- An independent agent reviewed the server configuration, regression script
  and documentation with no actionable findings.

This is a focused concurrency regression, not a load test. The full unit and
frontend suites reported above were not rerun for this server configuration change.
