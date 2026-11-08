# WXDC

自动订餐系统。当前仓库已整理为单层结构，运行数据统一放在 `data/` 下。

用户功能说明见 [USER_MANUAL.html](USER_MANUAL.html)，部署后也可以直接访问 `/help` 查看。

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
│   ├── latest_orders
│   ├── index
│   ├── set_user_no
│   ├── list_pending_orders
│   ├── view_order
│   ├── update_order
│   ├── pending_order_status
│   ├── submit_order
│   ├── submit_order_from_email
│   ├── config_dates
│   ├── api_config_order_date
│   ├── api_config_auto_submit
│   ├── add_date
│   ├── delete_date
│   ├── config_req
│   ├── orders_editor
│   ├── api_orders_overview
│   ├── api_orders_day_menu
│   ├── api_orders_apply
│   ├── register_page
│   └── api_register
├── wxapi.py
│   ├── get_order_list
│   ├── get_order_details
│   ├── get_order_headers
│   ├── get_week_book_data
│   ├── get_order_food_list
│   ├── cancel_order_detail
│   ├── set_order
│   ├── parse_week_book_cell
│   └── wechat_session
├── order_service.py
│   ├── format_orderdata_from_pending_order
│   ├── collect_intended_items
│   ├── submit_pending_order
│   └── apply_order_changes
├── menu_store.py
│   ├── save_week_menus
│   ├── load_week_menus
│   ├── inject_day_menus
│   └── strip_day_menus
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
│   ├── menus/
│   │   ├── <week-start>.json
│   ├── keys/
│   │   ├── dkim.private.key
│   │   └── dkim.public.key
│   └── logs/
└── templates/
    ├── index.html
    ├── register.html
    ├── list_pending_orders.html
    ├── view_order.html
    ├── order_editor.html
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
负责 Web 页面、订单查看与提交、订单状态刷新、日期配置、自动提交配置、每日菜谱/订单修改页、注册入口。

`wxdc.py`
负责每周自动抓取菜单、调用 LLM 生成订餐结果、生成 pending order、通知邮件和可选的自动提交。
支持 `--week current`（周五，订餐日期键 1-7）和 `--week next`（周日，订餐日期键 8-14）两种触发目标。

`wxdc_bind.py`
负责微信绑定、解绑和加密参数封装。

`wxapi.py`
封装订餐系统的 4 个新接口：订单查询、菜品查询、每日菜谱、退餐，以及下单 `setOrder`。
提供带自动解绑的 `wechat_session` 上下文。

`order_service.py`
负责格式化订单、提交后调用订单查询接口确认菜品是否成功、以及“先退后定”的差异同步逻辑。

`menu_store.py`
负责共享菜谱的落盘与读取。pending order 只保存 `menu_ref` 指向 `data/menus/<周一日期>.json`，不重复保存整份菜单。

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

### 2. 周订单自动生成（周五 / 周日两班）

1. cron 每周五执行 `python wxdc.py --runschedule --week current`
2. cron 每周日中午执行 `python wxdc.py --runschedule --week next`
3. `wxdc.py` 读取 `data/users/*.json`
4. 对每个用户，先调用 `wxdc_bind.BindWeChat`
5. `wxdc.AuthInfo.auth_by_openid` 获取 token
6. `wxdc.CanteenMenu.fetch_menu` 逐日请求菜单
7. `wxdc.AutoOrder.auto_order_week` 拼接 prompt 并调用 `wxdc.ask_llm`
8. `wxdc.py` 把整周菜单写入 `data/menus/<周一日期>.json`
9. `wxdc.py` 生成 `data/pending_orders/order_<user_no>_<target_monday>.json`，只保留 `auto_order` 和 `menu_ref`
10. `wxdc.py` 调用 `email_utils.send_email` 发送订餐摘要邮件
11. 若用户 JSON 中 `auto_submit` 为 `true`，重新登录账号，调用 `setOrder` 提交，随后用订单查询接口确认每个菜品，最后退出账号
12. 自动提交全部成功时删除 pending 文件；有失败菜品时保留文件并发送失败通知

