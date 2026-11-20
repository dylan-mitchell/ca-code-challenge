# Guided walkthrough

Use this order to understand the implementation before the live exercise.

1. **Start with the domain.** Read `services/main/catalog/models.py`.
   A Django model is a Python class describing a database table; fields describe
   columns, and a migration records the schema changes. Brand–industry uses a
   join table. Review has local foreign keys; Reviewer holds an external auth
   UUID. The `Meta` constraints become database checks. Inspect
   `catalog/migrations/0001_initial.py` to see the concrete schema.
2. **Follow Sarah's identity.** Read `services/auth/accounts/models.py`,
   then the two `management/commands/import_wordpress_*.py` files. Source user
   `sarah_k` (WordPress ID 2) becomes one auth User and one main Reviewer.
   The temporary mapping passes her stable public UUID between independently
   committed databases. Main never reads auth's tables. Import tests show
   rollback, safe reruns, and preserving edited records.
3. **Trace a public read.** Open `/brand/acme-insurance/` and
   `/api/brands/?page_size=2`. Acme has twelve reviews and a derived average of
   3.92; its obsolete WordPress average was 4.2. Read `catalog/queries.py`,
   `serialization.py`, and `api.py`. Django's queryset describes a SQL query;
   `annotate()` calculates average/count values in SQL, without storing them.
4. **Trace a protected write.** Read `accounts/views.py` and `operations.py`.
   Login returns a random token and stores only its digest. Follow a PATCH
   through `catalog/api.py`, `auth_client.py`, and the installable
   `review_auth` package. The injected lookup calls HTTP in main and the local
   token table in auth; shared verification checks the same identity/expiry
   contract. There is no cached role.
5. **Demonstrate the chosen tradeoff.** Run `scripts/smoke_test.py` against
   the imported local stack. It selects/clears a review, rejects an invalid
   atomic update, demotes an editor without replacing the token, revokes it,
   and briefly stops auth. Writes fail closed while public pages remain
   available. The script restores its edits and removes its test account.
6. **Follow the page boundary.** Read `config/urls.py`, `catalog/page_views.py`,
   and `templates/base.html`. The homepage/details render on the server.
   `/brand/` renders a shell that loads React. In `frontend/src/BrandList.tsx`,
   follow URL state, request cancellation, then success/error rendering.
   Try filters, Back/Forward, and `?page_size=2`; page navigation moves focus
   to the results heading. Shared SCSS classes style both template and React
   cards; the Vite manifest maps source entries to built filenames.

`README.md` contains runnable commands. `decisions_log.md` records the deliberate
tradeoffs; implementation defaults and verification evidence are documented
separately. No production deployment is included.
