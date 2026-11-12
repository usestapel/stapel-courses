# SPEC — stapel-courses 0.1.0 (courses, lessons, enrollment, progress, quizzes, certificates)

Status: **built locally, not public** (brigade CR, brick wave 2026-11-12;
no remote, no tag, no PyPI — owner's call).
Queue: `SPEC-BRICKS-WAVE-2026-11-12.md` §1 row `stapel-courses`; gates §3.
Consumers: this file is quoted by the React pair brief and the Studio
"education" archetype recipe; the gates in §11 enforce it (tests named
there). House style: `SPEC-STAPEL-ORDERS.md` applies verbatim (SimpleRouter
is not used — plain paths like stapel-reservations; `StapelAPIView` seams,
`AppSettings` + CONFIG.MD, `errors.py`, `@access`, `mutate_and_emit`,
`AnchorPagination`, `user_id CharField(64)`, sibling-import ban, MODULE.md,
capabilities.json). No client names.

## 1. Scope

| In (0.1.0) | Out (named) |
|---|---|
| `Course` → `Module` → `Lesson` (ordered), typed content blocks | live classes (stapel-video owns them) |
| `Enrollment` FSM with source and optional expiry | assignments with manual grading beyond a staff "passed" flag (rubrics, files, comments) |
| access gate strategy registry `free` / `enrolled` / `purchased` / `entitlement` | SCORM / xAPI / LTI |
| purchases through the orders purchasable seam (`course` type) and its facts | payments of its own (orders + billing own money) |
| `LessonProgress` + an enrollment progress cache | cohorts/teams as a model (an opaque `scope` id is reserved, not built) |
| drip (`none` / `days` / `date`) and sequential unlock | question banks shared between quizzes, randomised question subsets |
| `Quiz` / `Question` / `Attempt` with server-side grading | partial credit, essay questions, timed quizzes |
| completion rule → `Certificate` + public verification | certificate PDF rendering (a frontend or a doc service renders the record) |
| learner API, author/staff API, facts, Functions, GDPR, admin, seed command | discussion, reviews (stapel-chat / stapel-reviews) |

## 2. Models (app label `courses`)

Users are id strings (`user_id CharField(64)`, `str(user.pk)`), never FKs —
a pseudonymised id must fit. Media is an opaque id (`media_id ≤ 64`,
stapel-cdn / stapel-recordings own resolution); courses never fetches media.

- **Course**: `slug` (unique, ≤ 80), `title` ≤ 200, `summary` ≤ 500,
  `description` ≤ 20 000, `status` draft/published/archived, `author_id`,
  `cover_media_id`, `level` (all/beginner/intermediate/advanced),
  `language` ≤ 16, `access` (a registered strategy name), `price`
  Decimal(12,2) null + `currency` (purchased courses), `entitlement_key`
  ≤ 100, `drip` none/days/date, `sequential` bool, `access_days` (null =
  forever; enrollment expiry length), `certificate_enabled`, `scope` ≤ 64
  (opaque cohort/workspace id, reserved, filterable), `published_at`.
  Status edges: draft → published → archived → published. A published
  course's `slug` is frozen (it is in URLs and certificates).
- **Module**: `course`, `title`, `position`. Ordered `(position, id)`.
- **Lesson**: `module` (+ denormalised `course`), `title`, `position`,
  `blocks` JSON, `duration_seconds`, `free_preview`, `required` (counts for
  completion), `review_required` (the simple staff-passed flag), drip fields
  `unlock_after_days` / `unlock_at`.
- **Quiz**: `course`, exactly one of `lesson` / `module`, `title`,
  `pass_mark` (0–100 %), `max_attempts` (0 = unlimited), `shuffle_questions`,
  `shuffle_choices`, `required`, `reveal` never/after_submit/after_pass.
- **Question**: `quiz`, `kind` single/multiple/true_false/short_text,
  `prompt` ≤ 2000, `position`, `points` 1–100, `choices` JSON
  `[{"id", "text"}]` (≤ 20), `correct` JSON (choice ids / bool / accepted
  strings ≤ 20), `match` exact/normalised, `explanation` ≤ 2000.
- **Enrollment** (unique `(course, user_id)`): `status`, `source`
  free/purchase/entitlement/staff, `order_id` (the purchase that granted
  it), `expires_at`, progress cache (`completed_lessons`, `required_lessons`,
  `passed_quizzes`, `required_quizzes`, `progress_percent`,
  `last_lesson_id`), `activated_at`, `completed_at`.
- **CoursePurchase** (unique `(order_id, course)`): the idempotency ledger of
  the order facts: `user_id`, `state` placed/paid/confirmed/cancelled.
- **LessonProgress** (unique `(user_id, lesson)`): `status`
  started/submitted/completed, `position_seconds`, timestamps.
- **Attempt** (unique `(quiz, user_id, number)`): `status`
  in_progress/submitted, `seed`, `question_order`, `choice_order`,
  `answers`, `results`, `score`, `max_score`, `percent`, `passed`.
- **Certificate** (unique `number`, unique `(course, user_id)`):
  `holder_name` and `course_title` snapshots, `issued_at`, `revoked_at`.

`@access`: Course/Module/Lesson/Quiz/Question standard; Enrollment,
Certificate sensitive; LessonProgress, Attempt, CoursePurchase ops.

## 3. Enrollment FSM

`pending → active → completed`; `active|completed → expired` (beat, on
`expires_at`); `pending|active|completed → cancelled`; `cancelled|expired →
active` (re-grant / re-purchase / re-enroll); `cancelled|expired → pending`
(a new order placed). Access-granting statuses: **active, completed**. A
table `TRANSITIONS` (`fsm.py`) with an inversion test over every pair;
illegal → `error.409.enrollment_transition_invalid`. Staff transitions:
`active`, `cancelled`, `expired`.

## 4. Access gate

`STAPEL_COURSES["ACCESS_STRATEGIES"]` — MERGE registry `{name: dotted path |
None}` over the four built-ins; a dotted path REPLACES a built-in of the same
name. `Course.access` names one (`DEFAULT_ACCESS` = `enrolled` for new
courses). A strategy answers two questions:

| Strategy | self-enroll (`POST enroll/`) | content access |
|---|---|---|
| `free` | yes (source `free`), optional | everyone, enrolled or not (anonymous reads) |
| `enrolled` | yes (source `free`) | an enrollment in active/completed |
| `purchased` | no → `error.403.course_purchase_required` | an enrollment in active/completed (from an order or a staff grant) |
| `entitlement` | yes when `billing.check_entitlement` allows (source `entitlement`) | enrollment in active/completed **and** the entitlement still allowed (cached `ENTITLEMENT_CACHE_SECONDS`) |

An entitlement Function that is not reachable answers `error.503.
entitlement_unavailable` — never a guess. Staff and the course's author
always have access. A `free_preview` lesson is open to everyone regardless
of strategy, drip and sequence.

Lock reasons (outline and the 403 `error.403.lesson_locked` params):
`sign_in_required`, `enrollment_required`, `purchase_required`,
`entitlement_required`, `enrollment_inactive`, `drip` (with `unlocks_at`),
`sequential` (with `after_lesson_id` or `after_quiz_id`). The 403 always
carries all four params `reason`, `unlocks_at`, `after_lesson_id`,
`after_quiz_id` (null when they do not apply), declared in `errors.json`;
`tests/test_error_params.py` holds every raised error's params to its
declaration. Order of evaluation: access → drip → sequence.

**Drip** (`Course.drip`, default `DEFAULT_DRIP` = `none`): `days` unlocks a
lesson `unlock_after_days` after `activated_at`; `date` unlocks it at
`unlock_at`. **Sequential** (`Course.sequential`, default
`DEFAULT_SEQUENTIAL` = False): a lesson is locked until every earlier
*required* lesson is completed and every required quiz attached to those
lessons/their modules is passed.

## 5. Purchases (orders seam — never imported)

`courses.purchasables` is the purchasable resolver Function (orders'
`purchasables` contract). Keys are course ids (strings; slugs change before
publish). A key is known iff the course exists with `access = purchased` and
a price; `available = status == published`; `max_quantity = 1`. The preset
fragment `stapel_courses.preset.SETTINGS_DEFAULTS["STAPEL_ORDERS"]` registers
`{"course": {"resolve": "courses.purchasables"}}` — the host (or Studio)
merges it; orders never learns a course model.

Facts consumed (handlers idempotent on `CoursePurchase(order_id, course)`):

| Fact | Effect |
|---|---|
| `orders.order.placed` (lines with `purchasable_type == PURCHASABLE_TYPE`) | ledger rows `placed`; enrollment created/moved to `pending` (source `purchase`, `order_id`); `PURCHASE_ACTIVATION = "placed"` activates at once |
| `orders.order.paid` | ledger `paid`; pending enrollments of that order → `active` (`paid` and `confirmed` modes) |
| `orders.order.status_changed` `to == "confirmed"` | activates under `PURCHASE_ACTIVATION = "confirmed"` (an order confirmed by hand with `PAYMENT="none"`) |
| `orders.order.status_changed` `to == "cancelled"`, `orders.order.refunded` | ledger `cancelled`; the enrollment that order granted → `cancelled` (an enrollment granted by staff or another order is left alone) |

Activation sets `expires_at = now + access_days` when the course has one.
A fact for an unknown course or a line of another type is ignored with an
INFO line (someone else's event). `orders.order.refunded` is not emitted by
stapel-orders 0.1.0 — upstream ask O1; the consumer is ready.

## 6. Progress and completion

`POST courses/{slug}/lessons/{id}/progress/ {status?, position_seconds?}` is
an idempotent upsert on `(user_id, lesson)`: status only moves forward
(started → submitted → completed; a lesson with `review_required` cannot be
completed by the learner — `submitted` waits for staff `POST
author/lessons/{id}/review/ {user_id, passed}`); `position_seconds` is the
last playback position (may go back). Writing progress needs content access
(the same gate as reading). Each write recomputes the enrollment progress
cache in the same transaction under `select_for_update` on the enrollment.

Completion rule (`COMPLETION_RULE`, REPLACE dotted path; default: every
required lesson completed **and** every required quiz passed, with at least
one required item) is evaluated after a lesson completion and a quiz pass.
True → enrollment `completed` + `courses.course.completed`; then, when
`CERTIFICATES` and `course.certificate_enabled`, a `Certificate` is issued
once (`courses.certificate.issued`). Free (non-enrolled) learners of a
`free` course are auto-enrolled on their first progress write so the cache
has a row.

## 7. Quizzes

`POST quizzes/{id}/attempts/` starts an attempt (or returns the open one —
idempotent): attempts counted under `select_for_update` on the enrollment
row; over `max_attempts` → `error.409.quiz_attempts_exhausted`; a passed
quiz may still be retaken while attempts remain. The seed (31-bit) is stored;
question and choice orders are derived from it and stored, so every read of
the attempt shows the same order.

**No answer leaks before submission**: the attempt response for an open
attempt carries `id/kind/prompt/points/choices[{id,text}]` per question and
never `correct`, `explanation` or per-question results (a test inspects the
raw body). After submission, `results` carry `correct` (bool) and `points`;
the right answers and explanations are shown per `Quiz.reveal`.

Grading (server-side only): single — exactly the one correct id; multiple —
the selected set equals the correct set (all-or-nothing); true_false — the
bool; short_text — `exact` compares after `strip()`, `normalised` compares
NFKC + casefold + collapsed whitespace + stripped punctuation, against each
accepted string. `percent = 100 * score / max_score` (2 dp, half-up);
`passed = percent >= pass_mark`. A submit replay of a submitted attempt
returns 200 with the same result.

## 8. Certificates

`number` = `CERTIFICATE_NUMBER_PREFIX-YYYY-XXXXXXXX` (Crockford base32,
unique, retried on collision). `holder_name` from `HOLDER_NAME_RESOLVER`
(dotted path; default: the user's full name, else empty). `GET
certificates/{number}/` is public (anonymous): `{number, valid}` plus only
the fields in `PUBLIC_VERIFY_FIELDS` (`holder_name`, `course_title`,
`course_slug`, `issued_at`; default `course_title`, `issued_at`). An unknown
number is 404. A revoked certificate answers `valid: false`.

## 9. API (`/courses/api/v1/`)

Learner: `GET courses/` (catalog, published, `?level=&scope=`, anchor) ·
`GET courses/{slug}/` (outline with lock reasons, my enrollment, access) ·
`POST courses/{slug}/enroll/` · `GET courses/{slug}/lessons/{id}/` (content,
gated) · `POST courses/{slug}/lessons/{id}/progress/` · `GET
courses/{slug}/progress/` · `GET me/enrollments/` (anchor) · `GET
me/certificates/` · `GET quizzes/{id}/` · `POST quizzes/{id}/attempts/` ·
`GET attempts/{id}/` · `POST attempts/{id}/submit/` · `GET
certificates/{number}/` (public verification).

Author/staff (`author/…`): courses list/create/detail/update/delete(draft
only), `publish/` `archive/`, modules, lessons, quizzes (with answers),
questions, course enrollments list + staff grant, enrollment transition,
lesson review, certificate revoke. Authors are `Course.author_id`; staff see
all. Who may create a course: axis `AUTHORING` (`staff` default | `members`).

Wire types: a lesson's `blocks` is `LessonBlock[]`, a `oneOf` of
`TextBlock` / `VideoBlock` / `AttachmentBlock` / `EmbedBlock` (each with a
literal `type`) and `CustomBlock` (any type a host registers through
`BLOCK_TYPES`, its own fields, never a built-in name). A question's
`correct` is a string list (single / multiple: choice ids; short_text:
accepted answers) or a bool (true_false). Author resources split request
from response: POST bodies are `Author<Resource>Request`, PATCH bodies
`PatchedAuthor<Resource>` (same writable fields, all optional); neither
carries the read-only fields (ids, parents, timestamps, a quiz's
questions) the `Author<Resource>` responses add. The author/staff
enrollment list, grant and transition answer `AuthorEnrollment`: the
learner-facing `Enrollment` plus `user_id` and `learner` (`LearnerCard`
`{user_id, display_name, avatar_ref}` from `CARDS_FUNCTION`, default
`profiles.public_cards`, one batched call per page; `null` when profiles
is absent, failing or does not know the id). The learner's own enrollment
never names anyone.

Guest stance: catalog/outline/lesson/verify `ANONYMOUS_ALLOWED`; enroll,
progress, attempts `ANONYMOUS_ALLOWED` declared with
`ENROLLMENT_REQUIRES_ACCOUNT` (default True → a guest session gets
`error.403.enrollment_requires_account`, remediation `reauthenticate`;
an anonymous request gets 401); author views `ANONYMOUS_DENIED`.

## 10. Settings (`STAPEL_COURSES`), Functions, facts, GDPR

Settings: `ACCESS_STRATEGIES {}`, `DEFAULT_ACCESS "enrolled"`, `DEFAULT_DRIP
"none"`, `DEFAULT_SEQUENTIAL False`, `AUTHORING "staff"`,
`ENROLLMENT_REQUIRES_ACCOUNT True`, `PURCHASABLE_TYPE "course"`,
`PURCHASE_ACTIVATION "paid"` (paid/confirmed/placed),
`ENTITLEMENT_FUNCTION "billing.check_entitlement"`,
`ENTITLEMENT_KEY_TEMPLATE "course:{slug}"`, `ENTITLEMENT_CACHE_SECONDS 300`,
`BLOCK_TYPES {}` (MERGE, dotted validator paths), `EMBED_HOSTS []` (empty =
any https host), `DEFAULT_PASS_MARK 70`, `DEFAULT_MAX_ATTEMPTS 3`,
`COMPLETION_RULE`, `CERTIFICATES True`, `PUBLIC_VERIFY_FIELDS`,
`CERTIFICATE_NUMBER_PREFIX "CERT"`, `HOLDER_NAME_RESOLVER`, `NOTIFY True`,
`COURSE_URL_TEMPLATE ""`, `CERTIFICATE_URL_TEMPLATE ""`. Axes (capabilities):
`DEFAULT_ACCESS`, `DEFAULT_DRIP`, `DEFAULT_SEQUENTIAL`, `AUTHORING`,
`ENROLLMENT_REQUIRES_ACCOUNT`, `PURCHASE_ACTIVATION`, `CERTIFICATES`.

Functions: `courses.purchasables` (§5), `courses.enrollment.status
{user_id, course_id}` → `{enrolled, status, source, has_access, expires_at,
progress_percent}`, `courses.certificate.verify {number}` → the public view.

Facts (inside `mutate_and_emit`, key = enrollment/certificate id; no PII):
`courses.enrollment.activated`, `courses.enrollment.status_changed`,
`courses.course.completed`, `courses.certificate.issued`. Consumed:
`orders.order.placed|paid|status_changed|refunded`, `user.merged`
(re-parent a guest's enrollments, progress, attempts, certificates; a
course both accounts hold keeps the survivor's row with the union of
progress), `user.deleted` via `register_gdpr_owner`.

GDPR (`section = "courses"`, subject `account`): export = enrollments,
progress, attempts (answers included), certificates. Erase = delete
progress, attempts, enrollments and purchase ledger rows; certificates are
anonymised (user id pseudonymised, holder name cleared) and revoked, so a
verification answers `valid: false` and names nobody.

Checks: `E001` an `ACCESS_STRATEGIES` entry does not import to a strategy;
`E002` `DEFAULT_ACCESS` names no registered strategy; `E003`
`PUBLIC_VERIFY_FIELDS` names an unknown field; `E004` a `BLOCK_TYPES`
validator does not import; `E005` an enum setting (`DEFAULT_DRIP`,
`AUTHORING`, `PURCHASE_ACTIVATION`) is out of vocabulary; `E006`
`COMPLETION_RULE` / `HOLDER_NAME_RESOLVER` does not import; `W001`
`DEFAULT_ACCESS = "entitlement"` and the entitlement Function is not
reachable. With or without stapel-orders / stapel-billing installed the
defaults raise nothing.

## 11. Gates

pytest (sqlite) incl.: FSM table inversion; answers-never-leaked (raw body
scan for open attempts); stored-seed shuffle stability; grading per kind;
attempt-limit concurrency (`select_for_update`, two racing starts at the
limit → one attempt); enrollment activation idempotency (same fact twice →
one enrollment, one `activated` fact); cancel/refund deactivates only the
order's own grant; drip/sequential lock reasons; completion → certificate
once; public verify reveals only configured fields; GDPR export + erase;
user.merged; checks with and without fake orders/billing Functions;
architecture grep (no sibling import); contract drift (`make contract`),
wire test over `docs/schema.json`; `stapel-verify`; migration from zero.
