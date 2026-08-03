from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
import json
import requests
from datetime import datetime
import register
from wxdc import AuthInfo
from wxdc_bind import UnBindWeChat
from config_utils import APP_PORT, APP_SECRET_KEY, PENDING_ORDERS_DIR, REQ_FILE, SPEC_CONF_DATE_FILE, TOKEN_FILE, USERS_DIR

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY  # Needed for flash messages

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

def format_orderdata_from_pending_order(data):
    formatted_items = []
    # Sort keys to ensure ordering
    # Keys like "1", "2" should be sorted numerically
    sorted_keys = sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else 999)
    
    for key in sorted_keys:
        day_info = data[key]
        date_str = day_info.get("date")
        auto_orders = day_info.get("auto_order", {})
        
        # Meal type mapping: Breakfast=0, Lunch=1, Supper=2
        # Based on example: 0 is breakfast. 
        # Inferred: 1=Lunch, 2=Supper
        meal_types = {
            "breakfastorders": 0,
            "lunchorders": 1,
            "supperorders": 2
        }
        
        for meal_key, meal_code in meal_types.items():
            orders = auto_orders.get(meal_key, [])
            for item in orders:
                if isinstance(item, dict) and 'id' in item:
                    item_id = item['id']
                    # Format: date~type~id~quantity~'
                    # The example showed an ending single quote
                    formatted_str = f"{date_str}~{meal_code}~{item_id}~1~'"
                    formatted_items.append(formatted_str)
                    
    return ",".join(formatted_items)

