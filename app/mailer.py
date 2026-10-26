"""관리자(본인)에게만 보내는 메일. 설정이 없으면 출력만 하고 넘어간다."""
import os
import smtplib
from email.message import EmailMessage


def run_link() -> str:
    repo, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if repo and run_id:
        return f"https://github.com/{repo}/actions/runs/{run_id}"
    return ""


def send_admin(subject: str, body: str) -> bool:
    user = os.environ.get("MAIL_USER")
    pw = os.environ.get("MAIL_APP_PASSWORD")
    to = os.environ.get("MAIL_ADMIN") or user
    if not (user and pw and to):
        print(f"[admin mail skipped] {subject}\n{body}")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception as e:  # 메일 실패가 본 작업을 멈추면 안 됨
        print(f"[admin mail failed] {type(e).__name__}")
        return False
