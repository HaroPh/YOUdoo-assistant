# backend/tests/test_main_rerank.py
"""`/v1/rerank` — reranker của project cho Open WebUI (engine "External").

VÌ SAO TỒN TẠI. Open WebUI có đường RAG RIÊNG cho tệp người dùng đính kèm,
tách khỏi đường RAG kho tài liệu công ty trong backend. Đường đó KHÔNG có
reranker (`rag.reranking_model = ""`, đọc 2026-09-25) — "rerank" chỉ là chấm
lại cosine, tức xếp thuần dense. Cho Open WebUI tự chạy reranker thì nó chạy
trên CPU (container không có GPU: ~1 s/lượt so với ~21 ms trên GPU) và tải
thêm một bản 2,2 GB. Endpoint này cho nó dùng chung ĐÚNG model đang nằm trên
GPU của backend.

HỢP ĐỒNG — đọc thẳng từ mã Open WebUI 0.11.0 đang chạy
(`open_webui/retrieval/models/external.py`), dạng Cohere/Jina:

    POST /v1/rerank   Authorization: Bearer <token>
    gửi:  {"model": ..., "query": "...", "documents": ["...", ...], "top_n": N}
    nhận: {"results": [{"index": i, "relevance_score": s}, ...]}

Open WebUI tự sắp `results` theo `index` rồi lấy `relevance_score` theo thứ tự
tài liệu. Lỗi bất kỳ (kể cả HTTP khác 2xx) → nó trả None → `RerankCompressor`
ghi cảnh báo và trả NGUYÊN danh sách gốc. Nên reranker hỏng thì endpoint trả
503, KHÔNG bịa điểm: điểm giả cho ra một thứ tự rác mà nhìn vẫn hợp lệ.
"""
import httpx
import pytest

from src import main as main_module

TOKEN = "token-thu-cho-rerank"


def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://test")


def _hdr(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _moi_truong(monkeypatch):
    monkeypatch.setenv("YOUDOO_API_TOKEN", TOKEN)
    yield
    main_module._state.clear()


@pytest.fixture
def cham(monkeypatch):
    """Giả `reranker.score_pairs`: ghi lại lời gọi, trả điểm theo độ dài văn
    bản (đủ để thứ tự KHÁC thứ tự gửi lên — không thì test sắp xếp tự đúng)."""
    ghi = {"goi": []}

    def _gia(query, texts):
        ghi["goi"].append((query, list(texts)))
        return [float(len(t)) for t in texts]

    from src.rag import reranker
    monkeypatch.setattr(reranker, "score_pairs", _gia)
    return ghi


BODY = {"model": "bge", "query": "kỷ luật lao động",
        "documents": ["ngắn", "dài hơn một chút", "dài nhất trong ba đoạn"],
        "top_n": 3}


@pytest.mark.asyncio
async def test_khong_token_thi_401(cham):
    async with _client() as c:
        r = await c.post("/v1/rerank", json=BODY)
    assert r.status_code == 401
    assert cham["goi"] == [], "chưa xác thực mà đã chạy model"


@pytest.mark.asyncio
async def test_token_sai_thi_401(cham):
    async with _client() as c:
        r = await c.post("/v1/rerank", json=BODY, headers=_hdr("sai"))
    assert r.status_code == 401
    assert cham["goi"] == []


@pytest.mark.asyncio
async def test_dung_hop_dong_open_webui(cham):
    async with _client() as c:
        r = await c.post("/v1/rerank", json=BODY, headers=_hdr())
    assert r.status_code == 200, r.text
    kq = r.json()["results"]
    assert sorted(x["index"] for x in kq) == [0, 1, 2], "mỗi tài liệu đúng một kết quả"
    # Đúng thứ Open WebUI làm: sắp theo index rồi lấy điểm.
    diem = [x["relevance_score"] for x in sorted(kq, key=lambda x: x["index"])]
    assert diem == [float(len(d)) for d in BODY["documents"]]
    assert cham["goi"] == [(BODY["query"], BODY["documents"])]


@pytest.mark.asyncio
async def test_xep_theo_diem_giam_dan(cham):
    """Quy ước Cohere/Jina. Open WebUI không cần, nhưng client khác có thể dựa
    vào — và thứ tự gửi lên ở đây cố ý KHÁC thứ tự điểm."""
    async with _client() as c:
        r = await c.post("/v1/rerank", json=BODY, headers=_hdr())
    kq = r.json()["results"]
    assert [x["index"] for x in kq] == [2, 1, 0]


@pytest.mark.asyncio
async def test_top_n_cat_ket_qua(cham):
    async with _client() as c:
        r = await c.post("/v1/rerank", json={**BODY, "top_n": 2}, headers=_hdr())
    assert [x["index"] for x in r.json()["results"]] == [2, 1]


@pytest.mark.asyncio
async def test_reranker_hong_thi_503_KHONG_bia_diem(monkeypatch):
    """`score_pairs` trả None khi tắt, khi hỏng, và VĨNH VIỄN sau lần hỏng đầu
    trong đời tiến trình. Trả 503 ⇒ Open WebUI bắt lỗi, dùng danh sách gốc."""
    from src.rag import reranker
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: None)
    async with _client() as c:
        r = await c.post("/v1/rerank", json=BODY, headers=_hdr())
    assert r.status_code == 503
    assert "results" not in r.json()


@pytest.mark.asyncio
async def test_khong_tai_lieu_thi_rong_va_khong_goi_model(cham):
    async with _client() as c:
        r = await c.post("/v1/rerank", json={**BODY, "documents": []}, headers=_hdr())
    assert r.status_code == 200
    assert r.json() == {"results": []}
    assert cham["goi"] == []


@pytest.mark.asyncio
async def test_thieu_query_thi_422(cham):
    async with _client() as c:
        r = await c.post("/v1/rerank", json={"documents": ["x"]}, headers=_hdr())
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_MOI_route_v1_deu_doi_token():
    """Liệt kê route THẬT của app thay vì danh sách viết tay. `test_main_auth`
    liệt kê tay hai endpoint kèm cảnh báo "bọc một cái quên cái kia là để hở
    đúng một nửa" — thêm route thứ ba đúng là lúc bẫy đó xảy ra. Test này bắt
    được cả route thêm SAU NÀY."""
    from starlette.routing import Route
    v1 = [(r.path, sorted(r.methods - {"HEAD", "OPTIONS"})[0])
          for r in main_module.app.routes
          if isinstance(r, Route) and r.path.startswith("/v1/")]
    assert {p for p, _ in v1} >= {"/v1/models", "/v1/chat/completions", "/v1/rerank"}, v1
    async with _client() as c:
        for path, method in v1:
            r = await c.request(method, path, json={})
            assert r.status_code == 401, f"{method} {path} trả {r.status_code} khi KHÔNG có token"
