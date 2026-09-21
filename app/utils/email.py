import smtplib
from email.mime.text import MIMEText
from app.core.config import settings


def send_otp_email(to_email: str, otp: str) -> None:
    subject = "Your Talk Tamila password reset code"
    body = f"Your OTP is: {otp}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())