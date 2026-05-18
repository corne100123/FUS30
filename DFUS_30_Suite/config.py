import json
import shutil
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_APP_HOME = WORKSPACE_ROOT / ".fus30_data"
HOME_APP_HOME = Path.home() / ".fus30_data"

APP_HOME = WORKSPACE_APP_HOME
APP_HOME.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = APP_HOME / "fus30_config.json"
DEFAULT_DB_NAME = "fus30_operational.db"
DEFAULT_DB_PATH = APP_HOME / DEFAULT_DB_NAME
SESSION_PATH = APP_HOME / "fus30_session.json"
HOME_CONFIG_PATH = HOME_APP_HOME / "fus30_config.json"
HOME_DB_PATH = HOME_APP_HOME / DEFAULT_DB_NAME
HOME_SESSION_PATH = HOME_APP_HOME / "fus30_session.json"


def _migrate_home_data():
    """Move existing home-based configuration and database into the workspace."""
    if not HOME_APP_HOME.exists():
        return

    if HOME_CONFIG_PATH.exists() and not CONFIG_PATH.exists():
        try:
            CONFIG_PATH.write_bytes(HOME_CONFIG_PATH.read_bytes())
        except Exception:
            pass

    if HOME_DB_PATH.exists() and not DEFAULT_DB_PATH.exists():
        try:
            shutil.copy2(HOME_DB_PATH, DEFAULT_DB_PATH)
        except Exception:
            pass

    if HOME_SESSION_PATH.exists() and not SESSION_PATH.exists():
        try:
            SESSION_PATH.write_bytes(HOME_SESSION_PATH.read_bytes())
        except Exception:
            pass

    if CONFIG_PATH.exists():
        try:
            config = load_config()
            if config and config.get("db_path"):
                if config.get("db_path") == str(HOME_DB_PATH) and DEFAULT_DB_PATH.exists():
                    save_config(config.get("business_name", "FUS30"), DEFAULT_DB_PATH)
                elif config.get("db_path") != str(DEFAULT_DB_PATH) and not Path(config.get("db_path")).exists() and DEFAULT_DB_PATH.exists():
                    save_config(config.get("business_name", "FUS30"), DEFAULT_DB_PATH)
        except Exception:
            pass


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


_migrate_home_data()


def _get_configured_db_path_for_scripts():
    """Helper to load db_path from the config file for external scripts."""
    config = load_config()
    if config and config.get("db_path"):
        return config["db_path"]
    return get_default_db_path()


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
