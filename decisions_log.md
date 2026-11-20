# Decisions log

Record deliberate, agreed decisions here, along with their rationale and accepted tradeoffs. Proposals remain in discussion until agreed.

## 2026-11-19 — Derive brand average ratings from reviews

- **Decision:** Calculate each brand's average rating from its individual review ratings. Do not import WordPress's stored average into a separate Django field.
- **Why:** The source values disagree: Acme's stored average is 4.2, while its 12 reviews average approximately 3.92. Individual review ratings are authoritative, and there is no requirement to retain the inconsistent summary value in the new model.
- **Tradeoff:** Calculate the average during database queries rather than maintain a stored aggregate.

## 2026-11-19 — Allow multiple industries per brand

- **Decision:** Model brands and industries as a many-to-many relationship.
- **Why:** A brand may belong to multiple industries, and an industry may contain multiple brands. The seed data's one-industry-per-brand arrangement should not become a domain restriction.

## 2026-11-19 — Validate every protected request through auth

- **Decision:** Call the auth service on every protected request. Check token validity, current account status, and current roles. Do not cache authorization results initially.
- **Why:** A role change must affect subsequent authorization checks. If Sarah changes from editor to reader, an unexpired token must not preserve her former editing permission.
- **Accepted tradeoff:** Auth is a critical dependency for protected operations. If validation cannot complete, those operations fail closed. Public pages and read endpoints remain independent of auth.
- **Revisit when:** Measured request volume or latency makes the auth traffic untenable. Any alternative must explicitly address the resulting freshness of permission changes.

## 2026-11-19 — Use expiring opaque bearer tokens with introspection

- **Decision:** Issue expiring opaque tokens at login. Clients send them in the `Authorization: Bearer <token>` header; the main app uses auth-service introspection on every protected request.
- **Why:** Token records in auth support expiration and revocation, while current account and role checks preserve the authorization behavior agreed above. JWT's independent-verification capability is unnecessary for this design, and bearer headers suit the challenge's API/curl workflow without requiring browser session integration.
- **Accepted tradeoff:** The auth service must maintain token records and their lifecycle. Token lifetime and implementation details remain to be decided.

## 2026-11-19 — Use PostgreSQL with separate databases and credentials

- **Decision:** Use PostgreSQL for both Django services, with a separate database and credentials for each. Each service's credentials grant access only to its own application database.
- **Why:** Existing PostgreSQL experience makes it a familiar choice to implement and operate. It fits the relational domain and offers a clear path to a managed production deployment through AWS RDS. Separate databases and credentials preserve the boundary between content and authentication data.
- **Accepted tradeoff:** PostgreSQL requires database-server setup and operation rather than SQLite's file-based setup. Both services use the same engine to keep the technology stack consistent.
- **Scope:** Database-server topology and any AWS deployment remain undecided. This decision does not change the existing WordPress MariaDB migration source.

## 2026-11-19 — Import with per-database transactions and safe reruns

- **Decision:** Import auth accounts first in one auth-database transaction, then import content in one main-database transaction. Each service writes only to its own database. Do not introduce distributed transactions for this challenge.
- **Idempotency:** Match imported records by stable WordPress IDs backed by uniqueness constraints. Reruns reuse existing records and auth UUIDs rather than create duplicates or regenerate account identities.
- **Failure and recovery:** A failed phase rolls back its database changes. If auth commits and content fails, the auth records remain while all changes from the content phase roll back. Fix the failure and rerun, reusing the committed auth identities.
- **Why:** This provides atomic changes within each service and straightforward recovery without the coordination and operational complexity of a global transaction. Temporary completion of only the auth phase is an accepted tradeoff.
- **Rerun policy:** Create missing records and preserve existing records, as detailed below.

## 2026-11-19 — Query a fresh MariaDB restore for source extraction

- **Decision:** Restore the committed `db/dump.sql` into a fresh MariaDB source database, then extract the required data through read-only SQL queries.
- **Why:** A fresh restore makes the input reproducible and avoids drift from edits in an existing WordPress database volume. Direct queries provide access to all required accounts, raw content, custom fields, relationships, and source IDs. MariaDB handles the dump's SQL syntax and escaping, avoiding a custom dump parser and REST pagination or visibility constraints.
- **Accepted tradeoff:** Extraction requires a running MariaDB instance and knowledge of WordPress's storage schema. That is appropriate for this known migration source.
- **Scope:** Restore into a fresh source database rather than reset an existing working database. The agreed PostgreSQL destinations, per-database transactions, and safe-rerun behavior remain unchanged.

## 2026-11-19 — Keep the importer create-only and reproducible

- **Decision:** Create missing records and their required relationships. Recognize existing records by their WordPress IDs and reuse them without overwriting their fields, relationships, credentials, roles, or identifiers. Repeating a successful import against the same source should be a no-op for application data.
- **Why:** This is a one-time migration with safe retries after failure. After cutover, Django owns the data. Field-by-field synchronization and conflict resolution are unnecessary for this requirement.
- **Recovery:** Retain the agreed per-database transactions. If auth succeeds and content fails, a retry reuses the existing auth accounts and imports the missing content without resetting account state.
- **Accepted tradeoff:** Reruns do not refresh existing records when source data or import mappings change. During development, revised imports can be tested against fresh disposable destination databases.
- **Reproducibility:** Keep the importer and its run instructions in the submitted repository so reviewers can recreate the migration and verify safe reruns. It need not remain in operational use after cutover.

## 2026-11-19 — Approve the Brand and Industry schema

Both models belong to the main application. The approved Brand fields are:

| Field | Django type | Requirement |
|---|---|---|
| `id` | `BigAutoField` | Automatically generated primary key, independent of WordPress IDs. |
| `wordpress_id` | `PositiveBigIntegerField` | Required for imported records; otherwise nullable. Unique and positive when present. |
| `name` | `CharField(max_length=200)` | Required, non-whitespace text; not unique. |
| `slug` | `SlugField(max_length=200)` | Required and unique; preserve the imported WordPress slug exactly. |
| `description_html` | `TextField` | Optional sanitized semantic HTML. |
| `short_description` | `CharField(max_length=500)` | Optional plain text. |
| `website_url` | `URLField(max_length=2048)` | Optional; valid HTTP or HTTPS URL when supplied. |
| `founded_year` | `PositiveSmallIntegerField` | Optional; 1800–2100 when supplied, matching the source field bounds. |
| `headquarters` | `CharField(max_length=200)` | Optional free-text location. |
| `industries` | `ManyToManyField` | Zero or more Industry records. |
| `top_review` | `ForeignKey(Review, on_delete=SET_NULL)` | Optional (`null=True`, `blank=True`); one editor-selected review belonging to this brand. Database column: `top_review_id`. |

The approved Industry fields are:

| Field | Django type | Requirement |
|---|---|---|
| `id` | `BigAutoField` | Automatically generated primary key. |
| `wordpress_id` | `PositiveBigIntegerField` | Source `wp_terms.term_id`, not `term_taxonomy_id`. Required for imports; otherwise nullable. Unique and positive when present. |
| `name` | `CharField(max_length=200)` | Required, non-whitespace text; not unique. |
| `slug` | `SlugField(max_length=200)` | Required and unique. |

