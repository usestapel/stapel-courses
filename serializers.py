"""Serializers for the stapel-courses API.

The class names are the codegen contract: drf-spectacular names each
component after its serializer minus the ``Serializer`` suffix, and the
React pair generates its client from those names. Every CharField declares
a ``max_length``; money is a decimal string; instants are ISO 8601 UTC.
"""
import datetime

from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.utils import (
    PolymorphicProxySerializer,
    extend_schema_field,
    extend_schema_serializer,
)
from rest_framework import serializers

from . import access as access_mod
from . import blocks as blocks_mod
from . import models as m

UTC = datetime.timezone.utc

LOCK_REASON_CHOICES = list(access_mod.LOCK_REASONS)


def _dt(**kwargs):
    return serializers.DateTimeField(default_timezone=UTC, **kwargs)


def _price(**kwargs):
    return serializers.DecimalField(
        max_digits=m.PRICE_MAX_DIGITS, decimal_places=m.PRICE_DECIMAL_PLACES,
        coerce_to_string=True, **kwargs,
    )


def _percent(**kwargs):
    return serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=True, **kwargs)


def _lock_reason():
    return serializers.ChoiceField(choices=LOCK_REASON_CHOICES, allow_null=True)


# ── lesson content blocks ─────────────────────────────────────────────────
#
# Schema-only shapes of the built-in block types (``blocks.py`` validates
# them). ``LessonBlock`` is the union a lesson's ``blocks`` list carries: the
# four built-ins, each with a literal ``type``, plus ``CustomBlock`` — any
# type a host registers through ``BLOCK_TYPES``, with its own fields.


def _block_type(name):
    return serializers.ChoiceField(choices=[(name, name)])


class TextBlockSerializer(serializers.Serializer):
    type = _block_type("text")
    text = serializers.CharField(max_length=blocks_mod.TEXT_MAX_LENGTH)
    format = serializers.ChoiceField(
        choices=[("markdown", "markdown"), ("plain", "plain")], required=False,
        help_text="Default markdown.",
    )


class VideoBlockSerializer(serializers.Serializer):
    type = _block_type("video")
    media_id = serializers.CharField(max_length=m.MEDIA_ID_MAX_LENGTH, help_text="Opaque media id.")
    caption = serializers.CharField(max_length=blocks_mod.CAPTION_MAX_LENGTH, required=False,
                                    allow_blank=True)


class AttachmentBlockSerializer(serializers.Serializer):
    type = _block_type("attachment")
    media_id = serializers.CharField(max_length=m.MEDIA_ID_MAX_LENGTH, help_text="Opaque media id.")
    name = serializers.CharField(max_length=blocks_mod.NAME_MAX_LENGTH)


class EmbedBlockSerializer(serializers.Serializer):
    type = _block_type("embed")
    url = serializers.CharField(
        max_length=blocks_mod.URL_MAX_LENGTH,
        help_text="https; the host is in embed_hosts when that list is not empty.",
    )
    title = serializers.CharField(max_length=blocks_mod.CAPTION_MAX_LENGTH, required=False,
                                  allow_blank=True)


class CustomBlockSerializer(serializers.Serializer):
    """A host-registered block type (``BLOCK_TYPES``); its fields are the host's."""

    type = serializers.CharField(max_length=64)


class _CustomBlockSchema(OpenApiSerializerExtension):
    target_class = "stapel_courses.serializers.CustomBlockSerializer"

    def map_serializer(self, auto_schema, direction):
        return {
            "type": "object",
            "description": "A block type the host registered (BLOCK_TYPES); any type but the built-ins.",
            "properties": {
                "type": {
                    "type": "string",
                    "maxLength": 64,
                    "not": {"enum": sorted(blocks_mod.BUILTIN_BLOCK_TYPES)},
                },
            },
            "required": ["type"],
            "additionalProperties": True,
        }


LESSON_BLOCK = PolymorphicProxySerializer(
    component_name="LessonBlock",
    serializers=[
        TextBlockSerializer, VideoBlockSerializer, AttachmentBlockSerializer,
        EmbedBlockSerializer, CustomBlockSerializer,
    ],
    resource_type_field_name=None,
    many=True,
)


