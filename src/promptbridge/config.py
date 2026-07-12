from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from promptbridge.utils import read_json, write_json


PROTOCOLS = {"responses", "chat"}
AUTH_MODES = {"bearer", "none"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ProfileError(RuntimeError):
    """Raised when a provider profile or its credential is invalid."""


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    protocol: str
    base_url: str
    default_model: str
    auth: str = "bearer"

    def __post_init__(self) -> None:
        name = self.name.strip()
        model = self.default_model.strip()
        base_url = self.base_url.strip().rstrip("/")
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            raise ProfileError("Profile name must contain only letters, numbers, '-' or '_'.")
        if self.protocol not in PROTOCOLS:
            raise ProfileError(f"Unsupported protocol: {self.protocol}")
        if self.auth not in AUTH_MODES:
            raise ProfileError(f"Unsupported auth mode: {self.auth}")
        if not model:
            raise ProfileError("A default model is required.")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ProfileError("base_url must be an absolute HTTP(S) URL.")
        if parsed.username or parsed.password:
            raise ProfileError("Credentials must not be embedded in base_url.")
        if parsed.query or parsed.fragment:
            raise ProfileError("base_url must not contain a query string or fragment.")
        if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
            raise ProfileError("Remote providers must use HTTPS; HTTP is allowed only on loopback.")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "default_model", model)

    @property
    def origin(self) -> str:
        parsed = urlparse(self.base_url)
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProviderProfile":
        try:
            return cls(
                name=str(payload["name"]),
                protocol=str(payload["protocol"]),
                base_url=str(payload["base_url"]),
                default_model=str(payload["default_model"]),
                auth=str(payload.get("auth", "bearer")),
            )
        except KeyError as exc:
            raise ProfileError(f"Provider profile is missing {exc.args[0]!r}.") from exc


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path

    def ensure(self) -> None:
        if not self.path.exists():
            write_json(
                self.path,
                {"schema_version": 1, "active": None, "profiles": {}},
            )

    def list(self) -> list[ProviderProfile]:
        document = self._load()
        return sorted(
            (ProviderProfile.from_dict(item) for item in document["profiles"].values()),
            key=lambda profile: profile.name,
        )

    def add(self, profile: ProviderProfile) -> None:
        document = self._load()
        if profile.name in document["profiles"]:
            raise ProfileError(f"Provider profile {profile.name!r} already exists.")
        document["profiles"][profile.name] = profile.to_dict()
        if document["active"] is None:
            document["active"] = profile.name
        write_json(self.path, document)

    def get(self, name: str | None = None) -> ProviderProfile:
        document = self._load()
        resolved_name = name or document["active"]
        if not resolved_name:
            raise ProfileError("No active provider. Add one with `pb provider add`.")
        payload = document["profiles"].get(resolved_name)
        if payload is None:
            raise ProfileError(f"Unknown provider profile: {resolved_name}")
        return ProviderProfile.from_dict(payload)

    def active_name(self) -> str | None:
        return self._load()["active"]

    def set_active(self, name: str) -> None:
        document = self._load()
        if name not in document["profiles"]:
            raise ProfileError(f"Unknown provider profile: {name}")
        document["active"] = name
        write_json(self.path, document)

    def remove(self, name: str) -> ProviderProfile:
        document = self._load()
        payload = document["profiles"].pop(name, None)
        if payload is None:
            raise ProfileError(f"Unknown provider profile: {name}")
        if document["active"] == name:
            document["active"] = next(iter(document["profiles"]), None)
        write_json(self.path, document)
        return ProviderProfile.from_dict(payload)

    def _load(self) -> dict[str, Any]:
        self.ensure()
        document = read_json(self.path)
        if not isinstance(document, dict) or not isinstance(document.get("profiles"), dict):
            raise ProfileError(f"Invalid provider configuration: {self.path}")
        document.setdefault("schema_version", 1)
        document.setdefault("active", None)
        return document


class KeyringSecretStore:
    """Store provider-scoped API keys in the operating system credential store."""

    service_name = "promptbridge"

    def set(self, profile: ProviderProfile, secret: str) -> None:
        if profile.auth == "none":
            raise ProfileError(f"Provider {profile.name!r} does not use an API key.")
        if not secret.strip():
            raise ProfileError("API key cannot be empty.")
        keyring = self._keyring()
        try:
            keyring.set_password(self.service_name, self._username(profile), secret.strip())
        except Exception as exc:  # keyring backends expose platform-specific errors
            raise ProfileError(f"Could not store the API key in the system credential store: {exc}") from exc

    def get(self, profile: ProviderProfile) -> str | None:
        if profile.auth == "none":
            return None
        keyring = self._keyring()
        try:
            secret = keyring.get_password(self.service_name, self._username(profile))
        except Exception as exc:
            raise ProfileError(f"Could not read the system credential store: {exc}") from exc
        if not secret:
            raise ProfileError(
                f"No API key for {profile.name!r}. Run `pb provider set-key {profile.name}`."
            )
        return secret

    def delete(self, profile: ProviderProfile) -> None:
        if profile.auth == "none":
            return
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service_name, self._username(profile))
        except Exception:
            return

    @staticmethod
    def _username(profile: ProviderProfile) -> str:
        # Binding the credential to the origin prevents reusing it after a URL change.
        return f"{profile.name}@{profile.origin}"

    @staticmethod
    def _keyring():
        try:
            import keyring
        except ImportError as exc:
            raise ProfileError(
                "The `keyring` package is required for API keys. Install PromptBridge with `pip install -e .`."
            ) from exc
        return keyring
