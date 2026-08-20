# Trạng thái chung — hai phiên làm việc song song

Cập nhật lần cuối: **2026-08-21**.

## Cách dùng tệp này

Hai phiên Claude Code cùng làm trên repo này (một giữ **RAG/truy xuất**, một giữ
**ký ức người dùng**). Tệp này là chỗ **duy nhất** để biết trạng thái chung mà
không phải đọc lại hội thoại của nhau.

Quy ước:

- **Đóng một mục thì tự xoá nó khỏi đây**, kèm commit đã đóng nó. Đừng để mục
  chết nằm lại — một danh sách không ai dọn sẽ thành danh sách không ai đọc.
- **Không chép nội dung spec vào đây.** Chỉ ghi *cái gì đang treo* và *ai giữ*,
  rồi trỏ tới spec. Tệp này phải đọc hết trong một phút.
- **Không dùng tệp này thay cho test.** Ràng buộc giữa hai vùng phải cưỡng chế
  bằng test, không bằng dòng chữ ở đây. Bằng chứng: ràng buộc
  `render_memory_block` được `tests/evals/test_memory_presets.py` gác, nên không
  cần ai nhắn ai.
- **Trước khi sửa file thuộc vùng người khác**, xem mục "Ai giữ vùng nào". Đụng
  file phiên kia đang mở là cách đã từng gây sự cố.

## Đang chờ chủ dự án quyết

| # | mục | vùng | ghi chú |
|---|---|---|---|
| A | Hai key cho cùng một fact — `hien_thi_ma_don` + `always_show_order_code` đã có trong dữ liệu THẬT | ký ức | spec L2 xếp vào "giới hạn v1, tầng gộp đợt sau", nhưng đã thành hiện thực ngày đầu |
| B | Trần số fact trong khối ký ức — hiện **không có** | ký ức | liên quan A: trùng key làm khối phình nhanh gấp đôi |
| C | Chân sparse đã chết (64/64 truy vấn trả rỗng) — gỡ hẳn hay giữ và đổi nhãn `method` cho đúng sự thật | RAG | hồi sinh đã đo là CÓ HẠI (recall 1,0 → 0,9766) |

## Việc đang treo

| # | mục | ai giữ | chặn bởi |
|---|---|---|---|
| 1 | Đo `ĐỀ_XUẤT_GHI` với khối ký ức khác rỗng — **cần bộ ca riêng** | chưa ai | `MULTI_SOURCE_CASES` không có ca đề xuất ghi |
| 2 | 4 job `e2e_*` chưa port từ SP-1C1 | chưa ai | — |
| 3 | Tham chiếu thứ tự trong câu nối tiếp ("loại đầu tiên", "cái sau") | chưa ai | bài toán mới, chưa mở phạm vi |
| 4 | Dọn 11 worktree mồ côi + 2 stash rác | chưa ai | — |

**Mục 1 thu hẹp sau phép đo 2026-08-21.** Nửa `NGUỒN_DÙNG:` đã đo xong:
`citation_validity` giữ **1,0** ở mọi chân ký ức, tất định qua 3 lượt (spec
`2026-08-20-memory-synthesis-eval.md` §9). Nửa còn lại — `ĐỀ_XUẤT_GHI` — KHÔNG
đo chung được: `_strip_write_marker()` chỉ cắt marker chứ không chấm, và
`MULTI_SOURCE_CASES` không có ca nào đề xuất thao tác ghi. Cần bộ ca riêng.

**Kèm một quyết định đã có số đỡ lưng: ĐỪNG cắt ký ức khỏi `fuse_answer`.** Sự
không nhất quán giữa hai đường (`rag_node` không nạp / `fuse_answer` có nạp)
trông như bỏ sót, nhưng đo ra fact ép định dạng làm đường fuse TỐT LÊN
(`both_source` 0,750 → 0,875, tất định 3/3) trong khi làm đường RAG tệ đi. Cắt
cho "nhất quán" sẽ làm mất một ca đang đúng.

