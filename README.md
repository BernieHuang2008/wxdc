# WXDC

自动订餐系统。当前仓库已整理为单层结构，运行数据统一放在 `data/` 下。

## 项目文件树

```text
.
├── config_utils.py
│   ├── _merge_dicts
│   ├── load_config
│   ├── get_config
│   └── resolve_data_path
├── email_utils.py
│   └── send_email
├── register.py
│   ├── check_account
│   ├── send_reg_email
│   └── register
├── server.py
│   ├── get_all_users
│   ├── ensure_pending_orders_dir
│   ├── format_orderdata_from_pending_order
│   ├── place_order
│   ├── latest_orders
│   ├── index
│   ├── set_user_no
│   ├── list_pending_orders
│   ├── view_order
│   ├── update_order
│   ├── submit_order
│   ├── submit_order_from_email
│   ├── config_dates
│   ├── add_date
│   ├── delete_date
│   ├── config_req
│   ├── register_page
│   └── api_register
├── wxdc.py
│   ├── ask_llm
│   ├── AuthInfo.__init__
│   ├── AuthInfo.auth_by_openid
│   ├── AuthInfo.reauth
│   ├── AuthInfo.isCompleted
│   ├── CanteenMenu.__init__
│   ├── CanteenMenu.isCompleted
│   ├── CanteenMenu.menu
│   ├── CanteenMenu.fetch_menu
│   ├── AutoOrder.organize_menu
│   └── AutoOrder.auto_order_week
├── wxdc_bind.py
│   ├── encrypt
│   ├── UnBindWeChat
│   └── BindWeChat
├── test/test_send_email.py
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── install_cron.sh
├── install_cron.bat
├── requirements.txt
├── service/
│   ├── hg_wxdc.service
│   ├── install.sh
│   └── start.sh
├── test/
│   ├── a.bin
│   ├── a.js
│   ├── b642byte.py
│   ├── hash_cracker.py
│   ├── test_point.py
│   ├── test_send_email.py
│   └── wx.py
├── data/
│   ├── config.yaml
│   ├── req.txt
│   ├── spec_conf_date.txt
│   ├── token.txt
│   ├── users/
│   │   ├── *.json
│   ├── pending_orders/
│   │   ├── *.json
│   ├── keys/
│   │   ├── dkim.private.key
│   │   └── dkim.public.key
│   └── logs/
└── templates/
    ├── index.html
    ├── register.html
    ├── list_pending_orders.html
    ├── view_order.html
    ├── config_dates.html
    └── config_req.html
```

## 模块职责

`config_utils.py`
负责读取 `data/config.yaml`，并把路径、邮箱、微信、LLM、cron 配置统一导出。

`email_utils.py`
统一负责邮件发送，支持可选 DKIM 签名。

`register.py`
负责注册校验、发送激活邮件、落盘用户配置。

`server.py`
负责 Web 页面、订单查看与提交、日期配置、订餐需求配置、注册入口。

`wxdc.py`
负责每周自动抓取菜单、调用 LLM 生成订餐结果、生成 pending order 和通知邮件。

`wxdc_bind.py`
负责微信绑定、解绑和加密参数封装。

`service/`
保留旧的 systemd / shell 部署脚本，当前 Docker 方案不依赖它们。

`test/`
历史测试与实验脚本目录，`test_send_email.py` 是可复用的邮件测试入口，其余文件主要作为开发记录保留。

`test/test_send_email.py`
邮件发送测试入口，直接复用 `email_utils.send_email`。

## 业务调用链

### 1. 用户注册

1. 用户打开 `/register`
2. `server.register_page` 渲染注册页
3. 用户提交表单到 `/api/register`
4. `server.api_register` 调用 `register.send_reg_email`
5. `register.send_reg_email` 先调用 `register.check_account`
6. `register.check_account` 依次调用 `wxdc_bind.BindWeChat`、`wxdc.AuthInfo.auth_by_openid`、`wxdc_bind.UnBindWeChat`
7. 校验成功后，`register.send_reg_email` 调用 `email_utils.send_email`
8. 用户点击邮件激活链接 `/set_user_no?token=...`
9. `server.set_user_no` 读取 `data/token.txt`
10. `server.set_user_no` 调用 `register.register`
11. `register.register` 写入 `data/users/<user_no>.json`

### 2. 周订单自动生成

1. 容器内 cron 在每周五 16:00 执行 `python wxdc.py`
2. `wxdc.py` 读取 `data/users/*.json`
3. 对每个用户，先调用 `wxdc_bind.BindWeChat`
4. `wxdc.AuthInfo.auth_by_openid` 获取 token
5. `wxdc.CanteenMenu.fetch_menu` 逐日请求菜单
6. `wxdc.AutoOrder.auto_order_week` 拼接 prompt 并调用 `wxdc.ask_llm`
7. `wxdc.py` 生成 `data/pending_orders/order_<user_no>_<date>.json`
8. `wxdc.py` 调用 `email_utils.send_email` 发送订餐摘要邮件
9. 结束后调用 `wxdc_bind.UnBindWeChat`

