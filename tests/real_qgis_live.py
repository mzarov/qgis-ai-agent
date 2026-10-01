"""Live-model scenarios: the installed plugin, live QGIS, a real provider.

The scripted scenarios in `real_qgis_e2e` prove the plumbing; these prove
that a real model, given our prompts, skills and tool schemas, gets ordinary
requests right. Assertions are on outcomes only — the renderer, the label
field, the new layer, the number in the answer — never on the exact calls,
because a model is free to choose its own route.

Spending is capped three ways: a per-run token budget through the plugin's
own setting, a total for the whole suite after which the remaining scenarios
are skipped, and the CI job timeout. Usage lands in `live_usage.json` next to
the screenshots.

Configuration comes from the environment; without a key the module skips:

    LIVE_MODEL_URL      OpenAI-compatible base URL
    LIVE_MODEL          model id
    LIVE_MODEL_KEY      API key
    LIVE_TOTAL_TOKENS   suite-wide cap (default 1 500 000)
    LIVE_RUN_TOKENS     per-run cap (default 150 000)
    LIVE_ONLY           comma-separated scenario names to run, e.g. LiveBufferScenario

Run: `python3 tests/real_qgis_workflows.py real_qgis_live`.
"""

import json
import os
import unittest

from e2e_harness import ARTIFACTS, DISTRICT_POPULATIONS, PluginCase
from qgis.core import Qgis, QgsApplication, QgsProject

from ai_agent.core.settings import set_api_key, set_data_sharing_consent, set_token_budget

LIVE_URL = os.environ.get("LIVE_MODEL_URL", "").strip()
LIVE_MODEL = os.environ.get("LIVE_MODEL", "").strip()
LIVE_KEY = os.environ.get("LIVE_MODEL_KEY", "").strip()
TOTAL_TOKENS = int(os.environ.get("LIVE_TOTAL_TOKENS") or 1_500_000)
RUN_TOKENS = int(os.environ.get("LIVE_RUN_TOKENS") or 150_000)
LIVE_IDLE_TIMEOUT_S = 300
# Only unlocks the throwaway authentication database of the temporary CI profile.
PROFILE_MASTER_PASSWORD = "ai-agent-live-profile"  # pragma: allowlist secret
POPULATION_THRESHOLD = 50000
USAGE_FILE = "live_usage.json"
LOG_TAG = "AI Agent"
ONLY = [name.strip() for name in os.environ.get("LIVE_ONLY", "").split(",") if name.strip()]

USAGE: dict[str, int] = {}


def _spent() -> int:
    return sum(USAGE.values())


def _write_usage() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = {"model": LIVE_MODEL, "total_tokens": _spent(), "cap": TOTAL_TOKENS, "scenarios": USAGE}
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
        self._run_spent = 0
        USAGE[self.id()] = 0
        self.agent.usage_changed.connect(self._count)
        QgsApplication.messageLog().messageReceived.connect(self._logged)
        # Instrumentation only: record each run start, then hand over unchanged.
        start = self.agent.start
        self.agent.start = lambda *args, **kwargs: (self._run_started(kwargs), start(*args, **kwargs))[1]

    def tearDown(self) -> None:
        QgsApplication.messageLog().messageReceived.disconnect(self._logged)
        name = self.id().rsplit(".", 1)[-1]
        self.shot(f"{name}_end")
        _write_usage()
        transcript = {
            "runs": self.runs,
            "conversation": self.orchestrator.conversation.messages,
            "plugin_log": self.log,
        }
        (ARTIFACTS / f"{name}.json").write_text(json.dumps(transcript, indent=2, default=str), encoding="utf-8")
        print(
            f"  tokens: {USAGE.get(self.id(), 0)} (suite {_spent()} of {TOTAL_TOKENS}), runs: {self.runs}", flush=True
        )
        super().tearDown()

    def _run_started(self, options: dict) -> None:
        self.runs.append("verification" if options.get("verification") else "request")
        self._run_spent = 0

    def _count(self, spent: int) -> None:
        # The signal carries the running total of the current run.
        USAGE[self.id()] += max(0, spent - self._run_spent)
        self._run_spent = spent

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
