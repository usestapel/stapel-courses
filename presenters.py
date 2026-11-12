"""Presenters for stapel-courses — the DTO-building layer (§55).

Views resolve a presenter through ``get_presenter`` (never import one), so a
host swaps the presentation via ``STAPEL_SWAP`` without forking a view.

The attempt presenter is where "no answer leaks before submission" lives:
for an open attempt it emits each question through
``services.quizzes.question_view`` and leaves ``result``,
``correct_answer`` and ``explanation`` empty.
"""
from __future__ import annotations

from django.db.models import Count, Sum
from stapel_core.django.swappable import declare_swap, get_presenter

from .dto import (
    AccessStateDTO,
    AttemptDTO,
    AttemptQuestionDTO,
    AuthorEnrollmentDTO,
    CertificateDTO,
    CertificateVerificationDTO,
    ChoiceDTO,
    CorrectAnswerDTO,
    CourseCardDTO,
    CourseDetailDTO,
    CourseOutlineDTO,
    CourseProgressDTO,
    EnrollmentDTO,
    LessonDTO,
    LessonProgressDTO,
    LessonProgressStateDTO,
    LearnerCardDTO,
    OutlineLessonDTO,
    OutlineModuleDTO,
    OutlineQuizDTO,
    QuestionResultDTO,
    QuizDTO,
    QuizStandingDTO,
)

COURSE_PRESENTER_KEY = "STAPEL_COURSES_COURSE_PRESENTER"
ENROLLMENT_PRESENTER_KEY = "STAPEL_COURSES_ENROLLMENT_PRESENTER"
LESSON_PRESENTER_KEY = "STAPEL_COURSES_LESSON_PRESENTER"
QUIZ_PRESENTER_KEY = "STAPEL_COURSES_QUIZ_PRESENTER"
ATTEMPT_PRESENTER_KEY = "STAPEL_COURSES_ATTEMPT_PRESENTER"
CERTIFICATE_PRESENTER_KEY = "STAPEL_COURSES_CERTIFICATE_PRESENTER"
DEFAULT_COURSE_PRESENTER = "stapel_courses.presenters.CoursePresenter"
DEFAULT_ENROLLMENT_PRESENTER = "stapel_courses.presenters.EnrollmentPresenter"
DEFAULT_LESSON_PRESENTER = "stapel_courses.presenters.LessonPresenter"
DEFAULT_QUIZ_PRESENTER = "stapel_courses.presenters.QuizPresenter"
DEFAULT_ATTEMPT_PRESENTER = "stapel_courses.presenters.AttemptPresenter"
DEFAULT_CERTIFICATE_PRESENTER = "stapel_courses.presenters.CertificatePresenter"

declare_swap(COURSE_PRESENTER_KEY, DEFAULT_COURSE_PRESENTER)
declare_swap(ENROLLMENT_PRESENTER_KEY, DEFAULT_ENROLLMENT_PRESENTER)
declare_swap(LESSON_PRESENTER_KEY, DEFAULT_LESSON_PRESENTER)
declare_swap(QUIZ_PRESENTER_KEY, DEFAULT_QUIZ_PRESENTER)
declare_swap(ATTEMPT_PRESENTER_KEY, DEFAULT_ATTEMPT_PRESENTER)
declare_swap(CERTIFICATE_PRESENTER_KEY, DEFAULT_CERTIFICATE_PRESENTER)


def _or_none(value):
    return value or None


def _card_fields(course, stats: dict) -> dict:
    return {
        "id": course.pk,
        "slug": course.slug,
        "title": course.title,
        "summary": course.summary,
        "cover_media_id": _or_none(course.cover_media_id),
        "level": course.level,
        "language": _or_none(course.language),
        "access": course.access,
        "price": course.price,
        "currency": _or_none(course.currency),
        "author_id": course.author_id,
        "scope": _or_none(course.scope),
        "lesson_count": stats.get("lesson_count") or 0,
        "total_duration_seconds": stats.get("total_duration_seconds") or 0,
        "published_at": course.published_at,
    }


