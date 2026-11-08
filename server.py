import re
from collections import Counter
from html import escape

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
import os
import json
from datetime import datetime, timedelta
import register
import menu_store
import order_service
import wxapi
from config_utils import APP_PORT, APP_SECRET_KEY, PENDING_ORDERS_DIR, REQ_FILE, SPEC_CONF_DATE_FILE, TOKEN_FILE, USERS_DIR

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY  # Needed for flash messages


def check_perm(filename=None):
    """
    if the user (and its auth token) in 'request' environment
    is authorized to access the given filename, return the user_no if have.
    """
    if filename is not None:
        validation = re.fullmatch(r'order_(\d{7})_\d{4}-\d{2}-\d{2}\.json', filename)  # Basic validation
        if validation is None:
            # TODO security alert
            return False

        if validation.group(1) != request.cookies.get('user_no'):
            # TODO security alert
            return False

    # TODO: More checks instead of only checking cookie.

    return request.cookies.get('user_no')


PUBLIC_ENDPOINTS = {
    'index',
    'help_page',
    'set_user_no',
    'register_page',
    'api_register',
    'static',
}


@app.before_request
def enforce_auth():
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not check_perm():
        return "Unauthorized: 请先通过微信激活链接登录。", 403
    return None


def get_all_users():
    users = []
    if os.path.exists(USERS_DIR):
        for filename in os.listdir(USERS_DIR):
            if filename.endswith(".json"):
                users.append(filename[:-5])  # Remove .json extension to get user_no
    return users

def ensure_pending_orders_dir():
    if not os.path.exists(PENDING_ORDERS_DIR):
        os.makedirs(PENDING_ORDERS_DIR)

ensure_pending_orders_dir()

ORDER_DATE_MEAL_ORDER = ("b", "l", "s")


def get_next_order_monday():
    today = datetime.now().date()
    return today + timedelta(days=(7 - today.weekday()))


def normalize_meal_string(meals):
    if not isinstance(meals, str):
        return ""
    normalized = []
    for meal in ORDER_DATE_MEAL_ORDER:
        if meal in meals and meal not in normalized:
            normalized.append(meal)
    return "".join(normalized)


def load_user_data(user_no):
    user_file = os.path.join(USERS_DIR, f"{user_no}.json")
    if not os.path.exists(user_file):
        return None, user_file

    with open(user_file, "r", encoding="utf-8") as f:
        user_data = json.load(f)
    return user_data, user_file


def save_user_data(user_file, user_data):
    with open(user_file, "w", encoding="utf-8") as f:
        json.dump(user_data, f, ensure_ascii=False, indent=4)


def format_orderdata_from_pending_order(data):
    return order_service.format_orderdata_from_pending_order(data)


def save_pending_order_file(filepath, data):
    """Persist a pending order without embedding shared menus."""
    menu_store.strip_day_menus(data)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    menu_store.inject_day_menus(data)


def annotate_failed_items(data, failed_items):
    """Store known submission failures so the refresh view can mark them red."""
    grouped = {}
    for item in failed_items or []:
        if not isinstance(item, dict):
            continue
        date_str = item.get("date")
        if not date_str:
            continue
        grouped.setdefault(date_str, []).append(item)

    for day_info in data.values():
        if not isinstance(day_info, dict):
            continue
        day_info.pop("failed_items", None)
        items = grouped.get(day_info.get("date"))
        if items:
            day_info["failed_items"] = [
                {
                    "meal": item.get("meal"),
                    "meal_label": item.get("meal_label"),
                    "name": item.get("name"),
                    "reason": item.get("reason"),
                }
                for item in items
            ]