`--week current` 使用 `order_date` 的 1-7 键，目标是最近的周一；
`--week next` 使用 8-14 键，目标是再下一周，用于提前预订。

### 3. 用户查看与提交订单

1. 用户打开 `/pending_orders`
2. `server.list_pending_orders` 读取 `data/pending_orders/*.json`
3. 用户打开某个订单 `/pending_orders/<filename>`
4. `server.view_order` 读取 JSON，并通过 `menu_store.inject_day_menus` 从共享菜谱补全 `menu`
5. 用户修改后提交 `/pending_orders/<filename>/update`
6. `server.update_order` 去掉内嵌菜单后保存
7. 用户点击提交 `/submit_order/<filename>`
8. `server.submit_order` 调用 `order_service.submit_pending_order`
9. `order_service` 先绑定并认证，然后请求 `setOrder`
10. 在退出账号前调用 `getOrderList?querytype=1` 确认每个菜品是否已在系统中
11. 全部确认成功才删除 pending 文件；有失败菜品时返回 `failed_items` 并保留文件
12. 页面上的“刷新订餐状态”调用 `/pending_orders/<filename>/status`，把菜品标成绿色（已下单）、红色（失败）或灰色（已选未下单）

### 4. 邮件里的快速提交

1. 用户点击邮件中的提交链接
2. `server.submit_order_from_email` 读取订单文件
3. 之后流程与手动提交一致，失败菜品也会显示在结果页

### 5. 特殊日期与订餐需求配置

1. 用户打开 `/config/dates`
2. `server.config_dates` 读取用户 JSON 中的 `spec_conf_date`
3. 提交新增日期时走 `server.add_date`
4. 删除日期时走 `server.delete_date`
5. 日期表格下方有“是否自动提交”开关，通过 `/api/config/auto_submit` 保存到用户 JSON 的 `auto_submit`
6. 用户打开 `/config/req`
7. `server.config_req` 读取或写入用户 JSON 中的 `req`

### 6. 共享菜谱与刷新订餐状态

`data/menus/<周一日期>.json` 保存某一周每天的完整菜单：

```json
{
    "week_start": "2026-11-09",
    "updated_at": "2026-11-07T12:00:00",
    "days": {
        "2026-11-09": {
            "breakfastorders": [],
            "lunchorders": [],
            "supperorders": []
        }
    }
}
```

pending order 的每一天只保存：

```json
{
    "date": "2026-11-09",
    "menu_ref": "2026-11-09",
    "auto_order": {
        "breakfastorders": [],
        "lunchorders": [],
        "supperorders": []
    }
}
```

这样同一周的菜单只存一份，所有用户共享。旧订单如果仍然内嵌 `menu`，页面会继续兼容显示。

### 7. 每日菜谱 / 订单修改页

1. 首页点击“每日菜谱 / 订单修改”，打开 `/orders/editor`
2. 选择开始/结束日期后，前端调用 `/api/orders/overview`
3. `server.api_orders_overview` 调用每日菜谱接口 `getWeekBookData`，再用菜品查询接口 `getOrderList?querytype=1` 补充价格
4. 点击某个日期/餐次时，前端调用 `/api/orders/day_menu`，后端用 `getOrderFoodList` 拉取完整菜单
5. 用户修改某天各餐的菜品后点击“提交修改”，前端调用 `/api/orders/apply`
6. `order_service.apply_order_changes` 拉取系统当前 active 菜品，与提交的菜单比对
7. 先对多出来/不在新菜单中的菜品调用 `cancelOrderDetail` 退餐
8. 再对缺少的菜品调用 `setOrder` 定餐
9. 最后再次调用 `getOrderList?querytype=1` 确认结果，返回取消、提交和失败列表

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
`wxapi.set_order`

用途：
提交最终订单数据。

请求要点：
`data` 中单引号会被编码成 `%27`。
`X-Access-Token` 和 `CENTER_ID` 必须有效。

