# Build plan

Status: implementation authorized and in progress on `codex/django-migration`. All work stays local; no pushes.

This plan implements the requirements in `CHALLENGE.md` and the approved behavior in `decisions_log.md`. The decisions log remains the source of truth for schemas, API contracts, service boundaries, and user-visible behavior. This plan organizes the work without changing those decisions.

**Working approach**

Work through one phase at a time, splitting a phase into smaller changes when useful. Before changing code, explain the proposed files and relevant Django/React concepts. Implement the agreed slice, run its meaningful checks, and review the resulting code and behavior together before moving on. Keep the README current as commands become real. Tests accompany the feature they verify; the last phase checks the assembled system.

The user's subsequent instruction authorizes the complete build, parallel work where appropriate, an agent review after each completed chunk, focused commits at reasonable checkpoints, and a final independent agent review. Continue to explain meaningful changes and verification results, without requiring a new permission pause for each phase. Do not push any commits.

**Setup choices still to settle**

These are proposed defaults, not additions to the approved decisions log. Resolve them at the relevant checkpoint without reopening the already-approved architecture.

| Choice | Proposed approach | Resolve before |
|---|---|---|
| Local workflow | Docker Compose as the documented path, including frontend tooling, so a reviewer can reproduce the app with Docker. | Phase 1 |
| PostgreSQL topology | One local PostgreSQL server with separate application databases and roles. Explicitly deny each runtime role access to the other application's database. Keep test-database provisioning privileges separate from runtime credentials. | Phase 1 |
| Source database | A separately named disposable MariaDB restore of the committed dump. Preserve the existing WordPress containers' data volumes. | Phase 1 |
| Versions and ports | Select compatible supported Python, Django, Node, database, and frontend-tool versions; pin dependencies and document ports and configuration. | Phase 1 |
| Django–Vite integration | Review a small template integration against an existing integration package; select the simplest approach that correctly handles development refresh and production manifests. | Phase 7 |
| Test tooling | Use Django's test runner for service tests, an independent Python test command for the shared package, and focused frontend behavior tests. Select the frontend test tooling with the React implementation. | Relevant implementation phase |

Proposed directory layout: `services/main/`, `services/auth/`, `packages/shared_auth/`, and `frontend/`, with orchestration in the existing `scripts/` and Makefile. Directory and command names can be finalized in Phase 1. Preserve the WordPress source, committed SQL dump, and reference CSS.

**1. Establish the local foundation**

- [ ] Create separate Django project skeletons, a versioned shared-package skeleton, and frontend package/configuration scaffolding using the approved Vite, React plugin, TypeScript, Dart Sass, and npm choices.
- [ ] Add Compose configuration for the two services, PostgreSQL, isolated MariaDB import source, and frontend development/build tooling. Keep existing WordPress reference commands available.
- [ ] Document environment variable names and examples for service-local database access, source reads, Django settings, the introspection service credential, and the auth-only demo import password. Keep actual local configuration untracked.
- [ ] Make the shared package installable into each service from a versioned build. Establish the build/test command entry points without adding application behavior yet.
- [ ] Defer initial Django migrations until the custom auth User is configured in Phase 3. Avoid installing a second user/password/role store in the main application through default Django scaffolding.

Verification: both Django projects pass configuration checks; database services become ready; application credentials are isolated; the shared package can be imported by both projects. No existing database volumes are reset. Frontend scaffolding can type-check/build without implying the listing is implemented.

Review checkpoint: walk through project versus app, `manage.py`, settings, container boundaries, and the local commands. Confirm remaining setup choices before continuing.

**2. Implement the shared Python authentication library**

- [ ] Add role definitions, plain identity/token-result structures, introspection response encoding/validation, common errors, and error-payload construction.
- [ ] Implement token verification with the approved injected lookup function and the editor permission check. Keep service models, settings, database access, and HTTP transport outside the package.
- [ ] Add independent tests using fake lookup functions for active, expired, and inactive tokens; recognized roles and editor permission; malformed results; and lookup failures.

Verification: run package tests with neither Django project nor a database required. Verify that each service installs the intended package version. Do not create an auth endpoint merely to give the editor-permission helper another caller.

Review checkpoint: trace the verification function with fake lookup results, explaining what the package owns and what the future auth-database and main-service HTTP lookups will supply.

**3. Implement models and initial schema migrations**

