"""Quiz attempts: start (limit under a lock), shuffle by a stored seed, grade
on the server, reveal per ``Quiz.reveal`` (spec §7).

Nothing that tells a right answer leaves before submission: the open
attempt is presented from :func:`question_view`, which copies only ``id``,
``kind``, ``prompt``, ``points`` and the choices' ``id``/``text``.
"""
from __future__ import annotations

import random
import re
import secrets
import string
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from stapel_core.comm import mutate_and_emit

from ..errors import (
    ERR_400_ANSWER_INVALID,
    ERR_403_LESSON_LOCKED,
    ERR_404_ATTEMPT_NOT_FOUND,
    ERR_404_QUIZ_NOT_FOUND,
    ERR_409_QUIZ_ATTEMPTS_EXHAUSTED,
    ERR_409_QUIZ_EMPTY,
)
from ..models import (
    Attempt,
    AttemptStatus,
    Course,
    CourseStatus,
    Enrollment,
    QuestionKind,
    Quiz,
    RevealMode,
    TextMatch,
)
from . import CoursesError

SEED_BITS = 31
_PUNCT = re.compile(f"[{re.escape(string.punctuation)}]")
_SPACE = re.compile(r"\s+")


# ── grading ───────────────────────────────────────────────────────────────


def normalise(text: str) -> str:
    """NFKC, casefold, punctuation dropped, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    text = _PUNCT.sub("", text)
    return _SPACE.sub(" ", text).strip()


def is_correct(question, answer) -> bool:
    """Grade one answer; *answer* is the validated submission for the question."""
    if answer is None:
        return False
    kind = question.kind
    if kind == QuestionKind.SINGLE:
        ids = answer.get("choice_ids") or []
        return len(ids) == 1 and list(question.correct) == list(ids)
    if kind == QuestionKind.MULTIPLE:
        return set(answer.get("choice_ids") or []) == set(question.correct) and bool(question.correct)
    if kind == QuestionKind.TRUE_FALSE:
        return answer.get("value") is not None and bool(answer.get("value")) == bool(question.correct)
    if kind == QuestionKind.SHORT_TEXT:
        text = answer.get("text")
        if not isinstance(text, str) or not text.strip():
            return False
        if question.match == TextMatch.EXACT:
            return text.strip() in [str(a).strip() for a in question.correct]
        return normalise(text) in {normalise(a) for a in question.correct}
    return False


def _validate_answer(question, raw) -> dict | None:
    """Shape-check one submitted answer against its question (400 on misfit)."""
    if raw is None:
        return None
    kind = question.kind
    if kind in (QuestionKind.SINGLE, QuestionKind.MULTIPLE):
        ids = raw.get("choice_ids")
        known = {c["id"] for c in question.choices}
        if not isinstance(ids, list) or not set(ids) <= known or len(ids) != len(set(ids)):
            raise CoursesError(400, ERR_400_ANSWER_INVALID, {"question_id": question.pk})
        if kind == QuestionKind.SINGLE and len(ids) > 1:
            raise CoursesError(400, ERR_400_ANSWER_INVALID, {"question_id": question.pk})
        return {"choice_ids": list(ids)}
    if kind == QuestionKind.TRUE_FALSE:
        value = raw.get("value")
        if not isinstance(value, bool):
            raise CoursesError(400, ERR_400_ANSWER_INVALID, {"question_id": question.pk})
        return {"value": value}
    text = raw.get("text")
    if not isinstance(text, str):
        raise CoursesError(400, ERR_400_ANSWER_INVALID, {"question_id": question.pk})
    return {"text": text}


def percent_of(score: int, max_score: int) -> Decimal:
    if not max_score:
        return Decimal("0.00")
    return (Decimal(100) * Decimal(score) / Decimal(max_score)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


# ── shuffling ─────────────────────────────────────────────────────────────


def orders_for(quiz: Quiz, questions: list, seed: int) -> tuple[list[int], dict[str, list[str]]]:
    """Question order and per-question choice order, derived from *seed*."""
    rng = random.Random(seed)
    question_ids = [q.pk for q in questions]
    if quiz.shuffle_questions:
        rng.shuffle(question_ids)
    choice_order: dict[str, list[str]] = {}
    for question in questions:
        ids = [c["id"] for c in question.choices]
        if quiz.shuffle_choices and question.kind in (QuestionKind.SINGLE, QuestionKind.MULTIPLE):
            rng.shuffle(ids)
        choice_order[str(question.pk)] = ids
    return question_ids, choice_order


def question_view(question, choice_ids: list[str]) -> dict:
    """What a learner sees of a question before submission — nothing more."""
    by_id = {c["id"]: c for c in question.choices}
    return {
        "id": question.pk,
        "kind": question.kind,
        "prompt": question.prompt,
        "points": question.points,
        "choices": [{"id": cid, "text": by_id[cid]["text"]} for cid in choice_ids if cid in by_id],
    }


# ── attempts ──────────────────────────────────────────────────────────────


def quiz_for_learner(user, quiz_id):
    """The quiz, its course view and its lock state; 404 when not visible."""
    from .gate import course_view, is_privileged

    quiz = Quiz.objects.select_related("course").filter(pk=quiz_id).first()
    if quiz is None:
        raise CoursesError(404, ERR_404_QUIZ_NOT_FOUND)
    course = quiz.course
    if course.status != CourseStatus.PUBLISHED and not is_privileged(user, course):
        enrolled = Enrollment.objects.filter(course=course, user_id=str(getattr(user, "pk", ""))).exists()
        if course.status != CourseStatus.ARCHIVED or not enrolled:
            raise CoursesError(404, ERR_404_QUIZ_NOT_FOUND)
    view = course_view(course, user)
    return quiz, view, view.quiz_states.get(quiz.pk)


def attempts_used(quiz: Quiz, user_id: str) -> int:
    return Attempt.objects.filter(quiz=quiz, user_id=user_id).count()


def start(user, quiz_id) -> tuple[Attempt, bool]:
    """Start an attempt or return the open one. Returns ``(attempt, created)``."""
    from .enrollments import require_account

    user_id = require_account(user)
    quiz, view, state = quiz_for_learner(user, quiz_id)
    if state is not None and state.locked:
        raise CoursesError(403, ERR_403_LESSON_LOCKED, state.params())
    questions = list(quiz.questions.all())
    if not questions:
        raise CoursesError(409, ERR_409_QUIZ_EMPTY)
    with transaction.atomic():
        _lock_counter(quiz.course, user_id, view)
        open_attempt = Attempt.objects.filter(
            quiz=quiz, user_id=user_id, status=AttemptStatus.IN_PROGRESS
        ).first()
        if open_attempt is not None:
            return open_attempt, False
        used = attempts_used(quiz, user_id)
        if quiz.max_attempts and used >= quiz.max_attempts:
            raise CoursesError(409, ERR_409_QUIZ_ATTEMPTS_EXHAUSTED, {"max": quiz.max_attempts})
        seed = secrets.randbits(SEED_BITS)
        question_order, choice_order = orders_for(quiz, questions, seed)
        try:
            with transaction.atomic():
                attempt = Attempt.objects.create(
                    quiz=quiz, user_id=user_id, number=used + 1, seed=seed,
                    question_order=question_order, choice_order=choice_order,
                    max_score=sum(q.points for q in questions),
                )
        except IntegrityError:
            raise CoursesError(
                409, ERR_409_QUIZ_ATTEMPTS_EXHAUSTED, {"max": quiz.max_attempts}
            ) from None
    return attempt, True


def _lock_counter(course: Course, user_id: str, view) -> None:
    """Serialise attempt starts of one learner on one course.

    The lock is the enrollment row; a privileged user or a free-course
    learner without one locks the course row instead.
    """
    if view.enrollment is not None:
        Enrollment.objects.select_for_update().filter(pk=view.enrollment.pk).first()
    else:
        Course.objects.select_for_update().filter(pk=course.pk).first()


def get_attempt(user, attempt_id) -> Attempt:
    from . import user_id_of

    user_id = user_id_of(user)
    attempt = (
        Attempt.objects.select_related("quiz", "quiz__course")
        .filter(pk=attempt_id, user_id=user_id).first() if user_id else None
    )
    if attempt is None:
        raise CoursesError(404, ERR_404_ATTEMPT_NOT_FOUND)
    return attempt


def submit(user, attempt_id, answers: list[dict]) -> tuple[Attempt, bool]:
    """Grade and close an attempt; a replay returns the stored result."""
    from .progress import after_quiz

    attempt = get_attempt(user, attempt_id)
    if attempt.status == AttemptStatus.SUBMITTED:
        return attempt, False
    questions = {q.pk: q for q in attempt.quiz.questions.all()}
    submitted: dict[int, dict] = {}
    for raw in answers:
        question = questions.get(int(raw.get("question_id") or 0))
        if question is None:
            raise CoursesError(400, ERR_400_ANSWER_INVALID, {"question_id": raw.get("question_id")})
        submitted[question.pk] = _validate_answer(question, raw)
    with mutate_and_emit() as emit:
        attempt = Attempt.objects.select_for_update().select_related("quiz", "quiz__course").get(
            pk=attempt.pk
        )
        if attempt.status == AttemptStatus.SUBMITTED:
            return attempt, False
        score = 0
        max_score = 0
        results = {}
        for qid in attempt.question_order:
            question = questions.get(qid)
            if question is None:
                continue
            max_score += question.points
            correct = is_correct(question, submitted.get(qid))
            gained = question.points if correct else 0
            score += gained
            results[str(qid)] = {"correct": correct, "points": gained}
        attempt.answers = {str(k): v for k, v in submitted.items() if v is not None}
        attempt.results = results
        attempt.score = score
        attempt.max_score = max_score
        attempt.percent = percent_of(score, max_score)
        attempt.passed = attempt.percent >= Decimal(attempt.quiz.pass_mark)
        attempt.status = AttemptStatus.SUBMITTED
        attempt.submitted_at = timezone.now()
        attempt.save()
        enrollment = Enrollment.objects.filter(
            course_id=attempt.quiz.course_id, user_id=attempt.user_id
        ).values_list("pk", flat=True).first()
        if enrollment is not None:
            after_quiz(enrollment, emit)
    return attempt, True


def reveals_answers(attempt: Attempt) -> bool:
    """May this submitted attempt show the right answers and explanations?"""
    if attempt.status != AttemptStatus.SUBMITTED:
        return False
    mode = attempt.quiz.reveal
    if mode == RevealMode.AFTER_SUBMIT:
        return True
    if mode == RevealMode.AFTER_PASS:
        return bool(attempt.passed)
    return False


def quiz_summary(user, quiz_id) -> dict:
    """``GET quizzes/{id}/``: the rules and my standing, never the questions."""
    from . import user_id_of

    quiz, view, state = quiz_for_learner(user, quiz_id)
    user_id = user_id_of(user)
    mine = list(Attempt.objects.filter(quiz=quiz, user_id=user_id)) if user_id else []
    submitted = [a for a in mine if a.status == AttemptStatus.SUBMITTED]
    best = max((a.percent for a in submitted if a.percent is not None), default=None)
    used = len(mine)
    return {
        "quiz": quiz,
        "state": state,
        "question_count": quiz.questions.count(),
        "attempts_used": used,
        "attempts_left": None if not quiz.max_attempts else max(quiz.max_attempts - used, 0),
        "best_percent": best,
        "passed": any(a.passed for a in submitted),
        "open_attempt_id": next((a.pk for a in mine if a.status == AttemptStatus.IN_PROGRESS), None),
    }
