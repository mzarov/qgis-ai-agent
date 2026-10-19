import json
import os
import unittest

import token_ceilings
from e2e_harness import ARTIFACTS, DISTRICT_POPULATIONS, PluginCase
from qgis.core import Qgis, QgsApplication, QgsProject

from ai_agent.core.settings import set_api_key, set_data_sharing_consent, set_token_budget

LIVE_URL = os.environ.get("LIVE_MODEL_URL", "").strip()
LIVE_MODEL = os.environ.get("LIVE_MODEL", "").strip()
LIVE_KEY = os.environ.get("LIVE_MODEL_KEY", "").strip()
TOTAL_TOKENS = int(os.environ.get("LIVE_TOTAL_TOKENS") or 1_500_000)
RUN_TOKENS = int(os.environ.get("LIVE_RUN_TOKENS") or 150_000)
LIVE_IDLE_TIMEOUT_S = 300
PROFILE_MASTER_PASSWORD = "ai-agent-live-profile"  # pragma: allowlist secret
POPULATION_THRESHOLD = 50000
USAGE_FILE = "live_usage.json"
LOG_TAG = "AI Agent"
ONLY = [name.strip() for name in os.environ.get("LIVE_ONLY", "").split(",") if name.strip()]
REQUIRE_CEILINGS = os.environ.get("LIVE_REQUIRE_CEILINGS", "").strip() == "1"

CEILINGS = token_ceilings.load()

USAGE: dict[str, dict] = {}


def _spent() -> int:
    return sum(usage["total_tokens"] for usage in USAGE.values())


