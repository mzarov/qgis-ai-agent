import unittest

from ai_agent.core.llm import extra_headers
from ai_agent.core.llm.client import build_request

REMOTE = "https://llm.api.cloud.yandex.net/v1"


class ParseTest(unittest.TestCase):
    def test_names_and_values_are_read_one_per_line(self):
        text = "x-folder-id: b1g8f3k2\n\n# a note\nOpenAI-Project: maps "
        self.assertEqual(extra_headers.parse(text), {"x-folder-id": "b1g8f3k2", "OpenAI-Project": "maps"})

    def test_a_line_that_is_not_a_header_names_its_number(self):
        with self.assertRaises(ValueError) as caught:
            extra_headers.parse("x-folder-id: b1g8\nno colon here")
        self.assertIn("2", str(caught.exception))

    def test_what_the_transport_sets_itself_is_refused(self):
        for name in ("Authorization", "content-type", "X-Api-Key", "Host", "anthropic-version"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                extra_headers.parse(f"{name}: anything")

    def test_a_name_that_looks_like_a_credential_is_refused(self):
        for name in ("X-Auth-Token", "X-Secret", "Session-Id", "X-Access-Key"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                extra_headers.parse(f"{name}: anything")

    def test_a_malformed_name_or_value_is_refused(self):
        for line in ("bad name: v", "x-a: " + "v" * (extra_headers.MAX_VALUE + 1), "x-a:\tv\tw"):
            with self.subTest(line=line[:20]), self.assertRaises(ValueError):
                extra_headers.parse(line)

    def test_a_hand_edited_file_only_loses_its_bad_lines(self):
        kept = extra_headers.lenient("Authorization: x\nx-folder-id: b1g8\nnonsense")
        self.assertEqual(kept, {"x-folder-id": "b1g8"})


class RequestTest(unittest.TestCase):
    def test_the_headers_ride_on_every_model_request_and_never_replace_the_transports(self):
        _endpoint, headers, _model = build_request(
            url_override=REMOTE,
            key_override="sentinel",
            auth_type_override="Bearer",
            model_override="yandexgpt",
            dialect_override="openai",
            extra_headers_override="x-folder-id: b1g8",
        )
        self.assertEqual(headers["x-folder-id"], "b1g8")
        self.assertEqual(headers["Authorization"], "Bearer sentinel")
        self.assertEqual(headers["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
