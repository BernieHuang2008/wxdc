"""Client helpers for the wxdc ordering-system APIs.

All functions take an ``AuthInfo`` object (see ``wxdc.AuthInfo``) carrying
``user_no``, ``token``, ``center_id`` and ``jsessionid``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime

import requests

from config_utils import API_BASE_URL, WECHAT_CENTER_ID
from wxdc_bind import BindWeChat, UnBindWeChat

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.189 "
    "Mobile Safari/537.36 XWEB/1500213 MMWEBSDK/20260902 MMWEBID/2946 "
    "REV/d4fc11eab0fcfc8b94e281c66f602239c082677c "
    "MicroMessenger/8.0.79.3200(0x28004F3B) WeChat/arm64 Weixin NetType/WIFI "
    "Language/zh_CN ABI/arm64"
)

MEAL_TYPES = (
    ("breakfastorders", 0),
    ("lunchorders", 1),
    ("supperorders", 2),
)
MEAL_LABELS = {
    "breakfastorders": "早餐",
    "lunchorders": "午餐",
    "supperorders": "晚餐",
}
ORDER_TYPE_TO_MEAL = {meal_code: meal_key for meal_key, meal_code in MEAL_TYPES}

# Remote order-detail records use ORDERSTATUS=3/4 for cancelled/refunded rows.
CANCELLED_ORDER_STATUSES = {"3", "4"}

DEFAULT_TIMEOUT = 20


class WxApiError(RuntimeError):
    pass


def _headers(authinfo, referer="http://wxdc.szsy.cn/order/orderSearch"):
    return {
        "Host": "wxdc.szsy.cn",
        "Content-Length": "0",
        "X-Access-Token": authinfo.token,
        "CENTER_ID": authinfo.center_id or WECHAT_CENTER_ID,
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Origin": "http://wxdc.szsy.cn",
        "X-Requested-With": "com.tencent.mm",
        "Referer": referer,
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en-CN;q=0.8,en-US;q=0.7,en;q=0.6",
        "Cookie": f"JSESSIONID={authinfo.jsessionid}",
    }


def _parse_json_response(response, action):
    if response.status_code != 200:
        raise WxApiError(f"{action} failed: HTTP {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise WxApiError(f"{action} returned invalid JSON: {response.text[:300]}") from exc


def get_order_list(authinfo, starttime, endtime, page=1, querytype=0, orderstatus=""):
    """Call getOrderList.

    querytype=0 returns order headers; querytype=1 returns dish-level rows.
    """
    url = f"{API_BASE_URL}/api/orderdata/getOrderList"
    params = {
        "userno": authinfo.user_no,
        "starttime": starttime,
        "endtime": endtime,
        "page": page,
        "querytype": querytype,
        "orderstatus": orderstatus or "",
    }
    response = requests.post(
        url,
        params=params,
        headers=_headers(authinfo),
        timeout=DEFAULT_TIMEOUT,
    )
    return _parse_json_response(response, "getOrderList")


def get_order_details(authinfo, starttime, endtime, orderstatus=""):
    """Return every dish-level record (querytype=1), following pagination."""
    records = []
    page = 1
    while True:
        payload = get_order_list(
            authinfo,
            starttime,
            endtime,
            page=page,
            querytype=1,
            orderstatus=orderstatus,
        )
        result = payload.get("result") or {}
        batch = result.get("records") or []
        records.extend(batch)

        pages = int(result.get("pages") or 1)
        if page >= pages or not batch:
            break
        page += 1
        if page > 100:
            logging.warning("getOrderDetails pagination exceeded 100 pages, stopping")
            break
    return records


def get_order_headers(authinfo, starttime, endtime, page=1, orderstatus=""):
    payload = get_order_list(
        authinfo,
        starttime,
        endtime,
        page=page,
        querytype=0,
        orderstatus=orderstatus,
    )
    return (payload.get("result") or {}).get("records") or []


def get_week_book_data(authinfo, startdate, enddate):
    """Call getWeekBookData and return its ``result`` list."""
    url = f"{API_BASE_URL}/api/orderdata/getWeekBookData"
    params = {
        "startdate": startdate,
        "enddate": enddate,
        "userno": authinfo.user_no,
    }
    response = requests.get(
        url,
        params=params,
        headers=_headers(authinfo, referer="http://wxdc.szsy.cn/order/dailyMenu"),
        timeout=DEFAULT_TIMEOUT,
    )
    payload = _parse_json_response(response, "getWeekBookData")
    return payload.get("result") or []


def get_order_food_list(authinfo, selectdate):
    """Call getOrderFoodList and return the per-meal menu dict."""
    url = f"{API_BASE_URL}/api/orderdata/getOrderFoodList"
    params = {
        "selectdate": selectdate,
        "userno": authinfo.user_no,
        "foodtype": "",
    }
    response = requests.post(
        url,
        params=params,
        headers=_headers(authinfo, referer="http://wxdc.szsy.cn/order/orderFood"),
        timeout=DEFAULT_TIMEOUT,
    )
    payload = _parse_json_response(response, "getOrderFoodList")
    return payload.get("result") or {}


def cancel_order_detail(authinfo, orderid):
    """Cancel one submitted dish. ``orderid`` is the detail ``ID`` row."""
    url = f"{API_BASE_URL}/api/orderdata/cancelOrderDetail"
    params = {
        "userno": authinfo.user_no,
        "orderid": orderid,
    }
    response = requests.post(
        url,
        params=params,
        headers=_headers(authinfo),
        timeout=DEFAULT_TIMEOUT,
    )
    return _parse_json_response(response, "cancelOrderDetail")


def set_order(authinfo, order_data):
    """Submit ``date~type~dishid~qty~'`` entries (comma-separated)."""
    url = f"{API_BASE_URL}/api/orderdata/setOrder"
    encoded_data = order_data.replace("'", "%27")
    params = {
        "data": encoded_data,
        "userno": authinfo.user_no,
    }
    response = requests.post(
        url,
        params=params,
        headers=_headers(authinfo, referer="http://wxdc.szsy.cn/order/shoppingCart"),
        timeout=DEFAULT_TIMEOUT,
    )
    return response