def _write_usage() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = {
        "kind": token_ceilings.LIVE_KIND,
        # The bare model id: a provider URI carries the cloud folder, and artifacts are public.
        "model": token_ceilings.model_name(LIVE_MODEL),
        "total_tokens": _spent(),
        "cap": TOTAL_TOKENS,
        "scenarios": USAGE,
    }
    (ARTIFACTS / USAGE_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")


@unittest.skipUnless(LIVE_URL and LIVE_MODEL and LIVE_KEY, "no live model configured")
class LiveCase(PluginCase):
    api_url = LIVE_URL
    model_name = LIVE_MODEL
    idle_timeout_s = LIVE_IDLE_TIMEOUT_S

    @classmethod
    def setUpClass(cls) -> None:
        manager = QgsApplication.authManager()
        if not manager.masterPasswordIsSet():
            manager.setMasterPassword(PROFILE_MASTER_PASSWORD, True)

    def setUp(self) -> None:
        if ONLY and not any(name in self.id() for name in ONLY):
            self.skipTest("not selected by LIVE_ONLY")
        if _spent() >= TOTAL_TOKENS:
            self.skipTest(f"suite token cap reached: {_spent()} of {TOTAL_TOKENS}")
        super().setUp()
        set_api_key(LIVE_KEY, LIVE_URL, "openai")
        set_data_sharing_consent(True, LIVE_URL)
        set_token_budget(RUN_TOKENS)
        self.runs: list[str] = []
        self.log: list[str] = []
        self.scenario = type(self).__name__
        self.usage = USAGE[self.scenario] = dict.fromkeys(token_ceilings.LIVE_METRICS, 0)
        self.usage["runs"] = []
        QgsApplication.messageLog().messageReceived.connect(self._logged)
        start = self.agent.start

        def counted_start(*args: object, **kwargs: object) -> bool:
            previous = dict(self.agent.usage)
            started = start(*args, **kwargs)
            if started:
                self._close_run(previous)
                self.runs.append("verification" if kwargs.get("verification") else "request")
            return started

        self.agent.start = counted_start

    def tearDown(self) -> None:
        QgsApplication.messageLog().messageReceived.disconnect(self._logged)
        self._close_run()
        ceiling = token_ceilings.live_ceiling(CEILINGS, LIVE_MODEL, self.scenario)
        over = token_ceilings.exceeded(self.usage, ceiling)
        self.usage["ceiling"] = ceiling
        self.usage["exceeded"] = over
        name = self.id().rsplit(".", 1)[-1]
        self.shot(f"{name}_end")
        _write_usage()
        transcript = {
            "runs": self.runs,
            "conversation": self.orchestrator.conversation.messages,
            "plugin_log": self.log,
        }
        (ARTIFACTS / f"{name}.json").write_text(json.dumps(transcript, indent=2, default=str), encoding="utf-8")
        totals = ", ".join(f"{metric} {self.usage[metric]}" for metric in token_ceilings.LIVE_METRICS)
        print(f"  {totals} (suite {_spent()} of {TOTAL_TOKENS}), runs: {self.runs}", flush=True)
        missing = f"no token ceiling for {self.scenario} on {token_ceilings.model_name(LIVE_MODEL)}"
        if not ceiling:
            print(f"  {missing}", flush=True)
        super().tearDown()
        if over:
            self.fail(f"{self.scenario} spent over its token ceiling: {'; '.join(over)}")
        if REQUIRE_CEILINGS and not ceiling:
            self.fail(f"{missing}; refresh tests/data/token_ceilings.json (docs/smoke_checklist.md)")

    def _close_run(self, usage: dict[str, int] | None = None) -> None:
        if len(self.usage["runs"]) == len(self.runs):
            return
        run = dict(self.agent.usage if usage is None else usage)
        run["total_tokens"] = run["prompt_tokens"] + run["completion_tokens"]
        for metric in token_ceilings.LIVE_METRICS:
            self.usage[metric] += run[metric]
        self.usage["runs"].append({"kind": self.runs[-1], **run})

    def _logged(self, message: str, tag: str, level: object) -> None:
        if tag == LOG_TAG:
            self.log.append(message)

    def ask_and_apply(self, text: str) -> None:
        self.ask(text)
        self.apply()
        self.assertIn("verification", self.runs, f"no verification run after Apply; runs: {self.runs}")


class LiveStyleScenario(LiveCase):
    def test_graduated_colours_by_a_field(self) -> None:
        self.ask_and_apply("Colour the districts layer by the pop2020 field in 5 graduated classes.")
        renderer = self.layer("districts").renderer()
        self.assertEqual(renderer.type(), "graduatedSymbol", self.last())
        self.assertEqual(renderer.classAttribute(), "pop2020")
        self.assertEqual(len(renderer.ranges()), 5)
        self.shot("live_style")


class LiveQuestionScenario(LiveCase):
    def test_a_counting_question_is_answered_from_the_data(self) -> None:
        expected = sum(1 for population in DISTRICT_POPULATIONS if population > POPULATION_THRESHOLD)
        self.ask(
            f"How many features in the districts layer have pop2020 greater than {POPULATION_THRESHOLD}? "
            "Reply with the number first."
        )
        self.assertFalse(self.agent.has_pending_writes, "a question must not queue changes")
        self.assertIn(str(expected), self.last())
        self.shot("live_question")


class LiveLabelScenario(LiveCase):
    def test_labels_use_the_requested_field(self) -> None:
        self.ask_and_apply("Label the districts layer with its name field.")
        layer = self.layer("districts")
        self.assertTrue(layer.labelsEnabled(), self.last())
        self.assertIn("name", layer.labeling().settings().fieldName)
        self.shot("live_labels")


class LiveBufferScenario(LiveCase):
    def test_a_metric_buffer_becomes_a_new_polygon_layer(self) -> None:
        before = set(QgsProject.instance().mapLayers())
        self.ask_and_apply("Create a 500 metre buffer around the Main rivers layer as a new layer.")
        added = [layer for key, layer in QgsProject.instance().mapLayers().items() if key not in before]
        polygons = [layer for layer in added if layer.geometryType() == Qgis.GeometryType.Polygon]
        self.assertTrue(polygons, f"no new polygon layer; the model said: {self.last()}")
        self.assertGreaterEqual(polygons[-1].featureCount(), 1)
        self.shot("live_buffer")
