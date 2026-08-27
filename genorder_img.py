import os
from PIL import Image, ImageDraw, ImageFont
import datetime


# -------------------- 字体加载（支持中文） --------------------
def get_font(size, bold=False):
    """尝试加载中文字体，若失败则使用默认字体"""
    # 常见中文字体路径（按优先级）
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",   # Linux (Noto)
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux 备用
        "C:/Windows/Fonts/simhei.ttf",     # Windows 黑体
        "C:/Windows/Fonts/msyh.ttc",       # Windows 微软雅黑
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/Library/Fonts/Arial Unicode.ttf",    # macOS
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except IOError:
                continue
    # 若无可用字体，使用默认（可能不支持中文）
    return ImageFont.load_default()

# -------------------- 绘制表格函数 --------------------
def generate_order_summary_image(data, user_no, base_date, output_path="/app/order_summary.png"):
    # 列宽（固定）
    col_widths = {
        "date": 150,
        "breakfast": 200,
        "lunch": 200,
        "supper": 200
    }
    total_table_width = sum(col_widths.values()) + 4  # 加边框间距
    margin = 20
    row_height = 28       # 每个文本行的高度
    header_height = 35    # 表头行高
    font_size = 16
    bullet = "• "         # 项目符号

    # 准备数据行列表
    sorted_days = sorted(data.keys(), key=lambda x: int(x))
    rows = []
    max_lines_per_row = []  # 每行最大文本行数（用于动态行高）

    for day_key in sorted_days:
        day_info = data[day_key]
        date_str = day_info.get("date", "")
        auto_orders = day_info.get("auto_order", {})
        meals = {
            "breakfast": auto_orders.get("breakfastorders", []),
            "lunch": auto_orders.get("lunchorders", []),
            "supper": auto_orders.get("supperorders", [])
        }
        # 生成每个单元格的文本行列表
        cell_lines = {
            "date": [date_str],
            "breakfast": [],
            "lunch": [],
            "supper": []
        }
        for meal_key, orders in meals.items():
            if orders:
                for item in orders:
                    name = item.get("name", "Unknown")
                    price = item.get("price", 0)
                    cell_lines[meal_key].append(f"{bullet}{name} (￥{price})")
            else:
                cell_lines[meal_key].append("-")
        rows.append(cell_lines)
        # 该行最大文本行数
        max_lines = max(len(cell_lines["date"]), len(cell_lines["breakfast"]),
                        len(cell_lines["lunch"]), len(cell_lines["supper"]))
        max_lines_per_row.append(max_lines)

    # 计算图片总高度
    title_height = 80          # 标题区域（标题+日期）
    total_height = margin * 2 + title_height + header_height + sum(max(1, l) * row_height for l in max_lines_per_row)
    # 额外增加一些底部边距
    total_height += 20

    # 创建画布（白色背景）
    img_width = total_table_width + margin * 2
    img = Image.new('RGB', (img_width, total_height), color='white')
    draw = ImageDraw.Draw(img)

    # 加载字体
    font = get_font(font_size)
    font_bold = get_font(font_size, bold=True)

    # ---------- 绘制标题 ----------
    title_text = f"Auto Order Summary for {user_no}"
    week_text = f"Week starting: {base_date.isoformat()}"
    draw.text((margin, 10), title_text, fill='black', font=font_bold)
    draw.text((margin, 45), week_text, fill='black', font=font)

    # ---------- 表格起始 y 坐标 ----------
    start_y = margin + title_height

    # 绘制表头（带背景色）
    header_y = start_y
    x0 = margin
    y0 = header_y
    # 表头背景矩形（浅灰色）
    draw.rectangle([x0, y0, x0 + total_table_width, y0 + header_height], fill='#f2f2f2')
    # 表头边框（四周及内部竖线）
    draw.rectangle([x0, y0, x0 + total_table_width, y0 + header_height], outline='black')
    # 绘制内部竖线
    col_x = x0 + col_widths["date"]
    draw.line([col_x, y0, col_x, y0 + header_height], fill='black')
    col_x += col_widths["breakfast"]
    draw.line([col_x, y0, col_x, y0 + header_height], fill='black')
    col_x += col_widths["lunch"]
    draw.line([col_x, y0, col_x, y0 + header_height], fill='black')
    # 表头文字
    headers = ["Date", "Breakfast", "Lunch", "Supper"]
    col_positions = [x0, x0 + col_widths["date"], x0 + col_widths["date"] + col_widths["breakfast"],
                     x0 + col_widths["date"] + col_widths["breakfast"] + col_widths["lunch"]]
    for i, header in enumerate(headers):
        text_x = col_positions[i] + 5  # 左内边距
        text_y = y0 + (header_height - font_size) // 2
        draw.text((text_x, text_y), header, fill='black', font=font_bold)

    # ---------- 绘制数据行 ----------
    cur_y = header_y + header_height
    for row_idx, cell_lines in enumerate(rows):
        # 计算该行高度
        line_count = max_lines_per_row[row_idx]
        row_h = line_count * row_height
        # 绘制行边框（水平上边框已由上一行的下边框或表头边框绘制，但这里仍需绘制下边框）
        # 先绘制单元格边框（外边框和内部竖线）
        # 绘制矩形外框（左右、下边）
        draw.rectangle([x0, cur_y, x0 + total_table_width, cur_y + row_h], outline='black')
        # 绘制内部竖线
        col_x = x0 + col_widths["date"]
        draw.line([col_x, cur_y, col_x, cur_y + row_h], fill='black')
        col_x += col_widths["breakfast"]
        draw.line([col_x, cur_y, col_x, cur_y + row_h], fill='black')
        col_x += col_widths["lunch"]
        draw.line([col_x, cur_y, col_x, cur_y + row_h], fill='black')

        # 绘制每个单元格的文本
        col_positions = [x0, x0 + col_widths["date"], x0 + col_widths["date"] + col_widths["breakfast"],
                         x0 + col_widths["date"] + col_widths["breakfast"] + col_widths["lunch"]]
        cell_keys = ["date", "breakfast", "lunch", "supper"]
        for i, key in enumerate(cell_keys):
            lines = cell_lines[key]
            text_x = col_positions[i] + 5
            text_y = cur_y + 2
            for line in lines:
                draw.text((text_x, text_y), line, fill='black', font=font)
                text_y += row_height

        # 移动到下一行
        cur_y += row_h

    # 保存图片
    img.save(output_path)
    return True

# -------------------- 执行生成 --------------------
if __name__ == "__main__":
    # ===================== 模拟数据（替换为您的实际数据） =====================
    user_no = "1001"
    base_date = datetime.date(2026, 8, 24)  # 周一

    data = {
        "0": {
            "date": "2026-08-24 (Mon)",
            "auto_order": {
                "breakfastorders": [{"name": "牛奶牛奶牛奶牛奶", "price": 5}, {"name": "面包", "price": 8}],
                "lunchorders": [{"name": "红烧肉", "price": 25}, {"name": "米饭", "price": 2}],
                "supperorders": []
            }
        },
        "1": {
            "date": "2026-08-25 (Tue)",
            "auto_order": {
                "breakfastorders": [{"name": "豆浆", "price": 3}],
                "lunchorders": [],
                "supperorders": [{"name": "面条", "price": 15}]
            }
        },
        "2": {
            "date": "2026-08-26 (Wed)",
            "auto_order": {
                "breakfastorders": [],
                "lunchorders": [],
                "supperorders": []
            }
        }
    }
    # =========================================================================
    generate_order_summary_image(data, user_no, base_date, "order_summary.png")
