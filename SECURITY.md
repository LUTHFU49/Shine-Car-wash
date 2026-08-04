# ShineHub — Security Measures (Phase 15)

This document describes every security control implemented as of Phase
15, why it exists, and where to find it. Written for whoever picks up
Phase 16 (or an external reviewer) so nothing here needs to be
rediscovered by reading every file.

## Authentication

- **Account lockout**: `ACCOUNT_LOCKOUT_ATTEMPTS` (5) failed attempts locks an account for `ACCOUNT_LOCKOUT_MINUTES` (15). Enforced in `apps.accounts.views.login_view`, fields on `User` (`failed_login_attempts`, `locked_until`).
- **Login audit trail**: every attempt (success/fail, IP, reason) recorded in `apps.accounts.models.LoginAuditEntry`.
- **Password strength**: Django's standard validator stack plus a custom `ComplexPasswordValidator` (`apps/accounts/validators.py`), and a live frontend meter (`static/js/password-strength.js`).
- **Password history**: `PasswordReuseValidator` blocks reuse of the current password or the last `PASSWORD_HISTORY_COUNT` (default 5) — see `apps.accounts.models.PasswordHistory` and `record_password_history()`.
- **Email verification**: token-based, `EmailVerificationToken` model, expiring links.
- **Admin-forced password reset**: `User.must_change_password`, set via the `force_password_reset` admin action, enforced by `ForcePasswordChangeMiddleware` until cleared.
- **New-device login notification**: an email is sent when a login's (IP, user-agent) pair has no prior successful match for that user — skipped on an account's very first-ever login. See `_is_known_device()` in `apps/accounts/views.py`.
- **User-enumeration resistance**: the auth backend runs a dummy `check_password` for unknown usernames so timing doesn't reveal which usernames exist; the forgot-password flow shows an identical message regardless of whether the email is registered.

## Session management

- **Sliding inactivity timeout**: `SESSION_INACTIVITY_TIMEOUT_MINUTES` (default 60), independent of the 7-day "remember me" cookie ceiling — the two protect against different threats. Enforced by `apps.accounts.middleware.SessionSecurityMiddleware`.
- **Active session tracking**: `apps.accounts.models.UserSession`, refreshed (throttled to ~once/minute/session) by the same middleware.
- **Self-service session management**: "Active Sessions" page (`/accounts/sessions/`) — revoke one device or all others.
- **Automatic revocation on security events**: changing your password kills every *other* session; a forgotten-password reset kills *all* sessions; deactivating your account kills all sessions. See `revoke_sessions()` in `apps/accounts/models.py`.
- **Admin force-logout**: "Force logout everywhere" action on the User admin.
- **Cookies**: `HttpOnly`, `SameSite=Lax`, `Secure` in production (`DEBUG=False`).

## Role-based access control

Every view across all 18 apps was audited (see the RBAC scan performed this phase) — every state-changing or data-exposing view has an appropriate decorator (`login_required`, `role_required`, `staff_required`, `management_required`, `customer_required`, `employee_required` — `apps/core/decorators.py`). The only undecorated views are genuinely public pages (marketing, auth entry points, error pages) and the M-Pesa webhook (which has its own IP-allowlist protection instead — see below).

## Audit logging

- **Generic safety net**: `apps.audit_logs.middleware.AuditLogMiddleware` logs every state-changing (POST/PUT/PATCH/DELETE) request that succeeds, even if no view logs anything explicit. PUT/PATCH map to `UPDATE`, DELETE to `DELETE`; POST stays `OTHER` since it's inherently ambiguous (the specific view logs a more precise entry itself where it matters).
- **Structured before/after values**: `apps.audit_logs.utils.field_diff()` produces `{before, after}` diffs stored in `AuditLog.metadata` (JSONField) — wired into the User admin (role/active/staff/superuser/deactivated changes, and group membership changes) and the Group admin (permission changes).
- **User creation/deletion, permission changes**: all logged with actor, target, and (for updates) the actual before/after values — via `UserAdmin.save_model/save_related/delete_model/delete_queryset` and the custom `GroupAdmin`.
- **Tamper-evidence**: the audit log admin has `has_add_permission`/`has_change_permission` both hard-disabled — nobody, including a superuser, can add or edit entries through the UI. (Verified by test, not just by reading the code.)
- **~100 explicit domain-event log calls** already existed pre-Phase-15 across bookings/payments/inventory/feedback/etc. (e.g. "booking cancelled", "refund issued") — these were reviewed, not rebuilt.

## Input & application security

