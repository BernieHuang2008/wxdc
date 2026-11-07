import requests
import logging
import argparse
import json
import os
from wxdc_bind import BindWeChat, UnBindWeChat
import time
from datetime import date, datetime, timedelta
from config_utils import LLM_API_KEY, LLM_ENDPOINT, LLM_MODEL, PENDING_ORDERS_DIR, USERS_DIR, WEB_BASE_URL
from email_utils import send_email
import wxutils
import genorder_img, genorder_html
import menu_store
import order_service

def ask_llm(prompt: str) -> str:
    # Use Pollinations AI API for LLM interaction
    url = LLM_ENDPOINT
    api_key = LLM_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            'type': 'json_object'
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("choices")[0].get("message")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to call LLM: {e}")
        return ""

class AuthInfo:
    _openid = None
    center_id = "9053"  # szsy gzb
    user_no = None
    token = None
    jsessionid = None

    def __init__(self):
        pass

    def auth_by_openid(self, openid=None):
        self._openid = openid or self._openid

        url = "http://wxdc.szsy.cn/api/wechat/oauth"
        params = {
            "openId": self._openid
        }
        headers = {
            "Host": "wxdc.szsy.cn",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 XWEB/1420153 MMWEBSDK/20251101 MMWEBID/2946 MicroMessenger/8.0.67.3000(0x28004351) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
            "Accept": "application/json, text/plain, */*"
        }
        
        try:
            response = requests.post(url, params=params, headers=headers)
            response.raise_for_status()
            
            auth_data = response.json()
            self.center_id = str(auth_data.get("result").get("centerId"))
            self.token = auth_data.get("result").get("token")
            print(auth_data)
           # self.jsessionid = auth_data.get("result").get("jsessionid")
            
            logging.info("Authentication successful")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Authentication failed: {e}")
        except ValueError as e:
            logging.error(f"Error parsing auth response: {e}")

    def reauth(self):
        logging.info("Re-authenticating...")
        self.auth_by_openid(self._openid)

    def isCompleted(self):
        # print([self.user_no, self.token, self.jsessionid])
        return all([self.user_no, self.token, self.jsessionid])

class CanteenMenu:
    authinfo = None

    _menu = None

    def __init__(self, date=None, auth=None):
        self.date = date
        self.authinfo = auth

    def isCompleted(self):
        return self.authinfo.isCompleted()
    
    @property
    def menu(self):
        if self._menu is None:
            self.fetch_menu()
        return self._menu

    def fetch_menu(self):
        if not self.isCompleted():
            raise ValueError("User information is incomplete.")
        
        url = "http://wxdc.szsy.cn/api/orderdata/getOrderFoodList"
        params = {
            "selectdate": self.date,
            "userno": self.authinfo.user_no,
            "foodtype": ""
        }
        headers = {
            "Host": "wxdc.szsy.cn",
            "Proxy-Connection": "keep-alive",
            "Content-Length": "0",  # Explicitly setting content-length to 0 as per the raw request, though requests usually handles this
            "X-Access-Token": self.authinfo.token,
            "CENTER_ID": self.authinfo.center_id,
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 XWEB/1420153 MMWEBSDK/20251101 MMWEBID/2946 MicroMessenger/8.0.67.3000(0x28004351) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
            "Accept": "application/json, text/plain, */*",
            "Origin": "http://wxdc.szsy.cn",
            "X-Requested-With": "com.tencent.mm",
            "Referer": "http://wxdc.szsy.cn/order/orderFood",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-CN;q=0.8,en-US;q=0.7,en;q=0.6",
            "Cookie": f"JSESSIONID={self.authinfo.jsessionid}"
        }

        tolerance = 3
        while tolerance > 0:
            tolerance -= 1

            response = requests.post(url, params=params, headers=headers)

            match response.status_code:
                case 200:
                    pass
                case 401:
                    # Unauthorized access
                    self.authinfo.reauth()
                    continue
                case _:
                    logging.info("Status Code:", str(response.status_code))
                    logging.info("Response Headers:", str(response.headers))
                    continue
            
            # Try to parse JSON if possible
            try:
                self._menu = response.json().get("result")
                # logging.info("Response JSON:", self._menu)
                tolerance = 1000
                break
            except ValueError:
                logging.error("Error Decoding JSON: ", response.text)
                # logging.info("Response Text:", response.text)

        if tolerance == 0:
            logging.error("Failed to fetch menu after multiple attempts.")