- **Content format and rationale:** Preserve meaningful structure in the full description, including paragraphs, headings, lists, emphasis, and links, using an allowlist of semantic HTML elements and safe attributes. Exclude inline styling, layout markup, and theme-specific classes; visual presentation belongs in frontend templates/components and CSS/SCSS. Plain text is sufficient for the short description, whose 500-character limit bounds listing-card content. Keep sanitization as a small main-importer helper using an existing library; its exact implementation and allowlist remain implementation details.
- **Optional content:** Empty descriptions and zero industry associations are valid. Optional text uses an empty string; missing numeric/source-ID values use `NULL`. Initialize the short description from the WordPress excerpt, falling back to the body, using the plain-text conversion and shortening rules recorded in the importer execution decision below. The create-only importer preserves it afterward.
- **Relationships:** Use Django's generated many-to-many linking table, with valid foreign keys and a unique brand–industry pair. No hierarchy, primary industry, or additional relationship attributes are needed. Removing a link leaves both records intact; deleting an industry removes its links without deleting brands. Reviews protect their referenced brand from deletion. The optional `top_review` reference is cleared if its selected review is deleted, leaving the brand intact. Validate that the selected review belongs to the brand; the foreign key alone only guarantees that the review exists.
- **Constraints:** Back uniqueness, nonblank names/slugs, positive source IDs, and the optional founding-year range with database constraints. Validate field lengths, slug syntax, and URL format through the application as appropriate; model saves alone do not run full field validation.
- **Scope and rationale:** These fields cover displayed brand information, industry filtering, stable URLs, and import identity without recreating WordPress's generic metadata structure. Names are display labels rather than identities. Derive average ratings and review counts from reviews. Store the editor-selected top review reference on Brand, as approved in the revised top-review decision below. Omit Yoast metadata, ACF bookkeeping, logos, and a generic metadata JSON field from these models.

## 2026-11-19 — Approve the Review and Reviewer schema

Both models belong to the main application. Reviewer represents a public author profile; Review represents one published review. The approved Reviewer fields are:

| Field | Django type | Requirement |
|---|---|---|
| `id` | `BigAutoField` | Automatically generated local primary key. |
| `wordpress_id` | `PositiveBigIntegerField` | Source `wp_users.ID`. Required for imported profiles; otherwise nullable. Unique and positive when present. |
| `auth_user_id` | `UUIDField` | Required and unique; reuse the account's stable public UUID from the auth service. |
| `display_name` | `CharField(max_length=250)` | Required, non-whitespace public name; not unique. The length matches the WordPress account display-name limit. |

The approved Review fields are:

| Field | Django type | Requirement |
|---|---|---|
| `id` | `BigAutoField` | Automatically generated local primary key. |
| `wordpress_id` | `PositiveBigIntegerField` | Source review post ID. Required for imported reviews; otherwise nullable. Unique and positive when present. |
| `brand` | `ForeignKey(Brand, on_delete=PROTECT)` | Required; exactly one existing brand. |
| `reviewer` | `ForeignKey(Reviewer, on_delete=PROTECT)` | Required; exactly one existing reviewer profile. |
| `title` | `CharField(max_length=250)` | Required, non-whitespace text; not unique. |
| `slug` | `SlugField(max_length=200)` | Required and unique; preserve the imported WordPress slug exactly. |
| `body_html` | `TextField` | Optional sanitized semantic HTML; an empty body is valid. |
| `rating` | `PositiveSmallIntegerField` | Required whole number from 1 through 5. |
| `published_at` | `DateTimeField` | Required timezone-aware original publication timestamp. |
| `reviewer_name` | `CharField(max_length=250)` | Optional review-specific public byline. |
| `reviewer_location` | `CharField(max_length=200)` | Optional review-specific location. |

- **Identity and service boundary:** Reviews reference the local Reviewer primary key through a real foreign key. `auth_user_id` is an ordinary UUID column identifying an account in the separate auth database, not a cross-database foreign key. The import establishes the mapping; the main database enforces uniqueness but cannot enforce the external account's existence. Authentication, credentials, account status, and roles remain owned by auth. Reviewer stores no password, role, or email. An auth account may exist without a reviewer profile.
- **Attribution and rationale:** Preserve the source's distinction between the account author and review-specific name/location. Display `Review.reviewer_name` when populated; otherwise fall back to `Reviewer.display_name`. Profile name changes leave populated review bylines unchanged but affect the fallback for reviews with blank names. This accepted behavior preserves optional source attribution without requiring a frozen name on every review. Location belongs to the individual review, not a current address on the profile.
- **Relationships and deletion:** A brand and a reviewer can each have many reviews. Allow multiple reviews by the same reviewer for the same brand; do not add a unique brand–reviewer constraint, since Sarah's existing reviews already require this. Use `PROTECT` on both foreign keys to reject deletion of referenced brands or reviewers and prevent accidental loss of published reviews. Disabling an auth account leaves its local profile and published reviews intact; there is no cross-service deletion cascade.
- **Content format and optional values:** Apply the same sanitized semantic HTML approach approved for Brand, preserving content structure while leaving styling to the frontend. Empty bodies allow a title and rating without a narrative. Optional text uses an empty string; missing optional WordPress IDs use `NULL`.
- **Constraints and validation:** Back unique slugs, unique source IDs when present, unique auth UUIDs, nonblank required text, positive source IDs, and the rating range with database constraints as appropriate. A positive integer field alone does not enforce the 1–5 rating range. Validate field lengths, slug syntax, and sanitized content through the application/import path. The title and review-attribution length limits are application rules; report oversized source values rather than silently truncate them.
- **Publication dates:** Import valid `post_date_gmt` values as aware UTC datetimes. Preserve the original publication time rather than automatically assigning the import time. Invalid or zero source dates cause an import error rather than an invented timestamp.
- **Scope and rationale:** Import published reviews without adding draft or moderation workflow fields for this challenge. Keep author identity relational, preserve existing URLs and displayed review content, and support the agreed create-only reruns through source IDs. Brand averages and review counts remain derived from reviews. This approval records the schema only; implementation remains deferred.

## 2026-11-19 — Approve the auth service schema and token lifecycle

Use a custom User model extending Django's `AbstractUser`, with one application role per user, and a separate AccessToken model. Both belong to the auth service's PostgreSQL database. Configure `AUTH_USER_MODEL` before the first database migration. The approved User fields are:

| Field | Django type | Requirement |
|---|---|---|
| `id` | `BigAutoField` | Automatically generated internal primary key, referenced by tokens. |
| `public_id` | `UUIDField` | Automatically generated, required, and unique. Stable public identity, generated once and preserved. |
| `wordpress_id` | `PositiveBigIntegerField` | Source `wp_users.ID`. Required for imported accounts; otherwise nullable. Unique and positive when present. |
| `username` | `CharField(max_length=150)` | Required, unique, nonblank login identifier; preserve the WordPress username. |
| `email` | `EmailField(max_length=254)` | Optional and not unique; preserve the source email. Login uses usernames. |
| `password` | Django's inherited password field | Managed through Django's password helpers; store an encoded password hash, never plaintext. |
| `role` | `CharField(max_length=16)` | Required; `reader` or `editor`, defaulting to `reader`. |
| `is_active` | `BooleanField` | Required; defaults to `True`. Checked at login and introspection. |
| `date_joined` | `DateTimeField` | Required; preserve the original registration timestamp during import. |
| `last_login` | `DateTimeField` | Optional; initially `NULL`, recording the last successful login. |

Retain Django's standard optional `first_name` and `last_name` fields and its `is_staff` and `is_superuser` flags, normally defaulting to false. The inherited group and individual-permission relationships are not the authorization source for the main application's API. Public display names remain on the main application's Reviewer model.

The approved AccessToken fields are:

| Field | Django type | Requirement |
|---|---|---|
| `id` | `BigAutoField` | Automatically generated internal token-record identifier. |
| `user` | `ForeignKey(User, on_delete=CASCADE)` | Required; exactly one auth user. A user may have multiple tokens. |
| `token_digest` | `CharField(max_length=64)` | Required and unique; SHA-256 hexadecimal digest of the random bearer token. |
| `created_at` | `DateTimeField` | Automatically assigned issuance time. |
| `expires_at` | `DateTimeField` | Required fixed expiration time. |
| `revoked_at` | `DateTimeField` | Optional; `NULL` until explicitly revoked. |

