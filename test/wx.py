import hashlib
import time
import xml.etree.ElementTree as ET
import sys
import os
import json
import uuid
import requests
from flask import Flask, request, make_response

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import register

app = Flask(__name__)

# 定义你在微信公众平台测试号配置的 Token
WECHAT_TOKEN = ''

# 内存中的 session 字典，按 user_id (微信 openid) 管理注册进度
# 结构: { from_user: {"session_id": "...", "step": "step1_username", "userno": "..."} }
user_sessions = {}

def is_wechat_bound(wechat_id):
    user_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user")
    if not os.path.exists(user_dir):
        return False
    for filename in os.listdir(user_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(user_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    if user_data.get("wechat") == wechat_id:
                        return True
            except:
                pass
    return False

def is_userno_registered(userno):
    user_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user")
    filepath = os.path.join(user_dir, f"{userno}.json")
    return os.path.exists(filepath)

def complete_registration(userno, pwd, wechat_id):
    user_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user")
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, f"{userno}.json")
    user_config = {
        "UserNO": userno,
        "center_id": "9053",
        "pwd": pwd,
        "open_id": "",
        "jsessionid": "",
        "req": "我的订餐策略如下：...",
        "spec_conf_date": "",
        "wechat": wechat_id
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(user_config, f, ensure_ascii=False, indent=4)
        
    global user_sessions
    if wechat_id in user_sessions:
        del user_sessions[wechat_id]

@app.route('/wechat', methods=['GET', 'POST'])
def wechat():
    if request.method == 'GET':
        # 1. 提供测试接口适配微信公众平台测试号 (Token 验证)
        signature = request.args.get('signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        echostr = request.args.get('echostr', '')

        # 按字典序排序拼接后进行 SHA1 加密验证
        data = [WECHAT_TOKEN, timestamp, nonce]
        data.sort()
        temp_str = ''.join(data).encode('utf-8')
        hash_str = hashlib.sha1(temp_str).hexdigest()

        if hash_str == signature:
            return echostr
        else:
            return "Token Verification Failed"

    elif request.method == 'POST':
        # 2. 接收消息并解析 XML
        xml_data = request.data
        if not xml_data:
            return "success"
        
        try:
            xml_tree = ET.fromstring(xml_data)
            msg_type = xml_tree.find('MsgType').text
            from_user = xml_tree.find('FromUserName').text
            to_user = xml_tree.find('ToUserName').text
            
            # 这里以文本消息为例作为展示并响应，其他消息仅打印参数
            if msg_type == 'text':
                content = xml_tree.find('Content').text.strip()
                print(f"[WeChat Msg] {from_user} -> {to_user}: [TEXT] {content}")
                
                reply_content = ""
                
                # 检查是否处于注册 session 中
                if content.lower() == "注册wxdc":
                    if is_wechat_bound(from_user):
                        reply_content = "您当前的微信已绑定并注册了wxdc账户，无需重复注册。若需更改信息请联系管理员。"
                    else:
                        session_id = uuid.uuid4().hex[:8]
                        user_sessions[from_user] = {"session_id": session_id, "step": "username", "userno": ""}
                        reply_content = f"[Session: {session_id}] 欢迎使用微信订餐注册。第一步：请输入您的学号（用户名）："
                elif from_user in user_sessions:
                    session_info = user_sessions[from_user]
                    session_id = session_info["session_id"]
                    
                    if session_info["step"] == "username":
                        userno = content
                        if is_userno_registered(userno):
                            reply_content = f"[Session: {session_id}] 学号 {userno} 已经完成注册，请重试其他的学号。若要重新注册请重新发送「注册微信订餐」。"
                            del user_sessions[from_user]
                        else:
                            session_info["userno"] = userno
                            session_info["step"] = "password"
                            reply_content = f"[Session: {session_id}] 学号输入成功。第二步：请输入学号 {userno} 对应的密码："
                            
                    elif session_info["step"] == "password":
                        pwd = content
                        userno = session_info["userno"]
                        reply_content = f"[Session: {session_id}] 正在验证账户，请稍候...\n（若长时间未回复，请检查网络或重新注册）"
                        
                        # 同步验证（会阻塞本次请求，如超时可改异步，这里按照示例逻辑直接调用）
                        is_valid = register.check_account(userno, pwd)
                        if is_valid:
                            complete_registration(userno, pwd, from_user)
                            
                            activation_token = uuid.uuid4().hex
                            token_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "token.txt")
                            try:
                                with open(token_file_path, "a", encoding="utf-8") as f:
                                    f.write(f"{activation_token},{userno}\n")
                            except Exception as e:
                                print(f"Failed to append token to token.txt: {e}")
                                
                            reply_content = f"[Session: {session_id}] 注册成功！您的微信已与学号 {userno} 绑定。\n请点击以下链接激活您的设备身份并查看订餐：\nhttps://wxdc_backend.berniehg.top/set_user_no?token={activation_token}\n\n注意：此链接只能使用一次。"
                        else:
                            reply_content = f"[Session: {session_id}] 账户验证失败：学号或密码错误，或与订餐中心通信失败。请重新发送「注册微信订餐」从头开始注册。"
                            del user_sessions[from_user]

                if not reply_content:
                    return "success"

                reply_xml = f"""
                <xml>
                    <ToUserName><![CDATA[{from_user}]]></ToUserName>
                    <FromUserName><![CDATA[{to_user}]]></FromUserName>
                    <CreateTime>{int(time.time())}</CreateTime>
                    <MsgType><![CDATA[text]]></MsgType>
                    <Content><![CDATA[{reply_content}]]></Content>
                </xml>
                """
                
                response = make_response(reply_xml)
                response.content_type = 'application/xml'
                return response
            else:
                # 微信要求对于不能处理的消息类型直接回复 "success" 以免重试报错
                print(f"[WeChat Msg] Unsupported MsgType: {msg_type}")
                return "success"
                
        except Exception as e:
            print(f"Error parsing XML: {e}")
            return "success"

if __name__ == '__main__':
    # 微信公众号开发通常需要通过 80 端口或 443 端口提供外网服务
    # 测试阶段建议配合内网穿透工具 (如 ngrok/cpolar/frp) 暴露端口
    app.run(host='0.0.0.0', port=9123, debug=True)