**Mục 2 đang tắt một cổng chặn hồi quy Critical**:
`tests/jobs/test_cli.py::test_cli_survives_redirected_cp1252_stdout` bị skip
cứng vì thiếu job `e2e-smoke`. Nó gác đúng lớp lỗi vừa cắn phiên ký ức ở
`evals/` (thông điệp lỗi tiếng Việt làm chính dòng in lỗi ném
`UnicodeEncodeError` trên console cp1252, biến exit 2 đọc được thành exit 1
trống rỗng).

## Ai giữ vùng nào

| vùng | tệp chính |
|---|---|
| **RAG / truy xuất** | `src/rag/**`, `src/agents/synthesis.py`, `src/agents/history.py`, `evals/{retrieval,synthesis_live,multiturn,memory_presets}*` |
| **Ký ức người dùng** | `src/agents/user_memory.py`, `migrations/004_user_memory.sql`, `evals/cases.py`, phần `eval_memory` của `run_eval.py` |
| **Chung — hỏi trước khi sửa** | `src/agents/nodes.py`, `src/agents/fanout.py`, `src/agents/prompts.py`, `evals/run_eval.py` |

Bốn tệp "chung" là nơi cả hai lần merge vừa rồi đều xung đột. Sửa được, chỉ cần
báo trước.

## Đã đo — ĐỪNG bàn lại nếu không có số mới

| kết luận | chứng cứ |
|---|---|
| Ký ức **không** vào prompt tổng hợp RAG — cả ba loại fact đều không dương | spec `2026-08-20-memory-synthesis-eval.md` §3, §7 |
| Fact mâu thuẫn tài liệu **không** đè được luật | cùng spec §3, chân `conflict` |
| Khối ký ức **không** làm tịt marker `GHI_NHỚ:`/`QUÊN:` | cùng spec §8, 15/15 |
| Trần số chunk mỗi mục: **vô tác dụng** | tag `parked/rag-section-cap` |
| Ngữ cảnh hội thoại cho `synthesize()`: **không chữa được gì** | spec `2026-08-20-rag-roadmap-revision.md` |
| Cross-encoder là **lá phiếu**, không phải kẻ ghi đè | docstring `retrieve.rerank()` |

## CHƯA đo — danh sách "ta chưa biết"

- Khối ký ức trên `FUSE_PROMPT` (mục 1 ở trên).
- **Mọi phép đo ký ức tới nay đều dùng đúng MỘT fact.** Người dùng thật đang có
  5. Không có gì cho biết nó bắt đầu hại ở đâu.
- Thứ hạng bên trong top-6 có đổi câu trả lời cuối không (docstring `rerank()`).

## Bẫy vận hành

- **Hạn mức LLM**: tính đến tối 2026-08-20, **cả khoá chính lẫn khoá dự phòng
  đều cạn hạn mức NGÀY**.
- `--pace 4.5` **bắt buộc** cho mọi bộ eval gọi LLM (free tier 15 lượt/phút).
- Lỗi `cooldown` có **hai** nguyên nhân. Phân biệt bằng phép đo: chạy lại ở
  `--pace 9` (~6,7 lượt/phút) mà **vẫn** cooldown ⇒ cạn hạn mức ngày, đổi khoá;
  hết cooldown ⇒ chỉ là trần phút.
- **`llm_usage` KHÔNG dùng để chẩn đoán hạn mức** — nó chỉ ghi lượt *thành
  công*. Đã gặp: Google báo cạn 500 trong khi sổ ghi 22.
- **DB RAG thật**: `postgresql://admin:thay_bang_mat_khau@localhost:5434/ai_assistant`
  (container `youdoo-postgres`).
- Đụng `chunking`/`parse` thì phải `DELETE FROM rag_documents` rồi ingest lại
  (~3,5 phút). Không xoá thì content-hash bỏ qua toàn bộ 17 tệp.
