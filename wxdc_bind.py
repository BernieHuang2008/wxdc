import requests
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from config_utils import API_BASE_URL, WECHAT_BIND_PASSWORD, WECHAT_CENTER_ID, WECHAT_DEFAULT_TOKEN, WECHAT_DEFAULT_USER_NO, WECHAT_JSESSIONID, WECHAT_OPEN_ID

def encrypt(t: str) -> str:
    # Keys and initialization vectors must be bytes
    key = b"7Fpu9FSkjayCeqaE"
    iv = b"0123456789ABCDEF"
    
    # The input text needs to be bytes
    raw_data = t.encode('utf-8')
    
    # Apply PKCS7 padding (AES block size is 128 bits / 16 bytes)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(raw_data) + padder.finalize()
    
    # Set up the AES cipher in CBC mode
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    # Encrypt the data
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    # CryptoJS toString() by default returns a Base64 encoded string
    return base64.b64encode(ciphertext).decode('utf-8')


def UnBindWeChat(userno=WECHAT_DEFAULT_USER_NO,
                 jsessionid=WECHAT_JSESSIONID,
                 x_access_token=WECHAT_DEFAULT_TOKEN,
                 center_id=WECHAT_CENTER_ID):
    
    url = f"{API_BASE_URL}/api/wechat/unBind?userno={userno}"
    
    headers = {
        "Host": "wxdc.szsy.cn",
        "Proxy-Connection": "keep-alive",
        "X-Access-Token": x_access_token,
        "CENTER_ID": center_id,
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 XWEB/1420273 MMWEBSDK/20260201 MMWEBID/2946 REV/022cf9f51d90c3d7a76547829dd7d0d7281dd0f5 MicroMessenger/8.0.69.3040(0x28004555) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
        "Accept": "application/json, text/plain, */*",
        "Origin": "http://wxdc.szsy.cn",
        "X-Requested-With": "com.tencent.mm",
        "Referer": "http://wxdc.szsy.cn/order/mine",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en-CN;q=0.8,en-US;q=0.7,en;q=0.6"
    }
    
    cookies = {
        "JSESSIONID": jsessionid
    }
    
    response = requests.post(
        url, 
        headers=headers, 
        cookies=cookies
    )
    
    return response

def BindWeChat(open_id=WECHAT_OPEN_ID,
               userno=WECHAT_DEFAULT_USER_NO,
               pwd=WECHAT_BIND_PASSWORD,
               jsessionid=WECHAT_JSESSIONID):

    url = f"{API_BASE_URL}/api/wechat/toBind"
    
    # 构建请求头信息 (排除了由 requests 自动接管的 Content-Length 和 Content-Type 字段)
    headers = {
        "Proxy-Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 XWEB/1420273 MMWEBSDK/20260201 MMWEBID/2946 REV/022cf9f51d90c3d7a76547829dd7d0d7281dd0f5 MicroMessenger/8.0.69.3040(0x28004555) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
        "Accept": "application/json, text/plain, */*",
        "Origin": "http://wxdc.szsy.cn",
        "X-Requested-With": "com.tencent.mm",
        "Referer": "http://wxdc.szsy.cn/order/login",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en-CN;q=0.8,en-US;q=0.7,en;q=0.6"
    }
    
    # 提取 Cookie 放入单独的字典
    cookies = {
        "JSESSIONID": jsessionid
    }
    
    # 使用 files 字典并给键赋值 (None, "具体的值")，强制以 multipart/form-data 发送字符串数据
    multipart_data = {
        "openId": (None, open_id),
        "params": (None, encrypt(f'{{"userno":"{userno}","pwd":"{pwd}"}}'))
    }
    
    # 发送 POST 请求
    response = requests.post(
        url, 
        headers=headers, 
        cookies=cookies, 
        files=multipart_data
    )
    
    return response

# 测试调用
if __name__ == "__main__":
    userno_test = "2241112"
    jsessionid_test = ""
    access_token_test = ""
    
    # 也可以单独测试解绑
    # unbind_resp = UnBindWeChat(userno_test, jsessionid_test, access_token_test)
    # print(f"Unbind Status: {unbind_resp.status_code}")
    # print(f"Unbind Body: {unbind_resp.text}")

    resp = BindWeChat(jsessionid=jsessionid_test, userno=userno_test, x_access_token=access_token_test)
    print(f"Status Code: {resp.status_code}")
    print(f"Response Body: {resp.text}")
    