def reconcile_auto_order(data):
    """Repair auto_order ids that no longer match the dish name in the menu.

    Older pending orders could be generated with a broken fake-id mapping, so
    an auto_order entry may carry the name of one dish but the id of another.
    Match such entries back to the menu by name (and price) so that the
    preview table, the edit page and the submitted order all agree.
    """
    changed = False
    for day_info in data.values():
        if not isinstance(day_info, dict):
            continue
        menu = day_info.get("menu") or {}
        auto_order = day_info.get("auto_order") or {}
        for meal in ("breakfastorders", "lunchorders", "supperorders"):
            menu_items = [m for m in (menu.get(meal) or []) if isinstance(m, dict)]
            orders = auto_order.get(meal)
            if not isinstance(orders, list):
                continue
            for order in orders:
                if not isinstance(order, dict) or "id" not in order:
                    continue
                current = next((m for m in menu_items if m.get("id") == order["id"]), None)
                if current is not None and current.get("name") == order.get("name"):
                    continue

                candidates = [m for m in menu_items if m.get("name") == order.get("name")]
                if not candidates:
                    continue
                match = None
                try:
                    order_price = float(order.get("price"))
                    for candidate in candidates:
                        try:
                            if float(candidate.get("price")) == order_price:
                                match = candidate
                                break
                        except (TypeError, ValueError):
                            continue
                except (TypeError, ValueError):
                    pass
                if match is None and len(candidates) == 1:
                    match = candidates[0]
                if match is not None and match.get("id") != order["id"]:
                    order["id"] = match.get("id")
                    changed = True
    return changed


# 删除不再需要的内存字典和内部接口

@app.route('/latest-orders')
def latest_orders():
    user_no = check_perm()
    if not user_no:
        return "未登录，请点击微信中的激活链接以验证身份。", 403
    
    ensure_pending_orders_dir()
    files = [f for f in os.listdir(PENDING_ORDERS_DIR) if f.endswith('.json')]
    if user_no != "admin_wxdc":
        files = [f for f in files if f"_{user_no}_" in f]
    
    if not files:
        return "Not found: 当前暂未为您生成订餐文件。", 404
        
    files.sort(reverse=True)
    return redirect(url_for('view_order', filename=files[0]))

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/help')
def help_page():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'USER_MANUAL.html')


@app.route('/set_user_no')
def set_user_no():
    token = request.args.get('token')
    if not token:
        return "Please provide a token parameter, e.g., ?token=xxx", 400
    
    user_no = None
    if os.path.exists(TOKEN_FILE):
        lines = []
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        remaining_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',', 1)
            if len(parts) == 2 and parts[0] == token:
                user_no = parts[1]
                # 找到匹配的 token，不将其加回 remaining_lines，实现一次性消费
            else:
                remaining_lines.append(line)
                
        # 写回未使用的 token
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(remaining_lines) + ("\n" if remaining_lines else ""))
            
    if not user_no:
        return "Token 无效或已过期（每个激活链接只能使用一次）。", 400
    
    if hasattr(register, 'reg_email_pending_list') and user_no in register.reg_email_pending_list:
        register.register(user_no)
    
    response = redirect("/")
    # Set cookie to expire in 100 years
    response.set_cookie('user_no', user_no, max_age=60*60*24*365*100)
    return response

@app.route('/pending_orders')
def list_pending_orders():
    user_no = check_perm()
    if not user_no:
        return "Unauthorized: Please set your user_no first.", 403

    ensure_pending_orders_dir()
    files = [f for f in os.listdir(PENDING_ORDERS_DIR) if f.endswith('.json')]
    if user_no and user_no != "admin_wxdc":
        # Files are named like order_2241112_2026-03-23.json
        files = [f for f in files if f"_{user_no}_" in f]
    elif not user_no:
        # If no explicit admin cookie and no user cookie, maybe show nothing or prompt to set
        # Since prompt said "只做身份识别", if no user_no, let's show an empty list or redirect?
        # Let's just show an empty list if no cookie is set. Or prompt them.
        files = []
    
    files.sort(reverse=True)
    return render_template('list_pending_orders.html', files=files)

@app.route('/pending_orders/<filename>', methods=['GET'])
def view_order(filename):
    if not check_perm(filename):
        return "Unauthorized: You can only view your own orders.", 403

    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return "Order file not found.", 404
    
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return "Error decoding JSON file.", 500

    menu_store.inject_day_menus(data)
    if reconcile_auto_order(data):
        save_pending_order_file(filepath, data)

    return render_template('view_order.html', filename=filename, data=data)


