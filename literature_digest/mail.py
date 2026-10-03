from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .analysis import require_llm, require_analysis_payload
from .config import valid_email
from .references import validate_reference_files


class MailSetupError(RuntimeError):
    pass


class DeliveryUncertain(RuntimeError):
    pass


def smtp_settings(config):
    m = config["mail"]
    values = {k: os.environ.get(m[k + "_env"], "") for k in ("host", "user", "password", "from")}
    if not m["enabled"]:
        raise MailSetupError("发件未启用；需要 mail.enabled=true 并显式使用 --send")
    if any(not value for value in values.values()):
        raise MailSetupError("SMTP 环境变量不完整；请在运行环境自行配置，不要把密码发到聊天或写入配置文件")
    if any("\r" in v or "\n" in v for v in (values["host"], values["user"], values["from"])):
        raise MailSetupError("SMTP 地址含非法换行")
    if not valid_email(values["from"]):
        raise MailSetupError("SMTP sender must be a single email address")
    return values


def send_smtp(payload, config, state, digest_id, smtp_ssl=smtplib.SMTP_SSL, smtp_starttls=smtplib.SMTP, now=None):
    """Injectable adapter. Unknown post-DATA outcomes are never automatically retried."""
    require_llm(config)
    require_analysis_payload(payload)
    if payload.get("transport") == "connector":
        raise MailSetupError("Connector outbox must use the connector receipt workflow, not SMTP")
    if not valid_email(payload.get("recipient")) or any(c in payload.get("subject", "") for c in "\r\n"):
        raise MailSetupError("Invalid recipient or mail header")
    local_today = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config["timezone"])).date().isoformat()
    if payload["harvest_until"] != local_today:
        raise MailSetupError("待发送日报不是今天生成的，已拒绝过期原稿；请 run --send 重新生成当前窗口日报")
    if state.payload_has_sent_aliases(payload):
        raise MailSetupError("这份待发送日报包含已在其他日报发送的论文，拒绝重复发送；请重新生成当前日报")
    try:
        references = validate_reference_files(payload.get("reference_files", []))
    except ValueError as exc:
        raise MailSetupError(str(exc)) from None
    values = smtp_settings(config)
    message = EmailMessage()
    message["From"], message["To"] = values["from"], payload["recipient"]
    message["Subject"] = payload["subject"]
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = f"<{digest_id}@literature-digest.local>"
    message.set_content(payload["text"])
    message.add_alternative(payload["html"], subtype="html")
    for item in references:
        maintype, subtype = item["content_type"].split("/", 1)
        message.add_attachment(item["content"].encode("utf-8"), maintype=maintype, subtype=subtype,
                               filename=item["filename"], params={"charset": "utf-8"})
    server = None
    accepted = False
    try:
        if config["mail"]["security"] == "ssl":
            server = smtp_ssl(values["host"], int(config["mail"]["port"]), timeout=45, context=ssl.create_default_context())
        else:
            server = smtp_starttls(values["host"], int(config["mail"]["port"]), timeout=45)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(values["user"], values["password"])
    except Exception:
        if server:
            try:
                server.close()
            except Exception:
                pass
        # No DATA was attempted, so a later retry cannot duplicate a mail.
        raise MailSetupError("SMTP 连接、TLS 或登录失败；邮件未尝试发送，修复配置后可重试") from None
    state.status(digest_id, "sending")
    try:
        refused = server.send_message(message, from_addr=values["from"], to_addrs=[payload["recipient"]])
        if refused:
            raise DeliveryUncertain("SMTP 接收结果需要人工检查")
        accepted = True
        state.mark_sent(digest_id)
    except Exception:
        state.status(digest_id, "uncertain")
        raise DeliveryUncertain("SMTP 发送/落账结果不确定，已停止自动重试；请核对发件与收件记录后使用 resolve") from None
    finally:
        try:
            server.quit()
        except Exception:
            # QUIT failure after accepted DATA must not turn success into a resend.
            try:
                server.close()
            except Exception:
                pass
    return accepted
