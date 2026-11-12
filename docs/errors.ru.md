# Errors — Русский

`71` error keys. Canonical texts live in the code (`register_service_errors`); localized texts in `translations/errors.ru.json`.

| Код | Статус | Параметры | Действие | Текст |
|---|---|---|---|---|
| `error.400.bad_request` | 400 | — | `fix_input` | Некорректный запрос |
| `error.400.captcha_invalid` | 400 | — | `retry` | Проверка капчи не пройдена. Пожалуйста, попробуйте ещё раз. |
| `error.400.captcha_required` | 400 | — | `retry` | Требуется токен капчи. |
| `error.400.course_access_unknown` | 400 | `access` | `fix_input` | Неизвестный режим доступа {access} |
| `error.400.course_price_required` | 400 | — | `fix_input` | Для продажи курса через заказы нужны цена и валюта |
| `error.400.course_slug_frozen` | 400 | — | `fix_input` | Адрес опубликованного курса нельзя изменить |
| `error.400.course_slug_taken` | 400 | `slug` | `fix_input` | Адрес {slug} уже занят другим курсом |
| `error.400.expected_list` | 400 | — | `fix_input` | Ожидался список элементов |
| `error.400.field.blank` | 400 | `field` | `fix_input` | Поле «{field}» не может быть пустым |
| `error.400.field.does_not_exist` | 400 | `field` | `fix_input` | «{field}» не существует |
| `error.400.field.invalid` | 400 | `field` | `fix_input` | Поле «{field}» содержит недопустимое значение |
| `error.400.field.invalid_choice` | 400 | `field` | `fix_input` | Недопустимый вариант для поля «{field}» |
| `error.400.field.max_length` | 400 | `field`, `max_length` | `fix_input` | Поле «{field}» должно содержать не более {max_length} символов |
| `error.400.field.max_value` | 400 | `field`, `max_value` | `fix_input` | Значение поля «{field}» должно быть не больше {max_value} |
| `error.400.field.min_length` | 400 | `field`, `min_length` | `fix_input` | Поле «{field}» должно содержать не менее {min_length} символов |
| `error.400.field.min_value` | 400 | `field`, `min_value` | `fix_input` | Значение поля «{field}» должно быть не меньше {min_value} |
| `error.400.field.null` | 400 | `field` | `fix_input` | Поле «{field}» не может быть null |
| `error.400.field.required` | 400 | `field` | `fix_input` | Поле «{field}» обязательно |
| `error.400.field.unique` | 400 | `field` | `fix_input` | Значение поля «{field}» должно быть уникальным |
| `error.400.invalid_ad_id` | 400 | — | `fix_input` | Недопустимый идентификатор объявления |
| `error.400.lesson_block_invalid` | 400 | `index`, `reason` | `fix_input` | Блок содержимого {index} заполнен неверно ({reason}) |
| `error.400.question_invalid` | 400 | `reason` | `fix_input` | Вопрос составлен неверно ({reason}) |
| `error.400.quiz_answer_invalid` | 400 | `question_id` | `fix_input` | Ответ на вопрос {question_id} ему не подходит |
| `error.400.quiz_target_invalid` | 400 | — | `fix_input` | Тест относится ровно к одному уроку или модулю курса |
| `error.400.validation_error` | 400 | — | `fix_input` | Ошибка валидации |
| `error.400.verification_failed` | 400 | — | `verify` | Проверка не пройдена |
| `error.400.verification_invalid_factor` | 400 | — | `verify` | Этот способ подтверждения недоступен |
| `error.401.unauthorized` | 401 | — | `reauthenticate` | Требуется аутентификация |
| `error.402.payment_required` | 402 | — | `retry` | Требуется оплата |
| `error.403.course_authoring_forbidden` | 403 | — | `retry` | Вы не можете редактировать этот курс |
| `error.403.course_entitlement_required` | 403 | — | `retry` | Ваш тариф не включает этот курс |
| `error.403.course_purchase_required` | 403 | — | `retry` | Купите курс, чтобы начать обучение |
| `error.403.enrollment_requires_account` | 403 | — | `reauthenticate` | Войдите, чтобы записаться |
| `error.403.forbidden` | 403 | — | `retry` | У вас нет прав для выполнения этого действия |
| `error.403.lesson_locked` | 403 | `reason`, `unlocks_at`, `after_lesson_id`, `after_quiz_id` | `retry` | Этот урок пока закрыт ({reason}; откроется {unlocks_at}; после урока {after_lesson_id}; после теста {after_quiz_id}) |
| `error.403.lesson_review_required` | 403 | — | `retry` | Урок засчитывается после проверки |
| `error.403.network_blocked` | 403 | — | `contact_support` | Запросы из этой сети не разрешены. |
| `error.403.verification_enrollment_required` | 403 | — | `verify` | Требуется регистрация фактора подтверждения. |
| `error.403.verification_required` | 403 | — | `verify` | Требуется дополнительная проверка |
| `error.404.ad_not_found` | 404 | — | `retry` | Объявление не найдено |
| `error.404.certificate_not_found` | 404 | — | `retry` | Сертификат не найден |
| `error.404.course_module_not_found` | 404 | — | `retry` | Модуль не найден |
| `error.404.course_not_found` | 404 | — | `retry` | Курс не найден |
| `error.404.enrollment_not_found` | 404 | — | `verify` | Запись на курс не найдена |
| `error.404.lesson_not_found` | 404 | — | `retry` | Урок не найден |
| `error.404.not_found` | 404 | — | `retry` | Запрошенный ресурс не найден |
| `error.404.question_not_found` | 404 | — | `retry` | Вопрос не найден |
| `error.404.quiz_attempt_not_found` | 404 | — | `retry` | Попытка не найдена |
| `error.404.quiz_not_found` | 404 | — | `retry` | Тест не найден |
| `error.404.verification_challenge_not_found` | 404 | — | `verify` | Запрос на подтверждение не найден или истёк |
| `error.405.method_not_allowed` | 405 | — | `retry` | Метод не разрешён |
| `error.406.not_acceptable` | 406 | — | `retry` | Недопустимый формат ответа |
| `error.408.request_timeout` | 408 | — | `retry` | Время ожидания запроса истекло |
| `error.409.conflict` | 409 | — | `fix_input` | Ресурс уже существует |
| `error.409.course_not_draft` | 409 | — | `fix_input` | Удалить можно только черновик курса |
| `error.409.course_not_published` | 409 | — | `fix_input` | Запись на этот курс закрыта |
| `error.409.course_transition_invalid` | 409 | `from`, `to` | `fix_input` | Курс нельзя перевести из {from} в {to} |
| `error.409.enrollment_transition_invalid` | 409 | `from`, `to` | `verify` | Запись нельзя перевести из {from} в {to} |
| `error.409.quiz_attempts_exhausted` | 409 | `max` | `fix_input` | Попыток не осталось (не более {max}) |
| `error.409.quiz_empty` | 409 | — | `fix_input` | В этом тесте пока нет вопросов |
| `error.410.gone` | 410 | — | `retry` | Ресурс был безвозвратно удалён |
| `error.413.payload_too_large` | 413 | — | `retry` | Тело запроса слишком большое |
| `error.415.unsupported_media_type` | 415 | — | `retry` | Неподдерживаемый тип данных |
| `error.422.unprocessable_entity` | 422 | — | `wait_and_retry` | Невозможно обработать данные запроса |
| `error.423.locked` | 423 | — | `wait_and_retry` | Ресурс заблокирован |
| `error.423.verification_locked` | 423 | — | `wait_and_retry` | Слишком много неудачных попыток — подтверждение заблокировано |
| `error.429.rate_limit` | 429 | `retry_after_minutes` | `wait_and_retry` | Слишком много попыток. Повторите попытку через {retry_after_minutes} мин. |
| `error.429.too_many_requests` | 429 | — | `wait_and_retry` | Слишком много запросов. Пожалуйста, повторите попытку позже. |
| `error.500.internal` | 500 | — | `contact_support` | Что-то пошло не так |
| `error.503.entitlement_unavailable` | 503 | — | `wait_and_retry` | Сейчас не удаётся проверить ваш тариф, попробуйте чуть позже |
| `error.503.mandate_unavailable` | 503 | — | `retry` | Не удалось проверить доступ к рабочему пространству |
