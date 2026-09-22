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

> **ĐỔI 2026-09-22 (chủ dự án quyết, sau khi cổng ÂM thật FAIL):** phần dưới đây mô tả
> luật **HẠNG-1** như thiết kế BAN ĐẦU và như Task 1-7 đã thi hành trung thực. Chạy cổng
> ÂM thật trên 109 ca (Task 8) cho kết quả **thương mại 5/10 · khác 0/99 từ chối oan** —
> an toàn giữ nhưng tính năng chỉ bắn đúng NỬA số câu thương mại. Đo thêm theo k
> (task-9-brief, `do_topk.py`, chỉ đọc):
>
> | k | bắt được | từ chối oan |
> |---|---|---|
> | 1 | 5/10 | 0/99 |
> | 2 | 6/10 | 0/99 |
> | **3** | **9/10** | **0/99** ← chọn |
> | 4 | 9/10 | 0/99 |
> | 5 | 9/10 | 1/99 |
>
> Chủ dự án chọn **k=3** (Task 9, `retrieve.HIDDEN_TOP_K`): nhiều nhất bắt được mà vẫn
> 0/99 từ chối oan; k=5 mới bắt đầu có từ chối oan. Đây là **sửa SPEC** (luật phát hiện
> thay đổi), không phải sửa bug — mã Task 1-7 đúng với đặc tả nó nhận được. Đoạn mô tả
> "hạng-1" dưới đây GIỮ LẠI làm dấu vết quyết định đã bị thay, không phải mô tả hành vi
> hiện tại — xem đoạn "Luật hiện hành (từ Task 9)" ngay sau nó.

**`src/rag/types.py`** — `RetrievalResult` thêm trường cuối:

```python
hidden_classes: frozenset[str] = frozenset()   # lớp bị giấu mà lẽ ra lọt top-k
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
  3. (luật BAN ĐẦU, xem "ĐỔI 2026-09-22" ở trên) lấy phần tử hạng 1; nếu
     `row[11] not in visibility` → `hidden_classes = {row[11]}`. Bản bóng không có ứng
     viên nào (corpus không khớp gì) → `hidden_classes` rỗng.
- **Bất biến an toàn:** `chunks` trả về là bản đã lọc SQL; hàng của bản bóng không bao
  giờ rời hàm dưới bất kỳ dạng nào ngoài **tên lớp**. Có test khẳng định: khi
  `hidden_classes` khác rỗng, không chunk nào trong `result.chunks` thuộc lớp bị giấu.
- Chi phí: 3 truy vấn SQL (+3 mỗi `aux`) cho vai bị giới hạn, mili-giây, không LLM.
  Admin (`UNRESTRICTED`) không tốn gì thêm về mặt SQL: cùng không có mệnh đề lọc, cùng
  không chạy lượt bóng, cùng không thêm truy vấn như 19b (không còn "byte-for-byte" theo
  nghĩa đen sau khi `_COLS` thêm `c.visibility` cho MỌI truy vấn — xem ghi chú sửa chữ ở
  Task 8, đây là sửa CHỮ spec, không phải hồi quy mã).

**Luật hiện hành (từ Task 9, 2026-09-22) — TOP-K, thay luật hạng-1 ở trên:**

Bước 3 ở trên đổi thành: lấy **k ứng viên đầu** của bản bóng (`k = HIDDEN_TOP_K = 3`,
hằng ở `retrieve.py` cạnh `VIS_IDX`); `hidden_classes` = hợp MỌI lớp trong k ứng viên đó
mà vai không được xem (`_hidden_in_top_k`, đổi tên từ `_hidden_at_rank_one`). Ngoài top-k
bị giấu KHÔNG tính — vẫn giữ tinh thần "vai kho hỏi hoàn hàng mà bảng giá lọt hạng 4 vẫn
phải được trả lời bình thường", chỉ khác NGƯỠNG (hạng 1 → hạng ≤3). Mọi bất biến khác
(chống rò rỉ, tiền điều kiện F5 `TypeError` với `UNRESTRICTED`, vị trí gọi ngoài `try`
fail-open) giữ nguyên — luật đổi nằm gọn trong `_hidden_in_top_k`, không lan ra tầng trên.

**Vì sao hạng-1 lúc đầu, không phải "có mặt trong top-k":** vai kho hỏi *chính sách hoàn
hàng* (được xem) mà `bang_gia.xlsx` lọt hạng 5 khi không lọc thì vẫn phải được trả lời
bình thường. Chỉ khi thứ **tốt nhất** bị giấu mới là "bạn hỏi đúng thứ bị chặn" — đó là
lập luận BAN ĐẦU, và nó không sai về NGUYÊN TẮC (ngoài top-k vẫn không tính ở luật mới).
Cái nó đánh giá sai là NGƯỠNG: đo thật cho thấy phần lớn câu thương mại có tài liệu bị
giấu rơi ở hạng 2-3 chứ không phải hạng 1 (xem bảng k ở trên), nên "tốt nhất" cần đọc là
"trong vài ứng viên tốt nhất", không phải đúng một ứng viên đứng đầu. Luật nào cũng có rủi
ro **từ chối oan** ở chiều ngược; §6 đo đúng rủi ro đó, nay có SỐ ĐO kèm theo (bảng k).

Lưu ý thang đo: top-k của bản bóng là hạng **RRF trước rerank**; bản thấy được trả về
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
   giới hạn (đếm truy vấn); `hidden_classes` tính từ **top-k** (`HIDDEN_TOP_K`, Task 9;
   ban đầu là hạng-1, xem §3); `chunks` không chứa lớp giấu; `rag_node` trả
   `denied_message` không gọi LLM; `gather_docs` đặt `doc_denied`; `fuse_answer` nối câu
   từ chối và không để model viết nó; `departments_for` suy đúng từ cả hai profile và
   trả rỗng khi không vai nào xem. Fixture unit của Task 9 SÂU ≥4 hàng (không phải 2) —
   với đúng 2 hàng, top-3 luôn chứa cả hai và không còn ca nào diễn tả được "bị giấu
   NGOÀI top-k"; xem `tests/rag/test_retrieve_hidden.py`.
2. **Integration** (Postgres thật, schema `rag_test`, fixture 2 tài liệu của 19b **+ 2
   chunk 'all' nạp thêm ở Task 9** để có ≥4 hàng — cùng lý do như unit ở trên):
   ca thuận (hạng 1, giữ từ Task 5) — chunk `commercial` hạng 1 khi không lọc ⇒
   `hidden_classes={'commercial'}`; **ca thuận sâu** (Task 9) — `commercial` hạng 3
   (trong top-3) ⇒ báo; **ca ngược sâu** (Task 9, thay ca ngược cũ — fixture 2 tài liệu
   không còn diễn tả được biên top-3) — `commercial` hạng 4 (ngoài top-3) ⇒
   `hidden_classes` rỗng.
3. **Cổng ÂM mở rộng** (`evals/compare_visibility.py`): `eval_retrieval` ghi thêm
   `hidden: bool` cho từng ca; bất biến (c): lượt vai bị chặn phải có `hidden == True`
   ở **mọi ca thuần thương mại** (10/10) và `hidden == False` ở **mọi ca khác** (99/99).
   Đây chính là precision/recall của cờ — bắt **từ chối oan**. Kỳ vọng ban đầu: 10/10 ·
   0/99.
   **Đo thật (Task 8, 2026-09-22) với luật hạng-1: 5/10 · 0/99** — an toàn giữ (0 lộ, 0 từ
   chối oan) nhưng dưới-phát-hiện nặng. Đây LÀ chế độ hỏng mà mục này dự tính "quyết bằng
   số đo, không quyết trước" — chỉ khác chiều: spec ban đầu chỉ viết sẵn nhánh "nếu từ
   chối oan > 0 thì SIẾT luật (thêm sàn điểm)"; thực tế đo ra chiều NGƯỢC LẠI (dưới-phát-
   hiện, không phải từ chối oan), nên hướng sửa là NỚI luật (tăng k) chứ không phải siết.
   Đo thêm theo k (`do_topk.py`, Task 9): k=3 cho 9/10 · 0/99 — chủ dự án chọn (bảng đầy đủ
   ở §3). Nhánh "thêm sàn điểm" của bản gốc KHÔNG cần dùng vì k=3 đã đạt 0/99 từ chối oan.
4. **Probe sống** (`tests/live_verify_rbac_rag.py`, sửa): vai kho phải nhận đúng
   `denied_message` có tên phòng ban; ba vai kia kiểm bằng **footer trích
   `discount_policy.docx`**, không phải chuỗi con "5%" (vá điểm yếu probe cũ: "15%"
   chứa "5%").
5. **Độ trễ:** `lat_p50` vai kho trước/sau — mốc 521 ms (19b §10).

## 7. Rủi ro và giới hạn biết trước

- **Dưới-phát-hiện**: luật hạng-1 ban đầu chỉ bắt 5/10 câu thương mại thật (Task 8) —
  ĐÃ SỬA bằng top-3 (Task 9, xem §3/§6.3). Rủi ro tương tự vẫn còn ở chiều khác: câu
  thương mại nào có tài liệu bị giấu rơi NGOÀI top-3 ("bên bán phải đóng gói ra sao",
  đo được hạng >5) vẫn không bị bắt — chấp nhận, vì k lớn hơn bắt đầu sinh từ chối oan
  (k=5 cho 1/99).
- **Từ chối oan** khi một tài liệu thương mại tình cờ lọt **top-k** cho câu hỏi hợp lệ
  (ban đầu viết cho hạng-1). §6.3 đo trực tiếp trên 99 ca theo TỪNG giá trị k; k=3 (chọn)
  vẫn 0/99, k=5 mới bắt đầu có (1/99).
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
| `backend/src/rag/retrieve.py` | `_COLS` + `c.visibility`; bản bóng + luật top-k (`HIDDEN_TOP_K`, ĐỔI Task 9 từ hạng-1) |
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

**Task 8 (2026-09-22) — cổng ÂM thật trên 109 ca, luật hạng-1:** thương mại 5/10 · khác
0/99. Giả thuyết ban đầu "hạng-1 đủ" bị BÁC bởi số đo, không phải bởi review mã — 7 vòng
review Task 1-7 đều đúng với đặc tả nhận được, đặc tả sai.

**Task 9 (2026-09-22) — chủ dự án đổi luật sang top-3** (`HIDDEN_TOP_K=3` ở
`retrieve.py`, cạnh `VIS_IDX`). `_hidden_at_rank_one` → `_hidden_in_top_k(fused,
visibility, k=HIDDEN_TOP_K)`. Kết quả: unit 2919 passed / 1 skipped / 120 deselected
(mốc trước Task 9: 2917/1/119 — chênh +2 unit +1 integration, khớp 1 test unit bị thay
bằng 3 test mới và 1 test integration bị thay bằng 2 test mới); integration
`test_retrieve_hidden.py -m integration`: 4 passed, 0 skipped. Đột biến biên k (bắt buộc
của task): `HIDDEN_TOP_K` 3→4 làm đỏ đúng `test_bi_giau_o_hang_4_thi_khong_bao`; 3→2 làm
đỏ đúng `test_bi_giau_o_hang_3_thi_bao` — không test nào khác đỏ theo. Chi tiết đầy đủ:
`task-9-report.md` (workspace SDD, không vào git).
