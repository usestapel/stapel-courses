"""Response DTOs of the learner API (dataclass inside, DRF at HTTP).

Built by presenters (``presenters.py``) only; views never instantiate these
(stapel-swap-lint SWAP002). Field names are the wire names.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class CourseCardDTO:
    """A course as the catalog lists it."""

    id: int
    slug: str
    title: str
    summary: str
    cover_media_id: Optional[str]
    level: str
    language: Optional[str]
    access: str
    price: Optional[Decimal]
    currency: Optional[str]
    author_id: str
    scope: Optional[str]
    lesson_count: int
    total_duration_seconds: int
    published_at: Optional[dt.datetime]


@dataclass
class CourseDetailDTO(CourseCardDTO):
    """A course with its pacing and certificate settings."""

    status: str = "published"
    description: str = ""
    drip: str = "none"
    sequential: bool = False
    access_days: Optional[int] = None
    certificate_enabled: bool = True


@dataclass
class EnrollmentDTO:
    """A learner's enrollment with its progress cache."""

    id: int
    course_id: int
    course_slug: str
    course_title: str
    status: str
    source: str
    expires_at: Optional[dt.datetime]
    activated_at: Optional[dt.datetime]
    completed_at: Optional[dt.datetime]
    progress_percent: int
    completed_lessons: int
    required_lessons: int
    passed_quizzes: int
    required_quizzes: int
    last_lesson_id: Optional[int]
    created_at: dt.datetime


@dataclass
class AccessStateDTO:
    """Whether the caller sees the content, why not, and whether enrolling would work."""

    allowed: bool
    reason: Optional[str]
    can_enroll: bool
    privileged: bool


@dataclass
class OutlineQuizDTO:
    """A quiz in the outline: rules, lock state, passed."""

    id: int
    title: str
    required: bool
    pass_mark: int
    locked: bool
    lock_reason: Optional[str]
    passed: bool


@dataclass
class OutlineLessonDTO:
    """A lesson in the outline: lock state, lock reason and my progress; never content."""

    id: int
    title: str
    position: int
    duration_seconds: int
    free_preview: bool
    required: bool
    review_required: bool
    locked: bool
    lock_reason: Optional[str]
    unlocks_at: Optional[dt.datetime]
    after_lesson_id: Optional[int]
    after_quiz_id: Optional[int]
    progress_status: Optional[str]
    quizzes: list = field(default_factory=list)


@dataclass
class OutlineModuleDTO:
    """A module in the outline with its lessons and module quizzes."""

    id: int
    title: str
    position: int
    lessons: list = field(default_factory=list)
    quizzes: list = field(default_factory=list)


@dataclass
class CourseOutlineDTO:
    """A course, the caller's access and enrollment, and the outline."""

    course: CourseDetailDTO
    access: AccessStateDTO
    enrollment: Optional[EnrollmentDTO]
    modules: list = field(default_factory=list)


@dataclass
class LessonProgressStateDTO:
    """My progress on one lesson."""

    lesson_id: int
    status: str
    position_seconds: int
    completed_at: Optional[dt.datetime]


@dataclass
class LessonDTO:
    """An open lesson: content blocks, my progress, neighbours."""

    id: int
    course_slug: str
    module_id: int
    title: str
    position: int
    blocks: list
    duration_seconds: int
    free_preview: bool
    review_required: bool
    progress: Optional[LessonProgressStateDTO]
    quizzes: list
    prev_lesson_id: Optional[int]
    next_lesson_id: Optional[int]


@dataclass
class LessonProgressDTO:
    """The result of a progress write: the lesson row and the enrollment cache."""

    progress: LessonProgressStateDTO
    enrollment: Optional[EnrollmentDTO]


@dataclass
class QuizStandingDTO:
    """My standing on one quiz."""

    quiz_id: int
    passed: bool
    best_percent: Optional[Decimal]
    attempts_used: int


@dataclass
class CourseProgressDTO:
    """My progress on a course: lessons and quiz standings."""

    enrollment: Optional[EnrollmentDTO]
    lessons: list
    quizzes: list


@dataclass
class QuizDTO:
    """A quiz's rules and my standing; never its questions."""

    id: int
    title: str
    lesson_id: Optional[int]
    module_id: Optional[int]
    pass_mark: int
    max_attempts: int
    reveal: str
    question_count: int
    attempts_used: int
    attempts_left: Optional[int]
    best_percent: Optional[Decimal]
    passed: bool
    open_attempt_id: Optional[int]
    locked: bool
    lock_reason: Optional[str]


@dataclass
class ChoiceDTO:
    """One answer choice as shown to the learner."""

    id: str
    text: str


@dataclass
class CorrectAnswerDTO:
    """The right answer, present only when the quiz reveals it after submission."""

    choice_ids: Optional[list]
    value: Optional[bool]
    accepted: Optional[list]


@dataclass
class QuestionResultDTO:
    """How one submitted answer was graded."""

    correct: bool
    points: int


@dataclass
class AttemptQuestionDTO:
    """One question of an attempt; answer fields are empty while the attempt is open."""

    id: int
    kind: str
    prompt: str
    points: int
    choices: list
    answer: Optional[dict]
    result: Optional[QuestionResultDTO]
    correct_answer: Optional[CorrectAnswerDTO]
    explanation: Optional[str]


@dataclass
class AttemptDTO:
    """A quiz attempt in the stored order; graded fields are empty while it is open."""

    id: int
    quiz_id: int
    number: int
    status: str
    started_at: dt.datetime
    submitted_at: Optional[dt.datetime]
    questions: list
    score: Optional[int]
    max_score: int
    percent: Optional[Decimal]
    passed: Optional[bool]
    reveals_answers: bool


@dataclass
class CertificateDTO:
    """One of my certificates."""

    id: int
    number: str
    course_id: int
    course_slug: str
    course_title: str
    holder_name: str
    issued_at: dt.datetime
    valid: bool


@dataclass
class CertificateVerificationDTO:
    """The public verification view; unconfigured fields are null."""

    number: str
    valid: bool
    holder_name: Optional[str]
    course_title: Optional[str]
    course_slug: Optional[str]
    issued_at: Optional[dt.datetime]
