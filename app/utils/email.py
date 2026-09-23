import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from app.core.config import settings


def send_otp_email(to_email: str, otp: str) -> None:
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = settings.BREVO_API_KEY

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email}],
        sender={"email": "trainee.developer@nbmediatech.org", "name": "Talk Tamila"},
        subject="Your Talk Tamila password reset code",
        text_content=f"Your OTP is: {otp}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email.",
    )

    api_instance.send_transac_email(send_smtp_email)
