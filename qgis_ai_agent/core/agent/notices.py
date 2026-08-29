LIMIT_REACHED_MESSAGE = (
    "This task ran longer than I am allowed to, so I stopped where I got to. Narrow the request or split it into steps."
)
INTERJECTION_HEADER = (
    "The user broke in while you were working and said this. Treat it as a "
    "correction to the task, not as a new request: adjust what you are doing, "
    "drop what no longer applies, and keep going.\n\n"
)
APPLY_NOW_WITHOUT_WRITES = (
    "There is nothing queued to apply, so there is nothing to wait for. Queue the write calls first, "
    "or keep going with read tools."
)
APPLY_DECLINED_MESSAGE = "The user declined to apply the changes, so the run stopped here."
BUDGET_REACHED_MESSAGE = (
    "This task hit the token budget set in the settings, so I stopped where I got to. "
    "Raise the budget or split the request into smaller steps."
)
SNAPSHOT_FAILED_MESSAGE = "Could not create the safety snapshot. No planned changes were applied."
SENSITIVE_DATA_BLOCKED = (
    "Privacy mode blocked this tool because its result can contain sensitive GIS data. "
    "The user can allow sensitive data for this endpoint in Settings."
)
