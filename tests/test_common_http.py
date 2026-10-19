import json
import unittest
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlsplit

from ai_agent.qgis_tools.common import http
from ai_agent.qgis_tools.common.network import Answer

MB = 1024 * 1024


class Url:
    def __init__(self, url):
        self.url = url

    def host(self):
        return urlsplit(self.url).hostname or ""


class Request:
    KnownHeaders = SimpleNamespace(ContentTypeHeader="Content-Type")

    def __init__(self, url):
        self.url = url.url
        self.headers = {}

    def setRawHeader(self, name, value):
        self.headers[name.decode()] = value.decode()

    def setHeader(self, name, value):
        self.headers[name] = value


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.reply = Answer(body=b"{}")
        for name, value in (("send", self._send), ("QUrl", Url), ("QNetworkRequest", Request)):
            patcher = mock.patch.object(http, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _send(self, request, payload=None, feedback=None, on_progress=None):
        self.sent.append(("GET" if payload is None else "POST", request, payload, feedback))
        if on_progress is not None:
            on_progress(len(self.reply.body), len(self.reply.body))
        return self.reply

    def answer(self, payload=b"{}", failed=False, message=""):
        self.reply = Answer(body=payload, failed=failed, error=message)

    def test_json_comes_back_parsed_and_the_plugin_names_itself(self):
        self.answer(b'{"features": []}')
        self.assertEqual(http.get_json("https://stac.example/search"), {"features": []})
        method, request, _body, _feedback = self.sent[0]
        self.assertEqual((method, request.headers["User-Agent"]), ("GET", http.USER_AGENT.decode()))

    def test_a_post_sends_the_body_as_json(self):
        self.answer(b'{"ok": true}')
        self.assertEqual(http.post_json("https://stac.example/search", {"limit": 5}), {"ok": True})
        method, request, body, _feedback = self.sent[0]
        self.assertEqual((method, json.loads(body)), ("POST", {"limit": 5}))
        self.assertEqual(request.headers["Content-Type"], http.JSON_TYPE)

    def test_a_failed_request_names_the_host_and_the_reason(self):
        self.answer(failed=True, message="Connection refused")
        with self.assertRaisesRegex(ValueError, r"^stac\.example did not answer: Connection refused\. .*retry later"):
            http.get_json("https://stac.example/search")
        self.answer(failed=True)
        with self.assertRaisesRegex(ValueError, "did not answer: no answer"):
            http.get_bytes("https://tiles.example/a.tif", MB)

    def test_an_answer_that_is_not_json_is_refused_with_its_start(self):
        self.answer(b"<html>Service unavailable</html>")
        with self.assertRaisesRegex(ValueError, r"stac\.example sent something that is not JSON: b'<html>Service"):
            http.get_json("https://stac.example/search")
        self.answer(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "not JSON"):
            http.get_json("https://stac.example/search")

    def test_answers_past_the_limits_are_refused(self):
        self.answer(b" " * (http.MAX_JSON_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "too large to read"):
            http.get_json("https://stac.example/search")
        self.answer(b"x" * (3 * MB))
        with self.assertRaisesRegex(ValueError, r"tiles\.example sent 3 MB, over the limit of 2 MB"):
            http.get_bytes("https://tiles.example/a.tif", 2 * MB)
        self.assertEqual(http.get_bytes("https://tiles.example/a.tif", 3 * MB), b"x" * (3 * MB))

    def test_a_download_reports_its_bytes_to_the_feedback(self):
        self.answer(b"0123456789")
        feedback = mock.Mock()
        http.get_bytes("https://tiles.example/a.tif", MB, feedback)
        self.assertIs(self.sent[0][3], feedback)
        feedback.setProcessedCount.assert_called_with(10)
        feedback.setProgress.assert_called_with(100.0)


if __name__ == "__main__":
    unittest.main()
