"""Bước 2 hướng B: truy hồi của TA vs của OPEN WEBUI trên cùng hai tệp đính kèm.

Vì sao cần: trong hai ngày, tầng truy hồi của Open WebUI là mắt gãy BA lần
(MiniLM/top_k 3; "mục 29" trả về chunk mục lục; hàng mã 52 lượt đầu không lấy
được, lượt sau lấy được chỉ vì chuỗi dấu dài hơn đổi BM25/vector). Trước khi
quyết có lấy lại tầng truy hồi (bước 3: nạp tệp vào corpus ta + trả biên nhận),
phải biết retriever của ta có thật sự hơn không — chứ không phải "chắc là hơn".

THƯỚC DÙNG CHUNG, chạy được trên cả hai hệ: **đáp án có trong ngữ cảnh lấy về
@k**. Mỗi hệ trả một túi chunk theo pipeline THẬT của nó; ta chỉ hỏi chuỗi đáp
án có nằm trong túi đó không. Không LLM, không tốn hạn mức, không phải khớp
lược đồ nhãn giữa hai hệ (nhãn của ta là (tệp, section_path), của họ là chunk
cắt theo ký tự — không so trực tiếp được).

Đáp án lấy từ FIXTURE ĐÁP ÁN TAY (`tests/fixtures/ocr_bang_that/*.json`, đọc từ
ảnh trước khi nhìn output máy) và từ các lượt hỏi thật đã ghi trong ghi chú thi
hành. Không có câu nào đáp án do tôi suy ra lúc viết tệp này.

HAI CHÂN:
- TA: ingest hai PDF vào SCHEMA NHÁP (`RAG_SCHEMA`, mặc định `eval_attach`) —
  không đụng corpus sản xuất — rồi gọi đúng `retrieve.retrieve()`, tức cả
  hybrid + chân bỏ dấu + rerank như production.
- HỌ: gọi CHÍNH MÃ CỦA HỌ trong container (`query_doc_with_hybrid_search` +
  `get_embedding_function`), đọc cấu hình sống từ `webui.db`. Không chép lại
  logic của họ — chép lại là đo một thước khác thước đang gác.

Chạy (Docker + Ollama :11435 phải sống; ingest sẽ gọi VLM ~13 lượt):
    cd backend
    RAG_SCHEMA=eval_attach python -m tools.compare_attachment_retrieval
Kết quả ghi vào `tools/compare_attachment_retrieval_result.txt`.
"""
import json
import os
import subprocess
import sys
import unicodedata

THU_MUC_PDF = r"D:\Youdoo\tmp-docs\ocr-scan-that"
K = 10                      # bằng `rag.top_k` của Open WebUI, để so cùng ngân sách
KET_QUA = os.path.join(os.path.dirname(__file__), "compare_attachment_retrieval_result.txt")

