FROM python:3.11-slim

WORKDIR /app

# Cài đúng version đã pin ở requirements.txt (mcp==1.28.0 — có sẵn FastMCP +
# SSE transport, không cần extra [cli]; psycopg2-binary cho logging vào
# PostgreSQL). Cài từ requirements.txt thay vì gõ lại version ở đây để
# Dockerfile không bao giờ lệch khỏi requirements.txt (bài học từ chính lỗi
# này: "mcp[cli]>=1.0.0" từng resolve ra mcp 2.0.0, thiếu mcp.server.fastmcp).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py odoo_call.py config.py security.py rate_limit.py event_log.py audit_chain.py helpers.py ./
COPY tools/ ./tools/

EXPOSE 8003

# FastMCP SSE server mặc định bind 0.0.0.0:8003 (đọc MCP_ODOO_PORT) → override bằng env hoặc args
CMD ["python", "server.py"]