@extend_schema_field(LESSON_BLOCK)
class BlocksField(serializers.ListField):
    """A lesson's typed blocks; validated by ``blocks.clean_blocks``, typed as ``LessonBlock[]``."""

    def __init__(self, **kwargs):
        kwargs.setdefault("child", serializers.DictField())
        kwargs.setdefault("max_length", m.MAX_BLOCKS_PER_LESSON)
        super().__init__(**kwargs)


@extend_schema_field({
    "oneOf": [
        {"type": "array", "items": {"type": "string", "maxLength": m.ACCEPTED_TEXT_MAX_LENGTH},
         "maxItems": max(m.MAX_CHOICES, m.MAX_ACCEPTED_ANSWERS)},
        {"type": "boolean"},
    ],
    "description": "Per kind: single / multiple -> the right choice ids; true_false -> "
                   "the right bool; short_text -> the accepted answers.",
})
class CorrectField(serializers.JSONField):
    """A question's answer key: a string list (choice ids / accepted texts) or a bool."""


# ── catalog and outline ───────────────────────────────────────────────────


class CourseCardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    slug = serializers.SlugField(max_length=m.SLUG_MAX_LENGTH)
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    summary = serializers.CharField(max_length=m.SUMMARY_MAX_LENGTH, allow_blank=True)
    cover_media_id = serializers.CharField(max_length=m.MEDIA_ID_MAX_LENGTH, allow_null=True)
    level = serializers.ChoiceField(choices=m.CourseLevel.choices)
    language = serializers.CharField(max_length=m.LANGUAGE_MAX_LENGTH, allow_null=True)
    access = serializers.CharField(max_length=m.ACCESS_MAX_LENGTH)
    price = _price(allow_null=True)
    currency = serializers.CharField(max_length=m.CURRENCY_MAX_LENGTH, allow_null=True)
    author_id = serializers.CharField(max_length=m.USER_ID_MAX_LENGTH)
    scope = serializers.CharField(max_length=m.SCOPE_MAX_LENGTH, allow_null=True)
    lesson_count = serializers.IntegerField(min_value=0)
    total_duration_seconds = serializers.IntegerField(min_value=0)
    published_at = _dt(allow_null=True)


class CoursePageSerializer(serializers.Serializer):
    items = CourseCardSerializer(many=True)
    next_anchor = serializers.CharField(max_length=32, allow_null=True)
    prev_anchor = serializers.CharField(max_length=32, allow_null=True)
    has_next = serializers.BooleanField()
    has_prev = serializers.BooleanField()
    count = serializers.IntegerField(min_value=0)


class CourseDetailSerializer(CourseCardSerializer):
    status = serializers.ChoiceField(choices=m.CourseStatus.choices)
    description = serializers.CharField(max_length=m.DESCRIPTION_MAX_LENGTH, allow_blank=True)
    drip = serializers.ChoiceField(choices=m.DripMode.choices)
    sequential = serializers.BooleanField()
    access_days = serializers.IntegerField(allow_null=True, min_value=1, max_value=m.MAX_ACCESS_DAYS)
    certificate_enabled = serializers.BooleanField()


class EnrollmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    course_id = serializers.IntegerField()
    course_slug = serializers.SlugField(max_length=m.SLUG_MAX_LENGTH)
    course_title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    status = serializers.ChoiceField(choices=m.EnrollmentStatus.choices)
    source = serializers.ChoiceField(choices=m.EnrollmentSource.choices)
    expires_at = _dt(allow_null=True)
    activated_at = _dt(allow_null=True)
    completed_at = _dt(allow_null=True)
    progress_percent = serializers.IntegerField(min_value=0, max_value=100)
    completed_lessons = serializers.IntegerField(min_value=0)
    required_lessons = serializers.IntegerField(min_value=0)
    passed_quizzes = serializers.IntegerField(min_value=0)
    required_quizzes = serializers.IntegerField(min_value=0)
    last_lesson_id = serializers.IntegerField(allow_null=True)
    created_at = _dt()


