from collections.abc import Callable
from typing import Any

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMapLayer,
    QgsProcessingAlgRunnerTask,
    QgsProcessingFeedback,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterVectorDestination,
    QgsProject,
    QgsTask,
)

from ai_agent.qgis_tools.common.background import Background
from ai_agent.qgis_tools.processing.deadline import TIMED_OUT

FAILED = "There were errors executing the algorithm{0}"
PROJECT_DESTINATIONS = (
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterRasterDestination,
)
LAYER_OUTPUTS = (
    QgsProcessingOutputVectorLayer,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputMapLayer,
)


def runs_in_background(algorithm: Any) -> bool:
    try:
        return not bool(algorithm.flags() & Qgis.ProcessingAlgorithmFlag.NoThreading)
    except AttributeError:
        return False


class ProcessingInBackground(Background):
    def __init__(
        self,
        algorithm_id: str,
        parameters: dict[str, Any],
        load_output: bool,
        finish: Callable[[dict[str, Any]], dict[str, Any]],
        seconds: float,
    ) -> None:
        super().__init__(seconds, TIMED_OUT)
        self._algorithm_id = algorithm_id
        self._parameters = dict(parameters)
        self._load_output = load_output
        self._finish = finish
        # Held until the task is over: QGIS keeps only references to them.
        self._algorithm: Any = None
        self._context: Any = None
        self._feedback = _ErrorsKept()
        self._task: Any = None

    def _launch(self) -> None:
        from processing.tools.dataobjects import createContext

        self._algorithm = QgsApplication.processingRegistry().createAlgorithmById(self._algorithm_id)
        if self._algorithm is None:
            raise ValueError(f"Algorithm not found: {self._algorithm_id}.")
        if self._load_output:
            _point_outputs_at_project(self._algorithm, self._parameters)
        self._context = createContext(self._feedback)
        ok, message = self._algorithm.checkParameterValues(self._parameters, self._context)
        if not ok:
            raise ValueError(f"Unable to execute algorithm: {message}")
        flags = QgsTask.Flag.CanCancel | QgsTask.Flag.Hidden
        task = QgsProcessingAlgRunnerTask(self._algorithm, self._parameters, self._context, self._feedback, flags)
        if task.isCanceled():
            # The task cancels itself when prepare() refuses the parameters; the feedback holds why.
            raise ValueError(FAILED.format(self._feedback.reason()))
        task.progressChanged.connect(self._report)
        task.executed.connect(self._executed)
        self._task = task
        QgsApplication.taskManager().addTask(task)

    def _halt(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _executed(self, ok: bool, results: Any) -> None:
        # The task manager deletes the task after this signal.
        self._task = None
        if not ok or self._stopped_because is not None:
            # A stop that came while the results waited in the queue loads nothing.
            self._end(RuntimeError(FAILED.format(self._feedback.reason())))
            return
        try:
            outputs = dict(results or {})
            if self._load_output:
                from processing.gui.Postprocessing import handleAlgorithmResults

                handleAlgorithmResults(self._algorithm, self._context, self._feedback)
            else:
                outputs = _take_result_layers(self._algorithm, self._context, outputs)
            self._end(self._finish(outputs))
        except Exception as err:
            self._end(err)


class _ErrorsKept(QgsProcessingFeedback):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def reportError(self, error: str, fatalError: bool = False) -> None:
        self.errors.append(str(error))
        super().reportError(error, fatalError)

    def reason(self) -> str:
        return (": " + "; ".join(self.errors)) if self.errors else "."


def _point_outputs_at_project(algorithm: Any, parameters: dict[str, Any]) -> None:
    for definition in algorithm.parameterDefinitions():
        name = definition.name()
        if name not in parameters or not isinstance(definition, PROJECT_DESTINATIONS):
            continue
        value = parameters[name]
        if isinstance(value, QgsProcessingOutputLayerDefinition):
            value.destinationProject = QgsProject.instance()
        else:
            parameters[name] = QgsProcessingOutputLayerDefinition(value, QgsProject.instance())


def _take_result_layers(algorithm: Any, context: Any, results: dict[str, Any]) -> dict[str, Any]:
    for output in algorithm.outputDefinitions():
        name = output.name()
        if name not in results:
            continue
        if isinstance(output, LAYER_OUTPUTS) and not isinstance(results[name], QgsMapLayer):
            layer = context.takeResultLayer(results[name])
            if layer:
                results[name] = layer
        elif isinstance(output, QgsProcessingOutputMultipleLayers) and results[name]:
            results[name] = [
                (context.takeResultLayer(item) or item) if not isinstance(item, QgsMapLayer) else item
                for item in results[name]
            ]
    return results
