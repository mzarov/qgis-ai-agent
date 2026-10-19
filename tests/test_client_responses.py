import unittest
from unittest import mock

from ai_agent.core.llm import client
from ai_agent.core.llm.client import ApiResponseError
from ai_agent.qgis_tools.common.network import Answer


class BlockingResponseTest(unittest.TestCase):
    def setUp(self):
        self.answer = Answer(status=200, body=b"{}")
        for patch in (
            mock.patch.object(client, "send", side_effect=lambda *args, **kwargs: self.answer),
            mock.patch.object(client, "build_network_request", return_value=object()),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def post(self):
        return client.post_json("https://example.test/v1/chat/completions", {}, {})

    def test_http_failures_preserve_status_and_body_despite_qgis_error_code(self):
        body = b'{"error":{"message":"tools are not supported"}}'
        for status in (400, 401, 403, 404, 408, 429, 500, 503):
            with self.subTest(status=status):
                self.answer = Answer(status=status, body=body, failed=True, error="Server replied")
                with self.assertRaises(ApiResponseError) as caught:
                    self.post()
                self.assertEqual(caught.exception.status_code, status)
                self.assertEqual(caught.exception.body, body.decode())

    def test_an_http_failure_carries_the_wait_the_server_asked_for(self):
        self.answer = Answer(status=429, body=b"{}", failed=True, headers={"retry-after": "12"})
        with self.assertRaises(ApiResponseError) as caught:
            self.post()
        self.assertEqual(caught.exception.retry_after, 12.0)

    def test_transport_failures_remain_connection_errors_without_http_failure(self):
        for status in (0, 200):
            with self.subTest(status=status):
                self.answer = Answer(status=status, failed=True, error="connection interrupted")
                with self.assertRaisesRegex(ConnectionError, "connection interrupted"):
                    self.post()

    def test_successful_json_is_returned(self):
        self.answer = Answer(status=200, body=b'{"answer":"ok"}')
        self.assertEqual(self.post(), {"answer": "ok"})

    def test_successful_http_with_non_json_has_a_response_error(self):
        self.answer = Answer(status=200, body=b"not json")
        with self.assertRaisesRegex(ApiResponseError, "non-JSON") as caught:
            self.post()
        self.assertEqual(caught.exception.status_code, 200)

    def test_a_key_in_a_non_json_body_stays_out_of_the_message(self):
        page = b"<html><body>proxy debug: Bearer sk-ant-FAKE0123456789 api_key=FAKEAPIKEY0123</body></html>"
        self.answer = Answer(status=200, body=page)
        with self.assertRaisesRegex(ApiResponseError, "non-JSON") as caught:
            self.post()
        for secret in ("sk-ant-FAKE0123456789", "FAKEAPIKEY0123"):
            self.assertNotIn(secret, str(caught.exception))