class EnrollmentPageSerializer(serializers.Serializer):
    items = EnrollmentSerializer(many=True)
    next_anchor = serializers.CharField(max_length=32, allow_null=True)
    prev_anchor = serializers.CharField(max_length=32, allow_null=True)
    has_next = serializers.BooleanField()
    has_prev = serializers.BooleanField()
    count = serializers.IntegerField(min_value=0)


class AccessStateSerializer(serializers.Serializer):
    allowed = serializers.BooleanField()
    reason = _lock_reason()
    can_enroll = serializers.BooleanField(help_text="POST enroll/ would succeed for this caller now.")
    privileged = serializers.BooleanField(help_text="The caller is staff or the course's author.")


class OutlineQuizSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    required = serializers.BooleanField()
    pass_mark = serializers.IntegerField(min_value=0, max_value=100)
    locked = serializers.BooleanField()
    lock_reason = _lock_reason()
    passed = serializers.BooleanField()


class OutlineLessonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    position = serializers.IntegerField(min_value=0)
    duration_seconds = serializers.IntegerField(min_value=0)
    free_preview = serializers.BooleanField()
    required = serializers.BooleanField()
    review_required = serializers.BooleanField()
    locked = serializers.BooleanField()
    lock_reason = _lock_reason()
    unlocks_at = _dt(allow_null=True)
    after_lesson_id = serializers.IntegerField(allow_null=True)
    after_quiz_id = serializers.IntegerField(allow_null=True)
    progress_status = serializers.ChoiceField(choices=m.ProgressStatus.choices, allow_null=True)
    quizzes = OutlineQuizSerializer(many=True)


class OutlineModuleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    position = serializers.IntegerField(min_value=0)
    lessons = OutlineLessonSerializer(many=True)
    quizzes = OutlineQuizSerializer(many=True)


class CourseOutlineSerializer(serializers.Serializer):
    course = CourseDetailSerializer()
    access = AccessStateSerializer()
    enrollment = EnrollmentSerializer(allow_null=True)
    modules = OutlineModuleSerializer(many=True)


# ── lessons and progress ──────────────────────────────────────────────────


class LessonProgressStateSerializer(serializers.Serializer):
    lesson_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=m.ProgressStatus.choices)
    position_seconds = serializers.IntegerField(min_value=0)
    completed_at = _dt(allow_null=True)


class LessonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    course_slug = serializers.SlugField(max_length=m.SLUG_MAX_LENGTH)
    module_id = serializers.IntegerField()
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    position = serializers.IntegerField(min_value=0)
    blocks = BlocksField()
    duration_seconds = serializers.IntegerField(min_value=0)
    free_preview = serializers.BooleanField()
    review_required = serializers.BooleanField()
    progress = LessonProgressStateSerializer(allow_null=True)
    quizzes = OutlineQuizSerializer(many=True)
    prev_lesson_id = serializers.IntegerField(allow_null=True)
    next_lesson_id = serializers.IntegerField(allow_null=True)


class LessonProgressRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=m.ProgressStatus.choices, required=False)
    position_seconds = serializers.IntegerField(
        required=False, min_value=0, max_value=m.MAX_DURATION_SECONDS
    )


class LessonProgressSerializer(serializers.Serializer):
    progress = LessonProgressStateSerializer()
    enrollment = EnrollmentSerializer(allow_null=True)


class QuizStandingSerializer(serializers.Serializer):
    quiz_id = serializers.IntegerField()
    passed = serializers.BooleanField()
    best_percent = _percent(allow_null=True)
    attempts_used = serializers.IntegerField(min_value=0)


class CourseProgressSerializer(serializers.Serializer):
    enrollment = EnrollmentSerializer(allow_null=True)
    lessons = LessonProgressStateSerializer(many=True)
    quizzes = QuizStandingSerializer(many=True)


# ── quizzes and attempts ──────────────────────────────────────────────────


class QuizSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    lesson_id = serializers.IntegerField(allow_null=True)
    module_id = serializers.IntegerField(allow_null=True)
    pass_mark = serializers.IntegerField(min_value=0, max_value=100)
    max_attempts = serializers.IntegerField(min_value=0, help_text="0 = unlimited.")
    reveal = serializers.ChoiceField(choices=m.RevealMode.choices)
    question_count = serializers.IntegerField(min_value=0)
    attempts_used = serializers.IntegerField(min_value=0)
    attempts_left = serializers.IntegerField(allow_null=True, min_value=0, help_text="null = unlimited.")
    best_percent = _percent(allow_null=True)
    passed = serializers.BooleanField()
    open_attempt_id = serializers.IntegerField(allow_null=True)
    locked = serializers.BooleanField()
    lock_reason = _lock_reason()


class ChoiceSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=m.CHOICE_ID_MAX_LENGTH)
    text = serializers.CharField(max_length=m.CHOICE_TEXT_MAX_LENGTH)


class CorrectAnswerSerializer(serializers.Serializer):
    choice_ids = serializers.ListField(
        child=serializers.CharField(max_length=m.CHOICE_ID_MAX_LENGTH), allow_null=True,
        max_length=m.MAX_CHOICES,
    )
    value = serializers.BooleanField(allow_null=True)
    accepted = serializers.ListField(
        child=serializers.CharField(max_length=m.ACCEPTED_TEXT_MAX_LENGTH), allow_null=True,
        max_length=m.MAX_ACCEPTED_ANSWERS,
    )


class QuestionResultSerializer(serializers.Serializer):
    correct = serializers.BooleanField()
    points = serializers.IntegerField(min_value=0, max_value=m.MAX_POINTS)


class AnswerSerializer(serializers.Serializer):
    """One answer: ``choice_ids`` (single/multiple), ``value`` (true_false) or ``text``."""

    question_id = serializers.IntegerField()
    choice_ids = serializers.ListField(
        child=serializers.CharField(max_length=m.CHOICE_ID_MAX_LENGTH), required=False,
        max_length=m.MAX_CHOICES,
    )
    value = serializers.BooleanField(required=False, allow_null=True, default=None)
    text = serializers.CharField(required=False, max_length=m.ANSWER_TEXT_MAX_LENGTH, allow_blank=True)


class AttemptQuestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=m.QuestionKind.choices)
    prompt = serializers.CharField(max_length=m.PROMPT_MAX_LENGTH)
    points = serializers.IntegerField(min_value=1, max_value=m.MAX_POINTS)
    choices = ChoiceSerializer(many=True)
    answer = serializers.DictField(allow_null=True, help_text="My submitted answer; null while open.")
    result = QuestionResultSerializer(allow_null=True)
    correct_answer = CorrectAnswerSerializer(allow_null=True)
    explanation = serializers.CharField(max_length=m.EXPLANATION_MAX_LENGTH, allow_null=True)


class AttemptSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    quiz_id = serializers.IntegerField()
    number = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=m.AttemptStatus.choices)
    started_at = _dt()
    submitted_at = _dt(allow_null=True)
    questions = AttemptQuestionSerializer(many=True)
    score = serializers.IntegerField(allow_null=True, min_value=0)
    max_score = serializers.IntegerField(min_value=0)
    percent = _percent(allow_null=True)
    passed = serializers.BooleanField(allow_null=True)
    reveals_answers = serializers.BooleanField()


class AttemptSubmitRequestSerializer(serializers.Serializer):
    answers = AnswerSerializer(many=True, max_length=m.MAX_QUESTIONS_PER_QUIZ)


# ── certificates ──────────────────────────────────────────────────────────


class CertificateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField(max_length=m.CERTIFICATE_NUMBER_MAX_LENGTH)
    course_id = serializers.IntegerField()
    course_slug = serializers.SlugField(max_length=m.SLUG_MAX_LENGTH)
    course_title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    holder_name = serializers.CharField(max_length=m.HOLDER_NAME_MAX_LENGTH, allow_blank=True)
    issued_at = _dt()
    valid = serializers.BooleanField()