class AutoOrder:
    authinfo = None
    requirement = None

    def __init__(self):
        # Per-instance maps: these must NOT be shared between AutoOrder
        # instances (e.g. different users in the same process), otherwise the
        # fake_id_counter of a new instance restarts at 0 while the reverse
        # map still holds the previous instance's ids, causing fake ids to be
        # translated back to the wrong real dish.
        self.id_map = {
            # real_id: fake_id
        }
        self.id_map_reverse = {}
        self.fake_id_counter = 0

    def realid_2_fakeid(self, real_id):
        if real_id not in self.id_map:
            fake_id = self.fake_id_counter
            self.id_map[real_id] = fake_id
            self.id_map_reverse[fake_id] = real_id
            self.fake_id_counter += 1

        return self.id_map[real_id]

    def fakeid_2_realid(self, fake_id):
        return self.id_map_reverse[int(fake_id)]

    def organize_menu(self, foodlist):
        new_foodlist = []

        if not foodlist:
            return new_foodlist

        for food in foodlist:
            # sold out
            if food.get("ydflag"):
                continue

            new_food = {
                "id": self.realid_2_fakeid(food.get("id")),
                "name": food.get("name"),
                "price": float(food.get("price")),
            }
            new_foodlist.append(new_food)

        return new_foodlist
    
    def auto_order_week(self, weekly_data):
        prompt_menus = {}
        for day_key, day_info in weekly_data.items():
            date_str = day_info["date"]
            menu_info = day_info.get("menu", {})
            prompt_menus[date_str] = {}
            for meal in ["breakfastorders", "lunchorders", "supperorders"]:
                if menu_info and meal in menu_info and menu_info[meal]:
                    prompt_menus[date_str][meal] = self.organize_menu(menu_info[meal])
                else:
                    prompt_menus[date_str][meal] = []

        prompt = f"""
        你是一个食堂自动订餐系统，需要根据用户的需求以及一周的菜单，一次性为一周完成订餐。订餐结果请返回JSON格式。以日期为键，值为各餐的订餐列表（内容包括：所定餐品的id, name, price）。
        例如：
        # EXAMPLE JSON OUTPUT
        {{
            "2024-03-25": {{
                "breakfastorders": [{{
                    "id": "12345abc",
                    "name": "肉包子",
                    "price": 2.5
                }}],
                "lunchorders": [...],
                "supperorders": [...]
            }},
            "2024-03-26": {{ ... }}
        }}
        其中：
        - 字典的第一级键是日期。如果是休息日没有安排餐饮，可以为空json或者省略。
        - 只能订购提供的菜单中有的餐品（对应日期对应餐次的菜单）。如果没有提供对应的菜单（比如菜单为空），请返回空列表 []，或者不要包含该餐次。
        - 所有信息必须与菜单上的信息完全一致，才能订餐成功。请谨慎对待！
        - 如果某餐的菜单为空，不能订餐。

        请在思考时double check你的订餐结果是否满足要求，是否有不合理的地方（比如订了一个菜，但是这个菜在当天的菜单里没有）。如果发现问题，请修改你的订餐结果，直到它完全满足要求为止。

        # Order Requirement:
        {self.requirement}

        # Weekly Canteen Menu:
        {json.dumps(prompt_menus, ensure_ascii=False)}
        """

        logging.info("Prompt to LLM: %s", prompt)

        res = ask_llm(prompt)

        logging.info("LLM Response: %s", res)
        
        weekly_orders = json.loads(res.get("content"))

        # verify and populate
        for day_key, day_info in weekly_data.items():
            date_str = day_info["date"]
            day_info["auto_order"] = {
                "breakfastorders": [],
                "lunchorders": [],
                "supperorders": []
            }
            if date_str in weekly_orders:
                for meal in ["breakfastorders", "lunchorders", "supperorders"]:
                    CAIs = weekly_orders[date_str].get(meal, [])
                    # check
                    valid_orders = []
                    org_menu = prompt_menus.get(date_str, {}).get(meal, [])
                    for cai in CAIs:
                        if any(food['id'] == cai['id'] and food['name'] == cai['name'] and food['price'] == cai['price'] for food in org_menu):
                            valid_orders.append({
                                "id": self.fakeid_2_realid(cai['id']),
                                "name": cai['name'],
                                "price": cai['price']
                            })
                        else:
                            logging.error(f"Ordered item not found in menu for {date_str} {meal}: {cai}")
                    day_info["auto_order"][meal] = valid_orders

        return True


