import logging

logger = logging.getLogger("talktamila.sms")


def send_otp_sms(phone: str, otp: str) -> None:  # noqa: ARG001 - otp is intentionally never logged
    """SMS delivery is not connected yet. The code itself is never written to the logs."""
    masked = "*" * max(len(phone) - 4, 0) + phone[-4:]
    logger.warning("SMS provider not configured: OTP for %s was not delivered.", masked)