class CertificatePageSerializer(serializers.Serializer):
    items = CertificateSerializer(many=True)
    next_anchor = serializers.CharField(max_length=32, allow_null=True)
    prev_anchor = serializers.CharField(max_length=32, allow_null=True)
    has_next = serializers.BooleanField()
    has_prev = serializers.BooleanField()
    count = serializers.IntegerField(min_value=0)


class CertificateVerificationSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=m.CERTIFICATE_NUMBER_MAX_LENGTH)
    valid = serializers.BooleanField()
    holder_name = serializers.CharField(max_length=m.HOLDER_NAME_MAX_LENGTH, allow_null=True, allow_blank=True)
    course_title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH, allow_null=True)
    course_slug = serializers.SlugField(max_length=m.SLUG_MAX_LENGTH, allow_null=True)
    issued_at = _dt(allow_null=True)


# ── author / staff ────────────────────────────────────────────────────────


# Author resources: a ``…RequestSerializer`` is what a client sends (POST
# body ``<Resource>Request``); the PATCH body keeps the pinned
# ``Patched<Resource>`` name through :func:`_patch_body` and carries the same
# writable fields, all optional. The response serializer adds the read-only
# fields (ids, parents, timestamps, a quiz's questions).


def _patch_body(request_cls, resource: str):
    """The PATCH body of *resource*: *request_cls*, emitted as ``Patched<resource>``."""
    return extend_schema_serializer(component_name=resource)(
        type(f"{resource}PatchSerializer", (request_cls,), {"__module__": __name__})
    )


_COURSE_WRITABLE = (
    "slug", "title", "summary", "description", "author_id", "cover_media_id", "level",
    "language", "access", "price", "currency", "entitlement_key", "drip", "sequential",
    "access_days", "certificate_enabled", "scope",
)


class AuthorCourseRequestSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(max_length=m.SLUG_MAX_LENGTH)
    price = _price(allow_null=True, required=False, min_value=0)
    access = serializers.CharField(
        max_length=m.ACCESS_MAX_LENGTH, required=False,
        help_text="A registered access strategy name (GET author/access-strategies/).",
    )
    author_id = serializers.CharField(
        max_length=m.USER_ID_MAX_LENGTH, required=False,
        help_text="Staff only: whose course it is (default: the caller).",
    )
    access_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=m.MAX_ACCESS_DAYS
    )

    class Meta:
        model = m.Course
        fields = _COURSE_WRITABLE


class AuthorCourseSerializer(AuthorCourseRequestSerializer):
    published_at = _dt(read_only=True, allow_null=True)
    created_at = _dt(read_only=True)
    updated_at = _dt(read_only=True)

    class Meta:
        model = m.Course
        fields = ("id", "status", *_COURSE_WRITABLE, "published_at", "created_at", "updated_at")
        read_only_fields = ("id", "status")


AuthorCoursePatchSerializer = _patch_body(AuthorCourseRequestSerializer, "AuthorCourse")


class AuthorCoursePageSerializer(serializers.Serializer):
    items = AuthorCourseSerializer(many=True)
    next_anchor = serializers.CharField(max_length=32, allow_null=True)
    prev_anchor = serializers.CharField(max_length=32, allow_null=True)
    has_next = serializers.BooleanField()
    has_prev = serializers.BooleanField()
    count = serializers.IntegerField(min_value=0)


class AuthorModuleRequestSerializer(serializers.ModelSerializer):
    position = serializers.IntegerField(required=False, min_value=0, max_value=m.MAX_POSITION)

    class Meta:
        model = m.Module
        fields = ("title", "position")


class AuthorModuleSerializer(AuthorModuleRequestSerializer):
    class Meta:
        model = m.Module
        fields = ("id", "course", "title", "position")
        read_only_fields = ("id", "course")


AuthorModulePatchSerializer = _patch_body(AuthorModuleRequestSerializer, "AuthorModule")

_LESSON_WRITABLE = (
    "module_id", "title", "position", "blocks", "duration_seconds", "free_preview", "required",
    "review_required", "unlock_after_days", "unlock_at",
)