def lesson_stats(course_ids) -> dict:
    from .models import Lesson

    rows = (
        Lesson.objects.filter(course_id__in=list(course_ids)).values("course_id")
        .annotate(lesson_count=Count("id"), total_duration_seconds=Sum("duration_seconds"))
    )
    return {row["course_id"]: row for row in rows}


def outline_quiz(view, quiz) -> OutlineQuizDTO:
    state = view.quiz_states.get(quiz.pk)
    return OutlineQuizDTO(
        id=quiz.pk, title=quiz.title, required=quiz.required, pass_mark=quiz.pass_mark,
        locked=bool(state and state.locked), lock_reason=state.reason if state else None,
        passed=quiz.pk in view.passed_quizzes,
    )


class CoursePresenter:
    """Course -> catalog card, detail, and the outline with lock reasons."""

    def cards(self, courses) -> list[CourseCardDTO]:
        courses = list(courses)
        stats = lesson_stats(c.pk for c in courses)
        return [CourseCardDTO(**_card_fields(c, stats.get(c.pk, {}))) for c in courses]

    def detail(self, course) -> CourseDetailDTO:
        stats = lesson_stats([course.pk]).get(course.pk, {})
        return CourseDetailDTO(
            **_card_fields(course, stats),
            status=course.status,
            description=course.description,
            drip=course.drip,
            sequential=course.sequential,
            access_days=course.access_days,
            certificate_enabled=course.certificate_enabled,
        )

    def outline(self, view, can_enroll: bool) -> CourseOutlineDTO:
        modules = []
        for module in view.modules:
            lessons = []
            for lesson in view.lessons_by_module.get(module.pk, []):
                state = view.lesson_states[lesson.pk]
                lessons.append(OutlineLessonDTO(
                    id=lesson.pk, title=lesson.title, position=lesson.position,
                    duration_seconds=lesson.duration_seconds, free_preview=lesson.free_preview,
                    required=lesson.required, review_required=lesson.review_required,
                    locked=state.locked, lock_reason=state.reason, unlocks_at=state.unlocks_at,
                    after_lesson_id=state.after_lesson_id, after_quiz_id=state.after_quiz_id,
                    progress_status=view.progress.get(lesson.pk),
                    quizzes=[outline_quiz(view, q) for q in view.quizzes_by_lesson.get(lesson.pk, [])],
                ))
            modules.append(OutlineModuleDTO(
                id=module.pk, title=module.title, position=module.position, lessons=lessons,
                quizzes=[outline_quiz(view, q) for q in view.quizzes_by_module.get(module.pk, [])],
            ))
        enrollment = view.enrollment
        return CourseOutlineDTO(
            course=self.detail(view.course),
            access=AccessStateDTO(
                allowed=view.decision.allowed, reason=view.decision.reason,
                can_enroll=can_enroll, privileged=view.privileged,
            ),
            enrollment=get_enrollment_presenter()().present(enrollment) if enrollment else None,
            modules=modules,
        )


class EnrollmentPresenter:
    def present(self, enrollment) -> EnrollmentDTO:
        course = enrollment.course
        return EnrollmentDTO(
            id=enrollment.pk, course_id=course.pk, course_slug=course.slug,
            course_title=course.title, status=enrollment.status, source=enrollment.source,
            expires_at=enrollment.expires_at, activated_at=enrollment.activated_at,
            completed_at=enrollment.completed_at, progress_percent=enrollment.progress_percent,
            completed_lessons=enrollment.completed_lessons,
            required_lessons=enrollment.required_lessons,
            passed_quizzes=enrollment.passed_quizzes, required_quizzes=enrollment.required_quizzes,
            last_lesson_id=enrollment.last_lesson_id, created_at=enrollment.created_at,
        )


    def for_staff(self, enrollments) -> list[AuthorEnrollmentDTO]:
        """Enrollments with their learner: ``user_id`` and a card when one resolves."""
        from dataclasses import asdict

        from .services.learners import learner_cards

        enrollments = list(enrollments)
        cards = learner_cards(e.user_id for e in enrollments)
        result = []
        for enrollment in enrollments:
            card = cards.get(str(enrollment.user_id))
            result.append(AuthorEnrollmentDTO(
                **asdict(self.present(enrollment)), user_id=str(enrollment.user_id),
                learner=LearnerCardDTO(**card) if card else None,
            ))
        return result


