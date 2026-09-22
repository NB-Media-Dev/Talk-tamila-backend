import smtplib
import ssl
from email.mime.text import MIMEText
from app.core.config import settings


def send_otp_email(to_email: str, otp: str) -> None:
    subject = "Your Talk Tamila password reset code"
    body = f"Your OTP is: {otp}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.SMTP_HOST, 465, context=context, timeout=10) as server:
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())