"""Kế toán hạn mức free-tier (spec SP-1 §2).

Chính sách thuần — KHÔNG biết Postgres tồn tại. Mọi thứ đi qua UsageStore, nên
toàn bộ file này test được bằng kho trong bộ nhớ và một đồng hồ giả.
"""
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum

from .catalog import ModelSpec
from .store import UsageStore

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    OK = "ok"
    RPM = "rpm_exhausted"
    TPM = "tpm_exhausted"
    RPD = "rpd_exhausted"
    COOLDOWN = "cooldown"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BudgetLedger:
    def __init__(self, store: UsageStore, clock=None) -> None:
        self._store = store
        self._clock = clock or _utcnow
        # Cooldown chỉ nằm trong bộ nhớ có chủ đích: nó ngắn (giây tới phút),
        # nên mất khi khởi động lại là vô hại — cùng lắm thử lại một provider
        # đang ốm và ăn thêm một cái 429, mà 429 thì chuỗi fallback đã xử lý.
        self._cooldowns: dict[str, datetime] = {}

    # ── Khoá gộp ────────────────────────────────────────────────────────────
    def _scope_kwargs(self, spec: ModelSpec) -> dict:
        """quota_scope="model" (Google, Groq) → gộp theo alias.
        quota_scope="account" (OpenRouter) → gộp theo provider: mọi model free
        của OpenRouter chia chung một ví ~50 lượt/ngày."""
        if spec.quota_scope == "account":
            return {"provider": spec.provider}
        return {"alias": spec.alias}

    # ── Đọc ─────────────────────────────────────────────────────────────────
    def can_afford(self, spec: ModelSpec, base_tokens: int) -> Verdict:
        now = self._clock()

        until = self._cooldowns.get(spec.alias)
        if until is not None and now < until:
            return Verdict.COOLDOWN

        # Hệ số provider nhân Ở ĐÂY, không nhân lúc ước lượng: trước khi chọn
        # được spec thì chưa biết nhân hệ số nào (xem tokens.py).
        est = int(base_tokens * spec.token_multiplier)
        scope = self._scope_kwargs(spec)

        try:
            minute = self._store.usage_since(
                since=now - timedelta(seconds=60), **scope)
            # Cửa sổ TRƯỢT 24h, không phải "ngày lịch": Google reset hạn mức
            # lúc nửa đêm giờ Thái Bình Dương, Groq và OpenRouter reset ở múi
            # giờ khác — ba múi giờ là ba con bug đang chờ. Cửa sổ trượt chỉ
            # có một cách hiện thực và luôn THẬN TRỌNG HƠN mức thật; giá phải
            # trả là hơi bi quan ngay sau một đợt dùng dồn — chấp nhận được.
            day = self._store.usage_since(
                since=now - timedelta(hours=24), **scope)
        except Exception:
            # FAIL-OPEN, ngược với write_gate.py (fail-closed) và cố ý như vậy:
            # write_gate chặn thao tác ghi ERP KHÔNG HOÀN TÁC ĐƯỢC nên mơ hồ
            # thì phải khoá; sổ ngân sách chỉ chắn một cái 429 TỰ LÀNH mà chuỗi
            # fallback đã xử lý sẵn. Fail-closed ở đây là đánh sập cả hệ thống
            # để bảo vệ một hạn mức miễn phí — sai tỉ lệ.
            logger.warning("không đọc được sổ ngân sách, cho gọi (fail-open)",
                           exc_info=True)
            return Verdict.OK

        # Thứ tự kiểm theo chân trời hồi phục GIẢM DẦN, để phán quyết trả về là
        # cái cung cấp nhiều thông tin nhất. Cạn ngân sách ngày mà báo
        # "tpm_exhausted" sẽ khiến người đọc tưởng chờ một phút là xong.
        if spec.rpd is not None and day.requests >= spec.rpd:
            return Verdict.RPD
        if spec.rpm is not None and minute.requests >= spec.rpm:
            return Verdict.RPM
        if spec.tpm is not None and minute.total_tokens + est > spec.tpm:
            return Verdict.TPM
        return Verdict.OK

    # ── Ghi ─────────────────────────────────────────────────────────────────
    def record(self, spec: ModelSpec, prompt_tokens: int,
               completion_tokens: int, total_tokens: int) -> None:
        """total_tokens là con số CÓ THẨM QUYỀN cho mọi phép kiểm token.

        Đo 2026-07-28: gemma-4-26b-a4b-it trả prompt=11, completion=36 nhưng
        total=337 — có ~290 token "thinking" không nằm trong completion_tokens
        mà vẫn bị tính vào tổng. Cộng hai thành phần đếm thiếu 7 lần, tức sổ
        báo còn hạn mức trong khi ví đã cạn. prompt/completion vẫn lưu để chẩn
        đoán, nhưng không dùng cho phép kiểm nào.
        """
        try:
            self._store.record(
                ts=self._clock(), alias=spec.alias, provider=spec.provider,
                upstream=spec.upstream, prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens, total_tokens=total_tokens)
        except Exception:
            # Cùng lý do fail-open: không ghi được sổ thì mất một dòng kế toán,
            # KHÔNG được làm vỡ lượt gọi đã thành công.
            logger.warning("không ghi được sổ ngân sách", exc_info=True)

    def cooldown(self, spec: ModelSpec, seconds: float) -> None:
        self._cooldowns[spec.alias] = self._clock() + timedelta(seconds=seconds)
