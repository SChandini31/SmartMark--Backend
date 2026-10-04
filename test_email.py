from app.services.email_service import send_email

send_email(
    "chandinisaravana@gmail.com",
    "SmartMark Test Email",
    "Hello! This is a test email from SmartMark."
)

print("Email sent successfully!")