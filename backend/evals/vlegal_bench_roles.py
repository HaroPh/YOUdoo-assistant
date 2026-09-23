# backend/evals/vlegal_bench_roles.py
"""Phân loại câu hỏi VLegal-Bench theo 4 vai thật của hệ thống (src/agents/roles.py).

Nguồn: github.com/hieunguyen1053/vlegal-bench — 10.467 câu, 23 tác vụ pháp lý
tiếng Việt, closed-book (không có kho văn bản/đoạn-vàng để đo retrieval, chỉ
đo kiến thức/suy luận của LLM). Giấy phép **CC BY-NC-ND 4.0** (Copyright ©
2025 VLegal-Bench/CMC-OpenAI) — cấm rõ ràng "modifying, transforming... or
creating derivative works". Attribution bắt buộc khi dùng: "Dataset created
by CMC-OpenAI".

QUAN TRỌNG — vì sao module này KHÔNG ghi tệp đã chia ra đĩa: bộ chia theo vai
(accounting/sales/warehouse/mix/chung) tự nó LÀ một derivative work. Giữ nó
lại — kể cả chỉ trong repo nội bộ, không chia sẻ ra ngoài — vẫn phạm điều
khoản NoDerivatives (điều khoản cấm TẠO RA, không chỉ cấm CHIA SẺ). Vì vậy:

- Bản gốc, KHÔNG sửa: `git clone https://github.com/hieunguyen1053/vlegal-bench`
  vào `backend/evals/external-data/vlegal-bench/` (đã gitignore, không commit).
- Chỉ kịch bản phân loại này được commit — chạy lại trên bản gốc mỗi lần cần
  số liệu, không lưu kết quả `classify()`/`summarize()` thành tệp thường trực.

Vai `admin` KHÔNG có bộ từ khoá riêng: `RoleCfg("admin", ..., unrestricted=True,
rag_visibility=UNRESTRICTED)` trong `src/agents/roles.py` nghĩa là admin thấy
TOÀN BỘ tập, không lọc — coi nó là một miền hẹp riêng (như lần đầu tôi làm) là
bịa, hệ thống không có vai HR/luật chung.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

# 3 vai có miền nghiệp vụ HẸP thật trong roles.py (RoleCfg own/needs_sign_off
# khác nhau, MCP_* khác cổng). "admin" cố ý KHÔNG có mặt ở đây — xem docstring.
ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "accounting": ("thuế", "hóa đơn", "kế toán", "bảo hiểm xã hội", "quyết toán",
                   "ngân sách", "kiểm toán", "tài chính", "vốn đầu tư"),
    "sales": ("hợp đồng mua bán", "mua bán hàng hóa", "thương mại", "khách hàng",
              "chiết khấu", "giá cả", "bán hàng", "hợp đồng thương mại"),
    "warehouse": ("kho hàng", "vận chuyển", "giao hàng", "tồn kho",
                  "xuất nhập khẩu", "hải quan", "logistics"),
}

MIX = "mix"
CHUNG = "chung"
ADMIN = "admin"  # không lọc — xem summarize()

_TEXT_FIELDS = ("question", "answers", "instruction")


def classify(text: str) -> str:
    """Một trong accounting/sales/warehouse (khớp đúng 1 vai), `mix` (khớp
    ≥2), hoặc `chung` (không khớp vai hẹp nào — vẫn thuộc phạm vi `admin`)."""
    folded = text.lower()
    hits = [role for role, kws in ROLE_KEYWORDS.items()
            if any(kw in folded for kw in kws)]
    if not hits:
        return CHUNG
    if len(hits) > 1:
        return MIX
    return hits[0]


def record_text(row: dict) -> str:
    return " ".join(str(row.get(k, "")) for k in _TEXT_FIELDS)


def iter_records(root: str):
    """Đọc `*/*.jsonl` dưới `root` (bản clone gốc, không sửa). Bỏ qua dòng
    rỗng/hỏng JSON thay vì sập — dữ liệu bên thứ ba không đảm bảo sạch tuyệt
    đối theo từng dòng."""
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def summarize(root: str) -> dict[str, int]:
    """Đếm theo bucket. `admin` = tổng toàn bộ (không lọc, xem docstring)."""
    counts = {role: 0 for role in ROLE_KEYWORDS}
    counts[MIX] = 0
    counts[CHUNG] = 0
    total = 0
    for row in iter_records(root):
        counts[classify(record_text(row))] += 1
        total += 1
    counts[ADMIN] = total
    return counts


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Đếm câu VLegal-Bench theo vai — KHÔNG ghi tệp đã chia "
                     "(xem docstring module: NoDerivatives).")
    ap.add_argument("--root", required=True,
                    help="Thư mục bản clone gốc VLegal-Bench (chưa sửa)")
    a = ap.parse_args(argv)
    counts = summarize(a.root)
    total = counts[ADMIN]
    print(f"tong so cau: {total}")
    for role in (*ROLE_KEYWORDS, MIX, CHUNG):
        v = counts[role]
        print(f"{role}: {v} ({100 * v / total:.1f}%)" if total else f"{role}: 0")
    print(f"{ADMIN} (unrestricted, khong loc): {total} (100.0%)")


if __name__ == "__main__":
    main()
