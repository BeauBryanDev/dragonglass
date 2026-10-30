
import logging
import sys

from app.core.config import settings

FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
MASK = "**********"
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
QUIET_LOGGERS = ("httpx", "httpcore", "anthropic")


class RedactingFormatter(logging.Formatter):

    def __init__(self, fmt, secrets):

        super().__init__(fmt)
        self.secrets = [secret for secret in secrets if secret]

    def format(self, record):

        text = super().format(record)

        for secret in self.secrets:
            text = text.replace(secret, MASK)

        return text


def setup_logging():

    secrets = (settings.anthropic_api_key.get_secret_value(),
               settings.google_api_key.get_secret_value())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter(FORMAT, secrets))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
