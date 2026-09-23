#!/usr/bin/env bash
# Chạy 5 chân đo trên pool đã dựng: bash evals/bench_ngoai_legs.sh <zalo|tvpl> <thư-mục-kết-quả>
# Mỗi chân một tiến trình (reranker cache model một lần). Lượt bị loại: đổi tên
# *.DISCARDED.json trước khi chạy lại — không ghi đè (bài học R12).
set -u
DS=$1; OUT=$2
mkdir -p "$OUT"
PY=".venv/Scripts/python.exe -m evals.bench_ngoai leg $DS"
BGE=BAAI/bge-reranker-v2-m3; Q06=Qwen/Qwen3-Reranker-0.6B
run() {  # $1=nhãn  $2=model  $3=mode
  PYTHONIOENCODING=utf-8 RERANK_MODEL=$2 RAG_RERANK_MODE=$3 \
    $PY --leg "$1" --out "$OUT/$DS-$1.json" 2> "$OUT/$DS-$1.stderr.log"
  echo "[$DS/$1] exit=$? $(tail -1 "$OUT/$DS-$1.stderr.log")"
}
run no-rerank      "$BGE" blend
run bge-blend      "$BGE" blend
run bge-override   "$BGE" override
run qwen06-blend   "$Q06" blend
run qwen06-override "$Q06" override