# (tệp, câu hỏi, các biến thể đáp án chấp nhận, nguồn đáp án)
CASES = [
    ("DVT_2022.pdf", "tổng tài sản đầu năm là bao nhiêu",
     ["69.862.687.223"], "fixture DVT_2022_tr7.json mã 50 / so_dau_nam"),
    ("DVT_2022.pdf", "tổng cộng tài sản cuối năm là bao nhiêu",
     ["79.611.117.804"], "fixture tr7 mã 50 / so_cuoi_nam"),
    ("DVT_2022.pdf", "phân phối cho các quỹ năm trước là bao nhiêu",
     ["358.487.382"], "fixture tr9 mã 52 / nam_truoc — câu đã trượt lượt đầu trên Open WebUI"),
    ("DVT_2022.pdf", "chi phí thuế thu nhập doanh nghiệp năm nay là bao nhiêu",
     ["7.078.394.234"], "fixture tr9 mã 40 / nam_nay"),
    ("DVT_2022.pdf", "các khoản phải thu cuối năm là bao nhiêu",
     ["19.078.257.265"], "fixture tr7 mã 10 / so_cuoi_nam"),
    ("DVT_2022.pdf", "khấu hao luỹ kế tài sản cố định hữu hình cuối năm",
     ["58.099.826.029"], "fixture tr7 mã 33 / so_cuoi_nam (âm, in trong ngoặc)"),
    ("NTC_2025.pdf", "đầu tư góp vốn vào đơn vị khác là bao nhiêu",
     ["10.296.000.000"], "lượt hỏi thật 2026-09-11, hàng mã 253"),
    ("NTC_2025.pdf", "gửi cho tôi text thô của mục 29",
     ["CAM KET THUÊ", "CAM KẾT THUÊ"], "tr61 — câu đã trượt hai lần trên Open WebUI"),
    ("NTC_2025.pdf", "cam kết thuê hoạt động đến 1 năm là bao nhiêu",
     ["5.753.213.767"], "tr61 mục 29.2, đã đọc tay trong ghi chú thi hành"),
    ("NTC_2025.pdf", "tiền và tương đương tiền cuối năm là bao nhiêu",
     ["73.921.137.970"], "tr38 mã 70 / năm nay"),
    ("NTC_2025.pdf", "lưu chuyển tiền thuần từ hoạt động kinh doanh năm nay",
     ["21.577.867.782"], "tr38 mã 20 / năm nay"),
]


def fold(s: str) -> str:
    """Bỏ dấu + hạ chữ, để so nhãn chữ không bị lệch vì OCR đọc thiếu dấu."""
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def hit(texts: list[str], dap_an: list[str]) -> int | None:
    """Thứ hạng (1-based) của chunk ĐẦU TIÊN chứa đáp án; None nếu không có."""
    muc_tieu = [fold(d) for d in dap_an]
    for i, t in enumerate(texts, 1):
        ft = fold(t)
        if any(m in ft for m in muc_tieu):
            return i
    return None


# ── chân TA ──────────────────────────────────────────────────────────────────

def our_side() -> dict:
    from src.rag import db as _db
    from src.rag.config import RAG_SCHEMA
    from src.rag.ingest import ingest_path
    from src.rag.retrieve import retrieve

    if RAG_SCHEMA == "public":
        sys.exit("TỪ CHỐI: RAG_SCHEMA=public sẽ nạp tệp người dùng vào corpus SẢN "
                 "XUẤT. Chạy lại với RAG_SCHEMA=eval_attach.")
    conn = _db.connect()
    _db.ensure_schema(conn, RAG_SCHEMA)
    for ten in sorted({c[0] for c in CASES}):
        rep = ingest_path(os.path.join(THU_MUC_PDF, ten), conn=conn)
        print(f"  [ta] nạp {ten}: {rep.render().splitlines()[0] if rep.render() else 'ok'}", flush=True)
    n = conn.execute("SELECT count(*) FROM rag_chunks").fetchone()[0]
    print(f"  [ta] schema {RAG_SCHEMA}: {n} chunk", flush=True)

    out = {}
    for tep, q, dap_an, _ in CASES:
        kq = retrieve(q, k=K)
        # Truy hồi của ta quét CẢ schema nháp (hai tệp), không lọc theo tệp —
        # giống production hôm nay: không có phạm vi theo tệp. Đó chính là thứ
        # bước 3 sẽ thêm, nên ghi lại tệp của chunk trúng để thấy có lẫn không.
        texts = [c.text for c in kq.chunks]
        r = hit(texts, dap_an)
        nguon = [os.path.basename(str(c.source_file).replace("\\", "/")) for c in kq.chunks]
        out[(tep, q)] = {"rank": r, "n": len(texts),
                         "lech_tep": r is not None and nguon[r - 1] != tep}
    return out


# ── chân HỌ: chạy CHÍNH mã của họ trong container ────────────────────────────