- **User model and identity rationale:** Extend Django's standard user behavior to reuse password handling and account fields while adding import identity, a stable external UUID, and the application role. `User.public_id` is the value stored in the main application's `Reviewer.auth_user_id`; it is an identifier, not a credential or cross-database foreign key. Preserve it on reruns. Optional, nonunique email avoids imposing an unnecessary identity rule when usernames are the login identifiers.
- **Roles and rationale:** Use `TextChoices` for named Python role values and a database check restricting `role` to `reader` or `editor`. Each user has exactly one application role. Readers have no protected editing permission; editors may use the protected brand-editing operation. Public reads require no login. A single field makes role changes unambiguous without introducing multiple-group combinations or competing permission sources. Neither Django's staff nor superuser flag substitutes for the editor role in the main API. Multiple independent roles are an accepted future limitation, to revisit only if needed.
- **Initial role mapping:** Map WordPress subscribers to `reader` and the WordPress administrator to `editor`. Do not automatically grant Django staff or superuser privileges to the imported administrator. Preserve existing roles on import reruns.
- **Passwords:** Set new passwords through Django's password helpers when accounts are first imported, as permitted by the challenge. Reruns preserve existing passwords. Supply the explicitly configured local-demo password through the auth importer's environment, as recorded in the importer execution decision below.
- **Token storage and rationale:** Generate cryptographically secure random bearer tokens, return the raw value to the client once, and store only its SHA-256 digest. Introspection hashes the presented token and performs an indexed lookup using the unique digest. This avoids directly exposing usable bearer tokens through a read-only database leak. Token hashing applies to high-entropy random secrets; passwords continue to use Django's password hashing.
- **Token validity and current permissions:** On every protected request, introspection requires a matching token, `now < expires_at`, no revocation, and an active user. Return the user's stable UUID and current role; do not snapshot the role onto the token. Subsequent authorization checks therefore reflect role changes without reissuing tokens. Retain the agreed absence of authorization caching.
- **Lifetime and expiration:** Tokens have a configurable one-hour lifetime from issuance, with no sliding extension. Clients log in again after expiry; refresh tokens are a separate feature. The hour limits credential validity, not database-row retention: the row remains after expiry, and introspection rejects it based on `expires_at`.
- **Cleanup scope and rationale:** Do not implement token-record cleanup for this challenge. Expiration enforcement does not depend on deletion, and cleanup adds operational work without serving a challenge requirement. In a production system, periodically remove expired records once they no longer serve a retention purpose, avoiding indefinite accumulation. Cleanup cadence and any retention period remain outside this challenge's scope.
- **Revocation and deletion:** Explicit revocation can invalidate one token while leaving other logins usable. Account disabling or password changes revoke all of that account's tokens, so re-enabling an account does not revive old tokens. Prefer disabling accounts for normal access removal. Hard-deleting an auth user cascades to that user's token rows only; main-application reviewer profiles and reviews remain intact.
- **Constraints:** Enforce unique public UUIDs, unique nonblank usernames, unique positive WordPress IDs when present, allowed role values, unique token digests, and valid token-user foreign keys. Require `expires_at > created_at` and, when present, `revoked_at >= created_at`. Use timezone-aware timestamps. Check current expiry at request time rather than storing an `is_expired` flag. Field-format validation and Django password helpers remain application responsibilities.
- **Scope:** This approval records the schema and lifecycle decisions only; implementation remains deferred.

## 2026-11-19 — Approve the brand listing API contract

- **Endpoint and rationale:** Public `GET /api/brands/`, requiring neither a bearer token nor an auth-service call. Return enough structured data in one response for web and native mobile clients to render complete brand cards. Preserve the route required by the challenge. Implement the API using plain Django views, as recorded in the framework decision below.

The approved query parameters are:

| Parameter | Accepted values and behavior | Default |
|---|---|---|
| `industry` | Industry slug; repeat the parameter to select multiple industries. | No filter; include all brands. |
| `sort` | One of `average_rating`, `-average_rating`, `review_count`, or `-review_count`. A leading minus means descending. | `-average_rating` |
| `page` | Positive integer, starting at 1. | `1` |
| `page_size` | Integer from 1 through 100. | `20` |

- **Filtering:** Repeated industry values use OR semantics. For example, `industry=insurance&industry=finance` matches brands associated with either industry. Return each matching brand once, including all of its industry associations in the response. Brands with zero industries remain eligible for the unfiltered listing. Filtering must not multiply brands or their review aggregates.
- **Sorting:** Sort on the unrounded average or review count, then break ties by brand name and ID in ascending order. Brands with no reviews have no average and sort last for average-rating ordering in either direction.

The response envelope contains:

| Field | Shape and meaning |
|---|---|
| `count` | Integer total of matching brands across all pages. |
| `next` | Complete next-page API URL, preserving filters, sort, and page size; otherwise `null`. |
| `previous` | Complete previous-page API URL, preserving filters, sort, and page size; otherwise `null`. |
| `results` | Array of brand card objects for the requested page. |
| `available_industries` | Array of all industry choices as `{slug, name}`, independent of the current filter or page. |

Each brand card contains:

| Field | Shape and meaning |
|---|---|
| `id` | Main-application brand ID serialized as an opaque string, not the WordPress ID. |
| `name` | Brand name string. |
| `slug` | Brand slug string. |
| `industries` | Array of `{slug, name}` objects; `[]` when there are no associations. |
| `average_rating` | JSON number rounded to two decimal places, or `null` when there are no reviews. |
| `review_count` | Integer count of the brand's reviews; `0` when there are none. |
| `short_description` | Plain text string; may be empty. |
| `top_review` | Editor-selected review object, or `null` when no selection exists, even if the brand has reviews. |

The selected review object contains `id` (main-application ID serialized as a string), `slug`, `title`, integer `rating`, resolved `reviewer_name`, `published_at` as an explicit UTC ISO 8601 timestamp, and a plain text `snippet`.

- **Pagination and rationale:** Use page-number pagination with bounded page sizes. Mobile clients can follow `next` for load-more behavior; web clients can use the same contract for numbered pages. Reset to page 1 when filters or sorting change. This is sufficient for the challenge's directory and avoids cursor complexity around mutable aggregate sort values. Deterministic tie-breakers stabilize an unchanged dataset, but pagination does not freeze it: changes between requests can move brands between pages.
- **Top review selection and rationale:** The challenge explicitly requires a top review snippet and leaves its definition to us. Use the editor-selected review referenced by `Brand.top_review`, representing an editorial judgment of helpfulness. Label it as an "Editor's pick" while selection is manual. Return `null` when no selection exists; do not fall back to rating, recency, or any automatic ranking. This replaces the original highest-rating/newest/highest-ID rule, as recorded in the revised decision below.
- **Snippet and attribution:** Convert the selected review's sanitized body to plain text, preserving spaces between paragraphs and normalizing whitespace. Limit the snippet to 240 characters, ending at a word boundary and including an ellipsis when truncated. If the body is empty, use the title under the same limit. Apply the approved review-name fallback to the current Reviewer display name when the review-specific name is blank.
- **Filter options and rationale:** Include all `available_industries` in each response so the first listing request also supplies the filter choices. Repeating this small taxonomy is an accepted tradeoff for avoiding an additional request and endpoint. Do not derive the choices only from brands on the current page or under the current filter.
- **Mobile compatibility and rationale:** Keep field names, types, and missing-value conventions stable. Plain text card content can be rendered directly by native clients; clients format UTC timestamps for their locale. IDs are opaque strings suitable for list keys and local storage. An unrated brand returns `average_rating: null`, `review_count: 0`, and `top_review: null`; a zero average would misrepresent the 1–5 rating scale. Clients should tolerate additional response fields, while breaking changes require a separately versioned contract to support older installed apps.