class AuthorLessonRequestSerializer(serializers.ModelSerializer):
    position = serializers.IntegerField(required=False, min_value=0, max_value=m.MAX_POSITION)
    module_id = serializers.IntegerField(required=False)
    blocks = BlocksField(required=False)
    duration_seconds = serializers.IntegerField(
        required=False, min_value=0, max_value=m.MAX_DURATION_SECONDS
    )
    unlock_after_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=m.MAX_ACCESS_DAYS
    )
    unlock_at = _dt(required=False, allow_null=True)

    class Meta:
        model = m.Lesson
        fields = _LESSON_WRITABLE


class AuthorLessonSerializer(AuthorLessonRequestSerializer):
    class Meta:
        model = m.Lesson
        fields = ("id", "course", *_LESSON_WRITABLE)
        read_only_fields = ("id", "course")


AuthorLessonPatchSerializer = _patch_body(AuthorLessonRequestSerializer, "AuthorLesson")

_QUESTION_WRITABLE = (
    "kind", "prompt", "position", "points", "choices", "correct", "match", "explanation",
)


class AuthorQuestionRequestSerializer(serializers.ModelSerializer):
    position = serializers.IntegerField(required=False, min_value=0, max_value=m.MAX_POSITION)
    points = serializers.IntegerField(required=False, min_value=1, max_value=m.MAX_POINTS)
    choices = ChoiceSerializer(many=True, required=False, max_length=m.MAX_CHOICES)
    correct = CorrectField()

    class Meta:
        model = m.Question
        fields = _QUESTION_WRITABLE


class AuthorQuestionSerializer(AuthorQuestionRequestSerializer):
    class Meta:
        model = m.Question
        fields = ("id", "quiz", *_QUESTION_WRITABLE)
        read_only_fields = ("id", "quiz")


AuthorQuestionPatchSerializer = _patch_body(AuthorQuestionRequestSerializer, "AuthorQuestion")

_QUIZ_WRITABLE = (
    "lesson_id", "module_id", "title", "pass_mark", "max_attempts", "shuffle_questions",
    "shuffle_choices", "required", "reveal",
)


class AuthorQuizRequestSerializer(serializers.ModelSerializer):
    lesson_id = serializers.IntegerField(required=False, allow_null=True)
    module_id = serializers.IntegerField(required=False, allow_null=True)
    pass_mark = serializers.IntegerField(required=False, min_value=0, max_value=100)
    max_attempts = serializers.IntegerField(required=False, min_value=0, max_value=m.MAX_ATTEMPTS)

    class Meta:
        model = m.Quiz
        fields = _QUIZ_WRITABLE


class AuthorQuizSerializer(AuthorQuizRequestSerializer):
    questions = AuthorQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = m.Quiz
        fields = ("id", "course", *_QUIZ_WRITABLE, "questions")
        read_only_fields = ("id", "course", "questions")


AuthorQuizPatchSerializer = _patch_body(AuthorQuizRequestSerializer, "AuthorQuiz")


class AuthorCourseTreeModuleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=m.TITLE_MAX_LENGTH)
    position = serializers.IntegerField(min_value=0)
    lessons = AuthorLessonSerializer(many=True)
    quizzes = AuthorQuizSerializer(many=True)


class AuthorCourseTreeSerializer(serializers.Serializer):
    course = AuthorCourseSerializer()
    modules = AuthorCourseTreeModuleSerializer(many=True)


class EnrollmentGrantRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=m.USER_ID_MAX_LENGTH)
    expires_at = _dt(required=False, allow_null=True)


class EnrollmentTransitionRequestSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=[(s, s) for s in ("active", "expired", "cancelled")])
    reason = serializers.CharField(required=False, max_length=m.REASON_MAX_LENGTH, allow_blank=True)


class LessonReviewRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=m.USER_ID_MAX_LENGTH)
    passed = serializers.BooleanField()


class CertificateRevokeRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, max_length=m.REASON_MAX_LENGTH, allow_blank=True)
