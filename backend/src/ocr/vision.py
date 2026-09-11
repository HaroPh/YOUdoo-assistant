"""Máy đọc bảng bằng mô hình nhìn ảnh (VLM) — tầng 0 của OCR bậc 3.

Spec: docs/superpowers/specs/2026-09-11-ocr-bac-3-vlm-kiem-so-hoc-design.md
(§"Hợp đồng VLM", §"Nền (lát 2)"). Module này KHÔNG biết PDF, trang, DB hay
Tesseract: nhận PNG bytes, trả JSON theo hợp đồng. Số nó đọc chỉ được lưu khi
qua `so_hoc.classify_rows` — chuyện của tầng tài liệu, không phải đây.

Bốn thứ của nền (§18), tất cả ở đây:
1. Khoá RIÊNG `YOUDOO_VLM_API_KEY[_2.._9]` qua `providers.KeyRing` — không bao
   giờ đụng `GOOGLE_API_KEY*`. Không cấu hình → VLM TẮT, log có tên một lần.
2. Xoay khoá CHỈ khi 429; hết vòng → `VisionQuotaExhausted`, người gọi dừng VLM
   cho phần còn lại của lượt nạp.
3. Trần cứng `VLM_MAX_CALLS_PER_INGEST` — SUY LUẬN từ §10 (500 rpd/khoá, để lại
   ≥ 60% cho chatbot ⇒ 200), không đo. Vượt → `VisionCapReached`.
4. Đếm vào sổ `llm_usage` với alias `vlm-ocr` qua `store.record` nếu được tiêm.

VLM KHÔNG được xem text Tesseract (nếu xem, nó lặp số Tesseract và kiểm chéo
mất độc lập). Phản hồi thô được giữ nguyên trong `VisionTable.raw` để bắt làm
fixture (`tests/fixtures/ocr_bang_that/vlm_raw/`) — mọi thay đổi bộ kiểm sau
chạy offline trên đó.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from src.llm.catalog import spec_for
from src.llm.providers import KeyRing, client_for, keys_for_env

logger = logging.getLogger(__name__)

VLM_ENV = "YOUDOO_VLM_API_KEY"
VLM_MODEL_ENV = "YOUDOO_VLM_MODEL"
VLM_MODEL_DEFAULT = "gemini-3.5-flash-lite"
VLM_ALIAS = "vlm-ocr"                    # alias trong sổ llm_usage, tách khỏi chat
# Suy luận từ spec §10, KHÔNG đo: 500 rpd/khoá flash-lite, để ≥ 60% cho chatbot.
VLM_MAX_CALLS_PER_INGEST = 200
PROMPT_VERSION = "v1"

# Hợp đồng: chép, không diễn giải. `so_tien` là CHUỖI NGUYÊN VĂN (dấu chấm,
# ngoặc); công thức in trong nhãn giữ nguyên trong `nhan` — mã parse, không hỏi
# model trích. Phiên bản prompt nằm trong dấu vân tay đệm của tầng tài liệu.
PROMPT = """Đây là ảnh MỘT trang báo cáo tài chính Việt Nam dạng bảng chỉ tiêu.
Hãy CHÉP LẠI NGUYÊN VĂN bảng thành JSON, không suy diễn, không tính toán, không sửa số.

Trả về DUY NHẤT một object JSON theo đúng hình dạng này:
{"trang": {"mau": "<mã mẫu in trên trang, vd B01/BCTC hoặc B 01-DN, hoặc null>",
           "thong_tu": "<số thông tư in trên trang, vd 107/2017/TT-BTC, hoặc null>",
           "cot_gia_tri": ["<tên cột số thứ nhất nguyên văn>", "<tên cột số thứ hai>", ...]},
 "hang": [{"muc": "<đánh dấu STT nguyên văn: A-, I., 1., a), -, hoặc null>",
           "nhan": "<tên chỉ tiêu nguyên văn, GIỮ CẢ công thức in như (50=01+05+10)>",
           "ma_so": "<mã số nguyên văn hoặc null>",
           "thuyet_minh": "<ô thuyết minh nguyên văn hoặc null>",
           "so_tien": ["<ô số cột 1 nguyên văn>", "<ô số cột 2 nguyên văn>", ...]}]}

Quy tắc:
- Mỗi hàng của bảng là một phần tử `hang`, theo đúng thứ tự trên trang, kể cả hàng tiêu đề mục không có mã số (so_tien: []).
- `so_tien` có ĐÚNG số phần tử bằng số cột trong `cot_gia_tri`. Ô in dấu gạch ngang ghi "-". Ô trống ghi null. Số âm giữ nguyên dạng trong ngoặc, vd "(58.099.826.029)". GIỮ dấu chấm phân cách hàng nghìn.
- Không đưa ô thuyết minh (vd III.2, V.4) vào `so_tien`.
- Không bỏ hàng, không gộp hàng, không thêm hàng.
- Không viết gì ngoài object JSON."""

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class VisionUnavailable(RuntimeError):
    """Không có khoá VLM — trạng thái cấu hình, không phải lỗi."""


class VisionQuotaExhausted(RuntimeError):
    """Hết cả vòng khoá vì 429. Người gọi dừng VLM cho phần còn lại lượt nạp."""


class VisionCapReached(RuntimeError):
    """Chạm trần `VLM_MAX_CALLS_PER_INGEST`."""


class VisionBadResponse(ValueError):
    """Phản hồi không phải JSON theo hợp đồng. Mang độ dài để log, không mang nội dung."""


@dataclass(frozen=True)
class VisionTable:
    payload: dict
    raw: str
    model: str
    prompt_version: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def vlm_model_alias() -> str:
    return os.environ.get(VLM_MODEL_ENV) or VLM_MODEL_DEFAULT


def vlm_enabled() -> bool:
    return bool(keys_for_env(VLM_ENV))


def _text_of(content) -> str:
    """Gemini 3.x trả content là list khối; gộp các khối text. Bẫy đã trả giá
    hai lần trong repo (`.content` là list, không phải str)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict) and b.get("type") == "text":
                parts.append(str(b.get("text", "")))
        return "".join(parts)
    return str(content)


