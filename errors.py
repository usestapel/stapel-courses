"""i18n error keys of stapel-courses.

Only ``error.<status>.<slug>`` keys leave this package — human-readable
strings are translations, never literals in responses.
"""
from stapel_core.django.api.errors import register_service_errors

ERR_400_BLOCK_INVALID = "error.400.lesson_block_invalid"
ERR_400_QUESTION_INVALID = "error.400.question_invalid"
ERR_400_QUIZ_TARGET_INVALID = "error.400.quiz_target_invalid"
ERR_400_ACCESS_UNKNOWN = "error.400.course_access_unknown"
ERR_400_COURSE_PRICE_REQUIRED = "error.400.course_price_required"
ERR_400_SLUG_TAKEN = "error.400.course_slug_taken"
ERR_400_SLUG_FROZEN = "error.400.course_slug_frozen"
ERR_400_ANSWER_INVALID = "error.400.quiz_answer_invalid"
ERR_403_ENROLLMENT_REQUIRES_ACCOUNT = "error.403.enrollment_requires_account"
ERR_403_AUTHORING_FORBIDDEN = "error.403.course_authoring_forbidden"
ERR_403_PURCHASE_REQUIRED = "error.403.course_purchase_required"
ERR_403_ENTITLEMENT_REQUIRED = "error.403.course_entitlement_required"
ERR_403_LESSON_LOCKED = "error.403.lesson_locked"
ERR_403_REVIEW_REQUIRED = "error.403.lesson_review_required"
ERR_404_COURSE_NOT_FOUND = "error.404.course_not_found"
ERR_404_MODULE_NOT_FOUND = "error.404.course_module_not_found"
ERR_404_LESSON_NOT_FOUND = "error.404.lesson_not_found"
ERR_404_QUIZ_NOT_FOUND = "error.404.quiz_not_found"
ERR_404_QUESTION_NOT_FOUND = "error.404.question_not_found"
ERR_404_ATTEMPT_NOT_FOUND = "error.404.quiz_attempt_not_found"
ERR_404_ENROLLMENT_NOT_FOUND = "error.404.enrollment_not_found"
ERR_404_CERTIFICATE_NOT_FOUND = "error.404.certificate_not_found"
ERR_409_COURSE_NOT_PUBLISHED = "error.409.course_not_published"
ERR_409_COURSE_TRANSITION_INVALID = "error.409.course_transition_invalid"
ERR_409_COURSE_NOT_DRAFT = "error.409.course_not_draft"
ERR_409_ENROLLMENT_TRANSITION_INVALID = "error.409.enrollment_transition_invalid"
ERR_409_QUIZ_ATTEMPTS_EXHAUSTED = "error.409.quiz_attempts_exhausted"
ERR_409_QUIZ_EMPTY = "error.409.quiz_empty"
ERR_503_ENTITLEMENT_UNAVAILABLE = "error.503.entitlement_unavailable"

STAPEL_COURSES_ERRORS = {
    ERR_400_BLOCK_INVALID: "Content block {index} is invalid ({reason})",
    ERR_400_QUESTION_INVALID: "The question is invalid ({reason})",
    ERR_400_QUIZ_TARGET_INVALID: "A quiz belongs to exactly one lesson or module of the course",
    ERR_400_ACCESS_UNKNOWN: "Unknown access mode {access}",
    ERR_400_COURSE_PRICE_REQUIRED: "A course sold through orders needs a price and a currency",
    ERR_400_SLUG_TAKEN: "This address is already used by another course",
    ERR_400_SLUG_FROZEN: "The address of a published course cannot change",
    ERR_400_ANSWER_INVALID: "An answer does not fit its question",
    ERR_403_ENROLLMENT_REQUIRES_ACCOUNT: "Sign in to enroll",
    ERR_403_AUTHORING_FORBIDDEN: "You cannot edit this course",
    ERR_403_PURCHASE_REQUIRED: "Buy this course to start learning",
    ERR_403_ENTITLEMENT_REQUIRED: "Your plan does not include this course",
    ERR_403_LESSON_LOCKED: "This lesson is not open yet",
    ERR_403_REVIEW_REQUIRED: "This lesson is completed when a reviewer accepts it",
    ERR_404_COURSE_NOT_FOUND: "Course not found",
    ERR_404_MODULE_NOT_FOUND: "Module not found",
    ERR_404_LESSON_NOT_FOUND: "Lesson not found",
    ERR_404_QUIZ_NOT_FOUND: "Quiz not found",
    ERR_404_QUESTION_NOT_FOUND: "Question not found",
    ERR_404_ATTEMPT_NOT_FOUND: "Attempt not found",
    ERR_404_ENROLLMENT_NOT_FOUND: "Enrollment not found",
    ERR_404_CERTIFICATE_NOT_FOUND: "Certificate not found",
    ERR_409_COURSE_NOT_PUBLISHED: "This course is not open for enrollment",
    ERR_409_COURSE_TRANSITION_INVALID: "The course cannot move from {from} to {to}",
    ERR_409_COURSE_NOT_DRAFT: "Only a draft course can be deleted",
    ERR_409_ENROLLMENT_TRANSITION_INVALID: "The enrollment cannot move from {from} to {to}",
    ERR_409_QUIZ_ATTEMPTS_EXHAUSTED: "No attempts left (at most {max})",
    ERR_409_QUIZ_EMPTY: "This quiz has no questions yet",
    ERR_503_ENTITLEMENT_UNAVAILABLE: "Your plan cannot be checked right now; try again shortly",
}

#: Explicit remediation where the status heuristic would mislead.
STAPEL_COURSES_REMEDIATION = {
    ERR_403_ENROLLMENT_REQUIRES_ACCOUNT: "reauthenticate",
    ERR_503_ENTITLEMENT_UNAVAILABLE: "wait_and_retry",
}

register_service_errors(STAPEL_COURSES_ERRORS, remediation=STAPEL_COURSES_REMEDIATION)

__all__ = ["STAPEL_COURSES_ERRORS"] + sorted(name for name in list(globals()) if name.startswith("ERR_"))
