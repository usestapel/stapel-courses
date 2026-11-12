"""Purchases through the orders seam: the resolver answer and the order facts (spec §5).

Courses never imports stapel-orders. A course is sold as purchasable type
``PURCHASABLE_TYPE`` (``course``) whose resolver is ``courses.purchasables``;
the order facts arrive on the bus and are applied idempotently on the
``CoursePurchase(order_id, course)`` ledger row.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from stapel_core.comm import mutate_and_emit

from ..models import (
    GRANTING_STATUSES,
    Course,
    CoursePurchase,
    CourseStatus,
    Enrollment,
    EnrollmentSource,
    EnrollmentStatus,
    PurchaseState,
)
from .enrollments import ORDER, lock_or_create, move

logger = logging.getLogger(__name__)


def is_sellable(course: Course) -> bool:
    return course.access == "purchased" and course.price is not None and bool(course.currency)


def resolve(keys) -> dict:
    """The ``purchasables`` contract answer for course ids."""
    ids = [int(k) for k in keys if str(k).isdigit()]
    answer = {}
    for course in Course.objects.filter(pk__in=ids):
        if not is_sellable(course):
            continue
        answer[str(course.pk)] = {
            "title": course.title,
            "price": f"{course.price:.2f}",
            "currency": course.currency.upper(),
            "available": course.status == CourseStatus.PUBLISHED,
            "max_quantity": 1,
            "seller_id": course.author_id or None,
            "image": None,
            "url": _course_url(course),
        }
    return answer


def _course_url(course) -> str | None:
    from .events import _format

    return _format("COURSE_URL_TEMPLATE", slug=course.slug, course_id=course.pk) or None


def _course_lines(payload: dict) -> list[int]:
    from ..conf import courses_settings

    wanted = courses_settings.PURCHASABLE_TYPE
    ids = []
    for line in payload.get("lines") or []:
        if line.get("purchasable_type") == wanted and str(line.get("purchasable_key", "")).isdigit():
            ids.append(int(line["purchasable_key"]))
    return list(dict.fromkeys(ids))


def _lock_purchase(order_id: str, course: Course, user_id: str) -> tuple[CoursePurchase, bool]:
    row = CoursePurchase.objects.select_for_update().filter(order_id=order_id, course=course).first()
    if row is not None:
        return row, False
    try:
        with transaction.atomic():
            return CoursePurchase.objects.create(
                order_id=order_id, course=course, user_id=user_id, state=PurchaseState.PLACED
            ), True
    except IntegrityError:
        return CoursePurchase.objects.select_for_update().get(order_id=order_id, course=course), False


def _activate(purchase: CoursePurchase, emit) -> None:
    enrollment, _ = lock_or_create(purchase.course, purchase.user_id, {
        "status": EnrollmentStatus.PENDING, "source": EnrollmentSource.PURCHASE,
        "order_id": purchase.order_id,
    })
    if enrollment.status in GRANTING_STATUSES:
        return
    enrollment.source = EnrollmentSource.PURCHASE
    enrollment.order_id = purchase.order_id
    if enrollment.status != EnrollmentStatus.PENDING:
        enrollment.save(update_fields=["source", "order_id", "updated_at"])
    move(enrollment, EnrollmentStatus.ACTIVE, actor=ORDER, emit=emit)


def order_placed(payload: dict) -> int:
    """``orders.order.placed``: ledger rows and pending (or active) enrollments."""
    from ..conf import courses_settings

    order_id = str(payload.get("order_id") or "")
    user_id = str(payload.get("user_id") or "")
    course_ids = _course_lines(payload)
    if not order_id or not user_id or not course_ids:
        return 0
    touched = 0
    with mutate_and_emit() as emit:
        for course in Course.objects.filter(pk__in=course_ids):
            purchase, created = _lock_purchase(order_id, course, user_id)
            if not created:
                continue
            touched += 1
            enrollment, fresh = lock_or_create(course, user_id, {
                "status": EnrollmentStatus.PENDING, "source": EnrollmentSource.PURCHASE,
                "order_id": order_id,
            })
            if not fresh and enrollment.status in (EnrollmentStatus.CANCELLED, EnrollmentStatus.EXPIRED):
                enrollment.source = EnrollmentSource.PURCHASE
                enrollment.order_id = order_id
                move(enrollment, EnrollmentStatus.PENDING, actor=ORDER, emit=emit)
            if courses_settings.PURCHASE_ACTIVATION == "placed":
                _activate(purchase, emit)
        missing = set(course_ids) - set(Course.objects.filter(pk__in=course_ids).values_list("pk", flat=True))
    if missing:
        logger.info("courses: order %s names unknown course ids %s", order_id, sorted(missing))
    return touched


def _settle(order_id: str, state: str, activate: bool) -> int:
    moved = 0
    with mutate_and_emit() as emit:
        for purchase in CoursePurchase.objects.select_for_update().select_related("course").filter(
            order_id=order_id
        ):
            if purchase.state == PurchaseState.CANCELLED:
                continue
            if purchase.state != state:
                purchase.state = state
                purchase.save(update_fields=["state", "updated_at"])
            if activate:
                _activate(purchase, emit)
                moved += 1
    return moved


def order_paid(order_id: str) -> int:
    """A paid order activates its courses in every activation mode."""
    return _settle(str(order_id), PurchaseState.PAID, True)


def order_confirmed(order_id: str) -> int:
    from ..conf import courses_settings

    return _settle(str(order_id), PurchaseState.CONFIRMED,
                   courses_settings.PURCHASE_ACTIVATION in ("confirmed", "placed"))


def order_cancelled(order_id: str, reason: str = "") -> int:
    """Cancel/refund: the enrollments this order granted are cancelled."""
    cancelled = 0
    with mutate_and_emit() as emit:
        for purchase in CoursePurchase.objects.select_for_update().select_related("course").filter(
            order_id=str(order_id)
        ):
            if purchase.state == PurchaseState.CANCELLED:
                continue
            purchase.state = PurchaseState.CANCELLED
            purchase.save(update_fields=["state", "updated_at"])
            enrollment = Enrollment.objects.select_for_update().select_related("course").filter(
                course=purchase.course, user_id=purchase.user_id, order_id=purchase.order_id,
            ).first()
            if enrollment is None or enrollment.status in (EnrollmentStatus.CANCELLED, EnrollmentStatus.EXPIRED):
                continue
            move(enrollment, EnrollmentStatus.CANCELLED, actor=ORDER, emit=emit, reason=reason or "order")
            cancelled += 1
    return cancelled
