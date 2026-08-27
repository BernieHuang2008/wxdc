from config_utils import WEB_BASE_URL

def generate_html_table(data, user_no, base_date, output_filename):
    html_body = f"<h1>Auto Order Summary for {user_no}</h1>"
    html_body += f"<p>Week starting: {base_date.isoformat()}</p>"
    html_body += "<table border='1' cellspacing='0' cellpadding='5' style='border-collapse: collapse;'>"
    html_body += "<thead><tr style='background-color: #f2f2f2;'><th>Date</th><th>Breakfast</th><th>Lunch</th><th>Supper</th></tr></thead><tbody>"

    # Sort days
    sorted_days = sorted(data.keys(), key=lambda x: int(x))

    for day_key in sorted_days:
        day_info = data[day_key]
        date_str = day_info.get("date", "")
        auto_orders = day_info.get("auto_order", {})
        
        html_body += f"<tr><td>{date_str}</td>"
        
        for meal in ["breakfastorders", "lunchorders", "supperorders"]:
            html_body += "<td>"
            orders = auto_orders.get(meal, [])
            if orders:
                html_body += "<ul>"
                for item in orders:
                    name = item.get("name", "Unknown")
                    price = item.get("price", 0)
                    html_body += f"<li>{name} (￥{price})</li>"
                html_body += "</ul>"
            else:
                html_body += "-"
            html_body += "</td>"
        
        html_body += "</tr>"
        
    html_body += "</tbody></table>"

    # Add Action Buttons
    base_url = WEB_BASE_URL
    edit_url = f"{base_url}/pending_orders/{output_filename}"
    submit_url = f"{base_url}/submit_order_from_email/{output_filename}"

    html_body += f"""
    <div style="margin-top: 30px; font-family: sans-serif;">
        <p>Please review the order above.</p>
        <p>
            <a href="{edit_url}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-right: 15px;">编辑订单</a>
            <a href="{submit_url}" style="display: inline-block; padding: 10px 20px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px;">直接提交</a>
        </p>
        <p style="font-size: 12px; color: #888;">If the "Quick Submit" button doesn't work, please use the "Edit Order" page to submit.</p>
    </div>
    """

    return html_body