The approved response behavior is:

| Situation | HTTP response |
|---|---|
| Valid filters with no matching brands on the initial page | `200`, with `count: 0`, `results: []`, and no next/previous page. |
| Invalid sort, unknown industry slug, or malformed pagination | `400` with a structured error. |
| Requested page beyond the available pages | `404` with error code `page_not_found`. |
| Page size above 100 | `400` explaining the limit; do not silently clamp it. |

- **Errors and rationale:** Return an `error` object with a stable machine-readable `code`, a human-readable `message`, and the relevant query `parameter`. For example: `{"error":{"code":"invalid_sort","message":"Unsupported sort value.","parameter":"sort"}}`. Clients can use the code for behavior or translated messages without parsing English text.
- **Scope:** This approval records the API contract and rationale only; implementation remains deferred.

## 2026-11-19 — Revise top reviews to use editor selection

- **Decision and rationale:** Treat the top review as a review an editor considers helpful, rather than automatically choosing the highest star rating. A detailed lower-rated review may be more useful than a brief positive one. Manual curation supports that meaning without building voting or helpfulness scoring. Present the selection as an "Editor's pick" without implying community votes.
- **Schema:** Add optional `Brand.top_review`, a foreign key to Review with `null=True`, `blank=True`, and `on_delete=SET_NULL`. Django stores the selected review's local ID in `top_review_id`. A brand has at most one selection; choosing another review replaces the reference.
- **Integrity and deletion:** The selected review must belong to that brand. Validate this in the selection write path and any other path that can change the relationship; an ordinary foreign key only guarantees that the review exists. Deleting the selected review clears the reference without deleting the brand. The existing `Review.brand` and `Review.reviewer` deletion protection remains in effect.
- **Authorization:** Only users with the auth service's current `editor` role may select, replace, or clear the selection through a protected write operation. This includes the imported WordPress administrator, which maps to editor. Check permissions through introspection on every protected request; Django staff/superuser flags do not independently grant this API permission. The approved brand-update request/response contract is recorded below.
- **Listing behavior:** Keep the existing `top_review` response object and snippet/attribution rules. Resolve it from the explicit selection. When no review is selected, return `top_review: null`, including for brands with reviews. There is no automatic fallback. Average ratings and review counts remain derived from all of the brand's reviews.
- **Initial data and reruns:** The WordPress source has no curated selection, so imported brands initially have no top review. Any demonstration selections should be deliberate editorial choices made afterward. The create-only importer preserves existing selections on reruns.
- **Supersedes:** Replace the earlier decision to derive the top review using highest rating, newest publication, and highest ID, and the earlier exclusion of a stored top-review reference from Brand. The Brand schema and listing contract above have been updated to reflect this revision.
- **Scope:** Voting, helpfulness scores, and a separate editor interface are not part of this change. This records the revised decisions and rationale only; implementation remains deferred.

## 2026-11-19 — Approve the protected brand update API contract

- **Endpoint and rationale:** Use `PATCH /api/brands/<slug>/` with `Authorization: Bearer <opaque-token>` and `Content-Type: application/json`. One editor-only endpoint updates either or both of the supported fields. Partial updates let web and mobile clients submit only what changed.

The approved request fields are:

| Field | Accepted value | When omitted | How to clear |
|---|---|---|---|
| `short_description` | Plain text string of up to 500 characters. | Leave unchanged. | Send `""`. |
| `top_review_id` | String containing an existing review's application ID; the review must belong to this brand. | Leave unchanged. | Send `null`. |

- **Validation:** Require a JSON object with at least one supported field. Reject empty objects, arrays, other non-object bodies, and unknown or read-only fields such as `name`, `slug`, and `average_rating`. Reject `null` for `short_description`; missing text is represented by an empty string. Preserve submitted text without silently truncating it and render it as plain text. Require review IDs as strings, consistent with the listing contract; do not accept WordPress IDs as import identifiers in this endpoint. A missing review or a review belonging to another brand is a field-validation error.
- **Authorization:** Before updating, introspect the bearer token and require an active account with the current `editor` role. This applies to both fields. Readers may edit neither field. The imported WordPress administrator qualifies through its editor role; Django staff/superuser flags are not an independent permission source. If auth cannot complete validation, fail closed without changing the brand.
- **Atomicity and rationale:** Apply all submitted changes together or none of them. If the description is valid but the selected review is invalid, save neither change. This prevents partially applied edits and gives clients one unambiguous outcome for the requested update.
- **Success response and mobile rationale:** Return `200 OK` with the complete updated brand card, using the same object shape as one item in the listing's `results` array, without the pagination envelope. Expand `top_review` using the approved review/snippet shape when selected; return `null` after clearing it, with no fallback. Clients can replace their local card with the server's resulting state without another request or reconstructing the snippet. Assigning values that already match the stored values also returns `200`.

The approved errors are:

| Situation | HTTP status | Error code |
|---|---|---|
| Missing bearer token | `401` | `authentication_required` |
| Invalid, expired, or revoked token, or inactive account | `401` | `invalid_token` |
| Valid account with the reader role | `403` | `permission_denied` |
| Brand slug does not exist, after authorization succeeds | `404` | `brand_not_found` |
| Malformed JSON | `400` | `invalid_json` |
| Non-object body or empty update | `400` | `invalid_request` |
| Invalid field value or unsupported field | `400` | `validation_error` |
| Unsupported content type | `415` | `unsupported_media_type` |
| Auth service unavailable, timed out, or returned an unusable response | `503` | `auth_unavailable` |

- **Error shape:** Retain the `error` wrapper with stable machine-readable `code` and human-readable `message`. For body-validation errors, add `fields`, a map from field name to a list of objects containing `code` and `message`, so multiple field errors can be reported together. Omit `fields` for errors unrelated to a field. Listing query errors continue to use `parameter` for query parameters. A missing or wrong-brand review produces a `400` field error, not the `404` reserved here for the brand addressed by the URL.

Example field-validation error:

```json
{
  "error": {
    "code": "validation_error",
    "message": "One or more fields are invalid.",
    "fields": {
      "top_review_id": [
        {
          "code": "invalid_selection",
          "message": "Select an existing review belonging to this brand."
        }
      ]
    }
  }
}
```

- **Authentication error behavior and rationale:** Include `WWW-Authenticate: Bearer` on `401` responses, with `error="invalid_token"` when applicable. A `401` indicates missing or unusable credentials and can prompt login; a `403` indicates insufficient permission. A `503` means auth could not validate the request, not that the user's token is invalid. Clients should keep the user logged in and offer a retry for that outage.
- **Concurrency and accepted tradeoff:** Use last-write-wins for each submitted field. Update only submitted fields so an editor changing only the description does not overwrite another editor's top-review selection, and vice versa. If editors change the same field, the last successful write wins. Do not add version numbers or conditional-update headers for this challenge. Repeating an assignment has the same effect in isolation, but retrying after a network timeout can overwrite an intervening edit. Atomicity prevents partial updates; it does not detect stale editing sessions.
- **Scope:** This approval records the request, response, error, and concurrency contract only; implementation remains deferred.

## 2026-11-19 — Approve the login and token introspection API contracts

- **Endpoints and rationale:** Provide `POST /api/login/` for mobile/browser clients or curl to exchange credentials for a token, and `POST /api/tokens/introspect/` for the main application's backend to check tokens. Both accept JSON with `Content-Type: application/json` and return JSON. This is an application-specific JSON API using the active/inactive introspection convention, not a claim of full OAuth or RFC 7662 protocol compliance.

The login request contains required string fields `username` and `password`. Use the login username, not email. Check passwords exactly as supplied, without trimming or truncation. Require an object; reject malformed JSON, missing or incorrectly typed fields, and unsupported fields. No existing user token or service credential is required to log in.

