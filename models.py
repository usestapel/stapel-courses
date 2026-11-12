"""Models of stapel-courses.

Users are id strings (``str(user.pk)``), never foreign keys: an erased
learner's certificate keeps its number under a pseudonymised id, which a
foreign key cannot hold. Media is an opaque id; stapel-cdn / stapel-recordings
resolve it. Nothing here has a foreign key into a sibling module.
"""
from __future__ import annotations

from django.db import models
from stapel_core.access import access

USER_ID_MAX_LENGTH = 64
SLUG_MAX_LENGTH = 80
TITLE_MAX_LENGTH = 200
SUMMARY_MAX_LENGTH = 500
DESCRIPTION_MAX_LENGTH = 20_000
MEDIA_ID_MAX_LENGTH = 64
LANGUAGE_MAX_LENGTH = 16
ACCESS_MAX_LENGTH = 32
CURRENCY_MAX_LENGTH = 3
ENTITLEMENT_KEY_MAX_LENGTH = 100
SCOPE_MAX_LENGTH = 64
ORDER_ID_MAX_LENGTH = 64
PROMPT_MAX_LENGTH = 2000
EXPLANATION_MAX_LENGTH = 2000
CHOICE_ID_MAX_LENGTH = 16
CHOICE_TEXT_MAX_LENGTH = 500
ACCEPTED_TEXT_MAX_LENGTH = 200
ANSWER_TEXT_MAX_LENGTH = 500
HOLDER_NAME_MAX_LENGTH = 200
CERTIFICATE_NUMBER_MAX_LENGTH = 32
REASON_MAX_LENGTH = 200

#: Bounds (serializers enforce them; the wire carries them as limits).
MAX_BLOCKS_PER_LESSON = 50
MAX_CHOICES = 20
MAX_ACCEPTED_ANSWERS = 20
MAX_QUESTIONS_PER_QUIZ = 100
MAX_POINTS = 100
MAX_POSITION = 10_000
MAX_DURATION_SECONDS = 24 * 3600
MAX_ACCESS_DAYS = 3650
MAX_ATTEMPTS = 100
PRICE_MAX_DIGITS = 12
PRICE_DECIMAL_PLACES = 2


class CourseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class CourseLevel(models.TextChoices):
    ALL = "all", "All levels"
    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"


class DripMode(models.TextChoices):
    NONE = "none", "None"
    DAYS = "days", "Days since enrollment"
    DATE = "date", "Fixed date"


class EnrollmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class EnrollmentSource(models.TextChoices):
    FREE = "free", "Free"
    PURCHASE = "purchase", "Purchase"
    ENTITLEMENT = "entitlement", "Entitlement"
    STAFF = "staff", "Staff grant"


#: The enrollment statuses that open a course's content.
GRANTING_STATUSES = (EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED)


class PurchaseState(models.TextChoices):
    PLACED = "placed", "Placed"
    PAID = "paid", "Paid"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"


class ProgressStatus(models.TextChoices):
    STARTED = "started", "Started"
    SUBMITTED = "submitted", "Submitted for review"
    COMPLETED = "completed", "Completed"


#: Forward order of a lesson's progress; it never moves back.
PROGRESS_RANK = {
    ProgressStatus.STARTED: 0,
    ProgressStatus.SUBMITTED: 1,
    ProgressStatus.COMPLETED: 2,
}


class QuestionKind(models.TextChoices):
    SINGLE = "single", "Single choice"
    MULTIPLE = "multiple", "Multiple choice"
    TRUE_FALSE = "true_false", "True / false"
    SHORT_TEXT = "short_text", "Short text"


class TextMatch(models.TextChoices):
    EXACT = "exact", "Exact"
    NORMALISED = "normalised", "Normalised"


class RevealMode(models.TextChoices):
    NEVER = "never", "Never"
    AFTER_SUBMIT = "after_submit", "After each submission"
    AFTER_PASS = "after_pass", "After passing"


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"


def _price_field(**kwargs):
    return models.DecimalField(
        max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES, **kwargs
    )