@app.route('/pending_orders/<filename>/update', methods=['POST'])
def update_order(filename):
    if not check_perm(filename):
        return "Unauthorized: You can only update your own orders.", 403

    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File not found'}), 404
        
    try:
        updated_data = request.json
        if not isinstance(updated_data, dict):
            return jsonify({'success': False, 'message': 'Invalid order data'}), 400
        menu_store.strip_day_menus(updated_data)
        for day_info in updated_data.values():
            if isinstance(day_info, dict):
                day_info.pop('failed_items', None)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(updated_data, f, ensure_ascii=False, indent=4)
        return jsonify({'success': True, 'message': 'Order updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/pending_orders/<filename>/status', methods=['GET'])
def pending_order_status(filename):
    """Query the ordering system and return per-dish status for a pending order."""
    user_no = check_perm(filename)
    if not user_no:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File not found'}), 404

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500

    dates = [
        day_info.get('date')
        for day_info in data.values()
        if isinstance(day_info, dict) and day_info.get('date')
    ]
    if not dates:
        return jsonify({'success': True, 'status': {}})

    user_data, _ = load_user_data(user_no)
    if user_data is None:
        return jsonify({'success': False, 'message': 'User configuration not found'}), 404

    try:
        with wxapi.wechat_session(user_data) as authinfo:
            starttime, endtime = wxapi.date_range_for(dates)
            records = wxapi.get_order_details(authinfo, starttime, endtime)
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500

    active_counts = Counter()
    cancelled_counts = Counter()
    stored_failed = Counter()
    for day_info in data.values():
        if not isinstance(day_info, dict):
            continue
        date_str = day_info.get('date')
        for item in day_info.get('failed_items') or []:
            if isinstance(item, dict):
                stored_failed[(date_str, item.get('meal'), item.get('name'))] += 1

    for record in records:
        meal_key = wxapi.detail_meal_key(record)
        date_str = record.get('ORDERDATE')
        name = record.get('DISHESNAME')
        if not meal_key or not date_str or not name:
            continue
        key = (date_str, meal_key, name)
        if wxapi.is_active_detail(record):
            active_counts[key] += 1
        else:
            cancelled_counts[key] += 1

    statuses = {}
    for day_key, day_info in data.items():
        if not isinstance(day_info, dict):
            continue
        date_str = day_info.get('date')
        auto_order = day_info.get('auto_order') or {}
        day_status = {}
        for meal_key, _meal_code in wxapi.MEAL_TYPES:
            item_statuses = []
            for item in auto_order.get(meal_key, []) or []:
                name = item.get('name') if isinstance(item, dict) else None
                key = (date_str, meal_key, name)
                if active_counts[key] > 0:
                    active_counts[key] -= 1
                    item_statuses.append('ordered')
                elif stored_failed[key] > 0:
                    stored_failed[key] -= 1
                    item_statuses.append('failed')
                elif cancelled_counts[key] > 0:
                    cancelled_counts[key] -= 1
                    item_statuses.append('failed')
                else:
                    item_statuses.append('pending')
            day_status[meal_key] = item_statuses
        statuses[day_key] = day_status

    return jsonify({'success': True, 'status': statuses})


@app.route('/submit_order/<filename>', methods=['POST'])
def submit_order(filename):
    user_no = check_perm(filename)
    if not user_no:
        return "Unauthorized: You can only submit your own orders.", 403

    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File not found'}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            order_data_json = json.load(f)

        menu_store.inject_day_menus(order_data_json)
        if reconcile_auto_order(order_data_json):
            save_pending_order_file(filepath, order_data_json)

        user_data, _ = load_user_data(user_no)
        if user_data is None:
            return jsonify({'success': False, 'message': 'User configuration not found'}), 404

        success, message, failed_items = order_service.submit_pending_order(
            user_data, order_data_json
        )

        if success and not failed_items:
             # Remove the pending order file on success
             try:
                 os.remove(filepath)
                 message += " pending 订单已移除"
             except Exception as del_err:
                 message += f" (But failed to delete file: {del_err})"
                 
             return jsonify({'success': True, 'message': message, 'failed_items': []})
        else:
             if failed_items:
                 annotate_failed_items(order_data_json, failed_items)
                 save_pending_order_file(filepath, order_data_json)
             return jsonify({
                 'success': False,
                 'message': message,
                 'failed_items': failed_items,
             }), 500
             
    except Exception as e:
        return jsonify({'success': False, 'message': f"Unexpected error: {str(e)}"}), 500


@app.route('/submit_order_from_email/<filename>', methods=['GET'])
def submit_order_from_email(filename):
    user_no = check_perm(filename)
    if not user_no:
        return "Unauthorized: You can only submit your own orders.", 403

    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return "Order file not found.", 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
             order_data_json = json.load(f)

        menu_store.inject_day_menus(order_data_json)
        if reconcile_auto_order(order_data_json):
            save_pending_order_file(filepath, order_data_json)

        user_data, _ = load_user_data(user_no)
        if user_data is None:
            return "User configuration not found.", 404

        success, message, failed_items = order_service.submit_pending_order(
            user_data, order_data_json
        )

        if success and not failed_items:
            # Remove the pending order file on success
            try:
                os.remove(filepath)
            except Exception as del_err:
                print(f"Failed to delete file {filepath}: {del_err}")

            color = "green"
            title = "Order Submitted Successfully!"
            msg_body = "We have successfully processed your order request. The pending order file has been removed."
        else:
            if failed_items:
                annotate_failed_items(order_data_json, failed_items)
                save_pending_order_file(filepath, order_data_json)
            color = "red"
            title = "Order Submission Failed"
            msg_body = f"There was an error processing your order: {message}"

        failed_html = ""
        if failed_items:
            rows = "".join(
                f"<li>{escape(str(item.get('date', '')))} "
                f"{escape(str(item.get('meal_label', '')))} - "
                f"{escape(str(item.get('name', '')))}</li>"
                for item in failed_items
            )
            failed_html = f"<p>以下菜品未成功提交：</p><ul>{rows}</ul>"

        return f"""
        <html>
            <head><title>Order Status</title></head>
            <body style="text-align: center; padding-top: 50px; font-family: sans-serif;">
                <h1 style="color: {color};">{title}</h1>
                <p>{escape(msg_body)}</p>
                {failed_html}
                <p><a href="/pending_orders">View all pending orders</a></p>
                <br>
                <div style="color: #ccc; font-size: small;">Debug info: {escape(filename)}</div>
            </body>
        </html>
        """
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route('/config/dates', methods=['GET'])
def config_dates():
    configs = []
    user_no = check_perm()
    if not user_no:
        return "Unauthorized: You can only submit your own orders.", 403

    user_data, _ = load_user_data(user_no)
    if user_data is not None:
        spec_conf_date_content = user_data.get('spec_conf_date', '')
        lines = spec_conf_date_content.split('\n') if spec_conf_date_content else []
        today = datetime.now().date()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                parts = line.split(" ", 1)
                if len(parts) != 2: continue

                spec_date_str = parts[0]
                meals = parts[1].split()

                spec_date = datetime.strptime(spec_date_str, "%Y-%m-%d").date()

                if spec_date >= today:
                    configs.append({
                        "date": spec_date_str,
                        "meals": meals
                    })
            except ValueError:
                continue

    # Sort by date
    configs.sort(key=lambda x: x['date'])
    order_date = {}
    auto_submit = False
    if user_data is not None:
        if isinstance(user_data.get('order_date', {}), dict):
            order_date = user_data.get('order_date', {})
        auto_submit = bool(user_data.get('auto_submit', False))
    return render_template(
        'config_dates.html',
        configs=configs,
        order_date=order_date,
        auto_submit=auto_submit
    )


@app.route('/api/config/order_date', methods=['POST'])
def api_config_order_date():
    user_no = check_perm()
    if not user_no:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    payload = request.get_json(silent=True) or {}
    week = payload.get('week')
    selected_days = payload.get('order_date')

    if week not in ('current', 'next'):
        return jsonify({'success': False, 'message': 'Invalid week selector.'}), 400
    if not isinstance(selected_days, dict):
        return jsonify({'success': False, 'message': 'order_date must be an object.'}), 400

    user_data, user_file = load_user_data(user_no)
    if user_data is None:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    existing = user_data.get('order_date')
    if not isinstance(existing, dict):
        existing = {}

    start_key = 1 if week == 'current' else 8
    for day_offset in range(7):
        day_key = str(start_key + day_offset)
        meals = str(selected_days.get(str(day_offset+1), ""))
        meals = "".join(m for m in "bls" if m in meals)
        if meals:
            existing[day_key] = meals
        else:
            existing.pop(day_key, None)

    user_data['order_date'] = existing
    save_user_data(user_file, user_data)

    return jsonify({
        'success': True,
        'message': '订餐时间已保存。',
        'order_date': user_data['order_date'],
    })


@app.route('/api/config/auto_submit', methods=['POST'])
def api_config_auto_submit():
    user_no = check_perm()
    if not user_no:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get('enabled', False))

    user_data, user_file = load_user_data(user_no)
    if user_data is None:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    user_data['auto_submit'] = enabled
    save_user_data(user_file, user_data)
    return jsonify({
        'success': True,
        'message': '自动提交已' + ('开启。' if enabled else '关闭。'),
        'auto_submit': enabled,
    })