Successful login returns `200 OK` with:

| Field | Shape and meaning |
|---|---|
| `access_token` | Newly issued raw opaque token, returned once; auth stores only its digest. |
| `token_type` | String `Bearer`. |
| `expires_in` | Configured token lifetime in seconds; `3600` for the approved one-hour lifetime. |
| `expires_at` | Expiration timestamp as an explicit UTC ISO 8601 string. |
| `user` | Object containing `id`, `username`, and `role`. `id` is the stable public UUID matching `Reviewer.auth_user_id`, not the auth database's integer primary key. `role` is `reader` or `editor`. |

- **Login behavior:** Both readers and editors may log in. Each successful login creates an additional token and updates `last_login`, without revoking existing sessions. The role returned at login is a snapshot useful for client presentation; protected operations continue to authorize against fresh introspection. Do not issue a refresh token.
- **Login rejection and rationale:** Return the same `400 invalid_credentials` response for an unknown username, incorrect password, or disabled account, with the generic message `Invalid username or password.` This avoids disclosing account existence or state. Treat this as a rejected JSON credential exchange; protected endpoint `401` responses continue to indicate missing or invalid authorization credentials.

The approved login errors are:

| Situation | HTTP status | Error code |
|---|---|---|
| Malformed JSON | `400` | `invalid_json` |
| Body is not an object | `400` | `invalid_request` |
| Missing, invalid, or unsupported fields | `400` | `validation_error` |
| Rejected credentials or disabled account | `400` | `invalid_credentials` |
| Unsupported content type | `415` | `unsupported_media_type` |
| Auth temporarily cannot complete the operation | `503` | `auth_unavailable` |

- **Introspection service authentication and rationale:** Require a separate configured service credential, consisting of a client name such as `main-app` and a random secret, sent using HTTP Basic authentication. This authorizes the main backend to query tokens and is separate from the user's bearer token being examined. No additional user, role, or service-account table is needed. Keep this credential in backend configuration, never in mobile or browser code. Basic authentication is encoding, not encryption; deployed traffic must use HTTPS.

The introspection request uses `Authorization: Basic <encoded-service-credentials>` and a JSON object with one required, nonempty string field, `token`. The value is the user's opaque bearer token. The authorization header authenticates the calling service; the body supplies the user token to inspect. Reject missing, empty, or non-string token values and unsupported fields.

- **Active response:** Return `200 OK` with `active: true`, `expires_at` as a UTC ISO 8601 timestamp, and the same `user` object shape used at login (`id`, `username`, `role`). Require that the token exists, is unexpired, is unrevoked, and belongs to an active account. Read the user's current role. Introspection does not extend expiration, issue another token, or update `last_login`.
- **Inactive response and rationale:** For a properly authenticated request containing an unknown, expired, or revoked token, or a token belonging to a disabled account, return `200 OK` with only `{"active": false}`. Include no user details or inactivity reason. The lookup succeeded and found an inactive token; this is distinct from a failure to perform the lookup. An unknown nonempty token string is inactive, while a missing or incorrectly typed token field is a validation error. Never disguise infrastructure failures as an inactive-token result.
- **Caching:** Include `Cache-Control: no-store` on login and introspection responses. Login responses contain credentials; introspection results must not become stale authorization decisions. The main app continues to introspect every protected request without caching results.

The approved introspection errors are:

| Situation | HTTP status | Error code |
|---|---|---|
| Missing or incorrect service credentials | `401` | `invalid_client` |
| Malformed JSON | `400` | `invalid_json` |
| Body is not an object | `400` | `invalid_request` |
| Missing, empty, or non-string token, or unsupported fields | `400` | `validation_error` |
| Unsupported content type | `415` | `unsupported_media_type` |
| Auth cannot complete the check | `503` | `auth_unavailable` |

- **Error representation:** Use the existing `error` object with stable `code` and human-readable `message`, and the approved `fields` map for field-validation errors. An introspection service-authentication failure uses code `invalid_client`, message `Service authentication failed.`, and `WWW-Authenticate: Basic realm="auth-introspection"` on the `401` response.

The main application maps introspection outcomes as follows:

| Introspection outcome | Main-application behavior |
|---|---|
| Active token with current role `editor` | Continue validating and applying the protected brand update. |
| Active token with current role `reader` | Return `403 permission_denied`. |
| Inactive token | Return `401 invalid_token`. |
| Timeout, non-success response, or malformed/unusable response | Return `503 auth_unavailable`; make no change. |

- **Response validation and failure rationale:** Validate the introspection response shape, public UUID, and recognized role before trusting it. In particular, an introspection `401 invalid_client` means the main backend's service authentication failed; map it to `503` for the end user instead of prompting that user to log in again. This preserves the distinction between invalid user credentials and a service problem, while failing closed on protected writes.
- **Scope:** This approval records login and introspection contracts, service authentication, and error behavior only. The internal-revocation and logout-API scope is recorded below. No implementation changes are authorized by this entry.

## 2026-11-19 — Keep internal token revocation in scope; omit the logout API

- **Decision:** Include auth-internal operations to revoke one token or all tokens belonging to an account. Do not add a public logout or token-revocation HTTP endpoint for this challenge.
- **Rationale:** The challenge requires login and role-based access and asks how revocation works before token expiry, but does not require a logout endpoint. Small internal operations provide demonstrable revocation without expanding the public API or building a session-management interface.
- **Preserve the approved lifecycle:** Explicitly revoke outstanding tokens when an account is disabled or its password changes. Re-enabling an account must not revive those tokens. These opaque-token records require explicit revocation; changing a password or checking `is_active` alone is insufficient to implement the agreed lifecycle. This does not introduce a public password-reset flow.
- **Validation and demonstration:** Test that introspection rejects revoked tokens and reflects current roles. Document how to demonstrate revocation by invoking the auth-internal operations through Django's shell, alongside the relevant tests.
- **Logout distinction:** Removing a token from a client only removes that client's copy; it does not invalidate other copies. Server-side revocation makes the token unusable on subsequent checks wherever it is presented.
- **Scope:** Public logout/revocation endpoints and a session-management interface are excluded. Token-record cleanup remains excluded under the earlier decision. This entry records the approved scope and rationale only; implementation remains deferred.

## 2026-11-19 — Keep role changes internal; omit the role-change API

- **Decision:** Provide an auth-owned internal operation for trusted operators to change a user's role between `reader` and `editor`, callable through Django's shell. Do not add a role-change HTTP endpoint for this challenge.
- **Rationale:** The challenge requires role-based access and an explanation of how role changes take effect before token expiry, but does not require a role-management API. An internal operation and a documented demonstration satisfy that need without expanding the public API or introducing a role-management interface.
- **Authorization behavior:** Introspection reads the user's current role on every protected request. Changing a role therefore affects subsequent authorization checks without revoking or replacing existing tokens. This preserves the distinction between a valid token and permission to perform an operation; it does not retroactively cancel a request already authorized.
- **Administrative boundary:** Role changes are trusted auth-administration operations. Permission to edit brand content does not automatically grant permission to assign roles. Keep role ownership in the auth service and validate the allowed role values.
- **Validation and demonstration:** Test and document an editor login followed by an internal change to reader, then reuse the same unexpired token for the protected brand update. Introspection should report the current reader role and the main application should return `403 permission_denied`.
- **Scope:** The role-change API is excluded. The previously approved revocation behavior for account disabling and password changes remains unchanged. This entry records the scope and rationale only; implementation remains deferred.

## 2026-11-19 — Use plain Django views for both services

