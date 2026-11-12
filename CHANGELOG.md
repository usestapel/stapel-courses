# Changelog

All notable changes to stapel-courses are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pre-1.0 semver: **minor = breaking**, patch = compatible.

## [Unreleased]

## [0.1.0]

First release: courses, lessons, enrollment, progress, quizzes and
certificates — the base of an education product.

### Added
- **Content**: `Course` (slug, draft/published/archived, author, cover media
  id, level, language, summary, description) → `Module` → `Lesson` (ordered;
  typed content blocks text / video / attachment / embed with a merge
  registry `BLOCK_TYPES`, typed on the wire as the `LessonBlock` union with
  an open `CustomBlock` for host types; duration; free preview; required;
  review flag).
- **Enrollment** with a table FSM (pending → active → completed / expired /
  cancelled; re-grant), sources free / purchase / entitlement / staff, an
  optional expiry from `Course.access_days` (beat `expire_enrollments`,
  `manage.py courses_housekeeping`).
- **Access gate**: strategy registry `ACCESS_STRATEGIES` (free, enrolled,
  purchased, entitlement; REPLACE by dotted path), lock reasons per lesson in
  the outline and in `error.403.lesson_locked` (params `reason`,
  `unlocks_at`, `after_lesson_id`, `after_quiz_id`, declared in
  `errors.json` and gated by `tests/test_error_params.py`); drip by days since
  enrollment or by fixed date; sequential unlock (required lessons and
  quizzes). An unreachable entitlement Function answers 503, never a guess.
- **Purchases** through the orders seam: `courses.purchasables` resolver,
  `preset.SETTINGS_DEFAULTS` registering type `course`, consumers of
  `orders.order.placed` / `.paid` / `.status_changed` / `.refunded`
  (idempotent ledger `CoursePurchase`; `PURCHASE_ACTIVATION` paid /
  confirmed / placed; cancel and refund close only the order's own grant).
- **Progress**: idempotent forward-only upserts with the playback position, a
  progress cache on the enrollment recounted under its row lock, the
  completion rule (`COMPLETION_RULE`), a staff/author review verdict.
- **Quizzes** on a lesson or a module: single / multiple choice, true/false,
  short text (exact / normalised); server grading, pass mark, attempt limits
  counted under a lock, a stored shuffle seed, reveal modes; no right answer
  is sent before submission.
- **Author API shapes**: author writes take request components
  (`Author<Resource>Request` for POST, `PatchedAuthor<Resource>` for PATCH)
  without read-only fields; author/staff enrollments are `AuthorEnrollment`
  with `user_id` and a `LearnerCard` resolved through `CARDS_FUNCTION`
  (`profiles.public_cards`, never imported; absent → `user_id` only).
- **Review queue** `GET author/reviews/` (anchor, `?course=`): the lessons
  submitted for review in the caller's courses, with the learner.
- **Course certificates** `GET author/courses/{id}/certificates/` (anchor,
  `?revoked=`): number, holder, learner, issue and revocation;
  `POST author/certificates/{number}/revoke/` answers `AuthorCertificate`.
- **Error catalogs** `translations/errors.{ru,es}.json` for every code in
  `errors.py` (with the `.state.json` provenance sidecar), shipped in the
  wheel, and the per-language error reference `docs/errors.{en,ru,es}.md`;
  `tests/test_error_i18n.py` gates coverage, drift, placeholders, foreign
  keys and packaging.
- **Certificates**: issued once on completion, `PREFIX-YYYY-XXXXXXXX`
  numbers, public verification showing only `PUBLIC_VERIFY_FIELDS`,
  revocation.
- **API** `/courses/api/v1/` (learner + author/staff), facts
  `courses.enrollment.activated|status_changed`, `courses.course.completed`,
  `courses.certificate.issued`, Functions `courses.purchasables`,
  `courses.enrollment.status`, `courses.certificate.verify`, GDPR provider and
  owner, `user.merged` handler, admin, system checks E001–E006/W001,
  `manage.py courses_seed_demo`.
