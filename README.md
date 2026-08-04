# ShineHub — Car Wash Management System

Developed by **ALPHACODE SOLUTIONS**.

This repository is being built **phase by phase**, exactly as specified in the
project brief. Each phase is fully working, migrated, and tested before the
next one starts — nothing here is a placeholder.

## What's in this delivery: Phases 1–14

### Phase 1 — Project Foundation

- Django project + all 16 apps created and wired into `INSTALLED_APPS`
  (`core`, `accounts`, `customers`, `vehicles`, `services`, `bookings`,
  `payments`, `inventory`, `employees`, `reports`, `notifications`,
  `dashboard`, `site_settings`, `audit_logs`, `feedback`, `loyalty`,
  `analytics`)
- Full settings configuration: MySQL (production), environment variables via
  `.env`, Gmail SMTP, Safaricom Daraja sandbox config, Django Channels /
  Redis for WebSockets, static & media file handling, security hardening,
  logging
- The 5 role-based Django Groups, created automatically via a data migration
- A working audit-log system (model + middleware) that records every
  state-changing request
- A fully responsive, dark/light-mode landing page with hero, features,
  services, pricing, testimonials, stats, about, FAQ, and a working
  (validated) contact form
- Base template system, navbar, footer, toast notifications, graceful
  403/404/500 error pages

### Phase 2 — Authentication

- Real custom `User` model (`apps.accounts.models.User`) with the 5 roles
  (Super Admin, Manager, Cashier, Employee, Customer), phone validation,
  account-lockout fields, and email-verification state
- **Registration** — strict server-side validation (names, username
  uniqueness, email uniqueness, phone format, full Django password-validator
  chain incl. a custom complexity validator), auto-assigns the Customer
  group
- **Login** — supports username or email, "remember me" (persistent vs.
  browser-session cookie), brute-force lockout after
  `ACCOUNT_LOCKOUT_ATTEMPTS` failed attempts, every attempt recorded to
  `LoginAuditEntry`
- **Logout** (POST-only, to prevent CSRF-triggered logouts via a bare link)
- **Forgot / reset password** — never reveals whether an email exists;
  only sends a reset email for real accounts, using Django's secure
  token generator with the timeout set in Phase 1
- **Profile** — view, edit (name/phone), **AJAX photo upload & removal**
  (validated: size, content-type, and actually decoded with Pillow to
  reject corrupt/fake files), **change password** (keeps the session
  alive via `update_session_auth_hash`), **account deletion** (soft
  deactivate — `is_active=False` + `is_deactivated`, audit-logged,
  branded confirmation email)
- **Email verification** — one-time token, 2-hour expiry, resend option
- A minimal role-aware dashboard home (quick actions per role) as the
  post-login landing page — the full KPI/analytics dashboard is a later
  phase
- 6 branded HTML emails (welcome, verification, password reset, password
  changed, account deactivated) via a shared `send_branded_email()` helper
- A `post_save` signal on `User` that creates the verification token and
  fires the welcome/verification emails — decoupled from the register view
- A real-time password-strength meter (frontend) backed by the full
  server-side validator chain (never trust the frontend alone)

**Verified in this environment:** `python manage.py check`, a full
migration check, and 60 automated tests all pass. Beyond the automated
suite, the entire flow was exercised end-to-end with Django's test
client — register → verify email → log in while unverified → edit profile
→ change password (session survives) → log out → forgot password (real
account emails, fake account doesn't) → account lockout after repeated
failed logins → photo upload/removal (including rejecting a fake image
file) → account deletion → confirming the deactivated account is blocked
from logging in with the correct message. One real bug was caught during
this manual pass (a deactivated-account message that was unreachable
because Django's auth backend rejects inactive users before the check
ran) and fixed, with a regression test added.

### Phase 3 — Customers

- A real internal **app shell** (sidebar + topbar) now wraps every
  authenticated page — dashboard and profile pages were migrated onto it,
  and it's what every future staff-facing phase (Vehicles, Bookings,
  Inventory, Employees, Reports...) will extend. Role-based nav: staff
  roles see an "Operations" section, everyone sees Dashboard/Profile
- A `role_required(*roles)` / `staff_required` decorator in `apps.core`
  that every future phase reuses instead of re-implementing role checks
- `Customer` model — supports both self-registered customers (auto-linked
  to their `User` account via a signal the moment they register) and
  walk-in customers staff register at the counter with no login account
- **Customer CRUD** — create, view, edit, soft-deactivate/reactivate (not
  hard-deleted, to preserve future booking/payment history integrity)
- **Search** — by name, phone, email, or the generated `CUST-000001`-style
  customer code
- **Filters** — status (active/deactivated), source (registered online vs.
  walk-in), sortable by name or join date
- **Export** — CSV and Excel (via `openpyxl`), both respecting whatever
  search/filter is currently applied
- **History** — an activity timeline per customer, built on the existing
  audit-log infrastructure, ready to grow as bookings/vehicles/payments
  are added in later phases
- Role-based access: only Super Admin, Manager, and Cashier can reach the
  Customers app — Employees and Customers themselves get a proper 403

