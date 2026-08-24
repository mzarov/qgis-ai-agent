from qgis_ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_model,
    get_verify_ssl,
)

REQUESTS_INSTALL_MSG = (
    "Для запросов к API нужна библиотека requests. "
    "Установите её в Python QGIS. См. документацию плагина (раздел «Зависимости»)."
)


def chat(
    messages,
    timeout=60,
    url_override=None,
    model_override=None,
    key_override=None,
    auth_type_override=None,
    verify_override=None,
    stream=False,
    on_chunk=None,
):
    """
    Отправляет запрос в OpenAI-совместимый API.
    При stream=True и переданном on_chunk(content) вызывает on_chunk для каждого фрагмента ответа.
    """
    try:
        import json
        import requests
    except ImportError:
        raise RuntimeError(REQUESTS_INSTALL_MSG)

    url = (url_override or get_api_url() or "").strip().rstrip("/")
    if not url:
        raise ValueError("Не задан URL API. Укажите его в Настройках.")
    endpoint = f"{url}/chat/completions"
    key = (key_override if key_override is not None else get_api_key()) or ""
    key = key.strip()
    if not key:
        raise ValueError("Не задан API-ключ. Укажите его в Настройках.")

    model = (model_override if model_override is not None else get_model()) or ""
    auth_type = auth_type_override if auth_type_override is not None else get_auth_type()
    auth_header = f"{auth_type} {key}" if auth_type else f"Bearer {key}"
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "stream": bool(stream)}
    if verify_override is not None:
        verify_ssl = bool(verify_override)
    else:
        verify_ssl = get_verify_ssl()

    if stream and on_chunk:
        resp = requests.post(
            endpoint,
            json=body,
            headers=headers,
            timeout=timeout,
            verify=verify_ssl,
            stream=True,
        )
        resp.raise_for_status()
        full_content = []
        raw_lines = []
        for line in resp.iter_lines(decode_unicode=True):
            if line is not None:
                raw_lines.append(line)
            if not line or not line.strip():
                continue
            if line.strip() == "data: [DONE]":
                continue
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:].strip())
                    for choice in data.get("choices") or []:
                        delta = choice.get("delta") or {}
                        part = delta.get("content") or ""
                        if part:
                            full_content.append(part)
                            on_chunk(part)
                except json.JSONDecodeError:
                    pass
        result = "".join(full_content).strip()
        if not result and raw_lines:
            full_text = "\n".join(raw_lines).strip()
            if full_text.startswith("{"):
                try:
                    data = json.loads(full_text)
                    choices = data.get("choices") or []
                    if choices:
                        msg = choices[0].get("message") or {}
                        result = (msg.get("content") or "").strip()
                        if result:
                            on_chunk(result)
                except json.JSONDecodeError:
                    pass
        return result

    resp = requests.post(
        endpoint,
        json=body,
        headers=headers,
        timeout=timeout,
        verify=verify_ssl,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Пустой ответ API.")
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()
