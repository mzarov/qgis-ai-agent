import re

SKIPPED = "skipped"
CANCELLED = "cancelled"
CONNECTOR_OFF = "connector_off"
TIMEOUT = "timeout"
LAYER_AMBIGUOUS = "layer_ambiguous"
LAYER_NOT_FOUND = "layer_not_found"
FIELD_NOT_FOUND = "field_not_found"
BAD_EXPRESSION = "bad_expression"
NOT_SUPPORTED = "not_supported"
NO_RESULT = "no_result"
TOO_LARGE = "too_large"
NETWORK = "network"
QGIS_REFUSED = "qgis_refused"
BAD_ARGUMENTS = "bad_arguments"
ALGORITHM_FAILED = "algorithm_failed"
SNIPPET_FAILED = "snippet_failed"
OTHER = "other"
# The first match wins: a step skipped after a failure quotes nothing, a timeout is not any network failure.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (reason, re.compile(pattern))
    for reason, pattern in (
        (SKIPPED, r"not run because the earlier planned step"),
        (CANCELLED, r"the run was stopped|was cancelled|project changed while this plan"),
        (CONNECTOR_OFF, r"connector is turned off"),
        (TIMEOUT, r"timed out|timeout|ran past the|best-effort budget"),
        (LAYER_AMBIGUOUS, r"layer name .* is ambiguous"),
        (
            LAYER_NOT_FOUND,
            r"layer not found|layer id not found|planned (target layer|layer target)|no longer in the project",
        ),
        (FIELD_NOT_FOUND, r"field not found|has no field|fields that do not exist|no field named"),
        (
            BAD_EXPRESSION,
            r"could not (parse|evaluate) the expression|\(\) is not allowed|read-only select|the query failed",
        ),
        (
            NOT_SUPPORTED,
            r"is not a (vector|raster) layer|not a vector layer or table|is a web raster|editing mode|"
            r"read-only|without a qgis window|needs the qgis window",
        ),
        (
            NO_RESULT,
            r"nothing (matches|matched|found|is selected)|no (features?|scene|plugin|note) (match|found)|"
            r"produced no layer|has no value range|no longer exist",
        ),
        (
            NETWORK,
            r"could not fetch|did not answer|unreachable|is not json|\bhttp \d|service unavailable|"
            r"could not be resolved|redirect|connection|network addresses",
        ),
        (TOO_LARGE, r"more than \S+ features match|over the limit|too (large|big|many)|at most \d|exceeded"),
        (QGIS_REFUSED, r"qgis (refused|could not)|provider refused|could not commit"),
        (
            BAD_ARGUMENTS,
            r"must be|must run|must not|is required|is one of|unknown |is empty|has no parameter|needs a value|"
            r"does not accept|algorithm not found|does not exist|is not a number|is malformed",
        ),
    )
)
TOOL_FALLBACKS = {"run_processing": ALGORITHM_FAILED, "run_python": SNIPPET_FAILED}
# A snippet's error is the user's own text: only what the plugin itself says about the run is read from it.
RUN_REASONS = (SKIPPED, CANCELLED, TIMEOUT)
FOREIGN_TEXT_TOOLS = ("run_python",)
REASONS = (*dict.fromkeys(reason for reason, _ in PATTERNS), ALGORITHM_FAILED, SNIPPET_FAILED, OTHER)


def failure_reason(tool: str, error: str) -> str:
    lowered = str(error or "").lower()
    own_text = tool not in FOREIGN_TEXT_TOOLS
    for reason, pattern in PATTERNS:
        if (own_text or reason in RUN_REASONS) and pattern.search(lowered):
            return reason
    return TOOL_FALLBACKS.get(tool, OTHER)
