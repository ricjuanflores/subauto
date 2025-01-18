import configparser
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import errors
from rich.console import Console
from rich.prompt import Confirm, Prompt

from subauto.exceptions.api_manager import ApiManagerError
from subauto.exceptions.gemini import GeminiTokenApiError
from subauto.utils.logging import get_process_logger

logger_base = get_process_logger()

class APIKeyManager:
    """API Key and Application Configuration Manager."""
    ApiManagerError = ApiManagerError
    
    def __init__(self, app_name: str = "subauto"):
        self.app_name = app_name
        self.config_dir = Path.home() / f".{app_name}"
        self.config_file = self.config_dir / "config.ini"
        self.console = Console()
        self.parser = self._initialize_config()

    def _initialize_config(self) -> configparser.ConfigParser:
        """Initializes the configuration directory and file."""
        self.config_dir.mkdir(exist_ok=True)
        parser = configparser.ConfigParser()

        if self.config_file.exists():
            parser.read(self.config_file)

        return parser

    def has_api_key(self) -> bool:
        """Checks if an API key exists in the configuration file."""
        return self.parser.has_option("client", "gemini_api_key") and bool(
            self.parser.get("client", "gemini_api_key").strip()
        )

    def validate_api_key(self, api_key: str) -> None:
        """Validates the API key against the Gemini service."""
        logger_base.debug(f"validate_api_key: {api_key}")
        client = genai.Client(api_key=api_key)
        try:
            count_tokens = client.models.count_tokens(model="gemini-2.0-flash-exp", contents="test")
            logger_base.debug(f"count_tokens: {count_tokens}")
        except errors.ClientError as e:
            if e.message and "API key not valid" in e.message:
                raise GeminiTokenApiError("API key not valid", e)
            raise GeminiTokenApiError("Unexpected error while validating API key", e)

    def save_api_key(self, api_key: str) -> None:
        """Saves the API key in the configuration file."""
        if not self.parser.has_section("client"):
            self.parser.add_section("client")

        self.parser["client"]["gemini_api_key"] = api_key

        with open(self.config_file, "w") as f:
            self.parser.write(f)

        self.config_file.chmod(0o600)

    def _handle_cli_key(self, cli_api_key: str) -> str:
        """Handles the logic for API keys provided via CLI."""
        try:
            self.validate_api_key(cli_api_key)
            self.console.print("[green]✓ API key successfully validated[/]")
            self.save_api_key(cli_api_key)
            self.console.print("[green]✓ API key successfully saved[/]")
            return cli_api_key
        except (GeminiTokenApiError) as e:
            self.console.print(f"[red]✗ {str(e.message)}[/]")
            return self._request_api_key()
        except UnicodeError:
            self.console.print("[red]✗ API key not valid[/]")
            return self._request_api_key()


    def _request_api_key(self) -> str:
        """Requests and validates an API key from the user."""
        while True:
            try:
                api_key = Prompt.ask(
                    "[yellow]Please enter your Gemini API key[/]",
                    password=False,
                    console=self.console,
                )
                self.validate_api_key(api_key)
                self.console.print("[green]✓ API key successfully validated[/]")
                self.save_api_key(api_key)
                self.console.print("[green]✓ API key successfully saved[/]")
                return api_key
            except (GeminiTokenApiError) as e:
                self.console.print(f"[red]✗ {str(e.message)}[/]")
            except UnicodeError:
                self.console.print("[red]✗ API key not valid[/]")

    def _show_configuration_help(self) -> None:
        """Displays configuration instructions to the user."""
        self.console.print("[bold red]❌ No API key found.[/bold red]")
        self.console.print(
            "[yellow]👉 Please configure your API key to enable all application features.[/yellow]\n"
        )
        self.console.print("🔧 [bold]How to configure it:[/bold]")
        self.console.print("[green]1. Use the following command:[/]")
        self.console.print(f"   [cyan]{self.app_name} set-api-key YOUR_API_KEY[/]")

    def get_api_key(self, cli_api_key: Optional[str] = None) -> str:
        """Gets the API key from the available source."""
        if cli_api_key == "":
            raise ApiManagerError(message="API key cannot be empty")

        # Provided API key
        if cli_api_key:
            if self.has_api_key():
                # Confirm overwrite if an API key already exists
                if Confirm.ask(
                    "[yellow]An API key already exists in the config.ini file. Do you want to overwrite it?[/]",
                    console=self.console,
                ):
                    return self._handle_cli_key(cli_api_key)
                return self.parser.get("client", "gemini_api_key")
            return self._handle_cli_key(cli_api_key)

        # Use existing API key in config.ini
        if self.has_api_key():
            return self.parser.get("client", "gemini_api_key")

        # No API key available
        self._show_configuration_help()
        raise ApiManagerError(message="No API key available.")
