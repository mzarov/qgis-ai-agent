"""Budget kill switch: revoke the CI service account's model role once the budget is spent.

Triggered by the billing budget of the qgis-ai-agent folder. Lower thresholds
only log. Reversible: add the role back to the service account.
"""

import json
import os
import urllib.request

API = "https://resource-manager.api.cloud.yandex.net/resource-manager/v1/folders/{}:updateAccessBindings"


def _spent(message: dict) -> bool:
    try:
        amount = float(message["amount"])
        budget = float(message["budgeted_amount"])
    except (KeyError, TypeError, ValueError):
        return True  # An unreadable event fails safe: stop spending.
    return amount >= budget


def handler(event, context):
    messages = (event or {}).get("messages") or [{}]
    print(json.dumps({"event": event}))
    if not any(_spent(message) for message in messages):
        return {"revoked": False}
    body = {
        "accessBindingDeltas": [
            {
                "action": "REMOVE",
                "accessBinding": {
                    "roleId": os.environ["ROLE"],
                    "subject": {"id": os.environ["TARGET_SERVICE_ACCOUNT"], "type": "serviceAccount"},
                },
            }
        ]
    }
    request = urllib.request.Request(
        API.format(os.environ["FOLDER_ID"]),
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {context.token['access_token']}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = response.read().decode()
    print(json.dumps({"revoked": True, "operation": result[:500]}))
    return {"revoked": True}
