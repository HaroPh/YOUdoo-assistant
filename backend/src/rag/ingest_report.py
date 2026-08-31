"""Kết quả một lượt nạp tài liệu — spec 2026-08-29 mục 4.

Ba trạng thái TỆP, không phải ba số đếm:
    ingested  — đã sinh chunk và ghi DB
    unchanged — content_hash trùng, bỏ qua CÓ CHỦ Ý
    rejected  — không nạp được, KÈM LÝ DO, được gọi tên

Không có trạng thái thứ tư. Trước 2026-08-30 hàm nạp trả dict ba số đếm và
tệp `.doc`/`.xlsm`/`.pptx` rơi vào khoảng trắng giữa chúng: cả ba số đều 0,
không lời nào, tài liệu biến mất khỏi corpus.

Chữ `skipped` cũ bị bỏ có chủ ý: nó mang HAI nghĩa ("không đổi nên bỏ qua"
và "không hiểu nên bỏ qua") và chính sự mơ hồ đó là chỗ lỗi nấp được.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rejection:
    path: str
    reason: str


@dataclass
class IngestReport:
    ingested: int = 0
    unchanged: int = 0
    chunks: int = 0
    rejected: list[Rejection] = field(default_factory=list)

    def merge(self, other: "IngestReport") -> None:
        self.ingested += other.ingested
        self.unchanged += other.unchanged
        self.chunks += other.chunks
        self.rejected.extend(other.rejected)

    @property
    def ok(self) -> bool:
        return not self.rejected

    def render(self) -> str:
        lines = [f"đã nạp {self.ingested} · không đổi {self.unchanged} · "
                 f"chunk {self.chunks} · từ chối {len(self.rejected)}"]
        for r in self.rejected:
            lines.append(f"  TỪ CHỐI  {r.path}  —  {r.reason}")
        return "\n".join(lines)