def place_order(filename, order_data):
    # order_data format example: 2026-02-02~0~ID~1~',2026-02-02~0~ID~1~'        

    try:
        user_no = None
        parts = filename.split('_')
        if len(parts) >= 3 and parts[0] == "order":
            user_no = parts[1]
            
        if not user_no:
            return False, f"Could not determine user_no from filename: {filename}"
            
        user_file = os.path.join(USERS_DIR, f"{user_no}.json")
        if not os.path.exists(user_file):
            return False, "User configuration not found"
            
        with open(user_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        
        try:
            from wxdc_bind import BindWeChat
            BindWeChat(userno=user_data.get("UserNO"), pwd=user_data.get("pwd"))
        except Exception as e:
            print(f"Failed to bind WeChat: {e}")

        authinfo = AuthInfo()
        authinfo.user_no = user_no
        authinfo.auth_by_openid(user_data.get("open_id"))
        authinfo.jsessionid = user_data.get("jsessionid")
        if "center_id" in user_data:
            authinfo.center_id = user_data.get("center_id")
        
        if not authinfo.token:
             print("Failed to get token during place_order")
             return False, "Authentication failed"

        url = "http://wxdc.szsy.cn/api/orderdata/setOrder"
        
        # URL encode the single quotes as %27
        encoded_data = order_data.replace("'", "%27")
        
        params = {
            'data': encoded_data,
            'userno': authinfo.user_no
        }
        
        headers = {
            'Host': 'wxdc.szsy.cn',
            'Content-Length': '0',
            'X-Access-Token': authinfo.token,
            'CENTER_ID': authinfo.center_id,
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 XWEB/1420153 MMWEBSDK/20251101 MMWEBID/2946 MicroMessenger/8.0.67.3000(0x28004351) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'http://wxdc.szsy.cn',
            'X-Requested-With': 'com.tencent.mm',
            'Referer': 'http://wxdc.szsy.cn/order/shoppingCart',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-CN;q=0.8,en-US;q=0.7,en;q=0.6',
            'Cookie': f'JSESSIONID={authinfo.jsessionid}'
        }

        response = requests.post(url, params=params, headers=headers)
        UnBindWeChat(
            userno=authinfo.user_no, 
            jsessionid=authinfo.jsessionid, 
            x_access_token=authinfo.token, 
            center_id=authinfo.center_id
        )
        print(f"Order submission response: {response.status_code}")
        print(f"Response body: {response.text}")
        
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get('success', False) or res_json.get('code') == 200 or str(res_json.get('code')) == '200':
                 return True, "Order submitted successfully to remote server."
            else:
                 return False, f"Server returned error: {response.text}"
        else:
            return False, f"HTTP Error: {response.status_code}"
            
    except Exception as e:
        print(f"Error placing order: {e}")
        return False, str(e)


# 删除不再需要的内存字典和内部接口

@app.route('/latest-orders')
def latest_orders():
    user_no = request.cookies.get('user_no')
    if not user_no:
        return "未登录，请点击微信中的激活链接以验证身份。", 401
    
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
    ensure_pending_orders_dir()
    user_no = request.cookies.get('user_no')
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
    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return "Order file not found.", 404
    
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return "Error decoding JSON file.", 500
            
    return render_template('view_order.html', filename=filename, data=data)

@app.route('/pending_orders/<filename>/update', methods=['POST'])
def update_order(filename):
    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File not found'}), 404
        
    try:
        updated_data = request.json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(updated_data, f, ensure_ascii=False, indent=4)
        return jsonify({'success': True, 'message': 'Order updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/submit_order/<filename>', methods=['POST'])
def submit_order(filename):
    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File not found'}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            order_data_json = json.load(f)
            
        formatted_data = format_orderdata_from_pending_order(order_data_json)
        print(f"Formatted data for submission: {formatted_data}")

        success, message = place_order(filename, formatted_data)

        if success:
             # Remove the pending order file on success
             try:
                 os.remove(filepath)
                 message += " pending 订单已移除"
             except Exception as del_err:
                 message += f" (But failed to delete file: {del_err})"
                 
             return jsonify({'success': True, 'message': message})
        else:
             return jsonify({'success': False, 'message': message}), 500
             
    except Exception as e:
        return jsonify({'success': False, 'message': f"Unexpected error: {str(e)}"}), 500

@app.route('/submit_order_from_email/<filename>', methods=['GET'])
def submit_order_from_email(filename):
    filepath = os.path.join(PENDING_ORDERS_DIR, filename)
    if not os.path.exists(filepath):
        return "Order file not found.", 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
             order_data_json = json.load(f)
        
        formatted_data = format_orderdata_from_pending_order(order_data_json)
        print(f"Formatted data for email submission: {formatted_data}")

        success, message = place_order(filename, formatted_data)

        if success:
            # Remove the pending order file on success
            try:
                os.remove(filepath)
            except Exception as del_err:
                print(f"Failed to delete file {filepath}: {del_err}")

            color = "green"
            title = "Order Submitted Successfully!"
            msg_body = "We have successfully processed your order request. The pending order file has been removed."
        else:
            color = "red"
            title = "Order Submission Failed"
            msg_body = f"There was an error processing your order: {message}"

        return f"""
        <html>
            <head><title>Order Status</title></head>
            <body style="text-align: center; padding-top: 50px; font-family: sans-serif;">
                <h1 style="color: {color};">{title}</h1>
                <p>{msg_body}</p>
                <p><a href="/pending_orders">View all pending orders</a></p>
                <br>
                <div style="color: #ccc; font-size: small;">Debug info: {filename}</div>
            </body>
        </html>
        """
    except Exception as e:
        return f"Error: {str(e)}", 500




@app.route('/config/dates', methods=['GET'])
def config_dates():
    configs = []
    user_no = request.cookies.get('user_no')
    if not user_no:
        return "Please set your user_no first.", 403
        
    user_file = os.path.join(USERS_DIR, f"{user_no}.json")
    if os.path.exists(user_file):
        with open(user_file, 'r', encoding='utf-8') as f:
            user_data = json.load(f)
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
    return render_template('config_dates.html', configs=configs)

@app.route('/config/dates/add', methods=['POST'])
def add_date():
    user_no = request.cookies.get('user_no')
    if not user_no: return "Please set your user_no first.", 403
        
    date_str = request.form.get('date')
    meals = request.form.getlist('meals') # breakfast, lunch, supper

    if not date_str or not meals:
        return "Please select a date and at least one meal.", 400

    meals_str = " ".join(meals)
    new_line = f"{date_str} {meals_str}"

    user_file = os.path.join(USERS_DIR, f"{user_no}.json")
    if not os.path.exists(user_file): return "User not found.", 404

    with open(user_file, 'r', encoding='utf-8') as f:
        user_data = json.load(f)

    spec_conf_date_content = user_data.get('spec_conf_date', '')
    all_lines = [l.strip() for l in spec_conf_date_content.split('\n') if l.strip()]

    # Remove existing config for this date
    all_lines = [l for l in all_lines if not l.startswith(date_str + " ")]      
    all_lines.append(new_line.strip())
    all_lines.sort() # Keep file sorted

    user_data['spec_conf_date'] = "\n".join(all_lines)
    with open(user_file, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=4)

    return redirect(url_for('config_dates'))

@app.route('/config/dates/delete', methods=['POST'])
def delete_date():
    user_no = request.cookies.get('user_no')
    if not user_no: return "Please set your user_no first.", 403

    date_to_delete = request.form.get('date')

    user_file = os.path.join(USERS_DIR, f"{user_no}.json")
    if not os.path.exists(user_file): return "User not found.", 404

    with open(user_file, 'r', encoding='utf-8') as f:
        user_data = json.load(f)

    spec_conf_date_content = user_data.get('spec_conf_date', '')
    all_lines = [l.strip() for l in spec_conf_date_content.split('\n') if l.strip()]

    all_lines = [l for l in all_lines if not l.startswith(date_to_delete + " ")]
    
    user_data['spec_conf_date'] = "\n".join(all_lines)
    with open(user_file, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=4)

    return redirect(url_for('config_dates'))


@app.route('/config/req', methods=['GET', 'POST'])
def config_req():
    user_no = request.cookies.get('user_no')
    if not user_no:
        return "Please set your user_no first.", 403

    user_file = os.path.join(USERS_DIR, f"{user_no}.json")
    if not os.path.exists(user_file):
        return "User not found.", 404

    if request.method == 'POST':
        content = request.form.get('content')
        with open(user_file, 'r', encoding='utf-8') as f:
            user_data = json.load(f)
        user_data['req'] = content
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        return redirect(url_for('config_req'))

    with open(user_file, 'r', encoding='utf-8') as f:
        user_data = json.load(f)
    content = user_data.get('req', '')

    return render_template('config_req.html', content=content)

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
