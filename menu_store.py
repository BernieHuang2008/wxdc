"""Shared canteen-menu storage.

The canteen menu is identical for every user, so a pending order only stores
the dishes the user selected plus a ``menu_ref`` pointing at the shared week
file.  Shared menus live in ``data/menus/<monday>.json``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from config_utils import MENUS_DIR

MEAL_KEYS = ("breakfastorders", "lunchorders", "supperorders")


def ensure_menus_dir():
    os.makedirs(MENUS_DIR, exist_ok=True)
    return MENUS_DIR


def _menu_path(week_start):
    return os.path.join(MENUS_DIR, f"{week_start}.json")


def save_week_menus(week_start, days):
    """Persist ``{date: {meal: [...]}}`` for one week."""
    ensure_menus_dir()
    path = _menu_path(week_start)
    payload = {
        "week_start": str(week_start),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    return path


def load_week_menus(week_start):
    path = _menu_path(week_start)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload.get("days") or {}


def get_day_menu(week_start, date_str):
    return (load_week_menus(week_start) or {}).get(str(date_str))


def inject_day_menus(data):
    """Mutate a pending-order dict, adding ``menu`` from the shared store."""
    if not isinstance(data, dict):
        return False
    changed = False
    for day_info in data.values():
        if not isinstance(day_info, dict):
            continue
        week_start = day_info.get("menu_ref")
        if not week_start or day_info.get("menu"):
            continue
        menu = get_day_menu(week_start, day_info.get("date"))
        if menu:
            day_info["menu"] = menu
            changed = True
    return changed


def strip_day_menus(data):
    """Remove embedded menus that are already available through ``menu_ref``."""
    for day_info in data.values():
        if isinstance(day_info, dict) and day_info.get("menu_ref") and "menu" in day_info:
            del day_info["menu"]


def strip_menus_on_save(data):
    strip_day_menus(data)
    return data
