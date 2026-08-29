import pathlib
import unittest

from qgis_ai_agent.core import settings
from qgis_ai_agent.core.llm import client
from qgis_ai_agent.core.llm.client import build_request, is_local, resolve_endpoint
from qgis_ai_agent.core.llm.dialects import safe_endpoint_label

REMOTE = "https://api.openai.com/v1"
USERINFO_URL = "https://localhost:password@evil.example/v1"


def request(url, key):
    return build_request(url_override=url, key_override=key, auth_type_override="Bearer", model_override="демо")


class LocalHostTest(unittest.TestCase):
    def test_loopback_names_are_local(self):
        for url in ("http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]/v1"):
            self.assertTrue(is_local(url), url)

    def test_port_does_not_confuse_it(self):
        self.assertTrue(is_local("http://localhost:8080/v1"))

    def test_mdns_lan_names_are_not_privileged_as_loopback(self):
        self.assertFalse(is_local("https://ноутбук.local:11434/v1"))

    def test_public_hosts_are_not_local(self):
        for url in (REMOTE, "https://openrouter.ai/api/v1", "https://localhost.evil.com/v1"):
            self.assertFalse(is_local(url), url)

    def test_userinfo_cannot_spoof_a_local_host(self):
        for url in (
            USERINFO_URL,
            "https://workstation.local:password@evil.example/v1",
        ):
            self.assertFalse(is_local(url), url)

    def test_transport_endpoint_label_never_echoes_credentials_or_query(self):
        label = safe_endpoint_label("https://alice:sentinel@example.com:8443/v1?key=sentinel")
        self.assertEqual(label, "https://example.com:8443")


