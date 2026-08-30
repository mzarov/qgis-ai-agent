from typing import Any

from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings

from ai_agent.i18n import tr

SETTINGS_PREFIX = "ai_agent"
CONFIG_INDEX = "auth_config"
CONFIG_METHOD = "Basic"
CONFIG_NAME = "AI Agent"
PASSWORD_KEY = "password"
NO_MANAGER = tr("QGIS did not provide its authentication database.")
DISABLED = tr("The QGIS authentication database is disabled for this session.")
LOCKED = tr("The QGIS master password was not entered, so the key stays locked.")
STORE_FAILED = tr(
    "Could not save the key to the QGIS authentication database: {reason}.\n\n"
    "The key is stored encrypted inside your QGIS profile and is unlocked by the QGIS master password."
)
STORE_UNAVAILABLE = tr("The QGIS authentication database is unavailable: {reason}. API keys cannot be loaded or saved.")

_error = ""


def read(scope: str) -> str:
    global _error
    config_id = _stored_id(scope)
    if not config_id:
        _error = ""
        return ""
    try:
        manager = _unlocked_manager()
        ok, config = manager.loadAuthenticationConfig(config_id, QgsAuthMethodConfig(), True)
    except RuntimeError as error:
        _error = str(error)
        return ""
    except Exception as error:
        _error = _reason(error)
        return ""
    _error = ""
    return config.config(PASSWORD_KEY, "") if ok else ""


def write(scope: str, secret: str) -> None:
    global _error
    try:
        manager = _unlocked_manager()
        config = _config_for(manager, scope, secret)
        ok, stored = manager.storeAuthenticationConfig(config, True)
    except RuntimeError as error:
        _error = str(error)
        raise RuntimeError(STORE_FAILED.format(reason=error)) from error
    except Exception as error:
        _error = _reason(error)
        raise RuntimeError(STORE_FAILED.format(reason=_reason(error))) from error
    if not ok:
        _error = STORE_FAILED.format(reason=NO_MANAGER)
        raise RuntimeError(_error)
    _error = ""
    _remember_id(scope, stored.id())


def remove(scope: str) -> None:
    global _error
    config_id = _stored_id(scope)
    _forget_id(scope)
    if not config_id:
        _error = ""
        return
    try:
        _unlocked_manager().removeAuthenticationConfig(config_id)
    except RuntimeError as error:
        _error = str(error)
        raise RuntimeError(STORE_FAILED.format(reason=error)) from error
    except Exception as error:
        _error = _reason(error)
        raise RuntimeError(STORE_FAILED.format(reason=_reason(error))) from error
    _error = ""


def last_error() -> str:
    return _error


def failure_message() -> str:
    return STORE_UNAVAILABLE.format(reason=_error or tr("unknown error"))


def _config_for(manager: Any, scope: str, secret: str) -> QgsAuthMethodConfig:
    config = QgsAuthMethodConfig()
    config_id = _stored_id(scope)
    if config_id:
        loaded, existing = manager.loadAuthenticationConfig(config_id, QgsAuthMethodConfig(), True)
        if loaded:
            config = existing
    config.setName(CONFIG_NAME)
    config.setMethod(CONFIG_METHOD)
    config.setConfig(PASSWORD_KEY, secret)
    return config


def _unlocked_manager() -> Any:
    manager = QgsApplication.authManager()
    if manager is None:
        raise RuntimeError(NO_MANAGER)
    if manager.isDisabled():
        raise RuntimeError(DISABLED)
    if not manager.masterPasswordIsSet() and not manager.setMasterPassword(True):
        raise RuntimeError(LOCKED)
    return manager


def _stored_id(scope: str) -> str:
    value = QgsSettings().value(f"{SETTINGS_PREFIX}/{CONFIG_INDEX}/{scope}")
    return value if isinstance(value, str) else ""


def _remember_id(scope: str, config_id: str) -> None:
    QgsSettings().setValue(f"{SETTINGS_PREFIX}/{CONFIG_INDEX}/{scope}", config_id)


def _forget_id(scope: str) -> None:
    QgsSettings().remove(f"{SETTINGS_PREFIX}/{CONFIG_INDEX}/{scope}")


def _reason(error: Exception) -> str:
    return str(error).strip() or type(error).__name__