def _progress_state(row) -> LessonProgressStateDTO:
    return LessonProgressStateDTO(
        lesson_id=row.lesson_id, status=row.status, position_seconds=row.position_seconds,
        completed_at=row.completed_at,
    )


class LessonPresenter:
    """An open lesson with its content, my progress and its neighbours."""

    def present(self, view, lesson) -> LessonDTO:
        from .models import LessonProgress

        ordered = view.ordered_lessons()
        index = next(i for i, item in enumerate(ordered) if item.pk == lesson.pk)
        row = (
            LessonProgress.objects.filter(user_id=view.user_id, lesson=lesson).first()
            if view.user_id else None
        )
        return LessonDTO(
            id=lesson.pk, course_slug=view.course.slug, module_id=lesson.module_id,
            title=lesson.title, position=lesson.position, blocks=list(lesson.blocks or []),
            duration_seconds=lesson.duration_seconds, free_preview=lesson.free_preview,
            review_required=lesson.review_required,
            progress=_progress_state(row) if row else None,
            quizzes=[outline_quiz(view, q) for q in view.quizzes_by_lesson.get(lesson.pk, [])],
            prev_lesson_id=ordered[index - 1].pk if index > 0 else None,
            next_lesson_id=ordered[index + 1].pk if index + 1 < len(ordered) else None,
        )

    def progress(self, row, enrollment) -> LessonProgressDTO:
        return LessonProgressDTO(
            progress=_progress_state(row),
            enrollment=get_enrollment_presenter()().present(enrollment) if enrollment else None,
        )

    def course_progress(self, view) -> CourseProgressDTO:
        from .models import Attempt, AttemptStatus, LessonProgress

        rows = LessonProgress.objects.filter(course=view.course, user_id=view.user_id).order_by("id")
        standings = []
        quizzes = [q for qs in view.quizzes_by_lesson.values() for q in qs] + [
            q for qs in view.quizzes_by_module.values() for q in qs
        ]
        for quiz in sorted(quizzes, key=lambda q: q.pk):
            attempts = list(Attempt.objects.filter(quiz=quiz, user_id=view.user_id))
            submitted = [a for a in attempts if a.status == AttemptStatus.SUBMITTED]
            standings.append(QuizStandingDTO(
                quiz_id=quiz.pk, passed=any(a.passed for a in submitted),
                best_percent=max((a.percent for a in submitted), default=None),
                attempts_used=len(attempts),
            ))
        enrollment = view.enrollment
        return CourseProgressDTO(
            enrollment=get_enrollment_presenter()().present(enrollment) if enrollment else None,
            lessons=[_progress_state(row) for row in rows],
            quizzes=standings,
        )


class QuizPresenter:
    def present(self, summary: dict) -> QuizDTO:
        quiz, state = summary["quiz"], summary["state"]
        return QuizDTO(
            id=quiz.pk, title=quiz.title, lesson_id=quiz.lesson_id, module_id=quiz.module_id,
            pass_mark=quiz.pass_mark, max_attempts=quiz.max_attempts, reveal=quiz.reveal,
            question_count=summary["question_count"], attempts_used=summary["attempts_used"],
            attempts_left=summary["attempts_left"], best_percent=summary["best_percent"],
            passed=summary["passed"], open_attempt_id=summary["open_attempt_id"],
            locked=bool(state and state.locked), lock_reason=state.reason if state else None,
        )


