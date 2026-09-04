import unittest
from unittest import mock

from ai_agent.core.llm import client
from ai_agent.core.llm.client import ApiResponseError


class BlockingResponseTest(unittest.TestCase):
    def setUp(self):
        self.blocking = mock.Mock()
        self.blocking.ErrorCode.NoError = 0
        self.caller = self.blocking.return_value
        self.caller.errorMessage.return_value = "connection interrupted"
        self.caller.reply.return_value.content.return_value = b"{}"
        self.caller.reply.return_value.attribute.return_value = 200
        self.caller.post.return_value = 0
        for patch in (
            mock.patch.object(client, "QgsBlockingNetworkRequest", self.blocking),
            mock.patch.object(client, "build_network_request", return_value=object()),
            mock.patch.object(client, "QByteArray", side_effect=lambda value: value),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def post(self):
        return client.post_json("https://example.test/v1/chat/completions", {}, {})

    def test_http_failures_preserve_status_and_body_despite_qgis_error_code(self):
        body = b'{"error":{"message":"tools are not supported"}}'
        self.caller.post.return_value = 3
        self.caller.reply.return_value.content.return_value = body
        for status in (400, 401, 403, 404, 408, 429, 500, 503):
            with self.subTest(status=status):
                self.caller.reply.return_value.attribute.return_value = status
                with self.assertRaises(ApiResponseError) as caught:
                    self.post()
                self.assertEqual(caught.exception.status_code, status)
                self.assertEqual(caught.exception.body, body.decode())

    def test_transport_failures_remain_connection_errors_without_http_failure(self):
        self.caller.post.return_value = 1
        for status in (None, 0, 200):
            with self.subTest(status=status):
                self.caller.reply.return_value.attribute.return_value = status
                with self.assertRaisesRegex(ConnectionError, "connection interrupted"):
                    self.post()

    def test_successful_json_is_returned(self):
        self.caller.reply.return_value.content.return_value = b'{"answer":"ok"}'
        self.assertEqual(self.post(), {"answer": "ok"})

    def test_successful_http_with_non_json_has_a_response_error(self):
        self.caller.reply.return_value.content.return_value = b"not json"
        with self.assertRaisesRegex(ApiResponseError, "non-JSON") as caught:
            self.post()
        self.assertEqual(caught.exception.status_code, 200)
