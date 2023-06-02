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
            raise e.ResponseStatusNotOk(
                f"Статус ответа: {status.value} {status.phrase}. "
                f"Полный текст: {response.text}"
            )

    except requests.RequestException as error:
        raise e.RequestError(f"Ошибка при запросе: {error}")

    logging.info(msg="Получили ответ от эндпоинта API, статус OK")

    try:
        logging.info(msg="Преобразуем ответ в словарь")
        result = response.json()
    except ValueError as error:
        raise e.InvalidResponseData(f"Не удалось распарсить ответ: {error}")

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
        raise e.EmptyHomeworksList(
            "Ни одна работа пока не взята на проверку"
        )


def get_latest_homework(response: Dict) -> Dict:
    """
    Получает из ответа актуальную домашнюю работу.
    Для корректной работы функции необходимо предварительно гарантировать,
    что список работ в ответе не пуст.
    """
    for homework in response["homeworks"]:
        if not homework.get("date_updated"):
            raise e.UnexpectedHomeworkData(
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
        raise e.UnexpectedHomeworkData(
            "У домашней работы отсутствет название"
        )
    if not homework.get("status"):
        raise e.UnexpectedHomeworkData(
            "У домашней работы отсутствет статус"
        )
    if not HOMEWORK_VERDICTS.get(homework["status"]):
        raise e.UnexpectedHomeworkData(
            "Домашняя работа содержит неизвестный статус"
        )

    homework_name = homework["homework_name"]
    verdict = HOMEWORK_VERDICTS[homework["status"]]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    previous_status = ""

    try:
        logging.info(msg="Инициализируем бота")
        check_tokens()
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except e.MissingTokenError as error:
        logging.critical(f"Ошибка при инициализации: {error}")
        sys.exit()
    else:
        logging.info(msg="Успешно завершили инициализацию бота")

    while True:
        try:
            logging.info(msg="Запускаем итерацию работы бота")

            response = get_api_answer()
            check_response(response)
            homework = get_latest_homework(response)
            current_status = parse_status(homework)

            if current_status == previous_status:
                logging.info("Статус не изменился")
            else:
                previous_status = current_status
                send_message(bot=bot, message=current_status)

        except e.ResponseStatusNotOk as error:
            message = f"Статус ответа API отличается от OK: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except e.RequestError as error:
            message = f"Ошибка при запросе к API сервиса Домашка: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except e.InvalidResponseData as error:
            message = f"У ответа API неправильный формат данных: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except e.UnexpectedResponseData as error:
            message = f"Ответ API не соответствует документации: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except e.EmptyHomeworksList as error:
            message = f"API вернула пустой список домашних работ: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except e.UnexpectedHomeworkData as error:
            message = f"Данные о работе неправильного формата: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except e.MessageNotSent as error:
            message = f"Боту не удалось отправить сообщение: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        except Exception as error:
            message = f"Неизвестный сбой в работе программы: {error}"
            logging.error(message)
            send_message(bot=bot, message=message)

        else:
            logging.info(msg="Успешно завершили итерацию работы бота")

        finally:
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