@app.route('/config/dates/add', methods=['POST'])
def add_date():
    user_no = check_perm()
    if not user_no: return "Unauthorized: You can only submit your own orders.", 403

    date_str = request.form.get('date')
    meals = request.form.getlist('meals') # breakfast, lunch, supper

    if not date_str or not meals:
        return "Please select a date and at least one meal.", 400

    meals_str = " ".join(meals)
    new_line = f"{date_str} {meals_str}"

    user_data, user_file = load_user_data(user_no)
    if user_data is None: return "User not found.", 404

    spec_conf_date_content = user_data.get('spec_conf_date', '')
    all_lines = [l.strip() for l in spec_conf_date_content.split('\n') if l.strip()]

    # Remove existing config for this date
    all_lines = [l for l in all_lines if not l.startswith(date_str + " ")]      
    all_lines.append(new_line.strip())
    all_lines.sort() # Keep file sorted

    user_data['spec_conf_date'] = "\n".join(all_lines)
    save_user_data(user_file, user_data)

    return redirect(url_for('config_dates'))

@app.route('/config/dates/delete', methods=['POST'])
def delete_date():
    user_no = check_perm()
    if not user_no: return "Unauthorized: You can only submit your own orders.", 403

    date_to_delete = request.form.get('date')

    user_data, user_file = load_user_data(user_no)
    if user_data is None: return "User not found.", 404

    spec_conf_date_content = user_data.get('spec_conf_date', '')
    all_lines = [l.strip() for l in spec_conf_date_content.split('\n') if l.strip()]

    all_lines = [l for l in all_lines if not l.startswith(date_to_delete + " ")]
    
    user_data['spec_conf_date'] = "\n".join(all_lines)
    save_user_data(user_file, user_data)

    return redirect(url_for('config_dates'))