- [ ] Add auth User and AccessToken models, configuring `AUTH_USER_MODEL` before the first auth migration.
- [ ] Add Brand, Industry, Reviewer, and Review to the main service using the exact approved fields and constraints. Include the many-to-many industry relationship and optional selected-review reference.
- [ ] Generate and inspect migrations, including the Brand/Review relationship cycle. Apply them to fresh disposable application databases.
- [ ] Add focused tests for uniqueness, valid ratings and source IDs, allowed roles, deletion protection, and clearing a selected review when that review is deleted. Plan same-brand selection validation in the write path, since a foreign key alone does not enforce it.

Verification: schema creation succeeds from empty databases; no cross-service foreign keys or main-service password/role tables exist; derived rating/count fields are not stored. Preserve nullable versus empty-string conventions and allow multiple reviews by one reviewer for the same brand.

Review checkpoint: inspect representative model definitions and their database relationships, especially Sarah's external auth UUID versus her local Reviewer ID.

**4. Implement and verify the two-phase importer**

- [ ] Implement read-only extraction from the dedicated MariaDB source in each service's management command.
- [ ] Implement auth account creation/reuse, initial role mapping, and the explicitly configured local-demo password for new accounts only. Commit the auth transaction before exporting all source-account UUID mappings.
- [ ] Implement the wrapper's fresh temporary mapping handoff. Start main only after successful auth completion and a complete mapping export; stop and report failures accurately.
- [ ] Implement main content import in dependency order, creating profiles for review authors and preserving existing records and relationships. Keep the sanitizer a small importer helper using an existing library; apply the agreed plain-text short-description rules only on creation.
- [ ] Report created/existing counts after commit and actionable validation errors. Handle conflicting identities without merging or relinking them.

Verification: a fresh import produces 9 auth accounts, 8 reviewer profiles, 5 industries, 5 brands, and 60 reviews. Preserve original slugs, timestamps, ratings, and attribution; new brands have no selected top review. Rerun after changing local content, industry links, a selected review, account role/password, and other editable fields: identities and edits remain intact and no duplicates appear.

Exercise auth rollback, main rollback after auth succeeds, and mapping-export failure after auth commit. Confirm retries reuse committed UUIDs and recover. Use disposable test data for failure cases; do not modify the committed dump. Compare meaningful application state on reruns, not only row counts.

Review checkpoint: follow Sarah and one Acme review from source rows through both databases, then examine a successful rerun and a failed-phase recovery.

**5. Implement the auth API and internal lifecycle operations**

- [ ] Implement plain Django login and introspection views according to the approved JSON contracts and errors.
- [ ] Issue one-hour opaque tokens, store their digests, and expose the raw token only on issuance. Protect introspection with the separate Basic service credential.
- [ ] Use the shared verification code with the auth-owned lookup. Read current account status and role on each check.
- [ ] Implement internal revoke-one, revoke-all, account-disable/password-change revocation, and role-change operations. Document shell invocation; do not add public logout or role-change endpoints.

Verification: login rejection is the approved `400`; inactive introspection is `200` with only `active: false`; invalid service credentials receive the approved `401`. Cover expiry, individual/all-token revocation, disabled accounts, password changes, current roles, and no token revival after re-enabling an account. Check `no-store` headers and that introspection neither extends expiry nor changes last-login time.

Review checkpoint: obtain a token, inspect its stored representation, and demonstrate introspection before and after a role change or revocation.

**6. Implement the main API and reusable content queries**

- [ ] Implement brand query helpers and card serialization for the approved public listing: OR industry filtering, four sorts, page-number pagination, complete industry choices, calculated averages/counts, and explicit editor-selected review snippets.
- [ ] Implement strict query/body validation and the approved error representations. Reuse content helpers inside the main service for later page views.
- [ ] Implement the introspection HTTP lookup with bounded timeouts and validated responses; invoke shared verification and editor permission checks for every protected request.
- [ ] Implement atomic brand PATCH operations for short descriptions and selecting/clearing the top review. Preserve omitted fields and last-write-wins behavior for submitted fields.

Verification: test multi-industry brands, repeated rating values, unrated brands, ties, pagination bounds, empty filters/results, string IDs, and missing-value conventions. Acme's average comes from its reviews, not the source's stored 4.2. Industry joins must not duplicate brands or inflate aggregates. Selected reviews must belong to the brand, with no automatic fallback.

Prove editor success, reader `403`, invalid token `401`, and auth timeout/outage/malformed response/service-credential failure mapping to main `503`, with no write on failure. Demonstrate editor-to-reader demotion with the same unexpired token. Public reads remain available while auth is unavailable. Invalid multi-field updates make no partial changes; omitted fields retain concurrent edits.

