# Ký ức xuyên phiên L2 — báo cáo đo thật và nghiệm thu sống

**Ngày:** 2026-08-20
**Nhánh:** worktree-user-memory-l2
**Phạm vi:** Task 8 của kế hoạch — không viết code sản phẩm, chỉ đo và nghiệm thu.

---

## 1. Tóm tắt

Cả 6 cổng liên quan PASS, cả 6 kịch bản sống qua HTTP thật ĐẠT. Nhưng con số
đó chỉ đúng **sau khi** bước nghiệm thu sống tìm ra một lỗi Critical làm
**toàn bộ tính năng không hoạt động trong production**, trong khi 1822 test và
7 vòng review từng task đều xanh. Mục 4 kể lại đầy đủ.

## 2. Bốn cổng có thể thụt

| cổng | model | kết quả |
|---|---|---|
| `read` | gemini-3.5-flash-lite | **PASS** — tool_acc 1.000 / baseline 1.000, fabricated_param 0, p50 757ms |
| `planner` | gemini-3.5-flash-lite | **PASS** — tool_acc 1.000 / baseline 1.000, dangerous_misroute 0, p50 1068ms |
| `synthesis` | gemini-3.1-flash-lite | **PASS** — grounded_acc 1.000 / baseline 1.000, false_answer 0 |
| `multi_source` | gemini-3.1-flash-lite | **PASS** — both_source_coverage 0.750 / baseline 0.750, citation_validity 1.0, fabricated_number 0 |

⚠️ `synthesis` và `multi_source` **không đo được ở lượt đầu**: Google trả 429
RESOURCE_EXHAUSTED — cạn hạn mức NGÀY của `gemini-3.1-flash-lite`. Bộ đo dừng
và **từ chối đưa ra verdict** thay vì cho số giả (`exit 2`) — đúng thiết kế.
Đo lại sau khi hạn mức ngày reset thì cả hai PASS.

**Phát hiện phụ đáng ghi:** lúc đó sổ `llm_usage` nội bộ báo model này mới dùng
**6** lượt/24h trong khi Google báo **cạn 500/ngày**. Hai nguyên nhân cộng lại:
sổ dùng cửa sổ **trượt** 24h còn Google tính theo **ngày lịch**; và sổ chỉ đếm
lượt đi qua Router của dự án này, trong khi công việc RAG merge cùng ngày đốt
hạn mức Google mà không qua sổ. ⇒ **Sổ nội bộ không đủ để dự đoán hạn mức thật**
khi nhiều luồng việc dùng chung một project Google.

## 3. Bộ eval `memory` (mới)

```json
{
  "set": "memory", "n": 7,
  "false_injection": 0,
  "leaked_doc_code": 0,
  "recall": 1.0,
  "lat_p50": 2749, "lat_p95": 4012,
  "fails": [], "errors": []
}
```

Hai chỉ số gác **tuyệt đối** đều 0; `recall` 1.0 (bắt đúng cả 3 ca đáng nhớ).
Ghi nhận: 2 lượt bị `gemini-3.5-flash` trả rỗng với
`finish_reason=MALFORMED_FUNCTION_CALL`, chuỗi fallback xử lý đúng — không ảnh
hưởng kết quả nhưng đáng theo dõi nếu tái diễn.

## 4. Lỗi Critical mà nghiệm thu sống tìm ra

### 4.1 Triệu chứng

Tái lập **5/5** qua entry point HTTP thật: người dùng khai một sở thích → fact
**được ghi đúng vào DB** (kiểm bằng SQL, `thread_id` khớp từng request) → nhưng
câu trả lời **không có dòng công bố** `📝 Đã ghi nhớ:`. Tức **ghi âm thầm** —
đúng thứ mà quyết định thiết kế của chủ dự án ("ghi ngay + NÓI RÕ + dễ gỡ")
sinh ra để chặn. Người dùng không biết có gì để mà "quên đi".

### 4.2 Gốc rễ

Pool Postgres của production (`erp_agent.setup`) bắt buộc dựng với:

```python
kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
```

`row_factory=dict_row` là **yêu cầu của `AsyncPostgresSaver`** (LangGraph
checkpointer) — không bỏ được. Nhưng cả ba hàm DB của ký ức lại lấy ô **theo vị
trí** (`row[0]`, `row[1]`), nên với dict thì ném `KeyError: 0`.

Chuỗi nhân quả, đo được từng mắt bằng mũi đo trên graph thật:

1. Model phát marker đúng; `_apply_memory_markers` nhận đúng.
2. `INSERT ... RETURNING id` **commit ngay** (pool bật `autocommit`) → fact vào DB thật.
3. Dòng ngay sau: `(await cur.fetchone())[0]` → **`KeyError: 0`**.
4. Hai lệnh còn lại của `save_fact` (supersede cùng key, enforcement `MEMORY_CAP`) **không bao giờ chạy**.
5. `except Exception: continue` ở tầng gọi nuốt lỗi → **không thêm dòng công bố**.

