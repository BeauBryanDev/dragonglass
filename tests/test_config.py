
from pydantic import SecretStr

from app.core.config import settings


def test_keys_are_loaded_as_secrets():

    assert isinstance(settings.anthropic_api_key, SecretStr)
    assert isinstance(settings.google_api_key, SecretStr)
    assert settings.anthropic_api_key.get_secret_value()
    assert settings.google_api_key.get_secret_value()


def test_keys_never_appear_in_repr():

    shown = repr(settings)

    assert settings.anthropic_api_key.get_secret_value() not in shown
    assert settings.google_api_key.get_secret_value() not in shown
