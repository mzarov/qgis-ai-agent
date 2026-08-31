import unittest

from ai_agent.config import geocoder as geocoder_config
from ai_agent.core import credentials, settings
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

    def remove(self, key):
        self.values.pop(key, None)

    def sync(self):
        pass


class FakeConfig:
    def __init__(self, *_a, **_k):
        self._id = ""
        self._name = ""
        self._method = ""
        self._map: dict[str, str] = {}

    def setId(self, value):
        self._id = value

    def id(self):
        return self._id

    def setName(self, value):
        self._name = value

    def name(self):
        return self._name

    def setMethod(self, value):
        self._method = value

    def setConfig(self, key, value):
        self._map[key] = value

    def config(self, key, default=""):
        return self._map.get(key, default)


class FakeAuthManager:
    def __init__(self):
        self.stored: dict[str, FakeConfig] = {}
        self.unlocked = True
        self.disabled = False
        self.failure: Exception | None = None
        self.remove_result = True
        self.removed: list[str] = []
        self._next = 0

    def isDisabled(self):
        return self.disabled

    def masterPasswordIsSet(self):
        return self.unlocked

    def setMasterPassword(self, _verify=True):
        return self.unlocked

    def storeAuthenticationConfig(self, config, _overwrite=False):
        if self.failure is not None:
            raise self.failure
        if not config.id():
            self._next += 1
            config.setId(f"cfg{self._next:03d}")
        self.stored[config.id()] = config
        return True, config

    def loadAuthenticationConfig(self, config_id, _empty, _full=True):
        if self.failure is not None:
            raise self.failure
        found = self.stored.get(config_id)
        return (True, found) if found is not None else (False, FakeConfig())

    def removeAuthenticationConfig(self, config_id):
        if self.failure is not None:
            raise self.failure
        self.removed.append(config_id)
        if self.remove_result:
            self.stored.pop(config_id, None)
        return self.remove_result


class FakeApplication:
    manager = None

    @classmethod
    def authManager(cls):
        return cls.manager


class ScopedCredentialTest(unittest.TestCase):
    def setUp(self):
        self.saved_settings = settings.QgsSettings
        self.saved_store_settings = credentials.QgsSettings
        self.saved_application = credentials.QgsApplication
        self.saved_config = credentials.QgsAuthMethodConfig
        MemorySettings.values = {}
        settings.QgsSettings = MemorySettings
        credentials.QgsSettings = MemorySettings
        credentials.QgsAuthMethodConfig = FakeConfig
        credentials.QgsApplication = FakeApplication
        credentials._error = ""
        self.manager = FakeAuthManager()
        FakeApplication.manager = self.manager
        settings.set_api_url(REMOTE)

    def tearDown(self):
        settings.QgsSettings = self.saved_settings
        credentials.QgsSettings = self.saved_store_settings
        credentials.QgsApplication = self.saved_application
        credentials.QgsAuthMethodConfig = self.saved_config
        credentials._error = ""
        FakeApplication.manager = None

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

    def test_rewriting_a_key_reuses_one_config_instead_of_piling_them_up(self):
        settings.set_api_key("first", REMOTE, "openai")
        settings.set_api_key("second", REMOTE, "openai")
        self.assertEqual(len(self.manager.stored), 1)
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "second")

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
        self.assertEqual(len(self.manager.removed), 1)

    def test_failed_delete_keeps_the_auth_config_reachable(self):
        settings.set_api_key("secret", REMOTE, "openai")
        self.manager.failure = RuntimeError("auth database is locked")

        with self.assertRaisesRegex(RuntimeError, "Could not remove"):
            settings.delete_api_key(REMOTE, "openai")

        self.assertIn("cfg001", MemorySettings.values.values())
        self.assertIn("cfg001", self.manager.stored)

    def test_refused_delete_keeps_the_auth_config_reachable(self):
        settings.set_api_key("secret", REMOTE, "openai")
        self.manager.remove_result = False

        with self.assertRaisesRegex(RuntimeError, "refused to remove"):
            settings.delete_api_key(REMOTE, "openai")

        self.assertIn("cfg001", MemorySettings.values.values())
        self.assertIn("cfg001", self.manager.stored)

    def test_the_secret_itself_never_reaches_the_settings_file(self):
        settings.set_api_key("plaintext-secret", REMOTE, "openai")
        written = " ".join(str(value) for value in MemorySettings.values.values())
        self.assertNotIn("plaintext-secret", written)
        self.assertIn("cfg001", written)

    def test_a_refused_master_password_reads_empty_and_says_why(self):
        settings.set_api_key("secret", REMOTE, "openai")
        self.manager.unlocked = False
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "")
        self.assertIn("master password", settings.get_credential_store_error())

    def test_a_disabled_database_is_reported_not_swallowed(self):
        self.manager.disabled = True
        with self.assertRaises(RuntimeError):
            settings.set_api_key("secret", REMOTE, "openai")
        self.assertTrue(settings.credential_store_failure_message().strip())

    def test_a_missing_manager_does_not_crash_the_read(self):
        settings.set_api_key("secret", REMOTE, "openai")
        FakeApplication.manager = None
        self.assertEqual(settings.get_api_key(REMOTE, "openai"), "")

    def test_store_failure_is_visible_to_remote_requests(self):
        settings.set_api_key("secret", REMOTE, "openai")
        self.manager.failure = RuntimeError("auth database is locked")
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
            self.assertIn("auth database is locked", str(caught.exception))


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

    def test_sensitive_data_opt_in_is_scoped_by_endpoint_and_default_off(self):
        self.assertFalse(settings.get_allow_sensitive_data(REMOTE))
        settings.set_allow_sensitive_data(True, REMOTE)
        self.assertTrue(settings.get_allow_sensitive_data(REMOTE))
        self.assertFalse(settings.get_allow_sensitive_data(OTHER_REMOTE))

    def test_corrupt_opt_in_values_fail_closed(self):
        suffix = settings._url_settings_key(REMOTE)
        for raw in ("", "garbage", "enabled-ish"):
            MemorySettings.values[f"ai_agent/allow_sensitive_data/{suffix}"] = raw
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