- **Decision:** Implement the main application's and auth service's API endpoints using plain Django function-based views and `JsonResponse`. Use Django's existing models, ORM, password handling, transactions, and pagination support.
- **Rationale:** The API has four endpoints with explicit contracts. Plain views are proportionate to that scope and make the request handling straightforward to trace. Familiarity with Python, a desire to refresh Django gradually, and avoiding another framework to learn outweigh the convenience of DRF or Django Ninja's additional abstractions for this challenge.
- **Accepted tradeoff:** Own the API-specific parsing, strict input validation, authentication/permission integration, response serialization, pagination envelope, and error formatting. Preserve all approved contracts, including unknown-field rejection, string IDs, omission versus clearing, atomic updates, and the specified status codes; choosing plain views does not relax these rules.
- **Code organization:** Keep endpoint behavior explicit and use small, focused helpers for repeated behavior so the two services remain consistent. Keep application operations understandable independently of HTTP request handling. The approved shared Python package contents and boundaries are recorded below.
- **Scope:** This records the framework choice and rationale only. No implementation changes are authorized by this entry.

## 2026-11-19 — Approve the shared Python library boundaries

- **Decision and rationale:** Create a small auth-focused, installable Python package containing ordinary Python functions and data structures. Share authentication contracts and checks while keeping database ownership and service-specific operations in their services. This meets the shared-library requirement, keeps request handling explicit, and avoids coupling either service to the other's models or settings.

The package contains:

| Shared responsibility | Auth service use | Main application use |
|---|---|---|
| Role definitions (`reader`, `editor`) | Define and validate allowed account roles. | Interpret the current role returned by introspection. |
| Identity and token-result structures | Construct results containing public UUID, username, role, and expiry. | Consume the same information as predictable Python data. |
| Introspection response encoding and validation | Build the approved response shape. | Validate and read that response. |
| Token-verification function | Supply an auth-database lookup. | Supply an HTTP introspection lookup. |
| Editor permission check | No current editor-only auth endpoint needs this check. | Protect brand updates. |
| Common error types and error-payload construction | Represent auth failures and format error payloads. | Represent main-application failures and format error payloads. |

- **Injected lookup and rationale:** Use a function such as `verify_token(token, lookup=...)`. It calls the supplied lookup, rejects inactive or expired tokens, and returns a verified identity as plain Python data. Passing a lookup function lets both services execute the same verification code without the package owning a database or making auth call itself over HTTP. The editor permission check naturally has a main-application caller; do not invent an auth endpoint solely to give it another consumer.
- **Auth lookup:** Auth's service-local lookup hashes the token, queries its own database, checks revocation and account status, and supplies the current identity and expiration information. Auth's introspection view first authenticates the calling service using its Basic credential, then invokes shared verification with this database lookup.
- **Main lookup:** The main application's service-local lookup calls introspection using its configured service credential and validates the response through the shared contract code. The protected view explicitly calls shared verification with this HTTP lookup and then the shared editor permission check. Continue calling auth on every protected request; the helper introduces neither an authorization cache nor independent local verification of opaque tokens.
- **Plain-view integration:** Start with explicit function calls inside plain Django views. A custom decorator is not needed initially. The returned identity is not an auth User model copied into the main application. Each service supplies configuration; the package imports neither service's models nor settings.

Keep these responsibilities inside their services:

| Main application | Auth service |
|---|---|
| Brand, Industry, Review, and Reviewer models. | User and AccessToken models. |
| Brand queries, averages, counts, and selected-review loading. | Password verification and token issuance. |
| Brand-update validation and transactions. | Token generation, hashing, storage, and revocation. |
| HTML sanitization and content migration. | Account disabling, internal role changes, and account migration. |
| Templates and brand/review response construction. | Validation of the main application's service credentials. |
| Introspection HTTP connection, including URL, credentials, and timeout. | Auth-database lookup implementation. |

- **Failure boundaries:** Shared verification describes outcomes through ordinary error types such as `InvalidToken` and `AuthUnavailable`; service views map them to the approved HTTP contracts. Invalid/inactive tokens produce `200 {"active": false}` from auth introspection but `401 invalid_token` from a protected main endpoint. Verification unavailability produces `503 auth_unavailable`. A valid reader remains active in introspection but fails the main application's editor permission check with `403 permission_denied`. Shared error-payload construction does not decide the HTTP status.
- **Package organization:** Keep responsibilities grouped around contracts, verification/permissions, and errors. Give the package its own directory in this repository, `pyproject.toml`, explicit version, and tests. Install a versioned build into both services; no private registry is needed for this challenge. Use regular package installation for container builds; editable installation may be used as a development convenience.
- **Independent tests and rationale:** Run package tests without either Django project or a database, supplying fake lookup functions that return active identities, inactive results, or failures. Cover active/expired/inactive token handling, reader/editor permission decisions, malformed introspection responses and unknown roles, and error-payload consistency. Service integration tests separately verify database lookup, HTTP integration, and endpoint behavior. The injected function boundary makes these independent tests possible without a provider hierarchy or shared database.
- **Scope:** This records the approved shared-code responsibilities, service boundaries, packaging approach, and rationale only; implementation remains deferred.

## 2026-11-19 — Approve page composition with React at `/brand/`

- **Decision:** Place the React `<BrandList />` component at `/brand/`, inside a Django-rendered page layout. Render the homepage, brand detail, and review detail content with Django templates.
- **Rationale:** A dedicated directory preserves the existing WordPress brand archive URL and gives filtering, sorting, and pagination a natural home. Django-rendered content pages meet the challenge's requirements and preserve the existing detail permalinks. A bounded React component provides the required interactivity without introducing a single-page application or another routing framework.

| Route | Rendering and responsibility |
|---|---|
| `/` | Django-rendered homepage with a hero, a Browse brands link, up to six brand previews, and the six most recent reviews. |
| `/brand/` | Django-rendered layout, heading, and introduction, with React owning the filters, sort control, brand cards, pagination, and loading/empty/error states. |
| `/brand/<slug>/` | Django-rendered brand details and customer reviews, preserving the WordPress slug. |
| `/review/<slug>/` | Django-rendered complete review, preserving the WordPress slug. |
| `/api/brands/` | The approved public JSON listing contract, consumed by React and available to future mobile clients. |

- **Shared layout:** Use Django template inheritance for a common header, navigation, main content area, footer, and stylesheet references. Mount React inside a dedicated element in the directory template and load its JavaScript on that page only. Django supplies the surrounding layout; React owns the contents of its mount point.
- **Homepage content and rationale:** Preserve the existing theme's brand-preview and recent-review sections alongside the required hero. Order brand previews by calculated average rating and label that section Top-rated brands to describe the selection accurately. Use the approved derived ratings rather than the WordPress stored averages. Brand previews are a deliberate addition to the challenge's minimum homepage requirement.
- **Brand detail content:** Show the brand name, all associated industries, calculated average rating and review count, optional metadata, sanitized full description, and customer reviews. Show an Editor's pick section only when a top review has been explicitly selected; retain the approved no-fallback behavior. Link review titles to their full detail pages.
- **Review detail content:** Show the title, rating, reviewer name using the approved fallback, optional location, publication date, full sanitized body when present, and a link to the brand. Empty review bodies remain valid.
- **Navigation and mobile behavior:** Use ordinary links between pages so URLs remain shareable and support standard browser navigation and opening in another tab. React updates directory results through API requests without reloading the whole page. Keep directory filters, sorting, and pagination in URL query parameters so selections can survive reloads and navigation; the approved listing and browser-history behavior is recorded below.
- **Shared data logic:** Django page views query the main application's database directly through reusable query and formatting helpers; they do not call their own HTTP API. Reuse relevant calculations and formatting in API views, including average ratings, review counts, and reviewer-name resolution. These content helpers remain in the main application, outside the shared auth library.
- **Styling:** Use shared SCSS conventions for typography, spacing, cards, and industry badges across Django templates and React. Author the template and React markup separately while keeping their appearance consistent. The approved SCSS organization and asset tooling are recorded below.
- **Accepted JavaScript tradeoff:** Fetch the directory's initial results from the API after React mounts. The interactive directory requires JavaScript and must provide loading feedback plus a clear no-script message. The homepage and both detail pages deliver their content without JavaScript. React server rendering and hydration are unnecessary for this composition.
- **Initial navigation and scope:** Start with Home and Brands navigation links. A review archive, About page, and Contact page remain optional and are deferred rather than linked before they exist. This records page composition and its rationale only; the approved listing interaction behavior and frontend tooling are recorded below. Implementation remains deferred. No implementation changes are authorized by this entry.

