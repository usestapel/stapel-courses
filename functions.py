"""comm Functions provided by stapel-courses (schemas in ``schemas/functions/``).

- ``courses.purchasables`` — the orders purchasable resolver for type
  ``course`` (the ``purchasables`` contract; keys are course ids).
- ``courses.enrollment.status`` — one learner's standing on one course.
- ``courses.certificate.verify`` — the public verification view by number.
"""
from stapel_core.comm import function


@function("courses.purchasables")
def purchasables(payload):
    from .services.purchases import resolve

    return resolve(payload["keys"])


@function("courses.enrollment.status")
def enrollment_status(payload):
    from django.contrib.auth.models import AnonymousUser

    from .models import Course
    from .services.gate import course_view

    course_id = str(payload["course_id"])
    course = Course.objects.filter(pk=int(course_id)).first() if course_id.isdigit() else None
    if course is None:
        raise LookupError(f"course {course_id} not found")
    user_id = str(payload["user_id"])
    enrollment = course.enrollments.filter(user_id=user_id).first()
    view = course_view(course, _Subject(user_id) if user_id else AnonymousUser())
    return {
        "enrolled": enrollment is not None,
        "status": enrollment.status if enrollment else None,
        "source": enrollment.source if enrollment else None,
        "has_access": view.decision.allowed,
        "expires_at": enrollment.expires_at.isoformat() if enrollment and enrollment.expires_at else None,
        "progress_percent": enrollment.progress_percent if enrollment else 0,
    }


class _Subject:
    """A user id seen by the gate as a signed-in, non-staff learner."""

    is_authenticated = True
    is_anonymous = False
    is_staff = False

    def __init__(self, user_id: str):
        self.pk = user_id


@function("courses.certificate.verify")
def certificate_verify(payload):
    from .errors import ERR_404_CERTIFICATE_NOT_FOUND
    from .services import CoursesError
    from .services.certificates import public_view

    try:
        view = public_view(str(payload["number"]))
    except CoursesError as exc:
        if exc.key == ERR_404_CERTIFICATE_NOT_FOUND:
            raise LookupError(f"certificate {payload['number']} not found") from None
        raise
    issued = view["issued_at"]
    return {**view, "issued_at": issued.isoformat() if issued else None}
