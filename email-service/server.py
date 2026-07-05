"""
邮件发送微服务 — 常驻 K8s，通过 HTTP 接收其他服务的发信请求。
POST /send  {"to":"...","subject":"...","body":"..."}
"""
import os, json, smtplib
from email.message import EmailMessage
from http.server import HTTPServer, BaseHTTPRequestHandler

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/send":
            self._json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        to_addr = body.get("to", "")
        subject = body.get("subject", "")
        content = body.get("body", "")

        if not to_addr or not subject:
            self._json(400, {"error": "missing to/subject"})
            return

        try:
            msg = EmailMessage()
            msg["From"] = SMTP_FROM
            msg["To"] = to_addr
            msg["Subject"] = subject
            msg.set_content(content, subtype="html")

            if SMTP_PORT == 465:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as s:
                    s.login(SMTP_USER, SMTP_PASS)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
                    s.starttls()
                    s.login(SMTP_USER, SMTP_PASS)
                    s.send_message(msg)

            self._json(200, {"ok": True, "to": to_addr})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Email service starting on :{port} (SMTP: {SMTP_HOST}:{SMTP_PORT} user={SMTP_USER})")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