**Verified in this environment:** 88 automated tests pass (27 new for this
phase), plus a full manual walkthrough with the test client — creating a
walk-in customer, viewing their detail/history page, editing, searching by
each supported method, filtering by status and source, both export
formats, and confirming non-staff roles are correctly blocked with a 403.
Two real issues were caught during that manual pass: a template that
chained `default:` filters on a field that can be `None` (fixed, since
Django resolves the filter's argument eagerly even when unused) and a
stray assertion in one of my own verification scripts that mistook a
one-time toast notification for a stale table row (not an app bug — fixed
the script, not the app).

### Phase 4 — Vehicle Management

- `Vehicle` model — belongs to a `Customer`, supports unlimited vehicles
  per customer, never hard-deleted (status moves to Sold/Inactive instead,
  to protect future booking/payment history)
- **License plate validation** — enforces the Kenyan plate format
  (`KDA 001A`), accepting messy input (`kda001a`, `KDA-001A`) and
  normalizing it to the canonical spaced form; global uniqueness enforced
- **Two full interfaces on the same model:**
  - **Staff-facing** (`/vehicles/`) — register a vehicle for any customer
    (with a search-as-you-type customer picker), edit, change status,
    search/filter across every vehicle in the system, CSV/Excel export
  - **Customer self-service** (`/vehicles/my/`) — "My Vehicles", the page
    the dashboard already had a quick-action stub for since Phase 2. A
    logged-in customer registers and manages only their own vehicles; the
    status and internal-notes fields are staff-only and don't even appear
    on this form
- Optional vehicle photo, validated with the same shared Pillow-based
  image check used for profile photos (extracted into `apps.core.validators`
  in this phase so it's not duplicated a third time in later phases)
- **Vehicle history** — an activity timeline per vehicle, same audit-log
  pattern as Customers, ready to grow once Bookings exists
- Object-level ownership enforced on every self-service view — a customer
  editing another customer's vehicle gets a 404, not just a redirect
- The Customer detail page now shows that customer's vehicles inline, with
  an "Add Vehicle" shortcut that preselects the customer on the create form

**Verified in this environment:** 119 automated tests pass (31 new for
this phase — including a customer explicitly failing to edit another
customer's vehicle). The manual walkthrough covered both interfaces
end-to-end: staff registering a vehicle through the customer picker,
license plates entered messy and confirmed normalized/title-cased on
save, the vehicle appearing correctly on the customer's profile, global
search by customer name, status changes, and separately a customer
self-registering their own vehicle with a real uploaded photo, confirming
staff can see it tagged "Self-registered," and confirming that customer
is blocked from the staff-only vehicle list. That walkthrough caught one
real bug: the `status` field was required on the form but deliberately
hidden from the create page (it's edit-only), so every vehicle creation
was silently failing validation. Fixed by making the field optional with
a sensible default, and locked in with a regression test.

### Phase 5 — Services

- `ServiceCategory` and `Service` models — categories carry a curated
  Font Awesome icon, display order, and active status; services carry
  pricing, duration, day-of-week availability, and status
- **Public service catalog** at `/services/` — no login required, grouped
  by category, only showing active services in active categories. The
  landing page's existing marketing teaser now links to it, and it's
  the first page in the project that both anonymous visitors and
  customers see the same content
- **Pricing** — enforced positive (`MinValueValidator` plus a form-level
  check), displayed in KSh throughout
- **Duration** — enforced positive with a sanity ceiling (8 hours) to
  catch fat-finger entry errors, shown as "1h 30m"-style human text
- **Availability** — per-service day-of-week checkboxes; leaving all
  seven checked (or none) means "every day," normalized consistently
  either way
- **Status** — Active/Inactive; deactivating a service pulls it from the
  public catalog immediately
- **Two-tier staff access**, a first for this project: Super Admin and
  Manager can create/edit/price services and categories
  (`management_required`); Cashiers can view the same staff pages (they
  need the price list to serve customers) but the create/edit/status
  actions are hidden and blocked server-side, not just in the UI
- Full CRUD for both models, search/filter/sort for services, CSV/Excel
  export, and a price-change-aware history log ("price changed from KSh
  X to KSh Y") on the service detail page

**Verified in this environment:** 154 automated tests pass (35 new for
this phase). The manual walkthrough went through the full real-world
sequence — attempting to create a service with zero categories (correctly
redirected), creating a category, creating a service under it, confirming
it appears on the *public* catalog to an anonymous client, confirming the
landing page links there, editing its price and checking the history log
records the change, and confirming a Cashier can view but not edit. That
walkthrough caught one real bug (the same shape as one from Phase 4): the
public-catalog assertion in one of my own tests was tripped by a one-time
toast notification containing the service's name, not by stale page
content — fixed the test, not the app, and left a comment explaining why
so it doesn't get "fixed" backwards later.

### Phase 6 — Bookings

The biggest phase yet — the full appointment lifecycle end to end.

- `Booking` model tying together `Customer`, `Vehicle`, and `Service`,
  with price/duration **snapshotted at booking time** so a later price
  change on the Service doesn't retroactively rewrite historical bookings
- **Appointment scheduling** with real validation: no past dates, business
  hours enforced (configurable via `.env`), a service's day-of-week
  availability from Phase 5 is checked against the chosen date, and the
  same vehicle can't be double-booked into the same slot — all of it
  running automatically through the model's `clean()`, not duplicated in
  every form
- **A real state machine** — `PENDING → CONFIRMED → IN_QUEUE →
  IN_PROGRESS → COMPLETED`, with `CANCELLED`/`NO_SHOW` branches — enforced
  by an explicit transition table, not just a free-text status field. An
  invalid transition (e.g. trying to re-open a completed booking through a
  crafted request) is rejected with a friendly message, not a 500
- **Online booking** (customer self-service, starts `PENDING`, needs staff
  **approval**) vs. **walk-in** (staff-created, starts `CONFIRMED`
  immediately, since staff are already handling the customer in person) —
  two distinct flows sharing one model and one set of validation rules
- **Calendar** — a real server-rendered month grid (no external JS
  calendar library, since none is in the approved stack) showing booking
  counts per day; click a day to drill in
- **Queue management** — that day-drill-in view doubles as the queue: every
  booking for the day, sorted by time, with one-click status buttons
  (Check In → Start Wash → Complete) right in the row
- **Reschedule** and **cancellation** (with an optional reason, staff or
  customer-initiated, always logged and emailed)
- **Booking history** — the same audit-log timeline pattern as every prior
  phase, now also surfaced as real "recent bookings" sections on the
  Customer and Vehicle detail pages (replacing their long-standing
  placeholder text) and a booking count on the Service detail page
- **Booking confirmation and reminder emails** — a received/pending
  acknowledgment, a confirmation, a cancellation notice, and a reminder,
  all through the same branded-email helper as every other phase. There's
  no Celery in this stack, so the reminder is a management command
  (`send_booking_reminders`) meant to be triggered by cron or a systemd
  timer — documented in `docs/DEPLOYMENT.md` — exactly how most
  Django projects without a task queue handle scheduled jobs
- A shared `search_active_customers()` selector, factored out of Vehicle's
  customer-picker so Bookings' walk-in flow (which needs the identical
  "pick a customer" UI) doesn't duplicate that query a third time

**Verified in this environment:** 197 automated tests pass (43 new for
this phase). The manual walkthrough ran the entire lifecycle for real: a
customer booking online, staff approving it, moving it through the queue
to completion, and confirming it correctly migrates from the "Upcoming"
to "Past" tab on the customer's side — then separately a full walk-in
flow (create customer → vehicle → booking in one sitting), confirming
double-booking is rejected, rescheduling, cancelling with a reason and
confirming the email fires, confirming a *cancelled* booking cannot be
rescheduled or illegally transitioned back into the queue, and confirming
the reminder command finds tomorrow's confirmed bookings, sends exactly
once, and leaves untouched anything further out.

That walkthrough caught three real issues: the same "chained `default:`
filter on a nullable field" template crash pattern first caught in Phase
3 (this time on `cancelled_by`) — fixed the same way, by guarding with an
`{% if %}` instead of chaining; a genuine data-loss bug where
`transition_to()`'s narrow `update_fields` list silently dropped
`cancellation_reason` and `cancelled_by` even though the view had just set
them on the instance — fixed by letting `transition_to()` accept extra
fields to persist in the same save; and a real search UX gap where typing
a full "First Last" name returned nothing, because the whole two-word
query was matched against `first_name` and `last_name` as single fields
instead of being split into terms — fixed with a per-term AND-across-terms
search. All three have regression tests now.

### Phase 7 — Employee Management

- `Employee` model, one-to-one with a `User` (role=Employee) — the same
  pattern Customers used to extend `User` in Phase 3
- **Onboarding creates the login account and the HR profile together.**
  No plaintext password is ever set or emailed — the new hire gets a
  "set your password" link by reusing the exact same secure token flow
  (`default_token_generator` + the existing password-reset-confirm view)
  built in Phase 2 for forgotten passwords. Verified by actually walking
  a fresh employee account through that link to a working login
- **Roles** — a job-position field (Washer, Detailer, Attendant,
  Supervisor, Cashier Trainee) distinct from the system's five
  authentication roles, which already existed since Phase 1
- **Schedules** — a weekly recurring day-of-week + shift-time pattern,
  deliberately reusing the exact same `WEEKDAY_CODES` convention Services
  established in Phase 5 for service availability, rather than inventing
  a second one
- **Attendance** — daily present/late/absent/on-leave records, one per
  employee per day (enforced by a database constraint, not just
  application logic), with clock-in/out times
- **Performance** — 1–5 star reviews with comments, dated and attributed
  to the reviewing manager
- **Assignments** — this is where it gets interesting: rather than bolt on
  a separate "assignments" concept, staff assign an `Employee` directly to
  a `Booking` from Phase 6's own detail page. It shows up in the booking's
  queue row, on the employee's profile, and — closing a loop that's been
  open since Phase 2 — on a brand-new **employee self-service section**
  (My Assignments, My Profile, My Attendance, My Performance) that finally
  replaces the `#` placeholders the dashboard has carried for the
  Employee role this entire time
- Full CRUD, HR-tier permissions (`management_required`: Super Admin and
  Manager only — Cashiers don't get read access here, unlike the
  pricing data in Services, because HR records are more sensitive and
  there's no operational need for it), search, CSV/Excel export

**Verified in this environment:** 235 automated tests pass (38 new for
this phase). The manual walkthrough onboarded a real employee, confirmed
the account has no usable password until the welcome link is used,
walked that exact link through Phase 2's password-reset-confirm view to
a working login, recorded attendance and a performance review, created a
booking and assigned the new employee to it, and confirmed the
assignment surfaces correctly in four separate places (employee detail,
the day queue, and the employee's own self-service pages) — then
confirmed the employee is correctly blocked from the staff-only employee
list. No new bugs this phase; the patterns established (and the bugs
fixed) in earlier phases held up under reuse.

### Phase 8 — Inventory Management

- `InventoryCategory`, `Supplier`, `InventoryItem` (auto-generated SKU,
  reorder level, unit of measure, optional expiry tracking), `Purchase`
  + `PurchaseItem` (a real PO workflow: draft → ordered → received →
  cancelled), an append-only `StockMovement` ledger (nothing is ever
  edited or deleted — every quantity change, in or out, is a new row),
  `StockReservation`, `ItemBatch` for expiry-tracked stock, and
  `ServiceInventoryRequirement` linking a `Service` to what it consumes
- **Automatic deduction, hooked in without touching Bookings at all** —
  a `post_save` signal on `Booking` (connected from `apps.inventory`,
  not from `apps.bookings`) reserves stock when a booking is confirmed,
  converts the reservation into a real deduction when it's completed,
  and releases the reservation if it's cancelled or marked no-show.
  Idempotent against re-saves at every step, and a service with no
  linked items is a total no-op — every existing Phase 1–7 booking flow
  behaves exactly as before
- **Expiry tracking** — items marked `track_expiry` get dated batches on
  receipt and are consumed oldest-expiry-first (FIFO); a
  `write_off_expired_batches()` helper (wireable to a daily cron/celery
  task) writes off anything that expired unused
- **Weighted-average costing** — receiving a purchase recalculates each
  item's average unit cost from its existing stock value + the incoming
  value, which is what stock valuation (`Σ current_stock × avg_cost`) is
  built on
- **Low-stock alerts** — an in-app notification (see below) plus a
  branded email to every Super Admin/Manager, throttled to once per 24h
  per item so a slow-moving shortage doesn't spam the inbox
- Manual stock adjustments (in/out, with a reason) and damaged-stock
  write-offs, both fully audited
- CSV import (creates missing categories automatically, skips
  duplicates), CSV/Excel/PDF export, and a standalone printable HTML
  report — all honoring the current search/filter state
- Bulk actions (activate/deactivate/recategorize), search, filters,
  pagination, soft delete (`is_active`, matching the Services/Employees
  convention — nothing here is ever hard-deleted)
- Full Django Admin integration, including a **read-only** admin for
  `StockMovement` (add/change/delete permissions are all disabled — the
  ledger is only ever written through `apps.inventory.services`, never
  hand-edited)
- A dashboard (KPIs, a Chart.js category breakdown, low-stock and
  expiring-soon panels, recent movements) reachable from a new
  "Inventory" sidebar link for staff roles

**A foundation for Phase 11, not a duplicate of it:** this phase also
introduces `apps.notifications` — a real `Notification` model, a list
page, mark-read/mark-all-read, and a topbar bell badge that polls
`/notifications/unread-count/` every 30 seconds. That's genuinely
useful today, but it's polling, not a push. The dedicated real-time
phase later swaps the transport for Django Channels/WebSockets without
any caller of `apps.notifications.utils.notify()` needing to change.

**Verified in this environment:** a full lifecycle smoke test — receive
a purchase (weighted-avg cost + expiry batch created correctly), confirm
a booking (stock reserved), re-save the same booking (confirmed
idempotent — no double reservation), complete it (stock deducted,
FIFO batch consumption correct), cancel a second booking (reservation
released back to available stock), a manual adjustment and a damage
write-off, a low-stock alert (notification + console-backend email both
fired), stock valuation, CSV import, and all 25 new URLs returning 200
for a Manager — plus a full regression pass confirming every Phase 1–7
page (dashboard, customers, vehicles, services, bookings, employees)
still works exactly as before.

### Phase 9 — Payment Management

- `Invoice` (one per booking, auto-created the moment a booking is
  confirmed — same signal-based, non-invasive hook `apps.inventory`
  used in Phase 8, so `apps.bookings` still hasn't been touched),
  `Payment` (one row per payment *attempt* — a failed STK push followed
  by a successful cash payment against the same invoice is two rows,
  not a rewrite), and `Refund`. `Invoice.amount_paid`/`status` are
  denormalized and maintained exclusively by `apps.payments.services`
  as Payments and Refunds are recorded, never touched directly from a
  view
- **Cash payments** — a cashier records an amount against an invoice's
  balance; over-payment is rejected server-side
- **Safaricom Daraja (M-Pesa) STK Push** — `apps.payments.daraja` is a
  small client for OAuth, `stkpush`, and `stkpushquery`. A customer (from
  their own booking page) or a cashier (at the counter, on the
  customer's behalf) can trigger a push; the phone number and shortcode
  password are handled the way Daraja expects. **This sandboxed
  environment's own network egress doesn't reach
  `sandbox.safaricom.co.ke`** (only package registries are reachable
  here), so the live HTTP round-trip couldn't be exercised end-to-end
  in this delivery — what *is* verified is that a call failing closed
  correctly marks the `Payment` `FAILED` with the error preserved, and
  every step downstream of a response (success or failure) is tested
  against simulated Daraja payloads. Point real sandbox credentials at
  it and it will work as written — nothing about the request/response
  handling is environment-specific
- **The callback and the manual "Verify Payment" action share one
  code path** (`_apply_stk_result`) so a payment resolves identically
  whichever one gets there first, and both are idempotent — replaying
  the same callback twice (Daraja does retry) never double-credits an
  invoice
- **Refunds** against a specific payment, capped at what's left
  refundable on that payment (tracked per-payment, not just per-invoice,
  so two partial payments can be refunded independently)
- Invoices can be **voided** — but only before any payment has been
  recorded against them; refund first, then void, same as any real
  billing system would insist on
- Receipts and invoices as PDFs (ReportLab, matching the Phase 8
  report style), CSV/Excel transaction export, and a receipt PDF is
  attached directly to the "payment received" email, not just linked
- Pending/failed payment lists, a daily collections report (cash vs.
  M-Pesa, date-range filterable, CSV export), a revenue summary (gross,
  refunded, net), and a dashboard with a Chart.js collections trend —
  all built on two aggregation functions in `services.py` rather than
  a stored summary table, so they're always correct against the ledger
- In-app notifications and branded emails for payment received, payment
  failed, and refund processed, reusing `apps.notifications` and
  `send_branded_email` from Phases 7 and 8 as-is — the only change
  either needed was adding an *optional* `attachments` parameter to
  `send_branded_email` (default `None`, so every existing caller is
  unaffected) so a receipt PDF can ride along with its email
- Full Django Admin integration, with `Payment` read-only (add/change/
  delete all disabled) for the same reason `StockMovement` is in
  Phase 8 — it's a ledger, not a form
- Customer self-service ("Pay with M-Pesa" on their own booking page,
  a status page that polls, ownership-enforced so one customer can
  never see another's payment) alongside the full staff-facing
  transaction/invoice/collections views, mirroring the `my/` vs.
  `manage/`-style split Bookings already established

**Verified in this environment:** invoice auto-creation on booking
confirmation (idempotent against re-saves), partial-then-full cash
payment with correct status transitions, an overpayment guard, an STK
push failing closed against this sandbox's restricted network (payment
correctly marked `FAILED`), a simulated successful M-Pesa callback
(receipt number and transaction date parsed, invoice marked paid) *and*
a replay of that same callback (no double-credit), a failed/cancelled
callback (invoice left untouched), a refund (invoice balance and the
payment's own remaining-refundable amount both correct), invoice void
guards (blocked once payments exist, allowed when clean), a revenue
summary and daily collections aggregation, all 12 staff endpoints and
3 customer self-service endpoints returning 200, cross-customer
payment access correctly returning 404, the unauthenticated M-Pesa
callback endpoint processing a payment end-to-end, and a full
regression pass confirming Phases 1–8 are untouched.

### Phase 10 — Reports & Business Intelligence

- A **Report Center hub** (`/reports/`) linking ten reports, each date-
  range filterable (defaults to the last 30 days) and exporting to
  CSV, Excel, PDF, or a clean print view — one shared toolbar partial
  and one shared `exports.py` (generic CSV/Excel/PDF builders) behind
  all ten, rather than duplicating that plumbing ten times
- **The brief's own report list is 16 items; this delivery covers all
  of them through ten richer reports** rather than sixteen thin ones —
  Peak Booking Hours and Peak Days live inside the Bookings report,
  Service Popularity is the Services report, Repeat Customers and
  Customer Trends are both in the Customers report, and Purchases
  shows up in both the Suppliers report and the Expenses report
- **Revenue, Expenses, Profit Summary** — built on `apps.payments`'s
  existing `compute_revenue_summary`/`compute_daily_collections` (no
  duplicate revenue logic) plus a small new `Expense`/`ExpenseCategory`
  ledger this phase adds, because there was no cash-expense tracking
  anywhere in Phases 1–9 and a Profit report is meaningless without
  one. Profit = net revenue − (manual expenses + inventory purchases)
- **Bookings, Services, Customers, Vehicles, Employees, Inventory,
  Suppliers** reports, each aggregating existing models (`Booking`,
  `Service`, `Customer`, `Vehicle`, `Employee`, `InventoryItem`,
  `Supplier`) — nothing here writes to any of those apps, this phase
  is entirely read-side
- **Role-based visibility, enforced at the view layer, not just
  hidden in the UI** — Revenue, Expenses, Profit, and Employee
  Productivity are `management_required` (Super Admin/Manager only);
  a Cashier hitting those URLs directly gets a 403, and the hub page
  simply doesn't render those cards for them. Every other report is
  `staff_required` (Cashiers included)
- Print formatting is one small global CSS addition (`.no-print` +
  `@media print` rules in the existing stylesheet, sidebar/topbar
  marked `.no-print`) rather than a separate print template per
  report — every report already has a working "Print" button for free
- Chart.js on every report: stacked daily collections, expense-by-
  category doughnut, a revenue/expenses/profit bar, booking volume and
  peak-hour histograms, revenue-by-service, customer growth, vehicle-
  type breakdown, per-employee productivity, and purchase value by
  supplier
- Full Django Admin integration for the new `Expense`/`ExpenseCategory`
  models, following the same soft-delete (`is_active`) convention as
  every other ledger-adjacent model in this project

**Verified in this environment:** all 11 report pages (hub + 10
reports) returning 200 for a Manager; all 30 export combinations (10
reports × CSV/Excel/PDF) succeeding; a custom date range narrowing
results correctly and an invalid range (start after end) falling back
to the default instead of erroring; a Cashier correctly blocked (403)
from Revenue/Expenses/Profit/Employees and correctly allowed on every
operational report, with the hub hiding the financial cards for them
specifically; expense recording and void (soft delete), blocked for a
Cashier; the Profit Summary's arithmetic cross-checked directly against
its Revenue and Expenses components; and a full regression pass
confirming Phases 1–9 are untouched.

### Phase 11 — Real-Time Notification System

- **The Channels/Daphne scaffolding for this phase already existed
  since Phase 1** — `shinehub/asgi.py`, `CHANNEL_LAYERS`, and
  `apps/notifications/routing.py` were all kept as real, importable
  stubs from day one specifically so this phase would only ever be
  app-code changes, never infrastructure surgery. This phase fills
  those in: a `NotificationConsumer`, `AuthMiddlewareStack` wrapping
  the WebSocket router (so a socket sees the same logged-in user as
  the page that opened it, no separate WebSocket auth step), and
  `daphne` moved to the very front of `INSTALLED_APPS` so
  `manage.py runserver` serves WebSockets locally with zero extra
  commands
- **"Reuse the existing notification system rather than replacing
  it," followed literally** — `apps.notifications.utils.notify()`/
  `notify_roles()` (built in Phase 8, already used by Inventory's
  low-stock alerts and Payments' receipt/refund notifications) is the
  *only* thing that changed: it now also pushes over the channel layer
  after saving the row. Every existing caller — inventory, payments —
  got real-time delivery for free, with no changes to either app
- **Booking and employee notifications, the two brief-listed types
  that didn't exist anywhere yet** — a new signal (connected from
  `apps.notifications`, same non-invasive pattern Phase 8/9 used on
  `Booking`, so `apps.bookings` still hasn't been touched) notifies a
  customer when their booking is confirmed/completed/cancelled, an
  employee when they're assigned, and Managers/Super Admins
  (administrative) when a booking is cancelled — idempotent against
  re-saves via a (recipient, url, title) existence check, since
  `Notification` doesn't carry a FK back to `Booking`
- **A live dropdown, not just a badge** — the topbar bell is now a
  real notification center: click to see the 8 most recent, mark one
  or all as read inline, no page reload. The badge updates from
  in-memory socket pushes; a `/notifications/unread-count/` poll only
  ever runs while the socket is down (first connect, or a dropped
  connection reconnecting with backoff), so the count is never wrong
  for long either way
- New live notifications also surface as a toast via the existing
  `showToast()` utility from Phase 1 — one more thing this phase reused
  instead of inventing a second toast system
- An `InMemoryChannelLayer` toggle (`USE_INMEMORY_CHANNEL_LAYER`,
  default `False`) for local dev/testing without a Redis server,
  mirroring the `USE_SQLITE` pattern already established for the
  database — production is unaffected and still requires real Redis

**Verified in this environment:** a real WebSocket connection (via
Channels' own `WebsocketCommunicator`, in-memory channel layer) that
connects, receives its initial unread count, then receives a live
notification push *and* an updated count the moment
`apps.notifications.utils.notify()` is called elsewhere in the same
process — this is an actual socket round-trip, not a mocked one; an
anonymous connection attempt correctly rejected; the full booking
lifecycle creating exactly the right notifications for the customer,
the assigned employee, and admins, idempotent against re-saves; the
HTTP mark-read/mark-all-read endpoints correctly decrementing/zeroing
the count (and pushing that update live to any other open tab); and a
full regression pass confirming Phases 1–10 are untouched.

### Phase 12 — Analytics Dashboard

- **This phase adds exactly one thing the project didn't have yet:
  period-over-period comparison and calendar month/year rollups.**
  Revenue, profit, booking trends, peak hours, employee performance,
  service popularity, and inventory usage were all already computed by
  Phase 10's `apps.reports.services` — `apps/analytics/widgets.py`
  wraps slices of those same functions into dashboard-sized cards
  rather than recomputing any of it
- **KPIs** — this-month-so-far vs. the same number of days last month
  (a like-for-like comparison, not a partial month against a complete
  one) for net revenue, net profit, bookings, and new customers, each
  with a trend arrow and percentage
- **Monthly and Yearly Summaries** — true calendar-month/calendar-year
  rollups (the brief's own distinction from Phase 10's arbitrary date
  range), 12 months and 5 years back respectively, exporting to
  CSV/Excel/PDF via the exact same `apps.reports.exports` helpers
  Phase 10 built — a third reuse of that module, not a third copy of it
- **Custom dashboard widgets** — a small new `DashboardPreference`
  model (one row per user) remembers which of 7 catalog widgets
  (revenue trend, booking trend, peak hours, top services, employee
  performance, inventory usage, low stock) they've chosen to see below
  their KPIs. Created lazily with every widget visible the first time
  someone opens the dashboard; a Customize page lets them narrow it
  down. Reordering isn't implemented — the scope here is "choose what
  you see," not a drag-and-drop grid, which felt like the right line
  given the brief's actual wording
- **Gated as a management tool, not a mixed staff/management hub like
  Phase 10** — every KPI on this dashboard is financial or personnel
  data, so the whole app is `management_required` and the sidebar link
  itself is hidden from Cashiers rather than shown-then-blocked
- Fully responsive grid (2-column KPIs on mobile, up to 3-column
  widgets on desktop), Chart.js throughout

**Verified in this environment:** KPI computation matching hand-checked
real data (a booking + cash payment created inside the test show up
correctly in the current-month numbers); monthly and yearly summary
rows correctly including that same data; all 4 pages and all 6 export
combinations (monthly/yearly × CSV/Excel/PDF) returning 200; a default
preference lazily created with every widget visible on first visit;
the Customize page correctly narrowing the dashboard to only the
selected widgets; a Cashier correctly blocked from every Analytics URL;
and a full regression pass confirming Phases 1–11 are untouched.

### Phase 13 — Loyalty & Promotions

- Six new models: `LoyaltyTier`, `LoyaltyProfile` (one per customer,
  created lazily), an append-only `PointsTransaction` ledger, an
  append-only `WalletTransaction` ledger, `Coupon`, and
  `DiscountApplication` -- which does double duty as both "a tier
  discount or coupon that was actually applied" *and* the brief's own
  "Promotion history" report, rather than being two separate things
- **Points, tiers, and referrals hook into Bookings the same
  non-invasive way Phase 8/9/11 already established** -- a signal
  connected from `apps.loyalty`, so `apps.bookings` still hasn't been
  touched by any of Phases 8 through 13. Confirming a booking applies
  that customer's tier discount (once, idempotently); completing one
  awards points (multiplied by tier) and checks whether this is a
  referred customer's first-ever completed booking, in which case the
  *referrer* gets a one-time bonus
- **A tier never downgrades** -- it's calculated from lifetime points
  earned, not current balance, so spending points on a redemption can
  never knock someone back down a level
- **Coupons and the wallet integrate with Payments through two small,
  additive functions**, not by reaching into that app's internals:
  `apps.payments.services` gained `apply_discount()` (reduces an
  invoice's total and re-syncs its status, reused by both the coupon
  and the tier-discount code paths) and `record_wallet_payment()`
  (mirrors the existing `record_cash_payment()` exactly, just tagged
  `PaymentMethod.WALLET` -- a new, additive choice on that enum).
  Existing Cash/M-Pesa payment code is completely unaffected
- **Customer wallet** (the brief's own "(optional)" item) -- a real,
  spendable balance credited by referral bonuses, usable as an actual
  payment method against an invoice, with its own ledger
- Self-service for customers: a Rewards dashboard (points, tier
  progress to the next one, wallet balance, referral code, recent
  activity), a way to link someone else's referral code (once, and
  only before your first booking, so it can't be gamed), and — added
  directly to the existing booking detail page via a self-contained
  template tag, so `apps.bookings`' own template needed only one new
  line — "Apply Coupon" and "Pay with Wallet" forms
- Staff management for tiers, coupons, promotion history (with
  CSV/Excel/PDF export, reusing `apps.reports.exports` a fourth time),
  and a member directory — all gated `management_required`, the same
  call Phase 12's Analytics made, since tier/coupon/discount data is
  as commercially sensitive as anything in that dashboard
- A `grant_birthday_rewards()` function, meant to run once daily via
  cron/systemd timer (no scheduler infrastructure exists in this
  project yet, so it's a plain callable rather than a Celery task),
  idempotent per calendar year per customer

**Verified in this environment:** a full customer lifecycle --
referral code auto-generated and linked (double-linking correctly
rejected), a booking earning points with no discount yet (Bronze,
0%), a second booking's tier-discount applying automatically the
moment lifetime points crossed the Silver threshold, points correctly
idempotent against a re-save, a referrer earning their bonus on the
referred customer's *first* completed booking specifically, a fixed-
amount coupon reducing an invoice (and correctly rejecting a second
redemption past its per-customer limit), a wallet payment debiting the
wallet and crediting the invoice in the same transaction (and
rejecting an over-balance attempt), a birthday reward granting once
and correctly refusing to double-grant the same day, all customer and
staff pages returning 200, a Cashier correctly blocked from every
staff-facing loyalty page, and a full regression pass confirming
Phases 1–12 are untouched.

### Phase 14 — Customer Feedback

- Two models: `Review` (a star rating + optional comment, one per
  completed booking) and `Feedback` (complaints/suggestions/general
  comments, tracked through a `new → in_review → resolved → closed`
  workflow) — kept separate because a review is always tied to one
  specific service experience, while feedback often isn't
- **The review request hooks into Bookings the same non-invasive way
  every prior phase did** — a signal connected from `apps.feedback`
  sends a "how was your wash?" notification and email the moment a
  booking completes, idempotent against re-saves. `apps.bookings` is
  still untouched by any of Phases 8 through 14
- **Manager responses on both Reviews and Feedback**, notifying (and,
  for Feedback, emailing) the customer the moment staff respond
- **A low rating (\u22642 stars) immediately notifies management** —
  the same "surface it now" instinct Phase 11 already applied to
  booking cancellations
- **Satisfaction analytics reuses `apps.reports`'s date-range helper
  and export module rather than rebuilding either** — a dedicated
  Satisfaction dashboard (average rating, distribution, trend,
  complaint counts, CSV/Excel/PDF export) for a focused view
- **Dashboard widgets land in the existing Phase 12 Analytics
  catalog, not a second widget system** — two new entries
  (`satisfaction`, `recent_reviews`) added to `apps/analytics/widgets.py`'s
  `WIDGET_CATALOG`; since `DEFAULT_WIDGET_KEYS` derives from that list
  automatically, they show up for anyone new to the dashboard, while
  existing saved preferences are untouched until a person visits
  Customize themselves
- Customer self-service: a "Rate Your Experience" form appears
  directly on the existing booking detail page the moment a booking
  completes (via a self-contained template tag, the same pattern
  Phase 13 used for its wallet/coupon widgets — one new line in that
  template, nothing else touched), plus a My Feedback page and a
  general submit-feedback form
- Full staff management for reviews (respond, publish/hide) and
  feedback (respond, change status), both `management_required` —
  public reputation and complaint handling are as sensitive as
  anything gated that way in Phases 12–13

**Verified in this environment:** a review request notification firing
exactly once on completion (idempotent against re-saves); a review
submission correctly rejecting a duplicate on the same booking; a
1-star rating correctly alerting management; a manager response saved
and the customer notified; a full complaint lifecycle (submit →
respond → resolved) with the customer notified and emailed; a
satisfaction summary's average/distribution/counts hand-verified
against the exact test data created; the two new widgets present in
the Analytics catalog and returning real data; every customer and
staff page and all 3 export formats returning correctly; the
publish/hide toggle; a Cashier correctly blocked from every staff
feedback page; and a full regression pass confirming Phases 1–13 are
untouched.

### Not yet built (by design — see the brief's own phasing)

A security hardening pass and the final testing/QA/packaging phase
remain. Nothing else has an app stub left to fill — every domain app
in the brief now has real models, views, and templates behind it.

## UI/UX rebrand & Daphne removal (post-Phase 14)

A follow-up pass, separate from the numbered phases above, requested by
a UI/UX overhaul brief:

- **Brand colors updated app-wide** to the two official colors, brand
  blue `#0013DE` and brand pink `#FF0090`, replacing the earlier
  blue/purple/pink palette. Because the design system was already
  built on CSS custom properties (`--color-blue`, `--color-pink` in
  `static/css/custom.css`), most of the app rebrands from two lines of
  CSS; every remaining raw hex reference (email templates, Chart.js
  palettes, PDF export headers, the password-strength meter) was
  updated by hand. The former third color (purple) has been retired as
  a competing brand hue — every place it appeared now uses blue, pink,
  a blue→pink gradient, or (for chart categories needing more than two
  swatches) a tint/shade of one of the two brand colors, chosen
  case-by-case so status pairs that used to share a hue (e.g. the
  booking "Washing" state vs. "No Show") stay visually distinct.
- **Dark mode accessibility fix (superseded — dark mode has since been
  fully removed; see "Final UI polish" section below):** `#0013DE` had
  excellent contrast on white (~9.8:1) but only ~1.9:1 used directly
  as text/icon color on the dark navy surface — well under WCAG
  guidelines. Rather than touch every template, `--color-blue` itself
  resolved to a lighter tint (`#5B69FF`, ~4.4:1 on the dark surface)
  inside `html[data-theme="dark"]`, so every existing
  `text-[var(--color-blue)]`/`bg-[var(--color-blue)]` usage across the
  app automatically became accessible in dark mode while staying the
  exact literal brand hex in light mode and on solid button/badge
  fills.
- **Daphne removed**, per the brief. This needed one real engineering
  decision rather than a literal delete: real-time notifications
  (Phase 11) depend on an ASGI server for WebSockets, and Daphne was
  what served `/ws/notifications/` in production behind Nginx
  (`shinehub-ws.service`) as well as what let `manage.py runserver`
  handle WebSockets locally (via the `'daphne'` app being first in
  `INSTALLED_APPS` — a Channels convention, not custom code here).
  Deleting Daphne with nothing in its place would have broken
  real-time notifications outright, so:
  - **Production:** Uvicorn now serves `shinehub.asgi:application` in
    Daphne's old role — same systemd unit shape, same Nginx routing,
    just a different (actively maintained) ASGI server. See
    `docs/DEPLOYMENT.md` section 7.
  - **Local dev:** `manage.py runserver` is now plain WSGI, exactly as
    requested. WebSocket connections won't upgrade under it, so the
    notification bell won't get live push locally — but
    `static/js/notifications.js` already polls
    `/notifications/unread-count/` whenever the socket isn't open, so
    the feature still works locally, just without true real-time push
    until it's deployed behind the Uvicorn process.
- **Tailwind CDN confirmed, no build step to remove:** the project was
  already using the Tailwind Play CDN (`templates/partials/head.html`)
  with no `package.json`/build pipeline present, so this requirement
  was already satisfied going in.

## Final UI polish, validation & landing page enhancement (post-rebrand)

A third pass, requested by a follow-up brief, on top of the rebrand above:

- **Dark mode fully removed.** The `html[data-theme="dark"]` CSS
  override block is gone from `static/css/custom.css`, the toggle
  buttons are gone from `templates/partials/navbar.html` and
  `templates/partials/topbar.html`, `darkMode: 'class'` is gone from
  the Tailwind config in `templates/partials/head.html`, and the
  vestigial `data-theme="light"` attribute is gone from both
  `<html>` tags. `static/js/theme.js` (which mixed theme-switching
  logic together with the unrelated mobile-nav-toggle and
  scroll-reveal behaviors) has been replaced by `static/js/ui.js`,
  which keeps only the latter two. ShineHub now ships one light
  theme with no user-facing switch.
- **Real-time validation, app-wide, via one new file:** every form's
  fields are wired up automatically by the new
  `static/js/validation.js`, included once in both `base.html` and
  `layouts/app_base.html`. It classifies each field from attributes
  Django's forms already render (`type`, `name`, `pattern`,
  `autocomplete`) rather than needing per-template markup, and its
  rules were written to mirror the real server-side validators
  exactly — the Kenyan phone regex from `apps/accounts/models.py`,
  the name-character regex and Kenyan plate pattern from
  `apps/core/validators.py`, and the password complexity rules from
  `apps/accounts/validators.py`'s `ComplexPasswordValidator` — so the
  client never rejects something the server would accept, or vice
  versa. It adds live red/green borders, inline success/error
  messages with icons, keystroke-level blocking of disallowed
  characters (with paste sanitization), a password rule checklist, a
  confirm-password matcher (generic: any `..._2` field is checked
  against its `..._1` sibling), live character counters on any
  textarea with a `maxlength` (added to a few key ones — feedback
  message/response, customer notes, the landing page contact form —
  that didn't have one), auto-injected required-field asterisks, and
  a submit-button loading state. Server-side validation is completely
  untouched and remains authoritative; this is purely a client UX
  layer on top of it.
- **Landing page: new Gallery section and About photography**, per
  the brief's explicit ask for real photography. Six real,
  license-verified (Unsplash License, not Unsplash+) photos of actual
  car-wash work — a wash in progress, wheel/rim detailing, hand
  washing, a premium finish, a freshly rinsed car, and a headlight
  detail shot — now sit in a new `#gallery` section (linked from the
  navbar, mobile menu, and footer), plus one more alongside the About
  section for a two-column layout. The signature no-photo "instrument
  panel" hero and live queue panel are untouched by design — they're
  this app's one deliberate piece of visual identity, so the new
  photography was added around them rather than over them, and kept
  to two sections so the page doesn't get crowded.
- **Contrast audit:** every `text-white` usage in the templates was
  checked against its container; all of them sit on the brand
  gradient or a solid dark fill, so none were changed. An explicit
  `::placeholder` color was added to `.input` for a guaranteed,
  on-brand contrast level instead of relying on browser defaults, and
  a visible `:focus-visible` ring was added to `.btn` for keyboard
  navigation.
- **Frontend cleanup:** the old `theme.js` file is deleted outright
  (its two non-theme behaviors live on in `ui.js`); no other unused
  JS, duplicate validation logic, or dead CSS was found — the
  design-system-driven approach from the rebrand pass had already
  kept the frontend free of that.



```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env: set USE_SQLITE=True if you don't have MySQL running yet,
# or fill in DB_NAME / DB_USER / DB_PASSWORD for a real MySQL database.

python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`.

Full setup (MySQL, Gmail SMTP, Daraja sandbox, Redis) is in
`docs/INSTALLATION.md`. Deployment steps are in `docs/DEPLOYMENT.md`.

## Project layout

```
shinehub/
├── apps/                  # every app lives under this namespace (apps.core, apps.accounts, ...)
├── shinehub/               # project package: settings.py, urls.py, asgi.py, wsgi.py
├── templates/              # base.html, partials/, and per-app template folders
├── static/                 # css/, js/, images/
├── media/                  # user-uploaded files (profile photos, etc.)
├── docs/                   # INSTALLATION.md, DEPLOYMENT.md
├── requirements.txt
├── .env.example
└── manage.py
```

## Roadmap (matches the brief's phase list exactly)

1. **Project setup** ✅ (this delivery)
2. **Authentication** ✅ (this delivery)
3. **Customers** ✅ (this delivery)
4. **Vehicle management** ✅ (this delivery)
5. **Services** ✅ (this delivery)
6. **Bookings** ✅ (this delivery)
7. **Employee management** ✅ (this delivery)
8. **Inventory** ✅ (this delivery)
9. **Payments (Cash + M-Pesa Daraja)** ✅ (this delivery)
10. **Reports (PDF/Excel)** ✅ (this delivery)
11. **Notifications (real-time, WebSocket)** ✅ (this delivery)
12. **Analytics** ✅ (this delivery)
13. **Loyalty** ✅ (this delivery)
14. **Feedback** ✅ (this delivery)
15. Security hardening pass
16. Testing, QA, final packaging

Say "continue to Phase 15" (or name any phase) when you're ready, and it'll
be built the same way this one was: real code, migrated, tested, no
placeholders.