_THEIR_SCRIPT = r'''
import asyncio, json, sqlite3, sys
from open_webui.retrieval.utils import query_doc_with_hybrid_search, query_doc, get_embedding_function

c = sqlite3.connect("file:/app/backend/data/webui.db?mode=ro", uri=True)
def cfg(k, d=None):
    # Cot `value` khai JSON nhung SQLite luu nguyen kieu: so thi ra int, chuoi
    # thi ra chuoi CO ngoac kep. json.loads(int) nem TypeError.
    r = c.execute("select value from config where key=?", (k,)).fetchone()
    if not r or r[0] is None:
        return d
    v = r[0]
    if isinstance(v, (int, float, bool)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v

coll = {}
for fn in json.loads(sys.argv[1]):
    r = c.execute("select meta from file where filename=? and json_extract(data,'$.content') is not null "
                  "order by created_at desc limit 1", (fn,)).fetchone()
    coll[fn] = json.loads(r[0]).get("collection_name") if r else None

ef = get_embedding_function(cfg("rag.embedding_engine", ""), cfg("rag.embedding_model"), None,
                            cfg("rag.ollama.base_url"), cfg("rag.ollama.api_key", "") or "",
                            cfg("rag.embedding_batch_size", 1))
k = cfg("rag.top_k", 10)
# Ghi de k_reranker khi duoc yeu cau: `RerankCompressor` LUON cat xuong top_n =
# k_reranker, ke ca khi khong co reranking model (no tu cham lai bang cosine).
# Nen top_k_reranker=3 bien hybrid thanh dense-top-3. Do ca hai de tach CAU HINH
# khoi PIPELINE.
kr_override = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
# Tuy chon THEM (2026-09-25): ghi de k, va gan reranker NGOAI (backend Youdoo
# /v1/rerank) — dung CHINH ExternalReranker + get_reranking_function cua ho.
opt = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
if opt.get("k"):
    k = opt["k"]
dem = {"ok": 0, "none": 0}
rf = None
if opt.get("rerank"):
    from open_webui.retrieval.models.external import ExternalReranker
    from open_webui.retrieval.utils import get_reranking_function
    rr = ExternalReranker(api_key=opt["rerank"]["key"], url=opt["rerank"]["url"],
                          model="bge-reranker-v2-m3")
    _goc = rr.predict
    def _dem(sentences, user=None):
        # ExternalReranker tra None khi loi BAT KY; RerankCompressor khi do tra
        # NGUYEN danh sach goc trong im lang — tuc do "khong rerank" ma tuong la
        # co. Dem de ben ngoai tu choi so lieu neu co luot nao hong.
        r = _goc(sentences, user=user)
        dem["ok" if r is not None else "none"] += 1
        return r
    rr.predict = _dem
    rf = get_reranking_function("external", "bge-reranker-v2-m3", rr)
kr = kr_override or cfg("rag.top_k_reranker", k)

async def one(cn, q):
    if cfg("rag.enable_hybrid_search", False):
        res = await query_doc_with_hybrid_search(
            collection_name=cn, collection_result=None, query=q,
            embedding_function=lambda query, prefix=None: ef(query, prefix=prefix, user=None),
            k=k, reranking_function=rf, k_reranker=kr,
            r=cfg("rag.relevance_threshold", 0), hybrid_bm25_weight=cfg("rag.hybrid_bm25_weight", 0.5),
            enable_enriched_texts=cfg("rag.enable_hybrid_search_enriched_texts", False))
    else:
        emb = await ef(q, prefix=None, user=None)
        res = query_doc(collection_name=cn, query_embedding=emb, k=k)
    return (res or {}).get("documents", [[]])[0]

out = []
for fn, q in json.loads(sys.argv[2]):
    cn = coll.get(fn)
    if not cn:
        out.append({"tep": fn, "q": q, "loi": "khong tim thay collection"}); continue
    try:
        out.append({"tep": fn, "q": q, "docs": asyncio.run(one(cn, q))})
    except Exception as e:
        out.append({"tep": fn, "q": q, "loi": f"{type(e).__name__}: {e}"})
print("===JSON===")
print(json.dumps({"rows": out, "dem": dem, "k": k, "kr": kr}, ensure_ascii=False))
'''