@app.route('/config/req', methods=['GET', 'POST'])
def config_req():
    user_no = check_perm()
    if not user_no:
        return "Unauthorized: You can only submit your own orders.", 403

    user_data, user_file = load_user_data(user_no)
    if user_data is None:
        return "User not found.", 404

    if request.method == 'POST':
        content = request.form.get('content')
        user_data['req'] = content
        save_user_data(user_file, user_data)
        return redirect(url_for('config_req'))

    content = user_data.get('req', '')

    return render_template('config_req.html', content=content)

@app.route('/orders/editor')
def orders_editor():
    return render_template('order_editor.html')


def _parse_iso_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@app.route('/api/orders/overview', methods=['GET'])
def api_orders_overview():
    user_no = check_perm()
    if not user_no:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    start_str = request.args.get('starttime')
    end_str = request.args.get('endtime')
    if not start_str or not end_str:
        today = datetime.now().date()
        start_str = today.isoformat()
        end_str = (today + timedelta(days=6)).isoformat()

    start_date = _parse_iso_date(start_str)
    end_date = _parse_iso_date(end_str)
    if start_date is None or end_date is None:
        return jsonify({'success': False, 'message': '日期格式应为 YYYY-MM-DD'}), 400
    if end_date < start_date:
        start_date, end_date = end_date, start_date
        start_str, end_str = end_str, start_str
    if (end_date - start_date).days > 30:
        return jsonify({'success': False, 'message': '查询范围不能超过 31 天'}), 400

    user_data, _ = load_user_data(user_no)
    if user_data is None:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    try:
        with wxapi.wechat_session(user_data) as authinfo:
            week_book = wxapi.get_week_book_data(authinfo, start_str, end_str)
            records = wxapi.get_order_details(authinfo, start_str, end_str)
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500

    detail_prices = {}
    for record in records:
        if not wxapi.is_active_detail(record):
            continue
        meal_key = wxapi.detail_meal_key(record)
        date_str = record.get('ORDERDATE')
        name = record.get('DISHESNAME')
        if not meal_key or not date_str or not name:
            continue
        try:
            detail_prices[(date_str, meal_key, name)] = float(record.get('ORDERAMOUNT') or 0)
        except (TypeError, ValueError):
            detail_prices[(date_str, meal_key, name)] = 0

    week_by_date = {
        item.get('orderdate'): item
        for item in week_book
        if isinstance(item, dict) and item.get('orderdate')
    }

    days = {}
    current = start_date
    index = 1
    meal_fields = (
        ('breakfastorders', 'breakfast'),
        ('lunchorders', 'lunch'),
        ('supperorders', 'supper'),
    )
    while current <= end_date:
        date_str = current.isoformat()
        week_item = week_by_date.get(date_str) or {}
        auto_order = {}
        for meal_key, field in meal_fields:
            items = []
            for cell in wxapi.parse_week_book_cell(week_item.get(field, '')):
                price = detail_prices.get((date_str, meal_key, cell['name']), 0)
                for _ in range(max(1, int(cell.get('qty') or 1))):
                    items.append({
                        'id': None,
                        'name': cell['name'],
                        'price': price,
                        'order_status': cell.get('status', '0'),
                    })
            auto_order[meal_key] = items

        days[str(index)] = {
            'date': date_str,
            'week': week_item.get('week', ''),
            'auto_order': auto_order,
        }
        index += 1
        current += timedelta(days=1)

    return jsonify({
        'success': True,
        'starttime': start_str,
        'endtime': end_str,
        'days': days,
    })


