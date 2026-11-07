"""Order submission, confirmation and live-menu reconciliation."""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict

import wxapi

MEAL_TYPES = wxapi.MEAL_TYPES
MEAL_LABELS = wxapi.MEAL_LABELS


def _sorted_day_keys(data):
    return sorted(data.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)


def format_orderdata_from_pending_order(data):
    """Build the ``date~type~id~1~'`` payload for setOrder."""
    formatted_items = []
    for key in _sorted_day_keys(data):
        day_info = data[key]
        date_str = day_info.get("date")
        auto_orders = day_info.get("auto_order", {}) or {}
        for meal_key, meal_code in MEAL_TYPES:
            for item in auto_orders.get(meal_key, []) or []:
                if isinstance(item, dict) and item.get("id"):
                    formatted_items.append(
                        f"{date_str}~{meal_code}~{item['id']}~1~'"
                    )
    return ",".join(formatted_items)


def collect_intended_items(data):
    """Flatten a pending order into confirmable items."""
    items = []
    for key in _sorted_day_keys(data):
        day_info = data[key]
        date_str = day_info.get("date")
        auto_orders = day_info.get("auto_order", {}) or {}
        for meal_key, meal_code in MEAL_TYPES:
            for item in auto_orders.get(meal_key, []) or []:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                items.append(
                    {
                        "day": key,
                        "date": date_str,
                        "meal": meal_key,
                        "meal_code": meal_code,
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "price": item.get("price"),
                    }
                )
    return items


def _active_counts(records):
    counts = Counter()
    for record in records:
        if not wxapi.is_active_detail(record):
            continue
        meal_key = wxapi.detail_meal_key(record)
        name = record.get("DISHESNAME")
        date_str = record.get("ORDERDATE")
        if meal_key and name and date_str:
            counts[(date_str, meal_key, name)] += 1
    return counts


def _missing_items(intended, records):
    counts = _active_counts(records)
    missing = []
    for item in intended:
        key = (item["date"], item["meal"], item["name"])
        if counts[key] > 0:
            counts[key] -= 1
        else:
            missing.append(item)
    return missing


def _confirm_with_retry(authinfo, intended, starttime, endtime):
    failed = []
    for attempt in range(2):
        try:
            records = wxapi.get_order_details(authinfo, starttime, endtime)
            failed = _missing_items(intended, records)
        except Exception as exc:
            logging.warning("Order confirmation query failed: %s", exc)
            failed = intended
        if not failed or attempt == 1:
            return failed
        time.sleep(1.0)
    return failed


def _failed_payload(item, reason):
    return {
        "date": item.get("date"),
        "meal": item.get("meal"),
        "meal_label": MEAL_LABELS.get(item.get("meal"), item.get("meal")),
        "name": item.get("name"),
        "reason": reason,
    }


def submit_pending_order(user_data, data):
    """Submit all dishes in a pending order and verify them remotely.

    Returns ``(success, message, failed_items)``.  The WeChat session is
    unbound only after the confirmation query has run.
    """
    intended = collect_intended_items(data)
    if not intended:
        return True, "没有需要提交的菜品。", []

    formatted = format_orderdata_from_pending_order(data)
    starttime, endtime = wxapi.date_range_for([item["date"] for item in intended])

    try:
        with wxapi.wechat_session(user_data) as authinfo:
            response = wxapi.set_order(authinfo, formatted)
            try:
                payload = response.json()
            except ValueError:
                payload = None

            if response.status_code != 200 or not wxapi.response_is_success(payload):
                detail = response.text[:300]
                return False, f"订餐系统返回错误: HTTP {response.status_code} {detail}", []

            failed = _confirm_with_retry(authinfo, intended, starttime, endtime)
            failed_items = [_failed_payload(item, "not_confirmed") for item in failed]

            if failed_items:
                message = (
                    f"订单已提交，但 {len(failed_items)} 个菜品未在订餐系统中确认成功。"
                )
                return False, message, failed_items

            return True, "订单已提交并在订餐系统中确认成功。", []
    except Exception as exc:
        logging.exception("Order submission failed")
        return False, f"提交订单失败: {exc}", []


