#!/usr/bin/env bash
# Tạo database "langfuse" trong container youdoo-postgres đã có, nếu chưa
# tồn tại. KHÔNG dùng CREATE DATABASE IF NOT EXISTS — cú pháp đó không được
# PostgreSQL hỗ trợ cho CREATE DATABASE (khác CREATE TABLE). An toàn chạy
# lại nhiều lần (idempotent) — nếu database đã tồn tại thì bỏ qua, không lỗi.
set -euo pipefail

EXISTS=$(docker exec youdoo-postgres psql -U "${POSTGRES_USER:-admin}" \
  -d "${POSTGRES_DB:-ai_assistant}" -tAc \
  "SELECT 1 FROM pg_database WHERE datname = 'langfuse'")

if [ "$EXISTS" = "1" ]; then
  echo "Database 'langfuse' đã tồn tại — bỏ qua."
else
  docker exec youdoo-postgres psql -U "${POSTGRES_USER:-admin}" \
    -d "${POSTGRES_DB:-ai_assistant}" -c "CREATE DATABASE langfuse"
  echo "Đã tạo database 'langfuse'."
fi
