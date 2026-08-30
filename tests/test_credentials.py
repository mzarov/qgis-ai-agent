import sys
import types
import unittest

from ai_agent.config import geocoder as geocoder_config
from ai_agent.core import settings
from ai_agent.core.llm import client

REMOTE = "https://api.openai.com/v1"
OTHER_REMOTE = "https://api.anthropic.com/v1"
LOCAL = "http://localhost:11434/v1"


class MemorySettings:
    values: dict[str, object] = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


class FakeKeyring(types.ModuleType):
    def __init__(self):
        super().__init__("keyring")
        self.passwords: dict[tuple[str, str], str] = {}
        self.failure: Exception | None = None
        self.deleted: list[tuple[str, str]] = []

    def get_password(self, service, account):
        if self.failure is not None:
            raise self.failure
        return self.passwords.get((service, account))

    def set_password(self, service, account, value):
        if self.failure is not None:
            raise self.failure
        self.passwords[(service, account)] = value

    def delete_password(self, service, account):
        if self.failure is not None:
            raise self.failure
        self.deleted.append((service, account))
        del self.passwords[(service, account)]


class ScopedCredentialTest(unittest.TestCase):
    def setUp(self):
        self.saved_settings = settings.QgsSettings
        self.saved_keyring = sys.modules.get("keyring")
        MemorySettings.values = {}
        settings.QgsSettings = MemorySettings
        settings._credential_store_error = ""
        self.keyring = FakeKeyring()
        sys.modules["keyring"] = self.keyring
        settings.set_api_url(REMOTE)

    def tearDown(self):
        settings.QgsSettings = self.saved_settings
        settings._credential_store_error = ""
        if self.saved_keyring is None:
            sys.modules.pop("keyring", None)
        else:
            sys.modules["keyring"] = self.saved_keyring

    def test_different_endpoints_keep_different_keys(self):
        settings.set_api_key("openai-secret", REMOTE, "openai")
        settings.set_api_key("anthropic-secret", OTHER_REMOTE, "anthropic")
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "openai-secret")
        self.assertEqual(settings.get_api_key(OTHER_REMOTE, "anthropic"), "anthropic-secret")

    def test_auto_and_resolved_dialect_share_the_same_provider_key(self):
        settings.set_api_key("secret", REMOTE, "auto")
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "secret")

    def test_equivalent_endpoint_spelling_uses_the_same_key(self):
        settings.set_api_key("secret", "https://API.OPENAI.COM/v1/", "openai")
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "secret")

    def test_remote_key_is_not_returned_for_localhost(self):
        settings.set_api_key("remote-secret", REMOTE, "openai")
        self.assertEqual(settings.get_api_key(LOCAL, "openai"), "")

    def test_client_does_not_send_the_stored_remote_key_to_localhost(self):
        settings.set_api_key("remote-secret", REMOTE, "openai")
        _, headers, _ = client.build_request(
            url_override=LOCAL,
            auth_type_override="Bearer",
            model_override="local-model",
            dialect_override="openai",
        )
        self.assertNotIn("Authorization", headers)

    def test_empty_value_explicitly_deletes_only_the_scoped_key(self):
        settings.set_api_key("one", REMOTE, "openai")
        settings.set_api_key("two", OTHER_REMOTE, "anthropic")
        settings.set_api_key("", REMOTE, "openai")
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "")
        self.assertEqual(settings.get_api_key(OTHER_REMOTE, "anthropic"), "two")
        self.assertEqual(len(self.keyring.deleted), 1)

    def test_legacy_key_migrates_only_to_the_configured_remote_endpoint(self):
        legacy = (settings.KEYRING_SERVICE, settings.KEYRING_KEY)
        self.keyring.passwords[legacy] = "legacy-secret"
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "legacy-secret")
        self.assertNotIn(legacy, self.keyring.passwords)
        self.assertEqual(settings.get_api_key(OTHER_REMOTE, "anthropic"), "")

    def test_arbitrary_remote_override_cannot_claim_the_legacy_key(self):
        legacy = (settings.KEYRING_SERVICE, settings.KEYRING_KEY)
        self.keyring.passwords[legacy] = "legacy-secret"
        self.assertEqual(settings.get_api_key(OTHER_REMOTE, "anthropic"), "")
        self.assertEqual(self.keyring.passwords[legacy], "legacy-secret")
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "legacy-secret")

    def test_legacy_key_is_never_migrated_to_localhost(self):
        settings.set_api_url(LOCAL)
        legacy = (settings.KEYRING_SERVICE, settings.KEYRING_KEY)
        self.keyring.passwords[legacy] = "legacy-remote-secret"
        self.assertEqual(settings.get_api_key(LOCAL, "openai"), "")
        self.assertEqual(self.keyring.passwords[legacy], "legacy-remote-secret")

    def test_https_mdns_endpoint_is_remote_for_legacy_key_migration(self):
        endpoint = "https://workstation.local/v1"
        settings.set_api_url(endpoint)
        legacy = (settings.KEYRING_SERVICE, settings.KEYRING_KEY)
        self.keyring.passwords[legacy] = "legacy-secret"
        self.assertEqual(settings.get_api_key(endpoint, "openai"), "legacy-secret")

    def test_keyring_failure_is_visible_to_remote_requests(self):
        self.keyring.failure = RuntimeError("secret service is locked")
        settings.get_api_key(REMOTE, "openai")
        for key_override in (None, ""):
            with self.subTest(key_override=key_override), self.assertRaises(RuntimeError) as caught:
                client.build_request(
                    url_override=REMOTE,
                    key_override=key_override,
                    auth_type_override="Bearer",
                    model_override="model",
                    dialect_override="openai",
                )
            self.assertIn("secret service is locked", str(caught.exception))


