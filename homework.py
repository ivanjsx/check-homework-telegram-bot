import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler
from typing import Dict, List

import requests
from dotenv import load_dotenv
from telegram import Bot

import exceptions as e

load_dotenv()

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
    message = ""
    if not PRACTICUM_TOKEN:
        message = "Отсутствует токен для API сервиса Практикум.Домашка"
    if not TELEGRAM_TOKEN:
        message = "Отсутствует токен телеграм-бота"
    if not TELEGRAM_CHAT_ID:
        message = "Отсутствует идентификатор телеграм-чата"
    if message:
        logging.critical(msg=message)
        raise e.MissingTokenError(message)


def send_message(bot: Bot, message: str) -> None:
    """Отправляет сообщение в чат, определяемый переменной окружения."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logging.debug(msg="Сообщение успешно отправлено.")
    except Exception as error:
        logging.error(msg=f"Не удалось отправить сообщение: {error}")


def get_api_answer(timestamp: int = 0) -> Dict:
    """
    Делает запрос к единственному эндпоинту API-сервиса.
    В случае успеха, возвращает JSON с ответом.
    """
    params = {"from_date": timestamp}
    try:
        response = requests.get(url=ENDPOINT,
                                params=params,
                                headers=HEADERS,
                                timeout=REQUEST_TIMEOUT_IN_SECONDS)
    except Exception as error:
        message = f"Ошибка при запросе к основному API: {error}"
        logging.error(msg=message)

    if response.status_code != 200:
        message = (f"Статус ответа API отличается от 200: "
                   f"{HTTPStatus(response.status_code).value} "
                   f"{HTTPStatus(response.status_code).phrase}. "
                   f"Ключи ответа: {response.json().keys()}. "
                   f"Полный текст ответа: {response.text}")
        logging.error(msg=message)
        raise e.UnexpectedResponse(message)

    return response.json()


def check_response(response: Dict) -> None:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        message = 'Ответ API отличается от типа данных "dict"'
        logging.error(msg=message)
        raise e.UnexpectedResponse(message)
    if "homeworks" not in response.keys():
        message = "В ответе API отсутствует список работ"
        logging.error(msg=message)
        raise e.UnexpectedResponse(message)
    if not isinstance(response.get("homeworks"), list):
        message = 'Cписок работ отличается от типа данных "list"'
        logging.error(msg=message)
        raise e.UnexpectedResponse(message)


def get_homeworks_list(response: Dict) -> List:
    """Проверяет, есть ли работы в списке, возвращённом API."""
    homeworks_list = response.get("homeworks")
    if not homeworks_list:
        message = "Ни одна работа пока не была взята на проверку"
        logging.error(msg=message)
    return homeworks_list


def get_latest_homework(homeworks_list: List) -> Dict:
    """
    Получить из ответа API актуальную домашнюю работу.
    Для корректной работы функции необходимо предварительно гарантировать,
    что список работ в ответе API не пуст.
    """
    for homework in homeworks_list:
        if not homework.get("date_updated"):
            message = "У одной из работ отсутствет дата обновления"
            logging.error(msg=message)

    return sorted(
        homeworks_list,
        key=lambda homework: homework.get("date_updated"),
        reverse=True,
    )[0]


def parse_status(homework: Dict) -> str:
    """
    Извлекает статус из домашней работы.
    Возвращает подготовленную для отправки в Telegram строку.
    """
    homework_name = homework.get("homework_name")
    status = homework.get("status")
    verdict = HOMEWORK_VERDICTS.get(status)

    message = ""
    if not homework_name:
        message = "У домашней работы отсутствет название"
    if not status:
        message = "У домашней работы отсутствет статус"
    if not verdict:
        message = "Домашняя работа содержит неизвестный статус"
    if message:
        logging.error(msg=message)
        raise e.UnexpectedHomeworkData(message)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    previous_message = ""

    while True:
        try:
            answer = get_api_answer()
            check_response(answer)
            homeworks_list = get_homeworks_list(answer)
            homework = get_latest_homework(homeworks_list)
            current_message = parse_status(homework)

            if current_message != previous_message:
                send_message(bot=bot, message=current_message)
                previous_message = current_message
            else:
                logging.info("Статус не изменился.")

        except Exception as error:
            logging.error(f"Неизвестный сбой в работе программы: {error}")

        time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