## 2026-11-19 — Approve React brand listing behavior

- **Decision and rationale:** Use native industry checkboxes, a native sort dropdown, explicit Previous/Next pagination, and URL query parameters to represent the current listing selection. Keep the directory predictable, shareable, and usable on mobile and with a keyboard while consuming the already-approved API contract.
- **Immediate filtering:** Show the five available industry choices supplied by `available_industries`, independently of the current results. No selection means all brands, including those without industries; multiple selections use OR semantics. Apply each checkbox change immediately and reset to page 1. Clear industries removes industry selections, preserves sorting and page size, and returns to page 1. This small taxonomy does not need an Apply button or separate pending and applied selections.
- **Sorting:** Offer Highest rated (`-average_rating`, the default), Lowest rated (`average_rating`), Most reviewed (`-review_count`), and Fewest reviewed (`review_count`). Changing sort preserves industries and page size and resets to page 1. Django filters and sorts the entire matching dataset; React displays the returned order rather than sorting only the downloaded page. Preserve the approved tie-breakers and unrated-last behavior.
- **Pagination:** Default to 20 brands per page. Honor a valid URL `page_size` within the API's 1–100 limit without adding a page-size dropdown initially. Show Previous, Page X of Y, Next, and a result range/count; make unavailable directions inactive and omit pagination when there are zero results or only one page. Page changes preserve filters, sorting, and page size. Use links to `/brand/?...` so opening in another tab works, while ordinary clicks can update results without a full reload. Explicit paging keeps navigation compact and predictable. With the five source brands, `page_size=2` can demonstrate pagination without adding data.
- **URL ownership and rationale:** Read the current query from the page URL on initial load, reload, and history navigation, and keep controls synchronized with it. Send the corresponding query to `/api/brands/` while the browser stays at `/brand/`. Omit default values when useful for concise links, but do not silently replace invalid values with defaults or clamp them. The URL preserves selections and page, not a frozen result set; returning from a detail page can show updated data.

| Action | URL and history behavior |
|---|---|
| Open a link or reload | Read the URL, initialize controls, and request its results. |
| Change industries or sorting | Update the selection and reset page to 1 in one new history entry. |
| Change page | Update the page parameter and add one history entry. |
| Back or Forward | Restore the URL's controls and fetch its results without adding an entry. |
| Retry a failed request | Repeat the current request without changing the URL or history. |

- **History integration:** Use the browser History API for this bounded component; a routing framework is unnecessary. Returning through Back/Forward restores selection state without forcing a scroll to the top.

| Request outcome | Display and recovery |
|---|---|
| First request loading | Show Loading brands with a reserved results area. |
| Query changes | Show loading feedback and hide previous cards, count, and obsolete pagination. |
| Success with results | Show cards, matching count, result range, and applicable pagination. |
| Valid filters match nothing | Explain that no brands match the selected industries and offer Clear industries. |
| Unfiltered directory is empty | Explain that no brands are available yet; omit pagination. |
| Network failure, timeout, or server error | Show a load-failure message and Try again, preserving selections and URL. |
| Invalid query (`400`) | Explain the invalid listing selection and offer Reset listing to `/brand/`. |
| Page no longer exists (`404 page_not_found`) | Offer Go to first page, preserving industries, sorting, and page size. |

- **Loading tradeoff and controls:** Hide old results during a changed request so they cannot be mistaken for matches to the new selection. Accept brief loading feedback in exchange for this clarity. Keep filters and sorting usable while loading and retain previously loaded industry choices. Wait for current response metadata before enabling pagination. An invalid initial request may supply no taxonomy choices, so Reset listing must work independently of the checkbox controls.
- **Request correctness:** Cancel superseded requests where possible and ignore their eventual results and errors. Only the current request may update the visible outcome. This prevents a slower earlier request from replacing newer results or producing an irrelevant error after a rapid selection change.
- **Accessibility and mobile behavior:** Use labeled native controls, visible focus indicators, comfortably sized touch targets, and controls that wrap or stack on narrow screens. Keep focus on a filter while results update. After an explicit page change succeeds, move focus to the results heading. Announce loading, result counts, and errors through a small status region rather than making the entire card list live.
- **State boundary:** Keep the current query, latest response, and request status synchronized in React. Persist the query through the URL; loading and errors remain temporary component state. These behavior decisions do not select additional state-management or data-fetching libraries.
- **Scope:** This records the approved listing interactions, browser-history behavior, request states, accessibility behavior, and rationale only. The approved frontend tooling is recorded below; implementation remains deferred. No implementation changes are authorized by this entry.

## 2026-11-19 — Use Vite, the React plugin, Dart Sass, and npm

- **Decision:** Use Vite with the official `@vitejs/plugin-react` plugin to build React, Dart Sass through the npm `sass` package to compile SCSS, and npm to manage frontend dependencies and commands.
- **Rationale:** One frontend build workflow handles React and styling, with a development asset server, React refresh support, and production asset generation. Vite already integrates SCSS when a Sass compiler is installed, so no additional SCSS-specific Vite plugin is needed. Compared with coordinating esbuild and the Sass CLI separately, this provides the development workflow and asset manifest together while Django continues to own pages and the API.
- **Asset entry points:** Use a shared SCSS entry point that produces CSS loaded by the base Django template on every page, and a separate React entry point loaded only on `/brand/`. Shared styling must remain available independently of React execution, including when JavaScript is disabled.
- **Development workflow:** Run Django and Vite alongside each other. Visit the Django site; its development templates reference Vite-served assets and include the necessary React refresh integration. API requests continue to go to Django. Vite supplies frontend development assets without taking ownership of page routes.
- **Production workflow:** Build optimized JavaScript and CSS ahead of time, with content-hashed filenames and a manifest mapping source entry points to generated assets and dependencies. Django's template integration uses the manifest to reference the correct files. Compile before Django's `collectstatic` step, which gathers assets for deployment rather than compiling React or SCSS. Package the generated assets and required manifest with the application; a running Node or Vite server is not required in production for this architecture.
- **Reproducibility and commands:** Commit frontend source, configuration, `package.json`, and `package-lock.json`. Use `npm ci` to install locked dependency selections, `npm run dev` for the development asset server, and `npm run build` to produce JavaScript and CSS together. Document these commands in the README. The lockfile makes dependency installation repeatable without rewriting the selected versions during builds.
- **Accepted integration work:** Django needs deliberate development asset/refresh references and production manifest handling. The detailed template integration, including whether to use a small helper or an integration package, remains to be discussed; this decision does not select that implementation.
- **Scope:** This records the approved frontend build tools, workflow, and rationale only. The TypeScript choice and SCSS organization are recorded below; exact tool versions and implementation remain deferred. No dependencies are installed or implementation changes authorized by this entry.

## 2026-11-19 — Use TypeScript for the React frontend