- **SQL injection**: not applicable — the entire app uses the Django ORM exclusively; confirmed via a full-codebase search for raw SQL (`.raw()`, `cursor.execute`, `RawSQL`, `.extra()`) outside migrations — zero hits.
- **XSS**: Django's default auto-escaping is relied on everywhere; the only `|safe` usages (Chart.js data in 3 dashboards) were verified to be `json.dumps()`-encoded before being marked safe, so they can't break out of the `<script>` context. Verified end-to-end with a real `<script>alert(1)</script>` submission rendering escaped.
- **CSRF**: Django's standard middleware, verified end-to-end (a token-less POST gets a real 403, not a silent pass).
- **Clickjacking**: `X-Frame-Options: DENY` plus `frame-ancestors 'none'` in the CSP, both always-on (not just in production), verified via response headers.
- **File uploads**: a shared `apps.core.validators.validate_image_upload` enforces size limit, content-type allowlist, and an actual Pillow decode-and-verify (catches a disguised non-image file renamed with an image extension) — used consistently across all 4 upload points (profile photo, inventory item, service, vehicle).
- **CSV/Excel formula injection**: `apps.core.csv_utils.safe_csv_writer` / `safe_excel_row` prefix any cell starting with `=`, `+`, `-`, `@`, tab, or CR with a single quote, neutralizing it as a live formula in Excel/Sheets/LibreOffice. Wired into all 10 CSV export sites and all 7 Excel export sites across the app.
- **Open redirects**: `apps.core.redirects.safe_redirect_target` validates any `next`-style parameter against `url_has_allowed_host_and_scheme` before use — fixed in `login_view` and both notification "mark read" views (all three previously redirected to an unvalidated user-supplied URL).

## HTTP security headers

All active in every environment except where noted:

| Header | Value | Notes |
|---|---|---|
| `X-Frame-Options` | `DENY` | |
| `X-Content-Type-Options` | `nosniff` | |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | |
| `Content-Security-Policy` | see `settings.CONTENT_SECURITY_POLICY` | allowlists exactly the 4 external hosts the templates load (Google Fonts, cdnjs, Tailwind CDN) — no more, no less |
| `Permissions-Policy` | all listed features disabled | app doesn't use camera/mic/geolocation/payment/etc. |
| `Strict-Transport-Security` | 1 year, includeSubDomains, preload | production only (`DEBUG=False`) |
| SSL redirect / secure cookies | on | production only |

**Known limitation, not fixed this pass**: CSP's `script-src`/`style-src` include `'unsafe-inline'` because ~12 templates use inline `onclick=""` handlers and the Tailwind CDN runtime compiler injects inline `<style>`. Removing `'unsafe-inline'` safely requires converting those handlers to `addEventListener` first — tracked as a follow-up, not done blind.

## Rate limiting

Every threshold is env-overridable (`.env.example` has the full list). Auto-disabled during `manage.py test` (Django's test client reuses one IP for every request, which would otherwise make the test suite trip its own limits).

| Endpoint | Default limit | Key |
|---|---|---|
| Login | 10/5min | IP *and* attempted username |
| Registration | 5/hour | IP |
| Password reset request | 5/hr + 3/hr | IP + target email |
| Password reset confirm | 10/hour | IP |
| Resend verification email | 3/hour | user |
| Public contact form | 5/hour | IP |
| M-Pesa callback | 60/min | IP |
| M-Pesa initiate | 10/min | user |
| Refunds | 20/hour | user |
| Payment status poll | 60/min | user |
| Feedback/review submit | 10/hour | user |
| Notification poll fallback | 120/min | user |

Backed by Redis (`REDIS_CACHE_DB`) so limits are shared correctly across all Gunicorn/Daphne worker processes, not just per-process.

## M-Pesa callback hardening

Daraja doesn't sign its callbacks, so the standard mitigation is an IP allowlist: `MPESA_CALLBACK_ALLOWED_IPS` (empty by default — get the real list from Safaricom at go-live, since a wrong hardcoded default would silently break production payments). The callback handler is also confirmed idempotent by test: a duplicate Safaricom resend of the same result does not double-apply a payment.

## Data protection

- Passwords: Django's default PBKDF2 hashing (never touched/weakened).
- Secrets: `DJANGO_SECRET_KEY`, Daraja credentials, Gmail credentials, all via environment variables (`decouple.config`), never hardcoded.
- Tokens: email verification and password reset both use cryptographically random, expiring tokens.

## What's NOT covered by automated tests yet

Real, honestly-tracked gap: `apps/feedback`, `apps/loyalty`, `apps/analytics`, and `apps/reports` still have no dedicated test suite (payments, audit_logs, and inventory's stock-reservation logic were written this phase specifically because they were the highest-risk previously-untested code). Recommended next: at minimum, loyalty's wallet/points balance logic and coupon redemption, given they move value the same way payments does.