@app.route('/api/orders/day_menu', methods=['GET'])
def api_orders_day_menu():
    user_no = check_perm()
    if not user_no:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    date_str = request.args.get('date')
    if _parse_iso_date(date_str) is None:
        return jsonify({'success': False, 'message': '日期格式应为 YYYY-MM-DD'}), 400

    user_data, _ = load_user_data(user_no)
    if user_data is None:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    try:
        with wxapi.wechat_session(user_data) as authinfo:
            menu = wxapi.get_order_food_list(authinfo, date_str)
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500

    filtered_menu = {}
    for meal_key, _meal_code in wxapi.MEAL_TYPES:
        filtered_menu[meal_key] = [
            item for item in (menu.get(meal_key) or [])
            if isinstance(item, dict) and not item.get('ydflag')
        ]

    return jsonify({'success': True, 'date': date_str, 'menu': filtered_menu})


@app.route('/api/orders/apply', methods=['POST'])
def api_orders_apply():
    user_no = check_perm()
    if not user_no:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    payload = request.get_json(silent=True) or {}
    days = payload.get('days')
    if isinstance(days, dict):
        days = list(days.values())
    if not isinstance(days, list):
        return jsonify({'success': False, 'message': 'days 必须是数组'}), 400

    normalized_days = []
    for day in days:
        if not isinstance(day, dict) or _parse_iso_date(day.get('date')) is None:
            continue
        entry = {'date': day['date']}
        for meal_key, _meal_code in wxapi.MEAL_TYPES:
            items = day.get(meal_key) or []
            entry[meal_key] = [item for item in items if isinstance(item, dict)]
        normalized_days.append(entry)

    if not normalized_days:
        return jsonify({'success': False, 'message': '没有有效的日期数据'}), 400

    user_data, _ = load_user_data(user_no)
    if user_data is None:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    result = order_service.apply_order_changes(user_data, normalized_days)
    return jsonify(result), (200 if result.get('success') else 500)


@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
        
    student_id = data.get('studentId')
    password = data.get('password')
    email = data.get('email')

    if student_id in register.reg_email_pending_list:
        return jsonify({"success": False, "message": "This student ID is already pending registration. Please check your email."}), 400

    if student_id in get_all_users():
        return redirect("/set_user_no?user_no=" + student_id)
    
    if register.send_reg_email(student_id, password, email):
        return jsonify({"success": True, "message": "Registration email sent. Please check your email."})
    else:
        return jsonify({"success": False, "message": "Failed to send registration email."}), 500

if __name__ == '__main__':
    app.run("0.0.0.0", debug=True, port=APP_PORT)
