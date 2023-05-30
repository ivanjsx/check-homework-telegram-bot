"""Кастомные исключения, используемые при работе бота."""


class MissingTokenError(Exception):
    """Отсутствует один или несколько необходимых токенов."""

    pass


class UnexpectedResponse(TypeError):
    """Ответ API не соответствует ожидаемому формату."""

    pass


class UnexpectedHomeworkData(Exception):
    """Данные о работе не соответствуют ожидаемому формату."""

    pass


# class EndpointIsDead(Exception):
#     """Эндпоинт не отвечает."""

#     pass


# class EmptyHomeworksList(Exception):
#     """Список домашних работ, возвращённый API, пуст."""

#     pass
