from __future__ import annotations

import copy
import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT_DIR / "data")).resolve()
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", DATA_DIR / "config.yaml")).resolve()


DEFAULT_CONFIG = {
    "app": {
        "secret_key": "supersecretkey",
        "base_url": "https://wxdc_backend.berniehg.top",
        "port": 5008,
    },
    "cron": {
        "schedule": "0 16 * * 5",
    },
    "email": {
        "smtp_server": "smtp.163.com",
        "smtp_port": 25,
        "sender_email": "berniehuang2008@163.com",
        "password": "",
        "dkim": {
            "enabled": False,
            "selector": "default",
            "domain": "berniehg.top",
        },
    },
    "wechat": {
        "api_base_url": "http://wxdc.szsy.cn",
        "center_id": "9053",
        "open_id": "",
        "jsessionid": "",
        "bind_password": "",
        "default_user_no": "2241112",
        "default_token": "",
    },
    "llm": {
        "endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key": "",
        "model": "doubao-seed-2-0-lite-260215",
    },
    "paths": {
        "users_dir": "users",
        "pending_orders_dir": "pending_orders",
        "token_file": "token.txt",
        "req_file": "req.txt",
        "spec_conf_date_file": "spec_conf_date.txt",
        "dkim_private_key": "keys/dkim.private.key",
        "dkim_public_key": "keys/dkim.public.key",
        "logs_dir": "logs",
    },
}


def _merge_dicts(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dicts(base[key], value)
        else:
            base[key] = value
    return base


def load_config():
    config = copy.deepcopy(DEFAULT_CONFIG)
    if not CONFIG_PATH.exists() or yaml is None:
        return config

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    if isinstance(loaded, dict):
        _merge_dicts(config, loaded)
    return config


CONFIG = load_config()


def get_config(*keys, default=None):
    value = CONFIG
    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
        if value is None:
            return default
    return value


def resolve_data_path(value, default=None):
    raw = value if value not in (None, "") else default
    path = Path(raw)
    if not path.is_absolute():
        path = DATA_DIR / path
    return path


APP_SECRET_KEY = get_config("app", "secret_key", default=DEFAULT_CONFIG["app"]["secret_key"])
WEB_BASE_URL = get_config("app", "base_url", default=DEFAULT_CONFIG["app"]["base_url"])
APP_PORT = int(get_config("app", "port", default=DEFAULT_CONFIG["app"]["port"]))
CRON_SCHEDULE = get_config("cron", "schedule", default=DEFAULT_CONFIG["cron"]["schedule"])

SMTP_SERVER = get_config("email", "smtp_server", default=DEFAULT_CONFIG["email"]["smtp_server"])
SMTP_PORT = int(get_config("email", "smtp_port", default=DEFAULT_CONFIG["email"]["smtp_port"]))
SMTP_SENDER_EMAIL = get_config("email", "sender_email", default=DEFAULT_CONFIG["email"]["sender_email"])
SMTP_PASSWORD = get_config("email", "password", default=DEFAULT_CONFIG["email"]["password"])
DKIM_ENABLED = bool(get_config("email", "dkim", "enabled", default=DEFAULT_CONFIG["email"]["dkim"]["enabled"]))
DKIM_SELECTOR = get_config("email", "dkim", "selector", default=DEFAULT_CONFIG["email"]["dkim"]["selector"])
DKIM_DOMAIN = get_config("email", "dkim", "domain", default=DEFAULT_CONFIG["email"]["dkim"]["domain"])

API_BASE_URL = get_config("wechat", "api_base_url", default=DEFAULT_CONFIG["wechat"]["api_base_url"])
WECHAT_CENTER_ID = get_config("wechat", "center_id", default=DEFAULT_CONFIG["wechat"]["center_id"])
WECHAT_OPEN_ID = get_config("wechat", "open_id", default=DEFAULT_CONFIG["wechat"]["open_id"])
WECHAT_JSESSIONID = get_config("wechat", "jsessionid", default=DEFAULT_CONFIG["wechat"]["jsessionid"])
WECHAT_BIND_PASSWORD = get_config("wechat", "bind_password", default=DEFAULT_CONFIG["wechat"]["bind_password"])
WECHAT_DEFAULT_USER_NO = get_config("wechat", "default_user_no", default=DEFAULT_CONFIG["wechat"]["default_user_no"])
WECHAT_DEFAULT_TOKEN = get_config("wechat", "default_token", default=DEFAULT_CONFIG["wechat"]["default_token"])

LLM_ENDPOINT = get_config("llm", "endpoint", default=DEFAULT_CONFIG["llm"]["endpoint"])
LLM_API_KEY = get_config("llm", "api_key", default=DEFAULT_CONFIG["llm"]["api_key"])
LLM_MODEL = get_config("llm", "model", default=DEFAULT_CONFIG["llm"]["model"])

USERS_DIR = resolve_data_path(get_config("paths", "users_dir", default=DEFAULT_CONFIG["paths"]["users_dir"]), DEFAULT_CONFIG["paths"]["users_dir"])
PENDING_ORDERS_DIR = resolve_data_path(get_config("paths", "pending_orders_dir", default=DEFAULT_CONFIG["paths"]["pending_orders_dir"]), DEFAULT_CONFIG["paths"]["pending_orders_dir"])
TOKEN_FILE = resolve_data_path(get_config("paths", "token_file", default=DEFAULT_CONFIG["paths"]["token_file"]), DEFAULT_CONFIG["paths"]["token_file"])
REQ_FILE = resolve_data_path(get_config("paths", "req_file", default=DEFAULT_CONFIG["paths"]["req_file"]), DEFAULT_CONFIG["paths"]["req_file"])
SPEC_CONF_DATE_FILE = resolve_data_path(get_config("paths", "spec_conf_date_file", default=DEFAULT_CONFIG["paths"]["spec_conf_date_file"]), DEFAULT_CONFIG["paths"]["spec_conf_date_file"])
DKIM_PRIVATE_KEY_PATH = resolve_data_path(get_config("paths", "dkim_private_key", default=DEFAULT_CONFIG["paths"]["dkim_private_key"]), DEFAULT_CONFIG["paths"]["dkim_private_key"])
DKIM_PUBLIC_KEY_PATH = resolve_data_path(get_config("paths", "dkim_public_key", default=DEFAULT_CONFIG["paths"]["dkim_public_key"]), DEFAULT_CONFIG["paths"]["dkim_public_key"])
LOGS_DIR = resolve_data_path(get_config("paths", "logs_dir", default=DEFAULT_CONFIG["paths"]["logs_dir"]), DEFAULT_CONFIG["paths"]["logs_dir"])
