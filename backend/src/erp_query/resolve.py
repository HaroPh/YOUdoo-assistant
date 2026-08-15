"""Entity resolution via Odoo name_search, cộng tầng semantic tùy chọn cho
product.product (spec 2026-07-13-semantic-entity-resolution). Reports FACTS
(candidate matches + a needs_disambiguation flag); it never picks or prompts —
that policy lives in orchestration (C).

Kill-switch ERP_SEMANTIC_RESOLVE != "1" (hoặc model khác product.product) →
_resolve_legacy: hành vi trước feature từng bit — không semantic, không
reranker, không normalize."""
import math
import os
from difflib import SequenceMatcher

from .envelope import ok, fail_read
from .gateway import default_gateway
from . import semantic
from ..rag import reranker

MAX_CANDIDATES = 10


def _score(query: str, name: str) -> float:
    return round(SequenceMatcher(None, query.strip().lower(), (name or "").lower()).ratio(), 2)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _display(query, matches, exact, needs) -> str:
    if not matches:
        return f"Không tìm thấy '{query}'."
    if not needs:
        chosen = exact[0] if exact else matches[0]
        return f"Đã xác định: {chosen['name']} (ID {chosen['id']})."
    listing = "; ".join(f"{m['name']} (ID {m['id']})" for m in matches)
    return f"Có nhiều kết quả cho '{query}': {listing}."


def resolve_entity(model: str, query: str, limit: int = 5, *, gw=None) -> dict:
    if not (query or "").strip():
        # Finding 1: truy vấn rỗng → Odoo name_search coi là wildcard, trả bừa
        # các bản ghi → disambiguation vô nghĩa. Một tra cứu rỗng phải resolve
        # về KHÔNG CÓ, không phải "tất cả". Không chạm gateway.
        return ok({"matches": [], "needs_disambiguation": False},
                  "Không tìm thấy (thiếu từ khóa tra cứu).")
    gw = gw or default_gateway()
    if os.environ.get("ERP_SEMANTIC_RESOLVE", "1") == "1" and model == "product.product":
        return _resolve_enhanced(model, query, limit, gw)
    return _resolve_legacy(model, query, limit, gw)


def _resolve_legacy(model, query, limit, gw) -> dict:
    """Đường cũ nguyên vẹn — behavior trước feature, từng bit (spec §3)."""
    try:
        rows = gw.name_search(model, query, limit=limit)   # [(id, display_name), ...]
    except Exception as e:                                  # noqa: BLE001 — fail safe
        return fail_read("_resolve_legacy",
                         f"Lỗi tra cứu {model} — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
    matches = [{"id": rid, "name": name, "score": _score(query, name)} for rid, name in rows]
    exact = [m for m in matches if m["name"].strip().lower() == query.strip().lower()]
    needs = len(matches) > 1 and len(exact) != 1
    return ok({"matches": matches, "needs_disambiguation": needs},
              _display(query, matches, exact, needs))


def _resolve_enhanced(model, query, limit, gw) -> dict:
    """Union lexical + semantic, re-verify sống, cross-encoder confidence
    (spec §8). Index chỉ đề xuất ID — tên trong matches luôn là bản sống."""
    try:
        rows = gw.name_search(model, query, limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("_resolve_enhanced",
                         f"Lỗi tra cứu {model} — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
    cands = [{"id": rid, "name": name} for rid, name in rows]

    sem = semantic.semantic_candidates(model, query)
    if sem and len(cands) < MAX_CANDIDATES:
        have = {c["id"] for c in cands}
        extra = [s["odoo_id"] for s in sem
                 if s["odoo_id"] not in have][:MAX_CANDIDATES - len(cands)]
        if extra:
            try:
                fresh = gw.search_read(model, [["id", "in", extra]], ["display_name"])
                by_id = {r["id"]: r["display_name"] for r in fresh}
                # Giữ thứ tự RRF; ID archive/đã xóa không có trong fresh → tự rớt.
                cands += [{"id": i, "name": by_id[i]} for i in extra if i in by_id]
            except Exception:                               # noqa: BLE001
                pass   # fail-open: vứt nhánh semantic, giữ lexical (spec §8.5)

    if not cands:
        return ok({"matches": [], "needs_disambiguation": False},
                  f"Không tìm thấy '{query}'.")

    scores = reranker.score_pairs(query, [c["name"] for c in cands])
    if scores is not None:
        matches = [{"id": c["id"], "name": c["name"],
                    "score": round(_sigmoid(s), 4)}
                   for c, s in zip(cands, scores)]
        matches.sort(key=lambda m: m["score"], reverse=True)
        exact = [m for m in matches
                 if m["name"].strip().lower() == query.strip().lower()]
        if len(exact) == 1:
            needs = False   # rule cũ — ưu tiên trên cả ngưỡng (spec §8.7a)
        else:
            floor = float(os.environ.get("ERP_RESOLVE_AUTOPICK_FLOOR", "0.6"))
            gap = float(os.environ.get("ERP_RESOLVE_AUTOPICK_GAP", "0.15"))
            confident = matches[0]["score"] >= floor and (
                len(matches) == 1
                or matches[0]["score"] - matches[1]["score"] >= gap)
            needs = not confident
    else:
        # Reranker tắt/hỏng → SequenceMatcher trên chuỗi normalize (spec §8.6
        # — sửa luôn điểm mù dấu tiếng Việt của scorer cũ trên đường mới).
        matches = [{"id": c["id"], "name": c["name"],
                    "score": round(SequenceMatcher(
                        None, semantic.normalize(query),
                        semantic.normalize(c["name"])).ratio(), 2)}
                   for c in cands]
        exact = [m for m in matches
                 if m["name"].strip().lower() == query.strip().lower()]
        needs = len(matches) > 1 and len(exact) != 1
    return ok({"matches": matches, "needs_disambiguation": needs},
              _display(query, matches, exact, needs))


def _resolve_single(model, query, gw):
    """resolve_entity envelope -> (row_with_id_and_name, None) | (None, error_msg).
    Dùng chung cho mọi bounded context cần resolve MỘT bản ghi res.partner/
    product.product... theo tên trước khi đọc chi tiết (get_supplier_detail,
    get_customer_detail, get_product_suppliers)."""
    env = resolve_entity(model, query, gw=gw)
    if env.get("status") != "success":
        return None, env.get("display") or "Lỗi tra cứu."
    data = env.get("data") or {}
    matches = data.get("matches") or []
    if not matches:
        return None, f"Không tìm thấy '{query}'."
    if data.get("needs_disambiguation"):
        names = "; ".join(f"{m['name']} (ID {m['id']})" for m in matches)
        return None, f"Có nhiều kết quả cho '{query}': {names}."
    exact = [m for m in matches if (m["name"] or "").strip().lower() == query.strip().lower()]
    chosen = exact[0] if exact else matches[0]
    return {"id": chosen["id"], "name": chosen["name"]}, None