def parse_response(text: str) -> dict:
    """Bóc JSON khỏi phản hồi: bỏ rào ```json, lấy từ `{` đầu tới `}` cuối.
    Hỏng → `VisionBadResponse` với độ dài, KHÔNG kèm nội dung (log không được
    chứa số tiền đọc từ tài liệu người dùng)."""
    s = _JSON_FENCE.sub("", text or "")
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise VisionBadResponse(f"không có object JSON trong phản hồi ({len(text or '')} ký tự)")
    try:
        data = json.loads(s[i:j + 1])
    except json.JSONDecodeError as e:
        raise VisionBadResponse(f"JSON hỏng tại vị trí {e.pos} ({len(text or '')} ký tự)") from None
    if not isinstance(data, dict) or "hang" not in data:
        raise VisionBadResponse(f"JSON không có khoá `hang` ({len(text or '')} ký tự)")
    return data


def _is_rate_limit(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 429 or "429" in str(exc)


class VisionReader:
    """Một bộ đọc cho MỘT lượt nạp: giữ bộ đếm trần và vòng khoá.

    `client_factory(spec, api_key)` tiêm được (mặc định `providers.client_for`)
    để test bằng client giả — cùng khuôn `Router(client_factory=…)`.
    `store` là `UsageStore` (Postgres hay InMemory) hoặc None.
    """

    def __init__(self, *, client_factory=client_for, store=None,
                 max_calls: int = VLM_MAX_CALLS_PER_INGEST, ring: KeyRing | None = None) -> None:
        self._client_factory = client_factory
        self._store = store
        self._max_calls = max_calls
        self._ring = ring or KeyRing()
        self._clients: dict[int, object] = {}
        self.calls = 0
        self.failures = 0
        self._disabled_logged = False

    @property
    def model(self) -> str:
        return vlm_model_alias()

    def _client(self):
        idx, khoa = self._ring.current(VLM_ALIAS, VLM_ENV)
        if khoa is None:
            raise VisionUnavailable(f"không có khoá {VLM_ENV} — VLM tắt")
        if idx not in self._clients:
            self._clients[idx] = self._client_factory(spec_for(self.model), khoa)
        return self._clients[idx]

    def read_table(self, png: bytes) -> VisionTable:
        """PNG một trang → bảng theo hợp đồng. Ném một trong bốn lỗi có tên ở
        đầu module; người gọi biến chúng thành cảnh báo `IngestReport`."""
        if not vlm_enabled():
            if not self._disabled_logged:
                logger.info("VLM tắt: không có khoá %s — trang Tesseract hỏng giữ nguyên bậc ocr", VLM_ENV)
                self._disabled_logged = True
            raise VisionUnavailable(f"không có khoá {VLM_ENV}")
        if self.calls >= self._max_calls:
            raise VisionCapReached(f"đã gọi {self.calls} lượt, trần {self._max_calls}")

        from langchain_core.messages import HumanMessage
        msg = HumanMessage(content=[
            {"type": "text", "text": PROMPT},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}},
        ])
        so_khoa = max(1, len(keys_for_env(VLM_ENV)))
        for _ in range(so_khoa):
            client = self._client()
            self.calls += 1
            try:
                resp = client.invoke([msg])
            except Exception as e:                           # noqa: BLE001
                if _is_rate_limit(e):
                    if self._ring.rotate(VLM_ALIAS, VLM_ENV):
                        continue
                    raise VisionQuotaExhausted(f"hết {so_khoa} khoá {VLM_ENV} vì 429") from e
                self.failures += 1
                raise
            p, c, t = _usage(resp)
            self._record(p, c, t)
            text = _text_of(getattr(resp, "content", ""))
            try:
                payload = parse_response(text)
            except VisionBadResponse:
                self.failures += 1
                raise
            return VisionTable(payload=payload, raw=text, model=self.model,
                               prompt_version=PROMPT_VERSION, prompt_tokens=p,
                               completion_tokens=c, total_tokens=t)
        raise VisionQuotaExhausted(f"hết {so_khoa} khoá {VLM_ENV} vì 429")

    def _record(self, p: int, c: int, t: int) -> None:
        if self._store is None:
            return
        try:
            self._store.record(ts=datetime.now(timezone.utc), alias=VLM_ALIAS, provider="google",
                               upstream="google", prompt_tokens=p, completion_tokens=c, total_tokens=t)
        except Exception as e:                               # noqa: BLE001
            logger.warning("không ghi được sổ llm_usage cho %s: %s", VLM_ALIAS, e)


def _usage(resp) -> tuple[int, int, int]:
    """Cùng cách đọc như `Router._usage` nhánh Google: `usage_metadata`, tin
    `total_tokens` provider báo hơn p+c tự cộng."""
    meta = getattr(resp, "usage_metadata", None) or {}
    p = int(meta.get("input_tokens") or 0)
    c = int(meta.get("output_tokens") or 0)
    return p, c, int(meta.get("total_tokens") or (p + c))


def page_png(img) -> bytes:
    """Ảnh PIL → PNG bytes. Tầng tài liệu gọi với ảnh ĐÃ xoay theo OSD."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
