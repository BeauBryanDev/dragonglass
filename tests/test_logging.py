
import logging
import sys

import pytest

from app.core.logging import FORMAT, MASK, RedactingFormatter, setup_logging

SECRET = "sk-ant-not-a-real-key"


def make_record(message, exc_info=None):

    return logging.LogRecord("test", logging.ERROR, __file__, 1,
                             message, None, exc_info)


@pytest.fixture
def restore_root():

    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level

    yield root

    root.handlers = handlers
    root.setLevel(level)


def test_secret_is_masked_in_message():

    text = RedactingFormatter(FORMAT, [SECRET]).format(make_record(f"key is {SECRET}"))

    assert SECRET not in text
    assert MASK in text


def test_secret_is_masked_in_traceback():

    try:
        raise ValueError(f"bad key {SECRET}")
    except ValueError:
        record = make_record("request failed", sys.exc_info())

    text = RedactingFormatter(FORMAT, [SECRET]).format(record)

    assert "ValueError" in text
    assert SECRET not in text


def test_empty_secret_does_not_corrupt_output():

    text = RedactingFormatter(FORMAT, [""]).format(make_record("hello"))

    assert "hello" in text


def test_setup_is_safe_to_call_twice(restore_root):

    setup_logging()
    setup_logging()

    assert len(restore_root.handlers) == 1
    assert logging.getLogger("uvicorn.access").propagate
    assert logging.getLogger("httpx").level == logging.WARNING