def their_side(k_reranker: int | None = None, opt: dict | None = None) -> dict:
    teps = sorted({c[0] for c in CASES})
    pairs = [[c[0], c[1]] for c in CASES]
    p = subprocess.run(
        # `WEBUI_SECRET_KEY` chỉ dùng để KÝ JWT; lượt này chỉ đọc nên đặt giá
        # trị dùng-một-lần cho tiến trình `exec` — KHÔNG đụng tiến trình đang
        # chạy của họ, và `webui.db` mở chế độ chỉ-đọc.
        ["docker", "exec", "-i", "-e", "WEBUI_SECRET_KEY=probe-chi-doc",
         "youdoo-open-webui", "python", "-c", _THEIR_SCRIPT,
         json.dumps(teps), json.dumps(pairs, ensure_ascii=False),
         json.dumps(k_reranker), json.dumps(opt or {})],
        capture_output=True, text=True, encoding="utf-8")
    if "===JSON===" not in (p.stdout or ""):
        sys.exit(f"chân HỌ thất bại:\n{(p.stdout or '')[-800:]}\n{(p.stderr or '')[-1500:]}")
    goi = json.loads(p.stdout.split("===JSON===", 1)[1].strip())
    data, dem = goi["rows"], goi["dem"]
    if (opt or {}).get("rerank") and (dem["none"] > 0 or dem["ok"] == 0):
        sys.exit(f"reranker ngoài KHÔNG trả điểm ({dem}) — Open WebUI đã âm thầm dùng "
                 f"danh sách gốc, số đo sẽ là 'không rerank' giả làm 'có rerank'. "
                 f"Backend có đang chạy mã có /v1/rerank không?")
    out = {}
    for row, (tep, q, dap_an, _) in zip(data, CASES):
        if "loi" in row:
            out[(tep, q)] = {"rank": None, "n": 0, "loi": row["loi"]}
        else:
            out[(tep, q)] = {"rank": hit(row["docs"], dap_an), "n": len(row["docs"])}
    out["_cau_hinh"] = {"k": goi["k"], "kr": goi["kr"], "dem": dem}
    return out


