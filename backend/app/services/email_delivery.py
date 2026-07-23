import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.errors import AppError


def send_email_code(email: str, code: str, purpose: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise AppError(
            "EMAIL_NOT_CONFIGURED",
            "邮件服务尚未配置，请联系管理员配置 SMTP",
            status_code=503,
        )
    labels = {
        "verify_email": "验证邮箱",
        "reset_password": "重置密码",
    }
    message = EmailMessage()
    message["Subject"] = f"文渊：{labels[purpose]}验证码"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"您的验证码是 {code}，10 分钟内有效。请勿将验证码告知他人。")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
