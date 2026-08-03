import requests
import json

APPID = ""
SECRET = ""

def get_access_token():
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APPID}&secret={SECRET}"
    response = requests.get(url)
    data = response.json()
    if "access_token" in data:
        return data["access_token"]
    else:
        print("Failed to get access token:", data)
        return None

def create_tag(access_token, tag_name):
    url = f"https://api.weixin.qq.com/cgi-bin/tags/create?access_token={access_token}"
    payload = {
        "tag": {
            "name": tag_name
        }
    }
    
    # 使用 json=payload 会自动设置 Content-Type 为 application/json 并确保正确编码
    response = requests.post(url, json=payload)
    return response.json()

if __name__ == "__main__":
    token = get_access_token()
    if token:
        print(f"成功获取 Access Token: {token[:15]}...")
        # 结合上文的需求，我们将标签名命名为 "WXDC users" 
        tag_name = "WXDC users"
        
        print(f"正在尝试创建标签: {tag_name}")
        result = create_tag(token, tag_name)
        
        print("接口返回结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))