def response_is_success(payload):
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("success")) or str(payload.get("code")) == "200"


def parse_week_book_cell(value):
    """Parse ``name-qty-status@name-qty-status`` into dicts.

    Dish names may contain ``-`` so split from the right.
    """
    items = []
    if not value:
        return items
    for chunk in str(value).split("@"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.rsplit("-", 2)
        if len(parts) == 3:
            name, qty, status = parts
            try:
                qty = int(qty)
            except ValueError:
                qty = 1
        else:
            name, qty, status = chunk, 1, "0"
        items.append({"name": name.strip(), "qty": qty, "status": status})
    return items


def is_active_detail(record):
    return str(record.get("ORDERSTATUS")) not in CANCELLED_ORDER_STATUSES


def is_cancelled_detail(record):
    return str(record.get("ORDERSTATUS")) in CANCELLED_ORDER_STATUSES


def detail_meal_key(record):
    try:
        order_type = int(record.get("ORDERTYPE"))
    except (TypeError, ValueError):
        return None
    return ORDER_TYPE_TO_MEAL.get(order_type)


def detail_date(record):
    return record.get("ORDERDATE")


@contextmanager
def wechat_session(user_data, bind=True):
    """Bind, authenticate, then always unbind.

    ``AuthInfo`` is imported lazily to avoid a circular import with wxdc.py.
    """
    from wxdc import AuthInfo

    user_no = user_data.get("UserNO")
    jsessionid = user_data.get("jsessionid")

    if bind:
        try:
            BindWeChat(userno=user_no, pwd=user_data.get("pwd"))
        except Exception as exc:  # keep behaviour of existing place_order
            logging.warning("Failed to bind WeChat: %s", exc)

    authinfo = AuthInfo()
    authinfo.user_no = user_no
    authinfo.auth_by_openid(user_data.get("open_id"))
    authinfo.jsessionid = jsessionid
    if user_data.get("center_id"):
        authinfo.center_id = str(user_data.get("center_id"))

    try:
        if not authinfo.token:
            raise WxApiError("Authentication failed: empty token")
        yield authinfo
    finally:
        try:
            UnBindWeChat(
                userno=authinfo.user_no,
                jsessionid=authinfo.jsessionid,
                x_access_token=authinfo.token,
                center_id=authinfo.center_id,
            )
        except Exception as exc:
            logging.warning("Failed to unbind WeChat: %s", exc)


def date_range_for(dates):
    dates = [d for d in dates if d]
    if not dates:
        today = datetime.now().date().isoformat()
        return today, today
    return min(dates), max(dates)
