import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def send_email(to_email: str, subject: str, body: str):
    print("🔥 SEND_EMAIL FUNCTION CALLED 🔥")

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM")

    try:
        print(f"[EMAIL] Sending email to: {to_email}")

        message = EmailMessage()
        message["From"] = f"SmartMark <{email_from}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=20
        ) as server:

            print("[EMAIL] Connecting to SMTP...")
            server.starttls()

            print("[EMAIL] Logging into SMTP...")
            server.login(smtp_username, smtp_password)

            print("[EMAIL] Sending message...")
            server.send_message(message)

        print("[EMAIL] Email sent successfully")

    except Exception as e:
        print(f"[EMAIL ERROR] {type(e).__name__}: {e}")
        raise