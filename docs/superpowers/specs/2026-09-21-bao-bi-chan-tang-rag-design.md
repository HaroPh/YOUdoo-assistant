# Báo bị chặn ở tầng RAG — thiết kế

**Ngày:** 2026-09-21 · **Trạng thái:** đã duyệt thiết kế, chờ plan · **Nối tiếp:** 19b
(`docs/superpowers/specs/2026-09-20-rbac-tang-rag-design.md`)

## 1. Vấn đề

19b lọc tài liệu theo vai *bên trong SQL* của `retrieve()`, và làm đúng: vai `warehouse`
không còn chạm 4 tài liệu thương mại. Nhưng nghiệm thu sống (19b §10) cho thấy hệ quả
phía người dùng: vai kho hỏi *"Chính sách chiết khấu của công ty như thế nào?"* nhận một
câu trả lời **tự tin, có trích dẫn, lạc đề** — về bán cổ phần, trích `luat-doanhnghiep.pdf`
Điều 126 — vì chunk luật có chữ "chiết khấu" và `synthesize()` thấy đủ cớ để trả lời.

Spec 19b §7 vốn đòi *"không có 5%/10%/15%, có lời từ chối/không tìm thấy"*. Nửa đầu đạt,
nửa sau chưa. Người dùng thật sẽ tưởng trợ lý hiểu sai câu hỏi, không biết mình bị chặn,
và không biết hỏi ai.

Gốc rễ **không phải prompt**: hệ thống không có tín hiệu nào cho biết bộ lọc vừa giấu
ứng viên tốt nhất. Chỉ `retrieve()` mới biết được điều đó.

## 2. Quyết định đã chốt với chủ dự án

| Câu hỏi | Chốt |
|---|---|
| Vai bị chặn thấy gì? | **Nói rõ bị chặn + chỉ đúng phòng ban** — khớp kiểu `other_dept` bên ERP. Chấp nhận tiết lộ tài liệu tồn tại (công ty nhỏ, ai cũng biết có bảng giá). |
| Đường nào? | **Cả `rag` lẫn `mixed`** — đường mixed vốn đã có lỗ "nhập nhằng thất bại và không-có" (README, Known limitations). |
| Cách phát hiện? | **Truy vấn bóng không lọc bên trong `retrieve()`, luật hạng-1** (§3). Hai hướng bị loại: sửa prompt (không phân biệt được bị chặn/không có, và mọi lần đụng prompt đường tài liệu đều đo ra `refusal_acc` tụt); đếm ứng viên lớp giấu vượt ngưỡng (điểm dense/lexical không cùng thang, phải hiệu chỉnh từng chân). |

## 3. Hợp đồng `retrieve()` — tín hiệu `hidden_classes`

**`src/rag/types.py`** — `RetrievalResult` thêm trường cuối:

```python
hidden_classes: frozenset[str] = frozenset()   # lớp bị giấu mà lẽ ra đứng hạng 1
```

Mặc định rỗng ⇒ mọi chỗ dựng `RetrievalResult` hiện có (production, test, eval) không đổi.

**`src/rag/retrieve.py`**:

- `_COLS` thêm `c.visibility` ở **cuối** (`row[11]`). 11 cột đang dùng giữ nguyên chỉ số;
  `Chunk` không cần trường mới.
- Trong `retrieve()`, sau khi có `ordered` của bản đã lọc, **chỉ khi**
  `visibility is not UNRESTRICTED`:
  1. chạy lại `_dense`/`_sparse`/`_lexical_fold` (và các `aux`) với `UNRESTRICTED`,
     **dùng lại** `qvec`, `qseg`, chuỗi bỏ dấu đã tính — không nhúng lại, không rerank;
  2. gộp RRF y hệt nhánh chính (`_rrf`, `_rrf_fold`, cùng thứ tự);
  3. lấy phần tử hạng 1; nếu `row[11] not in visibility` → `hidden_classes = {row[11]}`.
     Bản bóng không có ứng viên nào (corpus không khớp gì) → `hidden_classes` rỗng.
- **Bất biến an toàn:** `chunks` trả về là bản đã lọc SQL; hàng của bản bóng không bao
  giờ rời hàm dưới bất kỳ dạng nào ngoài **tên lớp**. Có test khẳng định: khi
  `hidden_classes` khác rỗng, không chunk nào trong `result.chunks` thuộc lớp bị giấu.