`data` 的每一项格式：

```text
日期~餐次~菜品ID~数量~'
```

餐次：`0` 早餐、`1` 午餐、`2` 晚餐。多项用逗号分隔。

### 订单查询接口（querytype=0）

`POST http://wxdc.szsy.cn/api/orderdata/getOrderList`

调用函数：
`wxapi.get_order_list` / `wxapi.get_order_headers`

用途：
查询指定时间范围内的订单摘要（订单号、创建时间、金额、订单状态）。

脱敏后的请求示例：

```bash
curl -X POST 'http://wxdc.szsy.cn/api/orderdata/getOrderList?userno=<USER_NO>&starttime=<START_DATE>&endtime=<END_DATE>&page=1&querytype=0&orderstatus' \
  -H 'X-Access-Token: <TOKEN>' \
  -H 'CENTER_ID: <CENTER_ID>' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Cookie: JSESSIONID=<JSESSIONID>'
```

参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `userno` | 是 | 用户编号 |
| `starttime` | 是 | 开始日期，`YYYY-MM-DD` |
| `endtime` | 是 | 结束日期，`YYYY-MM-DD` |
| `page` | 是 | 页码，从 1 开始 |
| `querytype` | 是 | `0` 订单摘要；`1` 菜品明细 |
| `orderstatus` | 否 | 订单状态筛选，留空表示全部 |

返回示例（已脱敏）：

```json
{
  "success": true,
  "code": 200,
  "result": {
    "records": [
      {
        "ORDERNO": "<ORDER_NO>",
        "CREATEDATE": "2026-11-07 18:34:55",
        "ORDERTOTALAMOUNT": "2.00",
        "ORDERSTATE": "0",
        "ID": "<ORDER_ID>"
      }
    ],
    "total": 1,
    "size": 20,
    "current": 1,
    "pages": 1
  }
}
```

### 菜品查询接口（querytype=1）

`POST http://wxdc.szsy.cn/api/orderdata/getOrderList`（同一路径，`querytype=1`）

调用函数：
`wxapi.get_order_details`

用途：
查询订单中每个菜品的实际状态，用于提交后确认、页面刷新和“先退后定”的差异比对。

脱敏后的请求示例：

```bash
curl -X POST 'http://wxdc.szsy.cn/api/orderdata/getOrderList?userno=<USER_NO>&starttime=<START_DATE>&endtime=<END_DATE>&page=1&querytype=1&orderstatus' \
  -H 'X-Access-Token: <TOKEN>' \
  -H 'CENTER_ID: <CENTER_ID>' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Cookie: JSESSIONID=<JSESSIONID>'
```

参数与 `querytype=0` 相同，但 `querytype` 固定为 `1`。

返回示例（已脱敏）：

```json
{
  "success": true,
  "code": 200,
  "result": {
    "records": [
      {
        "ORDERDATE": "2026-11-13",
        "ORDERMENUNUMBER": "1",
        "ORDERTYPE": "1",
        "ORDERSTATUS": "0",
        "ID": "<ORDER_DETAIL_ID>",
        "DISHESNAME": "<DISH_NAME>",
        "ORDERAMOUNT": "7.00"
      }
    ],
    "total": 36,
    "size": 20,
    "current": 1,
    "pages": 2
  }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `ORDERDATE` | 用餐日期 |
| `ORDERTYPE` | `0` 早餐、`1` 午餐、`2` 晚餐 |
| `ORDERSTATUS` | 实测 `0` 为有效/已订，`3` 为已取消或失败记录 |
| `DISHESNAME` | 菜品名称 |
| `ORDERAMOUNT` | 该菜品金额 |
| `ID` | 菜品明细 ID，退餐接口的 `orderid` 使用此值 |

注意：
接口分页返回，`wxapi.get_order_details` 会自动翻页获取全部记录。
`ORDERSTATUS` 的语义来自实际响应观察，服务端如有调整以实际为准。

### 每日菜谱接口

`GET http://wxdc.szsy.cn/api/orderdata/getWeekBookData`