Review checkpoint: trace a listing request and a protected update through parsing, querying/authentication, validation, transaction, and response. Demonstrate a deliberate Editor's pick through PATCH after import.

**7. Build Django pages, shared SCSS, and asset integration**

- [ ] Implement the base layout and approved homepage, `/brand/` directory shell, `/brand/<slug>/`, and `/review/<slug>/` templates with ordinary navigation links.
- [ ] Build the seven approved SCSS files using `@use`, shared tokens and classes, scoped `.prose` styling, and responsive/accessibility rules. Preserve `reference/theme.css` as the reference.
- [ ] Implement the selected Django–Vite integration: development asset references and React refresh support, production manifest lookup including dependencies, and generated assets available to Django's static-file workflow.
- [ ] Keep shared CSS available on every page and React JavaScript limited to the directory. Add the directory's initial loading/no-script presentation while the full React behavior awaits Phase 8.

Verification: original detail URLs resolve, page content and links are correct, all industries and derived statistics render, and optional/empty content is handled. Homepage and detail pages remain styled with JavaScript disabled. Build assets before `collectstatic`, then verify production asset loading with Vite stopped. Check narrow and wide layouts and that shared styles load once.

Review checkpoint: show template inheritance, the shared CSS class conventions that React will also use, and how the manifest connects source assets to production filenames.

**8. Implement the React TypeScript directory**

- [ ] Build the listing, cards, native industry checkboxes, sorting, and Previous/Next controls against the approved API.
- [ ] Implement URL-derived query state, immediate filtering, page resets, valid page-size handling, browser history, and ordinary page links supporting new tabs.
- [ ] Implement loading, success, empty, invalid-query, missing-page, and transient-error states with their approved recovery actions. Keep known controls available, hide stale results, and cancel/ignore superseded requests and errors.
- [ ] Implement keyboard focus behavior, status announcements, responsive arrangements, and readable cards with optional Editor's pick snippets.
- [ ] Add focused behavior tests and run the explicit TypeScript check alongside the production build.

Verification: exercise filtering/sorting, a multi-page fixture or smaller page size, reload/share URLs, Back/Forward, retries without history additions, and out-of-order responses. Test an invalid initial URL with no taxonomy loaded, page-not-found recovery, and true empty results. Verify keyboard operation, focus after page navigation, status announcements, mobile layout, and normal navigation to Django detail pages. Use fixtures for states the five-brand source does not naturally produce.

Review checkpoint: walk through URL state, request state, and rendering separately, compare the shared styling on Django and React cards, then reproduce loading/error and rapid-filter scenarios together.

**9. Verify the complete setup and prepare delivery**

- [ ] Follow the README from a fresh isolated Compose project/volumes: configure, build, migrate, import, rerun, and run the app. Preserve existing developer and WordPress data during this check.
- [ ] Run the independent shared-package tests, service tests, frontend behavior tests, type check, production asset build, and integrated browser/API checks through documented commands. Fix any gaps found in the assembled system.
- [ ] Document exact local startup/shutdown, migration/import, frontend build, test, login, protected-update, internal role-change, and revocation commands. Explain configuration, service addresses, and safe failure recovery.
- [ ] Document how both services pin/install a shared-package version, how an upgrade reaches each service, and how a compatible transition would support a future breaking contract change. Explain the strategy without building a second protocol version or deployment system.
- [ ] Add the required concise modeling rationale, tradeoffs, what would change with more time or 100x the data, mobile-client considerations, and deliberate AI recommendations accepted or rejected.
- [ ] Prepare a short walkthrough covering architecture, one imported brand/reviewer, public listing, editor update, same-token role demotion, revocation/auth outage behavior, and safe import reruns. Clearly distinguish automated checks from manual observations.

Review checkpoint: complete the reproducible walkthrough together and confirm that the code and remaining limitations are understandable and defensible in the live session.

**Completion criteria and scope**

Completion requires all six challenge pillars to be implemented, the approved contracts to pass their relevant checks, the documented fresh-start workflow to work, and the README to cover the required delivery and upgrade instructions. Record actual verification results as work completes rather than treating unchecked plan items as evidence.

Keep the agreed exclusions: no new admin/editor/login UI, public logout or role-change API, registration/password-reset flow, refresh tokens, token cleanup, review submission/search, voting, or automatic top-review selection. AWS deployment is outside this build plan; optional archive/About/Contact pages remain deferred. Sanitization stays a small importer concern. Do not extend the shared auth package with content/import/template responsibilities.