def _normalize_desired(meal_items, menu, allow_unknown_id=False):
    """Map desired items to real menu entries.

    Returns ``(normalized, invalid)`` where normalized contains one dict per
    serving with a real dish id and canonical name/price.
    """
    menu_by_id = {}
    menu_by_name = defaultdict(list)
    for entry in menu or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        if entry.get("ydflag"):
            continue
        menu_by_id[str(entry["id"])] = entry
        menu_by_name[entry.get("name")].append(entry)

    normalized = []
    invalid = []
    for item in meal_items or []:
        if not isinstance(item, dict):
            continue
        provided_id = str(item.get("id")) if item.get("id") is not None else ""
        name = item.get("name")

        match = menu_by_id.get(provided_id)
        if match is None and name:
            candidates = menu_by_name.get(name) or []
            if len(candidates) == 1:
                match = candidates[0]
            elif provided_id and allow_unknown_id:
                # Menu unavailable: trust the client-provided id.
                match = {"id": provided_id, "name": name, "price": item.get("price")}
            elif candidates:
                match = candidates[0]

        if match is None:
            invalid.append(
                {
                    "id": provided_id or None,
                    "name": name,
                    "reason": "not_in_menu",
                }
            )
            continue

        normalized.append(
            {
                "id": str(match.get("id")),
                "name": match.get("name") or name,
                "price": match.get("price", item.get("price")),
            }
        )
    return normalized, invalid


def _group_details_by_date_meal(records):
    grouped = defaultdict(lambda: defaultdict(list))
    for record in records:
        if not wxapi.is_active_detail(record):
            continue
        meal_key = wxapi.detail_meal_key(record)
        date_str = record.get("ORDERDATE")
        if not meal_key or not date_str:
            continue
        grouped[date_str][meal_key].append(record)
    return grouped