@access.standard
class Course(models.Model):
    #: URL key; frozen once the course is published.
    slug = models.SlugField(max_length=SLUG_MAX_LENGTH, unique=True)
    #: Display title.
    title = models.CharField(max_length=TITLE_MAX_LENGTH)
    #: One-paragraph catalog summary.
    summary = models.CharField(max_length=SUMMARY_MAX_LENGTH, blank=True, default="")
    #: Long description (markdown).
    description = models.TextField(max_length=DESCRIPTION_MAX_LENGTH, blank=True, default="")
    #: draft / published / archived.
    status = models.CharField(
        max_length=16, choices=CourseStatus.choices, default=CourseStatus.DRAFT, db_index=True
    )
    #: str(user.pk) of the author; staff may reassign.
    author_id = models.CharField(max_length=USER_ID_MAX_LENGTH, db_index=True)
    #: Opaque stapel-cdn media id of the cover image.
    cover_media_id = models.CharField(max_length=MEDIA_ID_MAX_LENGTH, blank=True, default="")
    #: Audience level.
    level = models.CharField(max_length=16, choices=CourseLevel.choices, default=CourseLevel.ALL)
    #: Content language tag, e.g. en.
    language = models.CharField(max_length=LANGUAGE_MAX_LENGTH, blank=True, default="")
    #: Registered access strategy name (free / enrolled / purchased / entitlement / host-registered).
    access = models.CharField(max_length=ACCESS_MAX_LENGTH, default="enrolled")
    #: Price of a purchased course (orders resolver); null otherwise.
    price = _price_field(null=True, blank=True)
    #: ISO 4217 currency of price.
    currency = models.CharField(max_length=CURRENCY_MAX_LENGTH, blank=True, default="")
    #: Billing entitlement key; empty = ENTITLEMENT_KEY_TEMPLATE.
    entitlement_key = models.CharField(
        max_length=ENTITLEMENT_KEY_MAX_LENGTH, blank=True, default=""
    )
    #: Drip mode: none / days since enrollment / fixed date.
    drip = models.CharField(max_length=8, choices=DripMode.choices, default=DripMode.NONE)
    #: Lessons open only after earlier required lessons and quizzes are done.
    sequential = models.BooleanField(default=False)
    #: Enrollment lifetime in days from activation; null = forever.
    access_days = models.PositiveIntegerField(null=True, blank=True)
    #: Issue a certificate on completion.
    certificate_enabled = models.BooleanField(default=True)
    #: Opaque cohort or workspace id the course belongs to (filterable).
    scope = models.CharField(max_length=SCOPE_MAX_LENGTH, blank=True, default="", db_index=True)
    #: First publication instant.
    published_at = models.DateTimeField(null=True, blank=True)
    #: Creation instant.
    created_at = models.DateTimeField(auto_now_add=True)
    #: Last change instant.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-id",)

    def __str__(self) -> str:
        return self.slug


@access.standard
class Module(models.Model):
    #: The course.
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    #: Display title.
    title = models.CharField(max_length=TITLE_MAX_LENGTH)
    #: Order within the course.
    position = models.PositiveIntegerField(default=0)
    #: Creation instant.
    created_at = models.DateTimeField(auto_now_add=True)
    #: Last change instant.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")

    def __str__(self) -> str:
        return self.title


@access.standard
class Lesson(models.Model):
    #: The module.
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    #: The course (denormalised from module).
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    #: Display title.
    title = models.CharField(max_length=TITLE_MAX_LENGTH)
    #: Order within the module.
    position = models.PositiveIntegerField(default=0)
    #: Typed content blocks (blocks.py registry).
    blocks = models.JSONField(default=list, blank=True)
    #: Expected duration.
    duration_seconds = models.PositiveIntegerField(default=0)
    #: Open to everyone regardless of access, drip and sequence.
    free_preview = models.BooleanField(default=False)
    #: Counts for completion.
    required = models.BooleanField(default=True)
    #: Completed only by a reviewer's pass.
    review_required = models.BooleanField(default=False)
    #: Drip 'days': opens this many days after activation.
    unlock_after_days = models.PositiveIntegerField(null=True, blank=True)
    #: Drip 'date': opens at this instant.
    unlock_at = models.DateTimeField(null=True, blank=True)
    #: Creation instant.
    created_at = models.DateTimeField(auto_now_add=True)
    #: Last change instant.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")

    def __str__(self) -> str:
        return self.title