class BuildRequestTest(unittest.TestCase):
    def setUp(self):
        self.saved_credential_store_error = settings._credential_store_error
        settings._credential_store_error = ""

    def tearDown(self):
        settings._credential_store_error = self.saved_credential_store_error

    def test_local_endpoint_needs_no_key(self):
        endpoint, headers, model = request("http://localhost:11434/v1", "")
        self.assertEqual(endpoint, "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("Authorization", headers)
        self.assertEqual(model, "демо")

    def test_local_endpoint_still_uses_a_key_when_given(self):
        _, headers, _ = request("http://localhost:1234/v1", "ключ")
        self.assertEqual(headers["Authorization"], "Bearer ключ")

    def test_remote_endpoint_without_a_key_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            request(REMOTE, "")
        self.assertIn("localhost", str(caught.exception))

    def test_remote_plain_http_endpoint_is_refused_even_with_a_key(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            request("http://api.example/v1", "secret")

    def test_remote_endpoint_carries_the_key(self):
        _, headers, _ = request(REMOTE, "sk-демо")
        self.assertEqual(headers["Authorization"], "Bearer sk-демо")

    def test_content_type_is_always_json(self):
        for url, key in (("http://localhost:11434/v1", ""), (REMOTE, "sk-демо")):
            _, headers, _ = request(url, key)
            self.assertEqual(headers["Content-Type"], "application/json")

    def test_trailing_slash_is_trimmed(self):
        self.assertEqual(resolve_endpoint("http://localhost:11434/v1/"), "http://localhost:11434/v1")

    def test_empty_url_is_refused(self):
        with self.assertRaises(ValueError):
            resolve_endpoint("   ")

    def test_malformed_ipv6_url_is_reported_cleanly(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            resolve_endpoint("https://[::1")

    def test_url_without_a_hostname_is_refused(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            resolve_endpoint("https:///v1")

    def test_credentials_in_url_are_refused_before_they_can_be_saved_or_sent(self):
        credential_queries = (
            "api-key",
            "api_key",
            "client_secret",
            "password",
            "access-token",
            "refresh_token",
            "X-Amz-Security-Token",
            "X-Amz-Signature",
            "X-Goog-Credential",
            "X-Goog-Signature",
            "vendor_client_secret",
            "vendor-signature",
        )
        for query in credential_queries:
            with self.subTest(query=query), self.assertRaisesRegex(ValueError, "API key field"):
                resolve_endpoint(f"https://api.example/v1?{query}=sentinel")
        with self.assertRaisesRegex(ValueError, "API key field"):
            resolve_endpoint(USERINFO_URL)


if __name__ == "__main__":
    unittest.main()


class TransportTest(unittest.TestCase):
    SOURCE = (
        pathlib.Path(__file__).resolve().parent.parent / "qgis_ai_agent" / "core" / "llm" / "client.py"
    ).read_text(encoding="utf-8")

    def test_network_goes_through_qgis_not_requests(self):
        self.assertIn("QgsBlockingNetworkRequest", self.SOURCE)
        self.assertNotIn("import requests", self.SOURCE)
        self.assertNotIn("session.post", self.SOURCE)

    def test_headers_are_carried_onto_the_request(self):
        body = self.SOURCE.split("def build_network_request(")[1].split("\ndef ")[0]
        self.assertIn("setRawHeader", body)

    def test_ssl_opt_out_does_not_weaken_the_redirect_policy(self):
        body = self.SOURCE.split("def build_network_request(")[1].split("\ndef ")[0]
        self.assertIn("setPeerVerifyMode", body)
        self.assertIn("setSslConfiguration", body)
        self.assertIn("SameOriginRedirectPolicy", body)
        self.assertNotIn("NoLessSafeRedirectPolicy", body)

    def test_transfer_timeout_is_set_on_every_request(self):
        body = self.SOURCE.split("def build_network_request(")[1].split("\ndef ")[0]
        self.assertIn("setTransferTimeout", body)


class NetworkRequestConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.saved = client.QNetworkRequest, client.QSslSocket
        client.QNetworkRequest = _NetworkRequest
        client.QSslSocket = _SslSocket

    def tearDown(self):
        client.QNetworkRequest, client.QSslSocket = self.saved

    def test_ssl_opt_out_is_applied_to_the_request(self):
        request = client.build_network_request("https://example.test", {"X-Test": "yes"}, False, timeout=7)
        self.assertEqual(request.timeout, 7000)
        self.assertEqual(request.headers[b"X-Test"], b"yes")
        self.assertEqual(request.redirect_policy, "same-origin")
        self.assertEqual(request.applied_ssl.peer_mode, "verify-none")

    def test_default_verification_does_not_weaken_ssl(self):
        request = client.build_network_request("https://example.test", {}, True, timeout=3)
        self.assertEqual(request.timeout, 3000)
        self.assertIsNone(request.applied_ssl)

    def test_missing_override_fails_closed_instead_of_using_global_ssl_opt_out(self):
        saved = client.get_verify_ssl
        client.get_verify_ssl = lambda *args: False
        try:
            request = client.build_network_request("https://other.example", {}, None, timeout=3)
        finally:
            client.get_verify_ssl = saved
        self.assertIsNone(request.applied_ssl)


class _SslConfiguration:
    def __init__(self):
        self.peer_mode = None

    def setPeerVerifyMode(self, mode):
        self.peer_mode = mode


class _NetworkRequest:
    class Attribute:
        RedirectPolicyAttribute = "redirect"

    class RedirectPolicy:
        SameOriginRedirectPolicy = "same-origin"

    def __init__(self, url):
        self.url = url
        self.headers = {}
        self.timeout = None
        self.configuration = _SslConfiguration()
        self.applied_ssl = None
        self.redirect_policy = None

    def setRawHeader(self, name, value):
        self.headers[name] = value

    def setTransferTimeout(self, timeout):
        self.timeout = timeout

    def setAttribute(self, attribute, value):
        if attribute == self.Attribute.RedirectPolicyAttribute:
            self.redirect_policy = value

    def sslConfiguration(self):
        return self.configuration

    def setSslConfiguration(self, configuration):
        self.applied_ssl = configuration


class _SslSocket:
    class PeerVerifyMode:
        VerifyNone = "verify-none"


class BlockingCancellationTest(unittest.TestCase):
    def setUp(self):
        self.saved = client.QgsBlockingNetworkRequest, client.build_network_request, client.QByteArray
        _BlockingRequest.seen_feedback = None
        client.QgsBlockingNetworkRequest = _BlockingRequest
        client.build_network_request = lambda *args: object()
        client.QByteArray = lambda value: value

    def tearDown(self):
        client.QgsBlockingNetworkRequest, client.build_network_request, client.QByteArray = self.saved

    def test_feedback_reaches_qgis_blocking_request_for_cancellation(self):
        feedback = object()
        self.assertEqual(client.post_json("https://example.test", {}, {}, feedback=feedback), {})
        self.assertIs(_BlockingRequest.seen_feedback, feedback)


class _BlockingReply:
    def content(self):
        return b"{}"

    def attribute(self, attribute):
        return 200


class _BlockingRequest:
    seen_feedback = None

    class ErrorCode:
        NoError = 0

    def post(self, request, payload, force_refresh, feedback):
        _BlockingRequest.seen_feedback = feedback
        return self.ErrorCode.NoError

    def reply(self):
        return _BlockingReply()

    def test_transport_failure_is_distinct_from_an_api_error(self):
        self.assertIn("raise ConnectionError(", self.SOURCE)
        self.assertIn("raise ApiResponseError(status, text)", self.SOURCE)

    def test_non_json_answer_is_reported_clearly(self):
        body = self.SOURCE.split("def _decoded(")[1].split("\ndef ")[0]
        self.assertIn("non-JSON", body)
        self.assertIn("not a JSON object", body)
