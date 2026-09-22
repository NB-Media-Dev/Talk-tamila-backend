import resend
from app.core.config import settings


def send_otp_email(to_email: str, otp: str) -> None:
    resend.api_key = settings.RESEND_API_KEY

    resend.Emails.send({
        "from": f"{settings.SMTP_FROM_NAME} <onboarding@resend.dev>",
        "to": [to_email],
        "subject": "Your Talk Tamila password reset code",
        "text": f"Your OTP is: {otp}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email.",
    })