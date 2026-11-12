# stapel-courses — MODULE.md

> Agent-facing map of this module: what it provides, where to extend it
> without forking, and what not to do. Kept in the same change as any edit
> to a seam. See also README.md, CHANGELOG.md and docs/SPEC.md (the design).

## What this module provides

- **Course → Module → Lesson** (ordered). A lesson is a list of typed content
  blocks (`blocks.py`: text, video / attachment by opaque media id, embed by
  https URL). Courses are draft → published → archived (→ published); a
  published course's slug is frozen.
- **Enrollment** (one row per course and learner) with a table FSM
  (`fsm.py`: pending → active → completed / expired / cancelled, re-grant
  from expired/cancelled), a source (free, purchase, entitlement, staff) and
  an optional expiry (`Course.access_days`, beat).
- **The access gate** (`access.py` strategies + `services/gate.py`): the
  outline names a lock reason for every lesson and quiz; the content, progress
  and quiz endpoints ask the same computed view. Drip (days / date) and
  sequential unlock pace a course.
- **Progress** (`services/progress.py`): idempotent forward-only upserts, a
  progress cache on the enrollment, the completion rule, a certificate.
- **Quizzes** (`services/quizzes.py`): server grading, attempt limits under
  a lock, a stored shuffle seed, answers never sent before submission.
- **Purchases** (`services/purchases.py`): the orders purchasable resolver
  and the order-fact consumers. API under `/courses/api/v1/`.

## Extension points (fork-free)

### Settings — `STAPEL_COURSES` namespace (`conf.py`, registry in CONFIG.MD)

| Key | Default | What it customizes |
|---|---|---|
| `ACCESS_STRATEGIES` | `{}` | MERGE registry `{name: dotted path \| None}` over free / enrolled / purchased / entitlement; a dotted path under a built-in name REPLACES it. E001. |
| `DEFAULT_ACCESS` | `"enrolled"` | Axis. Strategy of a new course. E002 when unregistered. |
| `DEFAULT_DRIP` / `DEFAULT_SEQUENTIAL` | `"none"` / `False` | Axes. Pacing of a new course (each course overrides). |
| `AUTHORING` | `"staff"` | Axis. `members` lets any non-guest account create and edit its own courses. |
| `ENROLLMENT_REQUIRES_ACCOUNT` | `True` | Axis. Guests get `error.403.enrollment_requires_account`. A switch, not posture. |
| `PURCHASABLE_TYPE` | `"course"` | The orders line type that means a course. |
| `PURCHASE_ACTIVATION` | `"paid"` | Axis. `paid` / `confirmed` / `placed`: which order fact activates. |
| `ENTITLEMENT_FUNCTION` / `ENTITLEMENT_KEY_TEMPLATE` / `ENTITLEMENT_CACHE_SECONDS` | `billing.check_entitlement` / `course:{slug}` / `300` | The billing question, by name. |
| `BLOCK_TYPES` | `{}` | MERGE registry of block validators. E004. |
| `CARDS_FUNCTION` | `"profiles.public_cards"` | Learner display cards on the author/staff lists, asked by name, batched per page; `""` or unreachable = `user_id` only. |
| `EMBED_HOSTS` | `[]` | Axis. Embed host allowlist; empty = any https. Exposed as `embed_hosts` on the outline, the lesson and the author tree. |
| `DEFAULT_PASS_MARK` / `DEFAULT_MAX_ATTEMPTS` | `70` / `3` | New quiz defaults. |
| `COMPLETION_RULE` | `services.progress.default_completion_rule` | REPLACE dotted path `(enrollment) -> bool`. E006. |
| `CERTIFICATES` | `True` | Axis. Certificates on completion. |
| `PUBLIC_VERIFY_FIELDS` | `["course_title", "issued_at"]` | What `GET certificates/{number}/` shows. E003. |
| `CERTIFICATE_NUMBER_PREFIX` | `"CERT"` | `PREFIX-YYYY-XXXXXXXX`. |
| `HOLDER_NAME_RESOLVER` | `services.certificates.default_holder_name` | REPLACE dotted path `(user_id) -> str`. E006. |
| `NOTIFY`, `COURSE_URL_TEMPLATE`, `CERTIFICATE_URL_TEMPLATE` | `True`, `""`, `""` | Best-effort notifications and their links. |

### Access strategies (`access.py`)

```python
from stapel_courses.access import AccessStrategy, Decision, OPEN

class CohortOnly(AccessStrategy):
    def self_enroll_source(self, course, user_id): ...   # raise CoursesError to refuse
    def content_access(self, course, user_id, enrollment) -> Decision: ...

STAPEL_COURSES = {"ACCESS_STRATEGIES": {"cohort": "myapp.access.CohortOnly"}}
```

`GET author/access-strategies/` lists the effective registry (name,
built-in or not) and `DEFAULT_ACCESS` for an editor's picker; `Course.access`
stays a string validated against it. Staff and the author bypass strategies; `free_preview` lessons never reach
one. An unknown `Course.access` gates like `enrolled` (fail closed).