- **Decision:** Write React components in TypeScript (`.tsx`) and frontend logic in TypeScript (`.ts`), using the approved Vite and React-plugin build setup.
- **Rationale:** Type safety helps catch mismatched component props, invalid query-state values, and incorrect use of API response fields during development. Explicit types make nullable ratings, optional selected reviews, and loading/error states easier to understand and maintain.
- **Type checking:** Include an explicit `tsc --noEmit` check in the frontend build workflow and fail the build on type errors. Vite transforms TypeScript into browser JavaScript but does not perform type checking itself.
- **Runtime boundary:** TypeScript checks the code's declared types; it does not validate incoming JSON or URL parameters at runtime. Preserve input and response checks where needed. This choice does not select an additional runtime-validation library.
- **Scope:** This settles the frontend language choice and records its rationale. The Django services and shared Python library retain their approved language and boundaries. Implementation and dependency installation remain deferred.

## 2026-11-19 — Approve SCSS organization and shared Django/React styling

- **Decision and rationale:** Build one shared stylesheet from a small set of SCSS partials under `frontend/scss/`. Use the same CSS class names in Django templates and React components. The reference stylesheet is small enough for a compact structure that separates design values, layout, reusable components, content typography, and page arrangements without introducing a large styling framework.

| File | Responsibility |
|---|---|
| `main.scss` | Build entry point that assembles the stylesheet. |
| `_tokens.scss` | Shared colors, spacing, typography values, radii, shadows, widths, and compile-time breakpoint values where needed. |
| `_base.scss` | Basic element defaults and typography. |
| `_layout.scss` | Containers, grids, header, footer, and section spacing. |
| `_components.scss` | Shared cards, ratings, badges, controls, and pagination. |
| `_prose.scss` | Typography and spacing for sanitized descriptions and review bodies. |
| `_pages.scss` | Homepage, brand-directory, and detail-page arrangements. |

- **Assembly and maintenance:** Load tokens, base, layout, components, prose, and pages in that order using Sass `@use` in `main.scss`. Underscore-prefixed files are partials rather than separate build entry points. Keep the small shared components together initially; split them into individual partials when their size warrants it.
- **Design tokens:** Preserve the reference theme's CSS custom-property approach for shared design values, adding a small consistent spacing scale where useful. Components reference those values with `var(...)`. Use Sass variables for compile-time values such as shared breakpoints where appropriate, without duplicating the entire palette in both Sass and CSS variables. Central definitions make visual changes consistent across the site.
- **Shared styling boundary:** Django template includes and React components independently produce markup using the same classes. Load the compiled CSS through the base Django template on every page, independently of React execution; React does not load a duplicate copy. Heading levels and other semantic markup can follow each page's structure while classes provide consistent presentation.
- **Naming and selectors:** Use simple BEM-style names for components, parts, and actual variations, such as `.brand-card`, `.brand-card__title`, and `.brand-card--compact` if a compact variation is needed. Keep selectors shallow and component-specific to reduce accidental effects elsewhere; avoid depending on a chain of surrounding containers or broadly styling every heading in a large section.
- **Semantic content:** Wrap sanitized description and review HTML in a frontend-owned `.prose` container. Scope paragraph, list, heading, and link styling to that wrapper in `_prose.scss`. Stored HTML preserves content structure; presentation classes, layout rules, and visual styling remain in templates/components and stylesheets rather than database content.
- **Responsive and accessible presentation:** Start with layouts that fit narrow screens, adding wider arrangements as needed. Keep responsive rules with the styles they affect, such as header wrapping with header styles and directory control arrangement with directory styles. Include visible keyboard focus, usable touch targets, wrapping for long names and multiple industries, and reduced-motion handling for the reference theme's hover movement.
- **Reference and scope:** Preserve the visual starting point of `reference/theme.css`, including its colors, typography, cards, ratings, and spacing, while adding styles required by the approved listing behavior. Leave the reference file intact and author the maintainable SCSS source separately. This entry records organization, sharing conventions, and rationale only; no SCSS, template, React, or build implementation changes are authorized yet.

## 2026-11-19 — Coordinate imports with two management commands and a temporary identity map

- **Decision and rationale:** Use one Django management command in the auth project and another in the main project, coordinated sequentially by a thin wrapper script. A single documented entry point, such as `make import-wordpress`, runs auth first and main only after successful auth completion. This keeps ORM operations and transactions inside their owning services while providing a simple, repeatable import workflow. Command names are illustrative until implementation.
- **Prerequisites and boundaries:** Restore the committed dump into the dedicated MariaDB source and apply Django schema migrations to both PostgreSQL destinations before importing records. Keep the source unchanged across both phases. Each command queries only the source fields it needs through read-only access and writes only to its own PostgreSQL database. The import commands do not require running HTTP servers or new import API endpoints.
- **Auth phase:** Read WordPress accounts and roles, match existing accounts by `wordpress_id`, and create missing accounts with the approved initial role mapping and generated public UUIDs. Preserve existing UUIDs, passwords, roles, and account fields. Commit the entire auth phase before publishing its identity mapping. Import all WordPress accounts, including those without authored reviews; do not issue tokens during import.
- **Temporary identity handoff:** Export a JSON mapping from WordPress user ID to auth public UUID for both newly created and existing accounts. Include identifiers only, without credentials or roles. The wrapper uses a fresh temporary location for each run and starts main only after auth exits successfully and finishes writing the mapping. Regenerate the map from auth accounts on every rerun instead of reusing a leftover file. The file is a command handoff, not a persistent source of truth.
- **Local-demo passwords and rationale:** Supply one explicitly configured local-demo password through the auth importer's environment, required when creating new accounts. Set it through Django's password helpers and keep it out of mappings and logs. Existing passwords remain unchanged on reruns. This provides working reader and editor accounts for the challenge without a separate provisioning workflow; tokens are obtained afterward through login.
- **Main phase and identity linkage:** Read source content and the mapping, then create missing industries, reviewer profiles, brands and their industry links, and finally reviews in dependency order within one main-database transaction. Create reviewer profiles for authors of imported reviews. Store each mapped auth public UUID on the local Reviewer; reviews reference that Reviewer's local primary key. Read display names from the source without querying auth's database. Preserve all existing records and relationships.
- **Content preparation:** Keep HTML sanitization as a small main-importer helper using an existing library and the agreed semantic-content policy. For a new brand's short description, use its WordPress excerpt or fall back to its body, convert to plain text, normalize whitespace, and shorten at a word boundary within 500 characters. Preserve the approved slugs, ratings, attribution, and publication dates. Leave new brands' `top_review` unset. Reruns do not re-sanitize or regenerate existing content.
- **Validation and conflicts:** Report validation failures with the entity, WordPress ID, and offending field. A new-record username or slug collision with a different source identity stops the phase rather than merging unrelated records. Validate the identity handoff; an existing Reviewer's auth UUID that conflicts with the fresh mapping stops the main phase rather than silently relinking the profile. Preserve the existing create-only and database-constraint rules.

| Failure point | Database outcome and recovery |
|---|---|
| Auth fails before commit | Roll back that auth phase; do not run main. |
| Auth commits but mapping export fails | Keep committed auth records; do not run main. Rerun to regenerate the mapping from those accounts. |
| Main content import fails | Roll back that main phase; keep committed auth accounts. Fix the failure and rerun. |
| Both phases succeed | A rerun reuses existing records and identities without changing application data. |

- **Transaction rationale:** Use one `transaction.atomic()` boundary per destination phase. The mapping file is outside the database transaction, so an export failure after commit must not be described as an auth rollback. Safe reruns handle that gap and a failed main phase without distributed transactions.
- **Reporting and verification:** Report created versus already-existing counts after each successful commit. For a fresh import of the current committed dataset, expect nine auth accounts, eight reviewer profiles, five industries, five brands, and sixty reviews. A failed phase reports its failure and rollback status instead of presenting attempted inserts as committed records. The wrapper reports the overall outcome and stops on failure.
- **Scope:** This records importer execution, service coordination, local-demo password provisioning, bounded content preparation, and rationale only. The importer remains in the repository for reproducibility. No commands, dependencies, database changes, or other implementation are authorized by this entry.