- Chi phí: 3 truy vấn SQL (+3 mỗi `aux`) cho vai bị giới hạn, mili-giây, không LLM.
  Admin (`UNRESTRICTED`) không tốn gì — SQL giữ byte-for-byte như 19b đã khẳng định.

**Vì sao hạng-1, không phải "có mặt trong top-k":** vai kho hỏi *chính sách hoàn hàng*
(được xem) mà `bang_gia.xlsx` lọt hạng 5 khi không lọc thì vẫn phải được trả lời bình
thường. Chỉ khi thứ **tốt nhất** bị giấu mới là "bạn hỏi đúng thứ bị chặn". Luật này có
rủi ro **từ chối oan** ở chiều ngược; §6 đo đúng rủi ro đó.

Lưu ý thang đo: hạng-1 của bản bóng là hạng **RRF trước rerank**; bản thấy được trả về
theo thứ tự **sau rerank**. Chấp nhận — tín hiệu là "khớp thô mạnh nhất bị giấu", và §6
đo nó trực tiếp.

## 4. Suy tên phòng ban — `src/agents/rag_access.py` (mới)

Module nhỏ, để `roles.py` không phình. Tầng: `rag_access → roles → visibility`, không
chiều ngược.

```python
def departments_for(classes: frozenset[str], profile: dict | None = None) -> list[str]:
    """Tên hiển thị của các vai được xem ít nhất một lớp trong `classes`.
    Suy từ RoleCfg.rag_visibility — KHÔNG khai bảng riêng (lớp lỗi 'danh sách
    khai tay trôi khỏi sự thật'). Admin là UNRESTRICTED nên tự bị loại."""

def denied_message(role_cfg, classes: frozenset[str]) -> str:
    """Chuỗi TẤT ĐỊNH, không LLM, không footer trích dẫn."""
```

Ví dụ với `{'commercial'}` ở cả hai profile: `["Kế toán", "Bán hàng"]` →

> Tài liệu về việc này thuộc phạm vi Kế toán / Bán hàng; vai Kho không được xem.
> Bạn có thể hỏi trực tiếp phòng Kế toán hoặc Bán hàng.

Nếu `departments_for` trả rỗng (lớp không vai nào được xem — chỉ xảy ra khi cấu hình
sai) thì câu không nêu phòng ban, chỉ nói "vai X không được xem". Không nổ.

## 5. Hai node sản xuất

**`rag_node` (`src/agents/nodes.py`)** — sau `retrieve`, **trước** `synthesize()`:

```python
if result.hidden_classes:
    logger.info("rag_node: vai %s bị chặn lớp %s", role_cfg.name, sorted(result.hidden_classes))
    return {"messages": [AIMessage(content=denied_message(role_cfg, result.hidden_classes))]}
```

Kiểm tra tất định, không giao cho model. Không gọi LLM ⇒ không tốn hạn mức, không có
cửa cho model "tự viết lời từ chối" (đã đo: làm `refusal_acc` tụt).

**`gather_docs` (`src/agents/fanout.py`)** — khi `result.hidden_classes`:
trả `{"doc_context": [], "doc_denied": denied_message(role_cfg, result.hidden_classes)}`.
`doc_denied: str | None` là trường state mới (`src/agents/state.py`) và mang **chuỗi
thông điệp đã dựng** — vì `gather_docs` có `role_cfg` còn `make_fuse_answer_node(llm)`
thì không; đẩy chuỗi qua state tránh phải nối `role_cfg` vào node fuse. `clear` trong
`fuse_answer` đặt lại `None` như `doc_context`/`erp_facts`.

**`fuse_answer`** — khi `state["doc_denied"]`:
- phần TÀI LIỆU của `render_fuse_input` ghi rõ *"(bị hạn chế theo vai — KHÔNG kết luận
  gì về chính sách)"* thay vì để trống, để model không tự suy "chính sách không đề cập";
- câu từ chối tất định (`denied_message`) được **nối vào cuối** câu trả lời ERP.
  Model không được tự viết lời từ chối.
- **Thứ tự kiểm tra:** `doc_denied and not erp_facts` → trả thẳng `doc_denied` (không
  LLM) — đặt **trước** nhánh hiện có "cả hai chân rỗng → SAFE_MSG", vì `doc_denied` nghĩa
  là chân tài liệu **không rỗng về thông tin** (nó biết mình bị chặn). Nhánh SAFE_MSG
  giữ nguyên cho trường hợp còn lại.