调用函数：
`wxapi.get_week_book_data`

用途：
查询指定时间内用户实际已订的每日菜谱，用于“每日菜谱 / 订单修改”页。

脱敏后的请求示例：

```bash
curl -X GET 'http://wxdc.szsy.cn/api/orderdata/getWeekBookData?startdate=<START_DATE>&enddate=<END_DATE>&userno=<USER_NO>' \
  -H 'X-Access-Token: <TOKEN>' \
  -H 'CENTER_ID: <CENTER_ID>' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Cookie: JSESSIONID=<JSESSIONID>'
```

参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `startdate` | 是 | 开始日期，`YYYY-MM-DD` |
| `enddate` | 是 | 结束日期，`YYYY-MM-DD` |
| `userno` | 是 | 用户编号 |

返回示例（已脱敏）：

```json
{
  "success": true,
  "code": 200,
  "result": [
    {
      "orderdate": "2026-11-13",
      "week": "星期五",
      "breakfast": "<DISH_NAME>-1-0",
      "lunch": "<DISH_NAME_A>-1-0@<DISH_NAME_B>-1-0",
      "supper": "",
      "night": ""
    }
  ]
}
```

菜谱字符串格式：

```text
菜品名称-数量-状态@菜品名称-数量-状态
```

菜品名称可能包含 `-`，解析时应从右侧拆分出数量和状态（`wxapi.parse_week_book_cell` 已处理）。

### 退餐接口

`POST http://wxdc.szsy.cn/api/orderdata/cancelOrderDetail`

调用函数：
`wxapi.cancel_order_detail`

用途：
退掉已经提交的单个菜品。“每日菜谱 / 订单修改”页会先调用此接口退掉多余菜品，再调用 `setOrder` 定新菜。

脱敏后的请求示例：

```bash
curl -X POST 'http://wxdc.szsy.cn/api/orderdata/cancelOrderDetail?userno=<USER_NO>&orderid=<ORDER_DETAIL_ID>' \
  -H 'X-Access-Token: <TOKEN>' \
  -H 'CENTER_ID: <CENTER_ID>' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Cookie: JSESSIONID=<JSESSIONID>'
```

参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `userno` | 是 | 用户编号 |
| `orderid` | 是 | 菜品明细 ID，来自菜品查询的 `ID` 字段 |

返回示例（已脱敏）：

```json
{
  "success": true,
  "code": 200,
  "message": "退餐成功"
}
```

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
`cron.schedule`（周五这一班）
`cron.schedule_next`（周日提前预订这一班）
`email`
`wechat`
`llm`
`paths`
`paths.menus_dir`（共享菜谱目录，默认 `menus`）

用户 JSON 中新增：
`auto_submit`：是否自动提交，默认 `false`

## 运行方式

Docker 方式：

```bash
docker compose up -d --build
```

cron 安装方式（两条触发）：

```bash
# 周五：处理 order_date 的 1-7 键，目标是最近的周一
python wxdc.py --runschedule --week current

# 周日中午：处理 order_date 的 8-14 键，目标再下一周，用于提前预订
python wxdc.py --runschedule --week next
```

单用户手动执行：

```bash
python wxdc.py --runone --user <user_no> --week current
python wxdc.py --runone --user <user_no> --week next
```

## 备注

当前 README 里的接口和流程，是按仓库代码整理出来的运行说明。
远端接口如果有变化，以实际服务端为准。

本文档中的 4 个新接口示例均已脱敏：`<TOKEN>`、`<CENTER_ID>`、`<JSESSIONID>`、`<USER_NO>`、`<ORDER_DETAIL_ID>` 等都需要替换为真实值。
`ORDERSTATUS`、`ORDERSTATE` 等状态码含义来自实际响应观察，未获得官方文档，服务端调整时以实际响应为准。

页面模板统一放在 `templates/` 下。若运行环境中该目录出现 rclone/WebDAV 的 I/O 错误，需要在宿主机重挂载或修复远程目录后再继续。