### 4.3 Phạm vi hỏng rộng hơn triệu chứng

Đo đối chứng cùng bộ hàm trên hai cấu hình pool:

| hàm | pool như **test** dựng (mặc định, tuple) | pool như **production** dựng (dict_row) |
|---|---|---|
| `save_fact` | ✅ | ❌ `KeyError: 0` |
| `load_active_facts` | ✅ | ❌ `KeyError: 0` |
| `forget_fact` | ✅ | ❌ `KeyError: 0` |

Nghĩa là ngoài "ghi âm thầm": **đường đọc cũng chết** (ký ức không bao giờ được
nạp vào prompt) và **"quên đi" cũng chết**. Toàn bộ tính năng không hoạt động
trong production — chỉ là nó hỏng im lặng nên nhìn như đang chạy.

### 4.4 Vì sao 1822 test và 7 vòng review đều không thấy

Test đơn vị dùng pool giả; test tích hợp **tự dựng `AsyncConnectionPool` với
row factory MẶC ĐỊNH** — tức đo một cấu hình pool mà production không bao giờ
dùng. Đây đúng lớp lỗi của đợt `write-confirmation-ux-fix` trước đây: cơ chế
chết hoàn toàn trong production trong khi mọi vòng review từng task đều xanh,
vì không vòng nào chạy qua đường thật.

### 4.5 Bản sửa (commit `3e1001b`) — hai phần

1. **Code sản phẩm:** ba hàm DB lấy ô độc lập với row factory của pool.
2. **Test tích hợp:** fixture dựng pool bằng **đúng kwargs của production**.

Phần 2 mới là thứ chặn tái phát. Bằng chứng nó cần thiết: chỉ đổi fixture sang
cấu hình production mà **chưa** sửa code thì **6/7 test đỏ ngay** với đúng
`KeyError: 0`, trong khi trước đó cùng file xanh 7/7.

`erp_agent.py` **không bị đụng** — `dict_row`/`autocommit` là bắt buộc cho
checkpointer.

## 5. Nghiệm thu sống qua HTTP thật (sau bản sửa)

| # | thao tác | kết quả |
|---|---|---|
| 1 | Phiên A: `từ giờ trả lời ngắn gọn thôi nhé` | ✅ có `📝 Đã ghi nhớ: phong_cach_tra_loi = ngắn gọn` |
| 2 | Kiểm DB | ✅ đúng 1 dòng hiệu lực, `thread_id` khớp |
| 3 | **Phiên B, session_id KHÁC HẲN**: `cho tôi xem chi tiết đơn mua P00003` | ✅ xưng hô "anh Hào" (ký ức khác) **và** trả lời NGẮN GỌN đúng sở thích khai ở phiên A; số liệu ERP đúng (255, 10, 25.5) |
| 4 | `quên cái phong cách trả lời đi nhé` | ✅ có `🗑️ Đã bỏ ghi nhớ: phong_cach_tra_loi` |
| 5 | Kiểm DB lại | ✅ **6 dòng, không dòng nào bị xoá**; cả hai bản `phong_cach_tra_loi` đánh dấu superseded |
| 6 | `nhớ giúp tôi đơn P00003 là đơn quan trọng nhất` | ✅ model tự từ chối ghi mã chứng từ ngay ở tầng prompt — cổng phủ quyết không cần bắn (phòng thủ nhiều lớp) |

**Kịch bản 3 là kịch bản DUY NHẤT chứng minh cả đợt hoạt động đầu-cuối** —
và nó ĐẠT: sở thích khai ở một phiên được áp dụng ở một phiên hoàn toàn khác.

**Không thao tác ghi Odoo thật nào** được thực hiện trong toàn bộ quá trình đo.

## 6. Chưa làm được / giới hạn đã biết

- **Chập chờn có sẵn, không thuộc nhánh này:** bộ test thỉnh thoảng báo ERROR
  kèm `PytestUnraisableExceptionWarning` gán cho một test nhạy-thời-gian ngẫu
  nhiên (quan sát ở `test_eval_gate.py::test_nhip_tu_dong_suy_tu_rpm_catalog` và
  `test_resilience.py::test_retry_delay_defaults_to_pace_when_pacing`). Cả hai
  có trước nhánh này, không đo đồng hồ thật, và repo đã có commit gỡ một
  assertion biến-thiên-độ-trễ cùng họ. Không tái lập được sau nhiều lượt sạch.
- **`recall` của bộ `memory` chưa có baseline** — ghi nhận 1.0, chưa gác.
- Các giới hạn thiết kế đã ghi trong spec §9 (không có L1/L3, không chia sẻ
  giữa người dùng, không phát hiện hai fact mâu thuẫn khác key) giữ nguyên.