class ScopedCapabilityTest(unittest.TestCase):
    def setUp(self):
        self.saved_settings = settings.QgsSettings
        self.saved_geocoder_settings = geocoder_config.QgsSettings
        MemorySettings.values = {}
        settings.QgsSettings = MemorySettings
        geocoder_config.QgsSettings = MemorySettings

    def tearDown(self):
        settings.QgsSettings = self.saved_settings
        geocoder_config.QgsSettings = self.saved_geocoder_settings

    def test_capability_cache_is_scoped_by_url_model_and_dialect(self):
        settings.set_supports_tools(REMOTE, False, "model-a", "openai")
        self.assertFalse(settings.get_supports_tools(REMOTE, "model-a", "openai"))
        self.assertIsNone(settings.get_supports_tools(REMOTE, "model-b", "openai"))
        self.assertIsNone(settings.get_supports_tools(REMOTE, "model-a", "anthropic"))
        self.assertIsNone(settings.get_supports_tools(OTHER_REMOTE, "model-a", "openai"))

    def test_data_sharing_choices_are_scoped_by_endpoint_and_default_off(self):
        self.assertFalse(settings.get_data_sharing_consent(REMOTE))
        self.assertFalse(settings.get_allow_sensitive_data(REMOTE))
        settings.set_data_sharing_consent(True, REMOTE)
        settings.set_allow_sensitive_data(True, REMOTE)
        self.assertTrue(settings.get_data_sharing_consent(REMOTE))
        self.assertTrue(settings.get_allow_sensitive_data(REMOTE))
        self.assertFalse(settings.get_data_sharing_consent(OTHER_REMOTE))
        self.assertFalse(settings.get_allow_sensitive_data(OTHER_REMOTE))

    def test_corrupt_opt_in_values_fail_closed(self):
        suffix = settings._url_settings_key(REMOTE)
        for raw in ("", "garbage", "enabled-ish"):
            MemorySettings.values[f"ai_agent/data_sharing_consent/{suffix}"] = raw
            MemorySettings.values[f"ai_agent/allow_sensitive_data/{suffix}"] = raw
            self.assertFalse(settings.get_data_sharing_consent(REMOTE), raw)
            self.assertFalse(settings.get_allow_sensitive_data(REMOTE), raw)

    def test_ssl_opt_out_is_scoped_by_endpoint_and_defaults_on(self):
        self.assertTrue(settings.get_verify_ssl(REMOTE))
        settings.set_verify_ssl(False, REMOTE)
        self.assertFalse(settings.get_verify_ssl(REMOTE))
        self.assertTrue(settings.get_verify_ssl(OTHER_REMOTE))

    def test_geocoding_is_opt_in_and_provider_urls_are_not_model_settings(self):
        self.assertEqual(settings.get_geocoder_provider(), settings.GEOCODER_DISABLED)
        self.assertEqual(settings.get_geocoder_url(), "")
        settings.set_geocoder_provider(settings.GEOCODER_PHOTON)
        self.assertEqual(settings.get_geocoder_url(), settings.GEOCODER_PHOTON_URL)
        settings.set_custom_nominatim_url("https://geo.example/nominatim")
        settings.set_geocoder_provider(settings.GEOCODER_NOMINATIM)
        self.assertEqual(settings.get_geocoder_url(), "https://geo.example/nominatim")


if __name__ == "__main__":
    unittest.main()
