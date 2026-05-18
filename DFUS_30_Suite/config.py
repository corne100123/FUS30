import json
from pathlib import Path

APP_HOME = Path.home() / ".fus30_data"
APP_HOME.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_HOME / "fus30_config.json"
DEFAULT_DB_NAME = "fus30_operational.db"
DEFAULT_DB_PATH = APP_HOME / DEFAULT_DB_NAME


def get_default_db_path():
    return str(DEFAULT_DB_PATH)


def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open('r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
    return None


def save_config(biz_name, db_path=None):
    if db_path is None:
        db_path = get_default_db_path()
    db_path = str(db_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    config = {"business_name": biz_name, "db_path": db_path}
    with CONFIG_PATH.open('w', encoding='utf-8') as f:
        json.dump(config, f)
    return config


def _get_configured_db_path_for_scripts():
    """Helper to load db_path from the config file for external scripts."""
    config = load_config()
    if config and config.get("db_path"):
        return config["db_path"]
    return get_default_db_path()

SESSION_PATH = APP_HOME / "fus30_session.json"


def get_session_path():
    return SESSION_PATH


def load_session():
    if SESSION_PATH.exists():
        with SESSION_PATH.open('r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
    return {}


def save_session(session_data):
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SESSION_PATH.open('w', encoding='utf-8') as f:
        json.dump(session_data, f)
    return session_data


def clear_session():
    try:
        SESSION_PATH.unlink()
    except FileNotFoundError:
        pass
    return {}
