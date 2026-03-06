"""Tests for the provider registry."""

import os
from unittest.mock import MagicMock, patch

import pytest

from computer_use.core.errors import ConfigError
from computer_use.providers.registry import get_provider, list_providers


class TestListProviders:
    def test_returns_both_registered_providers(self):
        result = list_providers()
        assert sorted(result) == ["anthropic", "openai"]

    def test_contains_at_least_two_providers(self):
        result = list_providers()
        assert len(result) >= 2


class TestGetProvider:
    def test_unknown_provider_raises_config_error(self):
        with pytest.raises(ConfigError, match="Unknown provider 'banana'"):
            get_provider("banana", {})

    def test_api_key_from_config(self):
        fake_cls = MagicMock()
        fake_module = MagicMock()
        fake_module.AnthropicProvider = fake_cls

        config = {
            "providers": {
                "anthropic": {"api_key": "sk-from-config"},
            }
        }

        with patch("importlib.import_module", return_value=fake_module):
            provider = get_provider("anthropic", config)

        fake_cls.assert_called_once_with(api_key="sk-from-config")
        assert provider is fake_cls.return_value

    def test_api_key_from_env_var(self):
        fake_cls = MagicMock()
        fake_module = MagicMock()
        fake_module.AnthropicProvider = fake_cls

        with (
            patch("importlib.import_module", return_value=fake_module),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-from-env"}),
        ):
            provider = get_provider("anthropic", {})

        fake_cls.assert_called_once_with(api_key="sk-from-env")
        assert provider is fake_cls.return_value

    def test_config_key_takes_precedence_over_env(self):
        fake_cls = MagicMock()
        fake_module = MagicMock()
        fake_module.AnthropicProvider = fake_cls

        config = {
            "providers": {
                "anthropic": {"api_key": "sk-from-config"},
            }
        }

        with (
            patch("importlib.import_module", return_value=fake_module),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-from-env"}),
        ):
            get_provider("anthropic", config)

        fake_cls.assert_called_once_with(api_key="sk-from-config")

    def test_no_api_key_raises_config_error(self):
        fake_module = MagicMock()
        fake_module.AnthropicProvider = MagicMock()

        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with (
            patch("importlib.import_module", return_value=fake_module),
            patch.dict(os.environ, env, clear=True),
        ):
            with pytest.raises(ConfigError, match="No API key for 'anthropic'"):
                get_provider("anthropic", {})

    def test_model_from_config_is_passed(self):
        fake_cls = MagicMock()
        fake_module = MagicMock()
        fake_module.OpenAIProvider = fake_cls

        config = {
            "providers": {
                "openai": {
                    "api_key": "sk-test",
                    "model": "gpt-4o",
                },
            }
        }

        with patch("importlib.import_module", return_value=fake_module):
            get_provider("openai", config)

        fake_cls.assert_called_once_with(api_key="sk-test", model="gpt-4o")

    def test_model_omitted_when_not_in_config(self):
        fake_cls = MagicMock()
        fake_module = MagicMock()
        fake_module.AnthropicProvider = fake_cls

        config = {
            "providers": {
                "anthropic": {"api_key": "sk-test"},
            }
        }

        with patch("importlib.import_module", return_value=fake_module):
            get_provider("anthropic", config)

        fake_cls.assert_called_once_with(api_key="sk-test")
        assert "model" not in fake_cls.call_args.kwargs

    def test_dynamic_import_uses_correct_module_path(self):
        fake_cls = MagicMock()
        fake_module = MagicMock()
        fake_module.OpenAIProvider = fake_cls

        config = {"providers": {"openai": {"api_key": "sk-test"}}}

        with patch("importlib.import_module", return_value=fake_module) as mock_import:
            get_provider("openai", config)

        mock_import.assert_called_once_with("computer_use.providers.openai")