def main() -> None:
    # `.env` ở GỐC repo (DATABASE_URL, OLLAMA_URL, khoá VLM). Nạp tại đây thay
    # vì bắt người chạy tự export — cùng cách `tests/conftest.py` làm.
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    print("chân HỌ, như ĐANG cấu hình…", flush=True)
    ho = their_side()
    print("chân HỌ, với k_reranker = top_k (bỏ trần)…", flush=True)
    ho10 = their_side(k_reranker=K)
    print("chân TA (ingest schema nháp + retrieve thật)…", flush=True)
    ta = our_side()

    L = [f"Truy hồi TA vs OPEN WEBUI trên tệp đính kèm — k={K}, thước: đáp án có "
         f"trong ngữ cảnh lấy về", ""]
    L.append(f"{'tệp':14}{'câu hỏi':50}{'TA':>5}{'HỌ':>5}{'HỌ+kr':>7}  ghi chú")
    n_ta = n_ho = n_ho10 = 0
    for tep, q, _dap_an, nguon in CASES:
        a, b, c2 = ta[(tep, q)], ho[(tep, q)], ho10[(tep, q)]
        n_ta += a["rank"] is not None
        n_ho += b["rank"] is not None
        n_ho10 += c2["rank"] is not None
        gc = []
        if a.get("lech_tep"):
            gc.append("TA trúng chunk của TỆP KHÁC")
        if b.get("loi"):
            gc.append(f"HỌ lỗi: {b['loi']}")
        r = lambda x: ("#" + str(x["rank"])) if x["rank"] else "—"
        L.append(f"{tep[:13]:14}{q[:49]:50}{r(a):>5}{r(b):>5}{r(c2):>7}  "
                 f"{'; '.join(gc) or nguon}")
    L.append("")
    k0 = (CASES[0][0], CASES[0][1])
    L.append(f"TỔNG: TA {n_ta}/{len(CASES)} · HỌ như-cấu-hình {n_ho}/{len(CASES)} · "
             f"HỌ bỏ trần k_reranker {n_ho10}/{len(CASES)}")
    L.append(f"Số chunk giao mỗi lượt: TA {ta[k0]['n']} · HỌ {ho[k0]['n']} · HỌ+kr {ho10[k0]['n']}")
    L.append("")
    L.append("`RerankCompressor` của Open WebUI LUÔN cắt xuống top_n = k_reranker, kể cả")
    L.append("khi không có reranking model — khi đó nó TỰ chấm lại bằng cosine embedding.")
    L.append("Nên top_k=10 + top_k_reranker=3 = lấy 10, giao 3, xếp thuần dense: phần đóng")
    L.append("góp của BM25 cho hạng 4-10 bị bỏ. Đó là cấu hình, không phải pipeline.")
    txt = "\n".join(L)
    print("\n" + txt)
    with open(KET_QUA, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")


KET_QUA_RERANK = os.path.join(os.path.dirname(__file__), "compare_attachment_rerank_result.txt")


def rerank_sweep() -> None:
    """CHỈ chân HỌ — có nên nối reranker của project (/v1/rerank) vào Open WebUI?

    Thêm 2026-09-25. Không chạy chân TA (nó gọi VLM ~13 lượt, tốn hạn mức) vì
    câu hỏi ở đây chỉ nằm trong Open WebUI: cùng pipeline của họ, khác đúng
    một thứ là hàm rerank. Mức nền 10/11 của hàng #26 là dòng "cosine, kr=10".

    Thước vẫn là "đáp án có trong ngữ cảnh giao cho model". Ít chunk hơn thì
    khó chứa đáp án hơn — nên cái reranker phải chứng minh là giữ được đáp án
    với ÍT chunk hơn, không phải thắng khi cùng số chunk.
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    rr = {"url": "http://host.docker.internal:8002/v1/rerank",
          "key": os.environ["YOUDOO_API_TOKEN"]}
    cau_hinh = [
        ("NHƯ ĐANG CẤU HÌNH (đọc webui.db)", None, None),
        ("cosine (không reranker), k=10 kr=10", 10, {"k": 10}),
        ("reranker project,        k=10 kr=10", 10, {"k": 10, "rerank": rr}),
        ("reranker project,        k=10 kr=5 ", 5, {"k": 10, "rerank": rr}),
        ("reranker project,        k=10 kr=3 ", 3, {"k": 10, "rerank": rr}),
    ]
    L, chi_tiet = [], {}
    for ten, kr, opt in cau_hinh:
        print(f"chân HỌ: {ten.strip()}…", flush=True)
        kq = their_side(k_reranker=kr, opt=opt)
        ch = kq.pop("_cau_hinh")
        trung = sum(v["rank"] is not None for v in kq.values())
        n = max(v["n"] for v in kq.values())
        goi = f"reranker trả điểm {ch['dem']['ok']} lượt" if opt and opt.get("rerank") else "không reranker"
        L.append(f"{ten}  → {trung}/{len(CASES)}   (k={ch['k']}, kr={ch['kr']}, "
                 f"giao tối đa {n} chunk; {goi})")
        chi_tiet[ten] = kq
    L.append("")
    L.append("Từng câu (hạng chunk đầu tiên chứa đáp án; — = không có trong ngữ cảnh):")
    for tep, q, _dap, _nguon in CASES:
        hang = "  ".join(f"{(chi_tiet[t][(tep, q)]['rank'] or '—'):>2}" for t, _k, _o in cau_hinh)
        L.append(f"  [{hang}]  {tep[:8]}  {q[:52]}")
    txt = chr(10).join(L)
    print(txt)
    with open(KET_QUA_RERANK, "w", encoding="utf-8") as f:
        f.write(txt + chr(10))


if __name__ == "__main__":
    if "--rerank-sweep" in sys.argv:
        rerank_sweep()
    else:
        main()