def apply_order_changes(user_data, desired_days):
    """Make the remote order match ``desired_days`` (cancel first, then order).

    ``desired_days`` is an iterable of
    ``{"date": ..., "breakfastorders": [...], "lunchorders": [...],
       "supperorders": [...]}``.
    """
    desired_days = [d for d in desired_days if d.get("date")]
    if not desired_days:
        return {
            "success": True,
            "message": "没有需要修改的日期。",
            "cancelled": [],
            "ordered": [],
            "failed_items": [],
        }

    dates = sorted({day["date"] for day in desired_days})
    starttime, endtime = wxapi.date_range_for(dates)

    cancelled = []
    ordered = []
    failed_items = []
    plan_failures = []
    invalid_items = []

    try:
        with wxapi.wechat_session(user_data) as authinfo:
            records = wxapi.get_order_details(authinfo, starttime, endtime)
            existing = _group_details_by_date_meal(records)

            # plan per date
            plans = []
            for day in desired_days:
                date_str = day["date"]
                menu_fetched = True
                try:
                    menu = wxapi.get_order_food_list(authinfo, date_str)
                except Exception as exc:
                    logging.warning("Failed to fetch menu for %s: %s", date_str, exc)
                    menu = {}
                    menu_fetched = False

                date_plan = {"date": date_str, "cancel": [], "orders": [], "abort": not menu_fetched}
                if not menu_fetched:
                    plan_failures.append(
                        {
                            "date": date_str,
                            "meal": None,
                            "meal_label": "",
                            "name": date_str,
                            "reason": "menu_unavailable",
                        }
                    )
                    plans.append(date_plan)
                    continue

                for meal_key, _meal_code in MEAL_TYPES:
                    desired, invalid = _normalize_desired(
                        day.get(meal_key, []),
                        menu.get(meal_key, []),
                        allow_unknown_id=False,
                    )
                    for bad in invalid:
                        invalid_items.append(
                            {
                                "date": date_str,
                                "meal": meal_key,
                                "meal_label": MEAL_LABELS.get(meal_key, meal_key),
                                "name": bad.get("name"),
                                "reason": bad.get("reason", "not_in_menu"),
                            }
                        )

                    desired_by_name = defaultdict(list)
                    for item in desired:
                        desired_by_name[item["name"]].append(item)

                    existing_records = existing.get(date_str, {}).get(meal_key, [])
                    keep_counts = Counter()
                    for record in existing_records:
                        name = record.get("DISHESNAME")
                        if keep_counts[name] < len(desired_by_name.get(name, [])):
                            keep_counts[name] += 1
                        else:
                            date_plan["cancel"].append(record)

                    for name, items in desired_by_name.items():
                        missing = max(0, len(items) - keep_counts[name])
                        for item in items[:missing]:
                            date_plan["orders"].append(
                                {
                                    "id": item["id"],
                                    "name": item["name"],
                                    "meal_key": meal_key,
                                    "meal_code": _meal_code,
                                }
                            )

                plans.append(date_plan)

            # 1) cancel extras first
            for plan in plans:
                if plan.get("abort"):
                    continue
                for record in plan.get("cancel", []):
                    detail_id = record.get("ID")
                    name = record.get("DISHESNAME")
                    meal_key = wxapi.detail_meal_key(record)
                    entry = {
                        "date": plan["date"],
                        "meal": meal_key,
                        "meal_label": MEAL_LABELS.get(meal_key, meal_key),
                        "name": name,
                        "detail_id": detail_id,
                    }
                    try:
                        payload = wxapi.cancel_order_detail(authinfo, detail_id)
                        entry["success"] = wxapi.response_is_success(payload)
                        entry["message"] = payload.get("message", "") if isinstance(payload, dict) else ""
                    except Exception as exc:
                        entry["success"] = False
                        entry["message"] = str(exc)
                    cancelled.append(entry)

            # 2) place new dishes, grouped by date
            for plan in plans:
                if plan.get("abort"):
                    continue
                formatted = []
                for item in plan.get("orders", []):
                    formatted.append(
                        f"{plan['date']}~{item['meal_code']}~{item['id']}~1~'"
                    )
                if not formatted:
                    continue
                try:
                    response = wxapi.set_order(authinfo, ",".join(formatted))
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = None
                    ok = response.status_code == 200 and wxapi.response_is_success(payload)
                    for item in plan.get("orders", []):
                        ordered.append(
                            {
                                "date": plan["date"],
                                "meal": item["meal_key"],
                                "meal_label": MEAL_LABELS.get(item["meal_key"], item["meal_key"]),
                                "name": item["name"],
                                "success": ok,
                                "message": "" if ok else response.text[:300],
                            }
                        )
                except Exception as exc:
                    for item in plan.get("orders", []):
                        ordered.append(
                            {
                                "date": plan["date"],
                                "meal": item["meal_key"],
                                "meal_label": MEAL_LABELS.get(item["meal_key"], item["meal_key"]),
                                "name": item["name"],
                                "success": False,
                                "message": str(exc),
                            }
                        )

            # 3) verify the desired final state
            desired_intended = []
            for plan in plans:
                if plan.get("abort"):
                    continue
                for item in plan.get("orders", []):
                    desired_intended.append(
                        {
                            "date": plan["date"],
                            "meal": item["meal_key"],
                            "name": item["name"],
                        }
                    )

            missing = _confirm_with_retry(
                authinfo, desired_intended, starttime, endtime
            )
            failed_items = [
                _failed_payload(item, "not_confirmed") for item in missing
            ]
            failed_items.extend(invalid_items)
            failed_items.extend(plan_failures)

            cancel_failed = [entry for entry in cancelled if not entry.get("success")]
            order_failed = [entry for entry in ordered if not entry.get("success")]
            success = not failed_items and not cancel_failed and not order_failed

            message = (
                f"已取消 {len(cancelled)} 项，提交 {len(ordered)} 项"
                f"，失败 {len(failed_items) + len(cancel_failed) + len(order_failed)} 项。"
            )
            return {
                "success": success,
                "message": message,
                "cancelled": cancelled,
                "ordered": ordered,
                "failed_items": failed_items,
            }
    except Exception as exc:
        logging.exception("Failed to apply order changes")
        return {
            "success": False,
            "message": f"修改订单失败: {exc}",
            "cancelled": cancelled,
            "ordered": ordered,
            "failed_items": failed_items + plan_failures,
        }
