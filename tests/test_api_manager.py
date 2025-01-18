from configparser import ConfigParser
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, mock_open, patch

import pytest
import requests  # type: ignore
from google.genai import errors

from subauto.config.api_manager import APIKeyManager
from subauto.exceptions.api_manager import ApiManagerError
from subauto.exceptions.gemini import GeminiTokenApiError


@pytest.fixture
def api_manager() -> APIKeyManager:
    manager = APIKeyManager(app_name="test_app")
    manager.parser = ConfigParser()
    return manager


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    with patch("subauto.config.api_manager.Console") as mock:
        yield mock


@pytest.fixture
def mock_genai() -> Generator[Mock, None, None]:
    with patch("subauto.config.api_manager.genai") as mock:
        yield mock


class TestAPIKeyManager:
    def test_initialization(self, api_manager: APIKeyManager) -> None:
        assert api_manager.app_name == "test_app"
        assert isinstance(api_manager.parser, ConfigParser)
        assert str(api_manager.config_dir).endswith(".test_app")

    def test_has_api_key_true(self, api_manager: APIKeyManager, tmp_path: Path) -> None:
        test_file: Path = tmp_path / "config.ini"
        api_manager.config_file = test_file
        api_manager.parser.add_section("client")
        api_manager.parser.set("client", "gemini_api_key", "test_key")
        assert api_manager.has_api_key() is True

    def test_has_api_key_false(self, api_manager: APIKeyManager, tmp_path: Path) -> None:
        test_file: Path = tmp_path / "config.ini"
        api_manager.config_file = test_file

        with patch("pathlib.Path.open", mock_open()):
            gemini_api_key = api_manager.parser.get("client", "gemini_api_key", fallback=None)
            print(f"Valor de gemini_api_key antes de setear: {gemini_api_key}")
            assert api_manager.has_api_key() is False    



    def test_has_api_key_empty(self, api_manager: APIKeyManager) -> None:
        gemini_api_key = api_manager.parser.get("client", "gemini_api_key", fallback=None)
        print(f"Valor de gemini_api_key antes de setear zz: {gemini_api_key}")

        api_manager.parser.add_section("client")
        api_manager.parser.set("client", "gemini_api_key", "")
        assert api_manager.has_api_key() is False

    def test_validate_api_key_success(
        self, api_manager: APIKeyManager, mock_genai: Mock
    ) -> None:
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client
        api_manager.validate_api_key("valid_key")
        mock_genai.Client.assert_called_once_with(api_key="valid_key")
        mock_client.models.count_tokens.assert_called_once()

    def test_validate_api_key_invalid(
        self, api_manager: APIKeyManager, mock_genai: Mock
    ) -> None:
        
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 400
        mock_response.reason = "INVALID_ARGUMENT"
        mock_response.json.return_value = {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
            }
        }

        mock_client.models.count_tokens.side_effect = errors.ClientError(
            response=mock_response, code=400
        )

        with pytest.raises(GeminiTokenApiError) as exc:
            api_manager.validate_api_key("invalid_key")
        assert "API key not valid" in str(exc.value)

    def test_validate_api_key_unexpected_error(
        self, api_manager: APIKeyManager, mock_genai: Mock
    ) -> None:
        
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 500
        mock_response.reason = "INVALID_ARGUMENT"
        mock_response.json.return_value = {
            "error": {
                "code": 429,
                "message": "Resource has been exhausted (e.g. check quota).",
                "status": "RESOURCE_EXHAUSTED",
            }
        }

        mock_client.models.count_tokens.side_effect = errors.ClientError(
            response=mock_response, code=400
        )

        with pytest.raises(GeminiTokenApiError) as exc:
            api_manager.validate_api_key("some_key")
            
        print(f"exc.value: {exc.value}")
        assert"Unexpected error" in str(exc.value)

    @patch("subauto.config.api_manager.Confirm.ask")
    def test_get_api_key_cli_with_existing_confirmed(
        self, mock_confirm: Mock, api_manager: APIKeyManager
    ) -> None:
        api_manager.parser["client"] = {"gemini_api_key": "existing_key"}
        mock_confirm.return_value = True

        with patch.object(api_manager, "_handle_cli_key") as mock_handle:
            mock_handle.return_value = "con_new_key"
            
            result = api_manager.get_api_key("con_new_key")
            assert result == "con_new_key"
            mock_handle.assert_called_once_with("con_new_key")


    @patch("subauto.config.api_manager.Confirm.ask")
    def test_get_api_key_cli_with_existing_denied(
        self, mock_confirm: Mock, api_manager: APIKeyManager
    ) -> None:
        api_manager.parser["client"] = {"gemini_api_key": "existing_key"}
        mock_confirm.return_value = False

        result = api_manager.get_api_key("new_key")
        assert result == "existing_key"

    def test_get_api_key_empty_cli(self, api_manager: APIKeyManager) -> None:
        with pytest.raises(ApiManagerError) as exc:
            api_manager.get_api_key("")
        assert "API key cannot be empty" in str(exc.value)

    def test_get_api_key_no_key_available(
        self, api_manager: APIKeyManager
    ) -> None:
        with pytest.raises(ApiManagerError) as exc:
            api_manager.get_api_key()
        assert "No API key available" in str(exc.value)

    @patch("subauto.config.api_manager.Prompt.ask")
    def test_request_api_key_success(
        self, mock_prompt: Mock, api_manager: APIKeyManager
    ) -> None:
        mock_prompt.return_value = "test_key"

        with (
            patch.object(api_manager, "validate_api_key") as mock_validate,
            patch.object(api_manager, "save_api_key") as mock_save,
        ):
            result = api_manager._request_api_key()

            assert result == "test_key"
            mock_validate.assert_called_once_with("test_key")
            mock_save.assert_called_once_with("test_key")

    @patch("subauto.config.api_manager.Prompt.ask")
    def test_request_api_key_invalid_then_valid(
        self, mock_prompt: Mock, api_manager: APIKeyManager, mock_console: Mock
    ) -> None:
        mock_prompt.side_effect = ["invalid_key", "valid_key"]

        with (
            patch.object(api_manager, "validate_api_key") as mock_validate,
            patch.object(api_manager, "save_api_key") as mock_save,
        ):
            mock_validate.side_effect = [GeminiTokenApiError("Invalid key"), None]

            result = api_manager._request_api_key()
            assert result == "valid_key"
            assert mock_validate.call_count == 2
            mock_save.assert_called_once_with("valid_key")


    def test_handle_cli_key_success(
        self, api_manager: APIKeyManager, mock_console: Mock
    ) -> None:
        with (
            patch.object(api_manager, "validate_api_key") as mock_validate,
            patch.object(api_manager, "save_api_key") as mock_save,
        ):
            result = api_manager._handle_cli_key("test_key")

            assert result == "test_key"
            mock_validate.assert_called_once_with("test_key")
            mock_save.assert_called_once_with("test_key")

    def test_handle_cli_key_invalid(
        self, api_manager: APIKeyManager, mock_console: Mock
    ) -> None:
        with (
            patch.object(api_manager, "validate_api_key") as mock_validate,
            patch.object(api_manager, "_request_api_key") as mock_request,
        ):
            mock_validate.side_effect = GeminiTokenApiError("Invalid key")
            mock_request.return_value = "valid_key"

            result = api_manager._handle_cli_key("invalid_key")
            assert result == "valid_key"

