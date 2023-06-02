import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler
from typing import Dict

import requests
import telegram
from dotenv import load_dotenv

import exceptions as e

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}
REQUEST_TIMEOUT_IN_SECONDS = 10

HOMEWORK_VERDICTS = {
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
}


def check_tokens() -> None:
    """Проверяет доступность необходимых переменных окружения."""
    if not all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        raise e.MissingTokenError("Не все переменные окружения доступны")


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в чат, определяемый окружением."""
    try:
        logging.info(msg="Запускаем отправку сообщения в Телеграм")
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message[:telegram.constants.MAX_MESSAGE_LENGTH],
        )
    except telegram.error.TelegramError as error:
        raise e.MessageNotSent(f"Ошибка при отправке: {error}")
    logging.debug(msg="Успешно отправили сообщение в Телеграм")


def get_api_answer(timestamp: int = 0) -> Dict:
    """Делает запрос к единственному эндпоинту API сервиса Домашка."""
    try:
        logging.info(msg="Посылаем запрос к эндпоинту API")
        kwargs = {"url": ENDPOINT,
                  "headers": HEADERS,
                  "timeout": REQUEST_TIMEOUT_IN_SECONDS,
                  "params": {"from_date": timestamp}}
        response = requests.get(**kwargs)
        status = HTTPStatus(value=response.status_code)
        if status != HTTPStatus.OK:
            raise e.RequestError(
                f"Статус ответа: {status.value} {status.phrase}. "
                f"Полный текст: {response.text}"
            )

    except requests.RequestException as error:
        raise e.RequestError(f"Ошибка при совершении запроса: {error}")

    logging.info(msg="Получили ответ от эндпоинта API, статус OK")

    try:
        logging.info(msg="Преобразуем ответ в словарь")
        result = response.json()
    except ValueError as error:
        raise e.UnexpectedResponseData(f"Не удалось распарсить ответ: {error}")

    logging.info(msg="Успешно привели ответ к словарю")
    return result


def check_response(response: Dict) -> None:
    """Проверяет преобразованный ответ на соответствие документации."""
    if not isinstance(response, dict):
        raise e.UnexpectedResponseData(
            'Тип данных ответа отличается от "dict"'
        )
    if "homeworks" not in response:
        raise e.UnexpectedResponseData(
            "В ответе отсутствует ключ со списком работ"
        )
    if not isinstance(response["homeworks"], list):
        raise e.UnexpectedResponseData(
            'Тип данных списка работ отличается от "list"'
        )
    if not response["homeworks"]:
        raise e.UnexpectedResponseData(
            "API вернула пустой список домашних работ: "
            "ни одна работа пока не взята на проверку"
        )


def get_latest_homework(response: Dict) -> Dict:
    """
    Получает из ответа актуальную домашнюю работу.
    Для корректной работы функции необходимо предварительно гарантировать,
    что список работ в ответе не пуст.
    """
    if len(response["homeworks"]) == 1:
        return response["homeworks"][0]

    for homework in response["homeworks"]:
        if not homework.get("date_updated"):
            raise e.UnexpectedResponseData(
                "Не у всех работ указана дата обновления"
            )

    return sorted(response["homeworks"],
                  key=lambda homework: homework["date_updated"],
                  reverse=True)[0]


def parse_status(homework: Dict) -> str:
    """
    Извлекает статус из домашней работы.
    Возвращает подготовленную для отправки в Telegram строку.
    """
    if not homework.get("homework_name"):
        raise e.UnexpectedResponseData(
            "У домашней работы отсутствет название"
        )
    if not homework.get("status"):
        raise e.UnexpectedResponseData(
            "У домашней работы отсутствет статус"
        )
    if not HOMEWORK_VERDICTS.get(homework["status"]):
        raise e.UnexpectedResponseData(
            "Домашняя работа содержит неизвестный статус"
        )

    homework_name = homework["homework_name"]
    verdict = HOMEWORK_VERDICTS[homework["status"]]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def status_collection() -> str:
    """
    Делает всю основную работу бота до момента отправки сообщения.
    Требует последующей проверки необходимости отправки.
    """
    try:
        response = get_api_answer()
        check_response(response)
        homework = get_latest_homework(response)
        status = parse_status(homework)

    except e.RequestError as error:
        status = f"Ошибка при запросе к сервису Домашка: {error}"
        logging.error(status)

    except e.UnexpectedResponseData as error:
        status = f"Ответ не того формата или типа данных: {error}"
        logging.error(status)

    except Exception as error:
        status = f"Неизвестный сбой в работе программы: {error}"
        logging.error(status)

    finally:
        return status


def main():
    """Основная логика работы бота."""
    try:
        logging.info(msg="Инициализируем бота")
        check_tokens()
    except e.MissingTokenError as error:
        message = f"Ошибка при инициализации бота: {error}"
        logging.critical(message)
        sys.exit(message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logging.info(msg="Успешно завершили инициализацию бота")
    previous_status = ""

    while True:

        current_status = status_collection()

        if current_status != previous_status:
            try:
                send_message(bot=bot, message=current_status)
            except e.MessageNotSent as error:
                current_status = f"Не удалось отправить сообщение: {error}"
                logging.error(current_status)
        else:
            logging.info("Статус не изменился")

        previous_status = current_status
        time.sleep(RETRY_PERIOD)


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        filename="main.log",
        filemode="a",
        format="%(asctime)s, %(levelname)s, %(name)s, %(lineno)s, %(message)s",
    )

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    handler = StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s, %(levelname)s, %(name)s, %(lineno)s, %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    main()
