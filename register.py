import json
import os

from config_utils import (
    REQ_FILE,
    USERS_DIR,
    WECHAT_CENTER_ID,
    WECHAT_JSESSIONID,
    WECHAT_OPEN_ID,
    WEB_BASE_URL,
)
from email_utils import send_email
from wxdc import AuthInfo
from wxdc_bind import BindWeChat, UnBindWeChat


reg_email_pending_list = {}


def check_account(userno, pwd):
    user_data = {
        "UserNO": userno,
        "pwd": pwd,
        "openid": WECHAT_OPEN_ID,
        "jsessionid": WECHAT_JSESSIONID,
        "center_id": WECHAT_CENTER_ID,
    }

    try:
        BindWeChat(userno=userno, pwd=pwd)

        authinfo = AuthInfo()
        authinfo.user_no = userno
        authinfo.auth_by_openid(user_data.get("openid"))
        authinfo.jsessionid = user_data.get("jsessionid")
        if "center_id" in user_data:
            authinfo.center_id = user_data.get("center_id")

        if not authinfo.token:
            print("Failed to get token during place_order")
            return False

        UnBindWeChat(
            userno=authinfo.user_no,
            jsessionid=authinfo.jsessionid,
            x_access_token=authinfo.token,
            center_id=authinfo.center_id,
        )

        return True
    except Exception as e:
        print(f"Account validation failed: {e}")
        return False


def send_reg_email(userno, pwd, email):
    if check_account(userno, pwd):
        subject = "自动订餐系统-激活邮件"
        body = (
            "<h1>激活邮件</h1>"
            "<p>请点击以下链接激活您的自动订餐账户：</p>"
            "<a href='" + WEB_BASE_URL + "/set_user_no?user_no=" + userno + "'>激活账户</a>"
        )
        reg_email_pending_list[userno] = {
            "userno": userno,
            "pwd": pwd,
            "email": email,
        }
        send_email(subject, body, email)
        return True
    else:
        return False


def register(userno):
    userno = reg_email_pending_list[userno]["userno"]
    pwd = reg_email_pending_list[userno]["pwd"]
    email = reg_email_pending_list[userno]["email"]

    print("Account is valid and WeChat binding/unbinding succeeded.")

    os.makedirs(USERS_DIR, exist_ok=True)
    file_path = os.path.join(USERS_DIR, f"{userno}.json")
    user_config = {
        "UserNO": userno,
        "center_id": WECHAT_CENTER_ID,
        "pwd": pwd,
        "open_id": WECHAT_OPEN_ID,
        "jsessionid": WECHAT_JSESSIONID,
        "req": REQ_FILE.read_text(encoding="utf-8") if REQ_FILE.exists() else "",
        "spec_conf_date": "",
        "email": email,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(user_config, f, ensure_ascii=False, indent=4)
    print(f"配置文件已生成: {file_path}")