class AttemptPresenter:
    def present(self, attempt) -> AttemptDTO:
        from .models import AttemptStatus, QuestionKind
        from .services.quizzes import question_view, reveals_answers

        submitted = attempt.status == AttemptStatus.SUBMITTED
        reveal = reveals_answers(attempt)
        questions = {q.pk: q for q in attempt.quiz.questions.all()}
        items = []
        for qid in attempt.question_order:
            question = questions.get(qid)
            if question is None:
                continue
            shown = question_view(question, attempt.choice_order.get(str(qid), []))
            result = attempt.results.get(str(qid)) if submitted else None
            correct = None
            if reveal:
                correct = CorrectAnswerDTO(
                    choice_ids=list(question.correct)
                    if question.kind in (QuestionKind.SINGLE, QuestionKind.MULTIPLE) else None,
                    value=bool(question.correct) if question.kind == QuestionKind.TRUE_FALSE else None,
                    accepted=list(question.correct) if question.kind == QuestionKind.SHORT_TEXT else None,
                )
            items.append(AttemptQuestionDTO(
                id=shown["id"], kind=shown["kind"], prompt=shown["prompt"], points=shown["points"],
                choices=[ChoiceDTO(**c) for c in shown["choices"]],
                answer=attempt.answers.get(str(qid)) if submitted else None,
                result=QuestionResultDTO(**result) if result else None,
                correct_answer=correct,
                explanation=(question.explanation or None) if reveal else None,
            ))
        return AttemptDTO(
            id=attempt.pk, quiz_id=attempt.quiz_id, number=attempt.number, status=attempt.status,
            started_at=attempt.started_at, submitted_at=attempt.submitted_at, questions=items,
            score=attempt.score if submitted else None, max_score=attempt.max_score,
            percent=attempt.percent if submitted else None,
            passed=attempt.passed if submitted else None, reveals_answers=reveal,
        )


class CertificatePresenter:
    def present(self, certificate) -> CertificateDTO:
        return CertificateDTO(
            id=certificate.pk, number=certificate.number, course_id=certificate.course_id,
            course_slug=certificate.course.slug, course_title=certificate.course_title,
            holder_name=certificate.holder_name, issued_at=certificate.issued_at,
            valid=certificate.valid,
        )

    def verification(self, view: dict) -> CertificateVerificationDTO:
        return CertificateVerificationDTO(**view)


def get_course_presenter() -> type:
    return get_presenter(COURSE_PRESENTER_KEY, default=DEFAULT_COURSE_PRESENTER)


def get_enrollment_presenter() -> type:
    return get_presenter(ENROLLMENT_PRESENTER_KEY, default=DEFAULT_ENROLLMENT_PRESENTER)


def get_lesson_presenter() -> type:
    return get_presenter(LESSON_PRESENTER_KEY, default=DEFAULT_LESSON_PRESENTER)


def get_quiz_presenter() -> type:
    return get_presenter(QUIZ_PRESENTER_KEY, default=DEFAULT_QUIZ_PRESENTER)


def get_attempt_presenter() -> type:
    return get_presenter(ATTEMPT_PRESENTER_KEY, default=DEFAULT_ATTEMPT_PRESENTER)


def get_certificate_presenter() -> type:
    return get_presenter(CERTIFICATE_PRESENTER_KEY, default=DEFAULT_CERTIFICATE_PRESENTER)


__all__ = [
    "COURSE_PRESENTER_KEY",
    "ENROLLMENT_PRESENTER_KEY",
    "LESSON_PRESENTER_KEY",
    "QUIZ_PRESENTER_KEY",
    "ATTEMPT_PRESENTER_KEY",
    "CERTIFICATE_PRESENTER_KEY",
    "CoursePresenter",
    "EnrollmentPresenter",
    "LessonPresenter",
    "QuizPresenter",
    "AttemptPresenter",
    "CertificatePresenter",
    "get_course_presenter",
    "get_enrollment_presenter",
    "get_lesson_presenter",
    "get_quiz_presenter",
    "get_attempt_presenter",
    "get_certificate_presenter",
]
