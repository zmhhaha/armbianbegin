"""
SQLite Data Service — 极简 HTTP API
GET  /health              → 健康检查
GET  /tables              → 列出所有表
POST /query               → 执行 SELECT（body: {"sql": "SELECT ..."})
POST /execute             → 执行 INSERT/UPDATE/DELETE（body: {"sql": "..."})
GET  /backup              → 下载当前数据库备份
"""
import os, sqlite3, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

DB_PATH = os.getenv("DB_PATH", "/data/data.db")


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode() if length else ""

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok", "db": DB_PATH})
        elif path == "/tables":
            try:
                conn = sqlite3.connect(DB_PATH)
                rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                conn.close()
                self._send_json({"tables": [r[0] for r in rows]})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/backup":
            try:
                with open(DB_PATH, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=data.db")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        sql = data.get("sql", "")
        if not sql:
            self._send_json({"error": "Missing sql field"}, 400)
            return

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql)
            if path == "/query" or sql.strip().upper().startswith("SELECT"):
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                self._send_json({"rows": rows, "count": len(rows)})
            else:
                conn.commit()
                affected = cur.rowcount
                conn.close()
                self._send_json({"affected": affected})
        except Exception as e:
            conn.close()
            self._send_json({"error": str(e)}, 500)

    def log_message(self, format, *args):
        pass  # 静默日志


if __name__ == "__main__":
    # 启动时自动建表
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_reports (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            summary TEXT,
            keywords TEXT,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

    port = int(os.getenv("PORT", "8000"))
    print(f"SQLite Data Service starting on :{port}, db={DB_PATH}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