### Selling a course (orders, never imported)

`stapel_courses.preset.SETTINGS_DEFAULTS["STAPEL_ORDERS"]["PURCHASABLE_TYPES"]`
= `{"course": {"resolve": "courses.purchasables"}}`; merge it into the host's
`STAPEL_ORDERS`. The purchasable key is the course id (string). Known only
for `access="purchased"` with a price; `available` = published.

### Serializer seams and presenters (`views.py`, `presenters.py`)

Views inherit `StapelAPIView`. Presentation swaps via `STAPEL_SWAP`:
`STAPEL_COURSES_COURSE_PRESENTER`, `_ENROLLMENT_`, `_LESSON_`, `_QUIZ_`,
`_ATTEMPT_`, `_CERTIFICATE_PRESENTER`. The attempt presenter is the one place
that decides what of a question a learner sees.

| View group | Guest stance | Notes |
|---|---|---|
| `CatalogView`, `CourseOutlineView`, `LessonView`, `QuizView`, `CertificateVerifyView` | allowed (AllowAny) | content gated by the strategy; drafts 404 |
| `EnrollView`, `LessonProgressView`, `CourseProgressView`, `My*View`, `QuizAttemptsView`, `Attempt*View` | allowed (IsAuthenticated); body enforces `ENROLLMENT_REQUIRES_ACCOUNT` | attempts scoped to `user_id == me` (404 otherwise) |
| `Author*View` | denied (IsNotAnonymousUser) | scoped to `author_id == me` or staff; others 404; bodies are `Author*RequestSerializer` (POST) / `Author*PatchSerializer` (PATCH, emitted `PatchedAuthor*`) |

### Events & functions (comm surface)

| Kind | Name | Payload | Schema |
|---|---|---|---|
| Action (emits) | `courses.enrollment.activated` | `{enrollment_id, course_id, course_slug, user_id, source, order_id, expires_at}` | `schemas/emits/` |
| Action (emits) | `courses.enrollment.status_changed` | `{enrollment_id, course_id, user_id, from, to, actor, reason?}` | `schemas/emits/` |
| Action (emits) | `courses.course.completed` | `{enrollment_id, course_id, course_slug, user_id, completed_at}` | `schemas/emits/` |
| Action (emits) | `courses.certificate.issued` | `{certificate_id, number, course_id, user_id, issued_at}` | `schemas/emits/` |
| Action (consumes) | `orders.order.placed` / `.paid` / `.status_changed` / `.refunded` | course lines; idempotent on `CoursePurchase(order_id, course)` | `schemas/consumes/` |
| Action (consumes) | `user.merged` | re-parents enrollments, progress, attempts, certificates | `schemas/consumes/` |
| Action (consumes) | `user.deleted`, `gdpr.erasure.requested` | via `register_gdpr_owner("courses", ["account"], …)` | core |
| Function (provides) | `courses.purchasables` | orders purchasables contract | `schemas/functions/` |
| Function (provides) | `courses.enrollment.status` | `{user_id, course_id}` → standing | `schemas/functions/` |
| Function (provides) | `courses.certificate.verify` | `{number}` → public view | `schemas/functions/` |
| Function (calls) | `ENTITLEMENT_FUNCTION` | `{user_id, key}` → `{allowed, …}` | billing's |
| Function (calls) | `CARDS_FUNCTION` | `{user_ids}` → `{profiles, missing}` | profiles' `public_cards` |
| Notification | `courses.enrollment_activated`, `courses.completed`, `courses.certificate_issued` | `services/events.variables` | stapel-notifications (types not in its catalog yet) |

### Beat and commands

`get_courses_beat_schedule()`: expiry every 15 minutes;
`manage.py courses_housekeeping` runs it; `manage.py courses_seed_demo`
creates a small published demo course (`seed.py`).

### Reserved, not built

`Course.scope` (an opaque cohort/workspace id: stored and filterable, no
membership check), partial credit, timed quizzes, question banks, PDF
certificates, SCORM/xAPI, live classes (stapel-video).

## Contract emission

`make contract` emits `docs/{schema,flows,errors,capabilities}.json`,
`docs/llms.txt` and README.md (from `docs/readme.md`); enum names pinned in
`_codegen_settings.enum_name_overrides()`; `tests/test_contract_wire.py`
drives every declared operation. Emission is pinned to Python 3.12.

## Anti-patterns

- **Never import a sibling module** (`stapel_orders`, `stapel_billing`,
  `stapel_cdn`, …); `tests/test_architecture.py` greps the package.
- **Never return a question's `correct` / `explanation` to a learner** except
  through the attempt presenter after submission.
- **Never set `Enrollment.status` directly**; go through
  `services.enrollments.move` / `activate` / `staff_transition`.
- **Never count attempts outside the enrollment-row lock.**
- **Never read-then-create** an enrollment, progress row or purchase row;
  use the `lock_or_create` helpers (uniqueness decides the race).
