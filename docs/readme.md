## What this is

Courses for a Stapel education product: courses made of modules and
lessons, enrollment with a lifecycle and an access gate per course, lesson
progress, quizzes graded on the server, and certificates with a public
verification page. The module never imports a sibling: a course is **sold**
through stapel-orders as purchasable type `course` (its resolver is the
`courses.purchasables` Function and the order facts open and close the
enrollment), and a **plan** includes a course through stapel-billing's
`billing.check_entitlement` Function, asked by name.

## Quick start

```python
INSTALLED_APPS = [
    # ...
    "stapel_courses",
]

STAPEL_COURSES = {
    "DEFAULT_ACCESS": "enrolled",      # free | enrolled | purchased | entitlement
}

# urls.py
path("courses/api/", include("stapel_courses.urls"))   # -> /courses/api/v1/...

# settings.py — enrollment expiry (Celery optional; or manage.py courses_housekeeping)
from stapel_courses.beat import get_courses_beat_schedule
CELERY_BEAT_SCHEDULE = {**get_courses_beat_schedule()}
```

Sell courses next to stapel-orders (no import either way):

```python
from stapel_courses.preset import SETTINGS_DEFAULTS as COURSES

STAPEL_ORDERS = {
    "PURCHASABLE_TYPES": {**COURSES["STAPEL_ORDERS"]["PURCHASABLE_TYPES"]},  # "course"
}
STAPEL_COURSES = {"PURCHASE_ACTIVATION": "paid"}   # paid | confirmed | placed
```

A demo course: `python manage.py courses_seed_demo`.

## Concepts

- **Course → Module → Lesson** — ordered; a lesson is a list of typed
  content blocks (`text`, `video` and `attachment` by opaque media id,
  `embed` by https URL; a host registers more in `BLOCK_TYPES`). A lesson
  may be a free preview, optional, or need a reviewer's "passed".
- **Access** — each course names a strategy: `free` (everyone reads),
  `enrolled` (enroll for free, then read), `purchased` (buy it through
  orders), `entitlement` (a billing plan includes it). The outline names a
  lock reason for every lesson; staff and the author always see everything.
- **Enrollment** — `pending → active → completed`, `expired` (by the beat
  after `access_days`), `cancelled`; source `free`, `purchase`,
  `entitlement` or `staff`. One row per course and learner.
- **Pacing** — drip by days since enrollment or by fixed dates, and a
  sequential switch (a lesson opens after the earlier required lessons and
  quizzes are done).
- **Progress** — an idempotent upsert per lesson (forward-only status, last
  video position) and a progress cache on the enrollment.
- **Quizzes** — single/multiple choice, true/false, short text (exact or
  normalised match); attempt limits, pass mark, a stored shuffle seed;
  graded on the server; right answers are never sent before submission and
  afterwards only as the quiz's reveal mode allows.
- **Completion and certificates** — every required lesson completed and
  every required quiz passed completes the course; a certificate with a
  unique number is issued once; `GET certificates/{number}/` verifies it and
  shows only the fields `PUBLIC_VERIFY_FIELDS` names.
- **GDPR** — export of enrollments, progress, attempts and certificates;
  erasure deletes the learning data and anonymises and revokes certificates.