canteen_menu_lazy_fetch_cache = {}
def get_canteen_menu(date, authinfo):
    cache_key = date
    if cache_key in canteen_menu_lazy_fetch_cache:
        return canteen_menu_lazy_fetch_cache[cache_key]

    canteen_menu = CanteenMenu(date, auth=authinfo)
    canteen_menu.fetch_menu()
    canteen_menu_lazy_fetch_cache[cache_key] = canteen_menu
    return canteen_menu


def run_one(user_file, week="current"):
    """Generate orders for one user.

    ``week='current'`` targets the coming Monday (Friday run) and uses
    order_date keys 1-7.  ``week='next'`` targets the Monday after that
    (Sunday advance run) and uses order_date keys 8-14.
    """
    with open(user_file, "r", encoding="utf-8") as f:
        user_data = json.load(f)

    user_no = user_data.get("UserNO")
    logging.info(f"Processing orders for user: {user_no} (week={week})")

    try:
        BindWeChat(userno=user_data.get("UserNO"), pwd=user_data.get("pwd"))
    except Exception as e:
        logging.exception("Failed to bind WeChat.")
        return

    authinfo = AuthInfo()
    authinfo.user_no = user_no
    authinfo.auth_by_openid(user_data.get("open_id"))
    authinfo.jsessionid = user_data.get("jsessionid")

    next_monday = date.today() + timedelta(days=(7 - date.today().weekday()))
    week_offset = 7 if week == "next" else 0
    target_monday = next_monday + timedelta(days=week_offset)

    data = {}

    auto_order = AutoOrder()
    auto_order.authinfo = authinfo
    auto_order.requirement = user_data.get("req", "")

    # Fetch the whole target week once so the shared menu file is complete
    # even when a particular user only orders a few days.
    week_day_menus = {}
    for offset in range(7):
        menu_date = target_monday + timedelta(days=offset)
        canteen_menu = get_canteen_menu(menu_date.isoformat(), authinfo)
        menu = canteen_menu.menu or {}
        week_day_menus[menu_date.isoformat()] = {
            "breakfastorders": menu.get("breakfastorders", []),
            "lunchorders": menu.get("lunchorders", []),
            "supperorders": menu.get("supperorders", []),
        }

    configured_dates = user_data.get("order_date", {}) or {}
    for source_day in range(1, 8):
        dayorder = configured_dates.get(str(source_day + week_offset), "")
        if not dayorder:
            continue

        order_date = target_monday + timedelta(days=source_day - 1)
        full_menu = week_day_menus.get(order_date.isoformat(), {})

        data[str(source_day)] = {
            "date": order_date.isoformat(),
            "menu": {
                "breakfastorders": full_menu.get("breakfastorders", []) if "b" in dayorder else [],
                "lunchorders": full_menu.get("lunchorders", []) if "l" in dayorder else [],
                "supperorders": full_menu.get("supperorders", []) if "s" in dayorder else [],
            },
        }

    # read special config date from user data
    spec_conf_raw = user_data.get("spec_conf_date", "")
    if spec_conf_raw:
        spec_conf = spec_conf_raw.strip().split("\n")
        for line in spec_conf:
            line = line.strip()
            if not line:
                continue
            spec_date, submenus = line.split(" ", 1)
            submenus = submenus.split(" ")

            try:
                spec_date_obj = date.fromisoformat(spec_date)
            except ValueError:
                logging.warning(f"Invalid special date: {spec_date}")
                continue

            if target_monday <= spec_date_obj < target_monday + timedelta(days=7):
                day_offset = (spec_date_obj - target_monday).days

                canteen_menu = CanteenMenu(spec_date, auth=authinfo)

                if str(day_offset + 1) in data:
                    current_menu = data[str(day_offset + 1)]["menu"]
                else:
                    current_menu = {
                        "breakfastorders": [],
                        "lunchorders": [],
                        "supperorders": [],
                    }

                full_special_menu = week_day_menus.setdefault(
                    spec_date,
                    {
                        "breakfastorders": [],
                        "lunchorders": [],
                        "supperorders": [],
                    },
                )
                if canteen_menu.menu:
                    for meal_key in ("breakfastorders", "lunchorders", "supperorders"):
                        if meal_key in canteen_menu.menu:
                            full_special_menu[meal_key] = canteen_menu.menu[meal_key]

                for submenu in submenus:
                    meal = f"{submenu}orders"
                    if canteen_menu.menu and meal in canteen_menu.menu:
                        current_menu[meal] = canteen_menu.menu[meal]

                data[str(day_offset + 1)] = {
                    "date": spec_date,
                    "menu": current_menu,
                }

    # unbind after all menu fetching is done
    UnBindWeChat(userno=user_no, jsessionid=authinfo.jsessionid, x_access_token=authinfo.token, center_id=authinfo.center_id)

    # Call AI to process whole week orders at once
    auto_order.auto_order_week(data)

    # Store the shared full-week menu once; pending orders only keep a reference.
    menu_store.save_week_menus(target_monday.isoformat(), week_day_menus)
    for day_info in data.values():
        if isinstance(day_info, dict):
            day_info["menu_ref"] = target_monday.isoformat()
            day_info.pop("menu", None)

    output_filename = f"order_{user_no}_{target_monday.isoformat()}.json"
    PENDING_ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PENDING_ORDERS_DIR / output_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Inform User
    for inform_via in user_data.get("inform_via", []):
        match inform_via:
            case "email":
                html_body = genorder_html.generate_html_table(data, user_no, target_monday, output_filename)
                user_email = user_data.get("email", "berniehuang2008@163.com")
                send_email(f"自动订餐系统 - {user_no}", html_body, user_email)
            case "wechat":
                try:
                    logging.info("Wechat ADB Operation Started")
                    wxutils.connect()

                    for _ in range(2):
                        res = wxutils.navigate_to_chat(*user_data.get("wechat"))
                        if res == True:
                            break
                        else:
                            logging.error(f"WeChat navigation failed ({_}): {res}.")
                            wxutils.back_to_home()

                    wxutils.send_text(f"自动订餐系统 （{datetime.now().strftime('%H:%M:%S')}） - {user_no}")
                    genorder_img.generate_order_summary_image(data, user_no, target_monday)
                    wxutils.send_image("/app/order_summary.png")
                    time.sleep(0.5)
                    wxutils.send_text(f"快捷操作\n\n> 快速提交：{WEB_BASE_URL}/submit_order_from_email/{output_filename}\n\n> 编辑订单：{WEB_BASE_URL}/pending_orders/{output_filename}")
                    wxutils.navigate_to_tongxunlu_from_chat()
                    logging.info("WeChat notification sent successfully.")
                except:
                    logging.exception("Failed to send WeChat notification")

    if user_data.get("auto_submit"):
        logging.info(f"Auto-submit enabled for {user_no}, submitting {output_filename}")
        success, message, failed_items = order_service.submit_pending_order(user_data, data)
        logging.info(f"Auto-submit result for {user_no}: success={success}, message={message}")
        if success and not failed_items:
            try:
                os.remove(output_path)
            except OSError as exc:
                logging.warning(f"Failed to remove pending order {output_path}: {exc}")
        else:
            logging.error(f"Auto-submit failed for {user_no}: {failed_items}")
            failed_by_date = {}
            for item in failed_items:
                if isinstance(item, dict) and item.get("date"):
                    failed_by_date.setdefault(item["date"], []).append(item)
            for day_info in data.values():
                if not isinstance(day_info, dict):
                    continue
                day_info.pop("failed_items", None)
                items = failed_by_date.get(day_info.get("date"))
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
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            except OSError as exc:
                logging.warning(f"Failed to update pending order {output_path}: {exc}")

            user_email = user_data.get("email")
            if user_email:
                failed_rows = "".join(
                    f"<li>{item.get('date')} {item.get('meal_label')} - {item.get('name')}</li>"
                    for item in failed_items
                )
                body = (
                    f"<h1>自动提交未完全成功 - {user_no}</h1>"
                    f"<p>{message}</p>"
                    f"<ul>{failed_rows}</ul>"
                    f"<p>请登录系统查看并手动重试。</p>"
                )
                send_email(f"自动订餐自动提交失败 - {user_no}", body, user_email)


def schedule_run(week="current"):
    user_files = USERS_DIR.glob("*.json")
    for user_file in user_files:
        run_one(user_file, week=week)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="wxdc main script for Auto Ordering."
    )
    parser.add_argument('--runschedule', action='store_true', 
                        help='Run Scheduled Auto Order')
    parser.add_argument('--runone', action='store_true', 
                        help='Run One User (use with --user <user_no> )')
    parser.add_argument('--user', type=str, 
                        help='user_no (use with --runone)')
    parser.add_argument('--week', choices=['current', 'next'], default='current',
                        help='current: Friday run for the coming Monday (keys 1-7); '
                             'next: Sunday advance run for the week after (keys 8-14)')

    args = parser.parse_args()

    # 只有当两个参数都提供时才执行 b()
    if args.runone and args.user is not None:
        run_one(USERS_DIR / f"{args.user}.json", week=args.week)
    elif args.runschedule:
        schedule_run(week=args.week)
    else:
        parser.print_help()
