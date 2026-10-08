import logging

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from app.core.config import settings

logger = logging.getLogger(__name__)

def send_otp_email(to_email: str, otp: str) -> None:
    if not settings.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not set")
    if not settings.SMTP_FROM_EMAIL:
        raise RuntimeError("SMTP_FROM_EMAIL is not set")

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = settings.BREVO_API_KEY

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    message = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email}],
        sender={"email": settings.SMTP_FROM_EMAIL, "name": settings.SMTP_FROM_NAME},
        subject="Your Talk Tamila password reset code",
        text_content=(
            f"Your OTP is: {otp}\n\n"
            "This code expires in 10 minutes. If you didn't request this, ignore this email."
        ),
    )

    try:
        api_instance.send_transac_email(message)
    except ApiException as exc:
        logger.error("Brevo rejected the email: status=%s body=%s", exc.status, exc.body)
        raise