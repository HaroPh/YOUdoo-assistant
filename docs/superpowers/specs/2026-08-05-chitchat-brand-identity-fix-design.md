# Gán tên "Youdoo" vào `CHITCHAT_PROMPT`

**Ngày:** 2026-08-05
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

Chạy thử qua backend thật đang sống (`POST /v1/chat/completions`, model
`erp-assistant`, câu hỏi "Bạn là ai? Bạn có thể giúp gì?") cho kết quả nội
dung hợp lý (mô tả đúng năng lực: tra cứu đơn/tồn kho/khách hàng/nhà cung
cấp, tìm tài liệu, xử lý đơn từ) nhưng **không hề nhắc tên "Youdoo"**, chỉ
nói chung chung "trợ lý ERP nội bộ của công ty".

Grep toàn bộ `backend/src/agents/prompts.py`: chuỗi "Youdoo" xuất hiện
**0 lần**. Không phải gap riêng của chitchat — toàn hệ thống chưa từng
được gán tên thương hiệu này ở bất kỳ prompt nào.

## 2. Phạm vi: đúng 1 prompt, phủ được cả 2 node

`CHITCHAT_PROMPT` (`backend/src/agents/prompts.py:126-134`) được dùng bởi
CẢ HAI nơi một câu "bạn là ai?" có thể rơi vào:
- Node `respond_unknown` (`backend/src/agents/nodes.py:80-95`,
  `llm.ainvoke([SystemMessage(content=CHITCHAT_PROMPT), last_human])`).
- Nhánh chitchat của `intent_router` (cùng prompt, xác nhận qua docstring
  của `eval_chitchat`: "Gọi LLM giống hệt respond_unknown thật").

Sửa đúng 1 prompt này là đủ — không cần đụng `SYSTEM_PROMPT` (erp_read),
`FUSE_PROMPT`, `RAG_SYNTHESIS_PROMPT`, hay `GATHER_ERP_PROMPT`, vì các
prompt đó không phải là nơi câu hỏi "bạn là ai" thường rơi vào.

## 3. Ràng buộc từ eval set đang gác

`eval_chitchat` (`backend/evals/run_eval.py:496-520`) là set GÁC THẬT
(`violations` phải = 0) nhưng **chỉ kiểm tra một điều duy nhất**: response
không chứa cụm nào trong `HALLUCINATION_MARKERS` (các cụm kiểu "đã tạo",
"đã xác nhận", "đã cập nhật", "đã lưu"...) — hoàn toàn không liên quan tới
tên/danh tính. Thêm tên "Youdoo" không đụng tiêu chí gate này, nhưng vẫn
phải đo thật để xác nhận (không suy đoán) — nội dung câu mới không được
tình cờ chứa một cụm hallucination-marker nào.

## 4. Nội dung sửa

`backend/src/agents/prompts.py`, dòng đầu tiên của `CHITCHAT_PROMPT`
(dòng 126):

Từ:
```
Bạn là trợ lý ERP nội bộ, trả lời bằng tiếng Việt với giọng chuyên nghiệp, thân thiện.
```

Thành:
```
Bạn là Youdoo, trợ lý ERP nội bộ, trả lời bằng tiếng Việt với giọng chuyên nghiệp, thân thiện.
```

**Không đổi gì khác** trong `CHITCHAT_PROMPT` — danh sách năng lực (dòng
127), quy tắc chống bịa hành động (dòng 130), quy tắc không tiết lộ nhà
cung cấp model (dòng 132), giọng văn (dòng 134) giữ nguyên nguyên vẹn.
Thay đổi tối thiểu nhất có thể để đóng đúng gap đã đo được, không mở rộng
phạm vi.

## 5. Kiểm chứng

1. `pytest tests/agents/test_prompts.py tests/agents/test_fanout.py -q`
   xanh — không có test nào phụ thuộc câu đầu `CHITCHAT_PROMPT` nguyên
   văn cũ (nếu có, phải cập nhật đồng bộ, không phải bỏ qua).
2. Đo thật `--set chitchat` (8 ca + 8 ca near-miss,
   `evals.cases.CHITCHAT_CASES`): `violations` phải vẫn = 0 — xác nhận câu
   mới không vô tình khớp `HALLUCINATION_MARKERS` nào.
3. Gọi trực tiếp backend thật đang chạy
   (`POST http://localhost:8000/v1/chat/completions`, model
   `erp-assistant`, câu hỏi "Bạn là ai?") — xác nhận response THẬT SỰ nhắc
   tên "Youdoo", không chỉ suy luận từ prompt text.

## 6. File bị chạm

| File | Việc |
|---|---|
| `backend/src/agents/prompts.py` | Sửa 1 dòng đầu `CHITCHAT_PROMPT` |
| `backend/tests/agents/test_prompts.py` | Thêm test chốt "Youdoo" có trong `CHITCHAT_PROMPT` |
| `docs/superpowers/plans/2026-08-05-chitchat-brand-identity-fix-report.md` (mới) | Report đo thật `--set chitchat` + gọi backend thật xác nhận |

## 7. Tiêu chí hoàn thành

1. `CHITCHAT_PROMPT` chứa đúng câu mới ở §4.
2. `pytest` unit-only xanh toàn bộ.
3. `--set chitchat`: `violations == 0` — không hồi quy.
4. Gọi backend thật xác nhận response nhắc tên "Youdoo" cho câu hỏi
   "bạn là ai".