@access.standard
class Quiz(models.Model):
    #: The course.
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quizzes")
    #: The lesson it belongs to (or module).
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="quizzes", null=True, blank=True
    )
    #: The module it belongs to (or lesson).
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, related_name="quizzes", null=True, blank=True
    )
    #: Display title.
    title = models.CharField(max_length=TITLE_MAX_LENGTH)
    #: Percent needed to pass (0-100).
    pass_mark = models.PositiveSmallIntegerField(default=70)
    #: Attempt limit; 0 = unlimited.
    max_attempts = models.PositiveIntegerField(default=3)
    #: Shuffle question order per attempt (stored seed).
    shuffle_questions = models.BooleanField(default=False)
    #: Shuffle choice order per attempt (stored seed).
    shuffle_choices = models.BooleanField(default=False)
    #: Must be passed for completion.
    required = models.BooleanField(default=True)
    #: When right answers are shown after submission.
    reveal = models.CharField(
        max_length=16, choices=RevealMode.choices, default=RevealMode.AFTER_PASS
    )
    #: Creation instant.
    created_at = models.DateTimeField(auto_now_add=True)
    #: Last change instant.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(lesson__isnull=False, module__isnull=True)
                    | models.Q(lesson__isnull=True, module__isnull=False)
                ),
                name="courses_quiz_one_target",
            ),
        ]

    def __str__(self) -> str:
        return self.title


@access.standard
class Question(models.Model):
    #: The quiz.
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    #: single / multiple / true_false / short_text.
    kind = models.CharField(max_length=16, choices=QuestionKind.choices)
    #: Question text.
    prompt = models.TextField(max_length=PROMPT_MAX_LENGTH)
    #: Authored order.
    position = models.PositiveIntegerField(default=0)
    #: Points for a right answer.
    points = models.PositiveSmallIntegerField(default=1)
    #: [{id, text}] for choice kinds.
    choices = models.JSONField(default=list, blank=True)
    #: Right answer: choice ids, a bool, or accepted strings. Never sent to learners before submission.
    correct = models.JSONField(default=list, blank=True)
    #: Short text comparison: exact or normalised.
    match = models.CharField(max_length=16, choices=TextMatch.choices, default=TextMatch.NORMALISED)
    #: Shown after submission when the quiz reveals answers.
    explanation = models.TextField(max_length=EXPLANATION_MAX_LENGTH, blank=True, default="")

    class Meta:
        ordering = ("position", "id")

    def __str__(self) -> str:
        return self.prompt[:60]


@access.sensitive
class Enrollment(models.Model):
    #: The course.
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    #: str(user.pk) of the learner.
    user_id = models.CharField(max_length=USER_ID_MAX_LENGTH, db_index=True)
    #: Lifecycle status (fsm.py).
    status = models.CharField(
        max_length=16, choices=EnrollmentStatus.choices, default=EnrollmentStatus.PENDING,
        db_index=True,
    )
    #: How access was granted.
    source = models.CharField(max_length=16, choices=EnrollmentSource.choices)
    #: The order that granted it (purchase source).
    order_id = models.CharField(max_length=ORDER_ID_MAX_LENGTH, blank=True, default="")
    #: Access ends at this instant; null = never.
    expires_at = models.DateTimeField(null=True, blank=True)
    #: First activation (drip counts from it).
    activated_at = models.DateTimeField(null=True, blank=True)
    #: Completion instant.
    completed_at = models.DateTimeField(null=True, blank=True)
    #: Cache: required lessons completed.
    completed_lessons = models.PositiveIntegerField(default=0)
    #: Cache: required lessons in the course.
    required_lessons = models.PositiveIntegerField(default=0)
    #: Cache: required quizzes passed.
    passed_quizzes = models.PositiveIntegerField(default=0)
    #: Cache: required quizzes in the course.
    required_quizzes = models.PositiveIntegerField(default=0)
    #: Cache: floor percent of required items done.
    progress_percent = models.PositiveSmallIntegerField(default=0)
    #: The lesson progress was last written for.
    last_lesson_id = models.BigIntegerField(null=True, blank=True)
    #: Creation instant.
    created_at = models.DateTimeField(auto_now_add=True)
    #: Last change instant.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-id",)
        constraints = [
            models.UniqueConstraint(fields=("course", "user_id"), name="courses_enrollment_once"),
        ]

    @property
    def grants_access(self) -> bool:
        return self.status in GRANTING_STATUSES

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.course_id}"


