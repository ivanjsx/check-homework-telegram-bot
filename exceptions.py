"""Кастомные исключения, используемые при работе бота."""

import requests
import telegram


class MissingTokenError(Exception):
    """Отсутствует один или несколько необходимых токенов."""


class ResponseStatusNotOk(Exception):
    """Эндпоинт API вернул ответ с ошибочным статусом."""


class RequestError(Exception):
    """Ошибка запроса к эндпоинту API сервиса Домашка."""


class InvalidResponseData(ValueError):
    """Ответ эндпоинта API не соответствует ожидаемому формату данных."""


class UnexpectedResponseData(TypeError):
    """Ответ эндпоинта API не соответствует документации."""


class EmptyHomeworksList(TypeError):
    """Список домашних работ, возвращённый эндпоинтом API, пуст."""


class UnexpectedHomeworkData(TypeError):
    """Данные о работе не соответствуют ожидаемому формату."""


class MessageNotSent(telegram.error.TelegramError):
    """Боту не удалось отправить сообщение в телеграм-чат."""
