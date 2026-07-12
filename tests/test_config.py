from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from promptbridge.config import ProfileError, ProfileStore, ProviderProfile


class ProfileStoreTest(unittest.TestCase):
    def test_add_switch_and_remove_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(Path(tmp) / "providers.json")
            store.add(
                ProviderProfile(
                    name="openrouter",
                    protocol="chat",
                    base_url="https://openrouter.ai/api/v1",
                    default_model="vendor/model",
                )
            )
            store.add(
                ProviderProfile(
                    name="ollama",
                    protocol="chat",
                    base_url="http://127.0.0.1:11434/v1",
                    default_model="local-model",
                    auth="none",
                )
            )

            self.assertEqual(store.active_name(), "openrouter")
            store.set_active("ollama")
            self.assertEqual(store.get().name, "ollama")
            store.remove("ollama")
            self.assertEqual(store.get().name, "openrouter")

    def test_remote_http_and_embedded_credentials_are_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            ProviderProfile("unsafe", "chat", "http://example.com/v1", "model")
        with self.assertRaises(ProfileError):
            ProviderProfile("unsafe", "chat", "https://user:pass@example.com/v1", "model")
        with self.assertRaises(ProfileError):
            ProviderProfile("unsafe", "chat", "https://example.com/v1?target=other", "model")


if __name__ == "__main__":
    unittest.main()