### 3. 用户查看与提交订单

1. 用户打开 `/pending_orders`
2. `server.list_pending_orders` 读取 `data/pending_orders/*.json`
3. 用户打开某个订单 `/pending_orders/<filename>`
4. `server.view_order` 读取 JSON 并渲染详情
5. 用户修改后提交 `/pending_orders/<filename>/update`
6. `server.update_order` 覆盖保存文件
7. 用户点击提交 `/submit_order/<filename>`
8. `server.submit_order` 调用 `server.format_orderdata_from_pending_order`
9. `server.submit_order` 调用 `server.place_order`
10. `server.place_order` 先调用 `wxdc_bind.BindWeChat`
11. `server.place_order` 再通过 `wxdc.AuthInfo.auth_by_openid` 获取 token
12. `server.place_order` 请求远端订餐接口
13. 成功后调用 `wxdc_bind.UnBindWeChat`

### 4. 邮件里的快速提交

1. 用户点击邮件中的提交链接
2. `server.submit_order_from_email` 读取订单文件
3. 之后流程与手动提交一致

### 5. 特殊日期与订餐需求配置

1. 用户打开 `/config/dates`
2. `server.config_dates` 读取用户 JSON 中的 `spec_conf_date`
3. 提交新增日期时走 `server.add_date`
4. 删除日期时走 `server.delete_date`
5. 用户打开 `/config/req`
6. `server.config_req` 读取或写入用户 JSON 中的 `req`

## 外部接口说明

下面这些接口都来自当前代码，不是仓库里附带的官方文档。

### 微信绑定接口

`POST http://wxdc.szsy.cn/api/wechat/toBind`

调用函数：
`wxdc_bind.BindWeChat`

用途：
提交微信绑定信息，生成后续认证所需状态。

请求要点：
表单上传 `openId` 和 `params`，其中 `params` 是 AES-CBC 后的 Base64 字符串。

关键头部：
`Origin`、`Referer`、`X-Requested-With`、`Cookie: JSESSIONID=...`

### 微信解绑接口

`POST http://wxdc.szsy.cn/api/wechat/unBind?userno=...`

调用函数：
`wxdc_bind.UnBindWeChat`

用途：
在绑定、抓菜单、提交订单后释放会话。

关键头部：
`X-Access-Token`、`CENTER_ID`、`Cookie: JSESSIONID=...`

### 微信 OAuth 接口

`POST http://wxdc.szsy.cn/api/wechat/oauth?openId=...`

调用函数：
`wxdc.AuthInfo.auth_by_openid`

用途：
换取 `token` 和 `centerId`，供后续菜单和下单接口使用。

### 菜单接口

`POST http://wxdc.szsy.cn/api/orderdata/getOrderFoodList`

调用函数：
`wxdc.CanteenMenu.fetch_menu`

请求参数：
`selectdate`、`userno`、`foodtype`

返回内容：
当天各餐次菜单，供 `AutoOrder.auto_order_week` 过滤和选菜。

### 下单接口

`POST http://wxdc.szsy.cn/api/orderdata/setOrder?data=...&userno=...`

调用函数：
`server.place_order`

用途：
提交最终订单数据。

请求要点：
`data` 中单引号会被编码成 `%27`。
`X-Access-Token` 和 `CENTER_ID` 必须有效。

### LLM 接口

`POST https://ark.cn-beijing.volces.com/api/v3/chat/completions`

调用函数：
`wxdc.ask_llm`

用途：
根据一周菜单和用户偏好生成订餐结果。

请求要点：
`Authorization: Bearer <api_key>`
请求体包含 `model` 和 `messages`

### SMTP 邮件接口

`smtp.163.com:25`

调用函数：
`email_utils.send_email`

用途：
发送激活邮件和每周订餐摘要邮件。

说明：
邮件正文为 HTML。
是否启用 DKIM 由 `data/config.yaml` 中的 `email.dkim.enabled` 控制。

## 配置文件

主配置文件：
`data/config.yaml`

建议维护这些字段：
`app`
`cron`
`email`
`wechat`
`llm`
`paths`

## 运行方式

Docker 方式：

```bash
docker compose up -d --build
```

cron 安装方式：

```bat
install_cron.bat
```

## 备注

当前 README 里的接口和流程，是按仓库代码整理出来的运行说明。
远端接口如果有变化，以实际服务端为准。