## 6. Đo lường — tất định, không tốn hạn mức

1. **Unit** (`tests/rag/`, `tests/agents/`): với conn giả — bản bóng chỉ chạy khi bị
   giới hạn (đếm truy vấn); `hidden_classes` tính từ hạng-1; `chunks` không chứa lớp
   giấu; `rag_node` trả `denied_message` không gọi LLM; `gather_docs` đặt `doc_denied`;
   `fuse_answer` nối câu từ chối và không để model viết nó; `departments_for` suy đúng
   từ cả hai profile và trả rỗng khi không vai nào xem.
2. **Integration** (Postgres thật, schema `rag_test`, fixture 2 tài liệu của 19b):
   ca thuận — chunk `commercial` là hạng-1 khi không lọc ⇒ `hidden_classes={'commercial'}`;
   **ca ngược** — tài liệu `all` là hạng-1 (truy vấn trục 1) ⇒ `hidden_classes` rỗng.
3. **Cổng ÂM mở rộng** (`evals/compare_visibility.py`): `eval_retrieval` ghi thêm
   `hidden: bool` cho từng ca; bất biến (c): lượt vai bị chặn phải có `hidden == True`
   ở **mọi ca thuần thương mại** (10/10) và `hidden == False` ở **mọi ca khác** (99/99).
   Đây chính là precision/recall của cờ — bắt **từ chối oan**. Kỳ vọng: 10/10 · 0/99.
   Nếu đo ra từ chối oan > 0: siết luật thành "hạng-1 bị giấu **và** điểm thấy được
   dưới sàn" — quyết bằng số đo, không quyết trước.
4. **Probe sống** (`tests/live_verify_rbac_rag.py`, sửa): vai kho phải nhận đúng
   `denied_message` có tên phòng ban; ba vai kia kiểm bằng **footer trích
   `discount_policy.docx`**, không phải chuỗi con "5%" (vá điểm yếu probe cũ: "15%"
   chứa "5%").
5. **Độ trễ:** `lat_p50` vai kho trước/sau — mốc 521 ms (19b §10).

## 7. Rủi ro và giới hạn biết trước

- **Từ chối oan** khi một tài liệu thương mại tình cờ đứng hạng-1 cho câu hỏi hợp lệ.
  §6.3 đo trực tiếp trên 99 ca; luật dự phòng đã nêu.
- **Tiết lộ tồn tại**: câu từ chối cho biết có tài liệu thuộc Kế toán/Bán hàng. Chủ dự
  án chấp nhận (§2).
- Bản bóng dùng hạng RRF, bản thấy dùng hạng sau rerank — hai thang khác nhau, đã nêu §3.
- Chỉ áp dụng cho lớp `commercial` hiện có; thêm lớp mới thì `departments_for` tự suy,
  không cần sửa gì ở đây.

## 8. Ngoài phạm vi

- Ghi vệt kiểm toán cho lượt đọc tài liệu **bị từ chối** (mục 17b chỉ ghi lượt đọc ERP).
- Cổng theo vai cho `synthesis_live`/`multiturn` (đã khai `role` trong JSON, chưa ai đọc).
- Thông điệp từ chối cho `skill` node — các SOP hiện không đọc tài liệu thương mại.

## 9. Cấu trúc mã

| Tệp | Thay đổi |
|---|---|
| `backend/src/rag/types.py` | `RetrievalResult.hidden_classes` |
| `backend/src/rag/retrieve.py` | `_COLS` + `c.visibility`; bản bóng + luật hạng-1 |
| `backend/src/agents/rag_access.py` | **mới** — `departments_for`, `denied_message` |
| `backend/src/agents/state.py` | `doc_denied: str \| None` |
| `backend/src/agents/nodes.py` | `rag_node` trả từ chối tất định |
| `backend/src/agents/fanout.py` | `gather_docs` đặt `doc_denied`; `fuse_answer` nối từ chối |
| `backend/evals/run_eval.py` | `per_case[].hidden` |
| `backend/evals/compare_visibility.py` | bất biến (c) |
| `backend/tests/live_verify_rbac_rag.py` | oracle mới cho cả hai chiều |

## 10. Ghi chép thực thi

*(điền khi thi hành: số cờ 10/10 · 0/99 hay không, lat_p50, toàn văn 4 câu trả lời probe,
khó khăn, giả thuyết bị bác)*