@access.ops
class CoursePurchase(models.Model):
    """The idempotency ledger of the orders facts: one row per (order, course)."""

    #: Order id from the orders facts.
    order_id = models.CharField(max_length=ORDER_ID_MAX_LENGTH)
    #: The course bought.
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="purchases")
    #: The buyer.
    user_id = models.CharField(max_length=USER_ID_MAX_LENGTH, db_index=True)
    #: Last order fact applied.
    state = models.CharField(max_length=16, choices=PurchaseState.choices)
    #: Creation instant.
    created_at = models.DateTimeField(auto_now_add=True)
    #: Last change instant.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("order_id", "course"), name="courses_purchase_once"),
        ]


@access.ops
class LessonProgress(models.Model):
    #: str(user.pk) of the learner.
    user_id = models.CharField(max_length=USER_ID_MAX_LENGTH, db_index=True)
    #: The lesson.
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    #: The course (denormalised).
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="progress")
    #: started / submitted / completed; only moves forward.
    status = models.CharField(
        max_length=16, choices=ProgressStatus.choices, default=ProgressStatus.STARTED
    )
    #: Last playback position.
    position_seconds = models.PositiveIntegerField(default=0)
    #: First write.
    started_at = models.DateTimeField(auto_now_add=True)
    #: Completion instant.
    completed_at = models.DateTimeField(null=True, blank=True)
    #: Last write.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user_id", "lesson"), name="courses_progress_once"),
        ]


@access.ops
class Attempt(models.Model):
    #: The quiz.
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    #: str(user.pk) of the learner.
    user_id = models.CharField(max_length=USER_ID_MAX_LENGTH, db_index=True)
    #: 1-based attempt number per quiz and learner.
    number = models.PositiveIntegerField()
    #: in_progress / submitted.
    status = models.CharField(
        max_length=16, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS
    )
    #: Shuffle seed, stored so every read shows one order.
    seed = models.BigIntegerField()
    #: Question ids in the order shown.
    question_order = models.JSONField(default=list)
    #: {question id: [choice ids]} in the order shown.
    choice_order = models.JSONField(default=dict)
    #: Submitted answers by question id.
    answers = models.JSONField(default=dict, blank=True)
    #: {question id: {correct, points}} after grading.
    results = models.JSONField(default=dict, blank=True)
    #: Points scored.
    score = models.PositiveIntegerField(default=0)
    #: Points available.
    max_score = models.PositiveIntegerField(default=0)
    #: 100 * score / max_score, 2 dp.
    percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    #: percent >= pass mark; null while open.
    passed = models.BooleanField(null=True, blank=True)
    #: Start instant.
    started_at = models.DateTimeField(auto_now_add=True)
    #: Submission instant.
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-id",)
        constraints = [
            models.UniqueConstraint(
                fields=("quiz", "user_id", "number"), name="courses_attempt_number_once"
            ),
        ]


@access.sensitive
class Certificate(models.Model):
    #: Public verification number.
    number = models.CharField(max_length=CERTIFICATE_NUMBER_MAX_LENGTH, unique=True)
    #: The course completed.
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="certificates")
    #: str(user.pk) of the holder (pseudonymised on erasure).
    user_id = models.CharField(max_length=USER_ID_MAX_LENGTH, db_index=True)
    #: Name printed on the certificate (snapshot).
    holder_name = models.CharField(max_length=HOLDER_NAME_MAX_LENGTH, blank=True, default="")
    #: Course title at issue (snapshot).
    course_title = models.CharField(max_length=TITLE_MAX_LENGTH)
    #: Issue instant.
    issued_at = models.DateTimeField()
    #: Revocation instant; null = valid.
    revoked_at = models.DateTimeField(null=True, blank=True)
    #: Why it was revoked.
    revoke_reason = models.CharField(max_length=REASON_MAX_LENGTH, blank=True, default="")

    class Meta:
        ordering = ("-id",)
        constraints = [
            models.UniqueConstraint(fields=("course", "user_id"), name="courses_certificate_once"),
        ]

    @property
    def valid(self) -> bool:
        return self.revoked_at is None

    def __str__(self) -> str:
        return self.number
