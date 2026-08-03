import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from email_utils import send_email


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Sending test email...")

    test_subject = "Test Email from WXDC Script"
    test_body = """
    <html>
        <body>
            <h1>This is a test email</h1>
            <p>If you see this, the send_email function is working correctly.</p>
            <p>Check the headers to verify DKIM signature.</p>

            <div style="margin-top: 30px; font-family: sans-serif;">
                <p>Test Buttons (Simulated Only):</p>
                <p>
                    <a href="#" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-right: 15px;">Edit Order</a>
                    <a href="#" style="display: inline-block; padding: 10px 20px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px;">Quick Submit</a>
                </p>
            </div>
        </body>
    </html>
    """

    recipient = "berniehuang2008@163.com"

    send_email(test_subject, test_body, recipient, use_dkim=True)
