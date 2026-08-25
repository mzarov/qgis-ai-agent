import unittest

from qgis_ai_agent.core.llm.client import build_request, is_local, resolve_endpoint

REMOTE = "https://api.openai.com/v1"


def request(url, key):
    return build_request(
        url_override=url, key_override=key, auth_type_override="Bearer", model_override="демо"
    )


class LocalHostTest(unittest.TestCase):
    def test_loopback_names_are_local(self):
        for url in ("http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]/v1"):
            self.assertTrue(is_local(url), url)

    def test_port_does_not_confuse_it(self):
        self.assertTrue(is_local("http://localhost:8080/v1"))

    def test_mdns_names_are_local(self):
        self.assertTrue(is_local("http://ноутбук.local:11434/v1"))

    def test_public_hosts_are_not_local(self):
        for url in (REMOTE, "https://openrouter.ai/api/v1", "https://localhost.evil.com/v1"):
            self.assertFalse(is_local(url), url)


class BuildRequestTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
