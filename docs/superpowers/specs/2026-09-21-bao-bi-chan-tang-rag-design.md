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

**Task 10 (2026-09-22) — miễn `KNOWN_UNFLAGGED` cho ca không k nào bắt được, cổng ÂM
cuối cùng PASS.** Xem §6.3/§7 và mục dưới cho số đo; mã: `commercial_unflagged_known` /
`_new` + `known_stale` (hai kiểm rữa: ca được miễn NAY CÓ CỜ → rữa "đã chữa được"; câu
trong danh sách KHÔNG còn trong bộ ca → rữa "đổi tên/xoá"). Miễn KHÔNG áp cho
`leaked`/`other_flagged`. Unit 2925/1/120/0 warning (+6 test so Task 9).

### Task 8 (hoàn tất, 2026-09-22) — Step 1, 2, 4 và tổng kết thi hành

**Step 1 — toàn suite (số cuối cùng, tại `c345e33`):**
- Qua launcher, `-m "not integration and not live"`: **2925 passed, 1 skipped, 120
  deselected, 0 warning** (256,80 s).
- Lượt CI-parity (đúng môi trường CI thật: 4 biến `ODOO_*` giả đặt, `DATABASE_URL`
  VẮNG), trên `tests/jobs tests/evals tests/agents`: **1583 passed, 0 failed.**
  (Khó khăn tự bắt: lượt CI-parity ĐẦU TIÊN của chính người viết báo cáo này dùng
  `env -u DATABASE_URL` trong shell vốn không có `.env`, nên xoá nhầm LUÔN cả 4 biến
  `ODOO_*` mà CI thật CÓ đặt — 17 failed giả, 16 ở một file file nhánh này không hề
  đụng. Đọc `.github/workflows/tests.yml` xác nhận CI đặt đủ 4 biến `ODOO_*`, chỉ
  KHÔNG đặt `DATABASE_URL`; chạy lại đúng môi trường đó cho ra 1583/0. Bài học: mô
  phỏng CI phải sao y biến môi trường CI, xoá NHIỀU hơn CI xoá thì tạo báo động giả.)

**Step 2 — integration một mình, qua launcher (DSN in ra):** **23 passed, 18
deselected, 0 skipped.**

**Step 3 — cổng ÂM/DƯƠNG cuối cùng, sau khi luật đổi sang top-3 (Task 9) và có miễn
`KNOWN_UNFLAGGED` (Task 10):**

```
CỔNG ÂM PASS — thương mại 10 ca (lộ 0, không báo chặn 1 — trong đó 1 ca đã biết
được miễn, 0 ca mới), khác 99 ca (kém đi 0, từ chối oan 0)
```
exit 0.

```
GATE PASS — model=0.963 baseline=0.963
```
exit 0 — đường admin KHÔNG hồi quy vì việc thêm lượt bóng.

lat_p50: **admin 523 ms, warehouse 558 ms** (+35 ms, đo trên corpus THẬT ~3 900 chunk).
So với con số Task 5 (+4,2 ms, ×2,50, đo trên **fixture 2 tài liệu**): con số fixture
chứng minh lượt bóng là cỡ mili-giây và không gọi LLM, nhưng KHÔNG nói được chi phí
tuyệt đối trên corpus thật, nơi chân dense đắt hơn — +35 ms mới là con số thật của
lượt bóng trên dữ liệu sản xuất; hai con số không được lẫn vào nhau.

Bảng k đầy đủ (`do_topk.py`, chỉ đọc, không sửa mã production; k=1 tái hiện đúng
5/10 · 0/99 nên tự chứng minh đáng tin) — đây là bằng chứng cho quyết định chọn k=3:

| k | bắt được | từ chối oan |
|---|---|---|
| 1 | 5/10 | 0/99 |
| 2 | 6/10 | 0/99 |
| **3** | **9/10** | **0/99** ← chọn |
| 4 | 9/10 | 0/99 |
| 5 | 9/10 | 1/99 |

Ca duy nhất không k nào bắt được: *"bên bán phải đóng gói hàng ra sao trước khi
chuyển đi?"* (mong đợi `sla.docx`) — tài liệu ẩn của nó đứng hạng **> 5** trong bản
bóng. Miễn qua `KNOWN_UNFLAGGED` (Task 10), có kiểm rữa staleness: cổng sẽ FAIL nếu
ca này bắt đầu được phát hiện, hoặc câu hỏi biến mất khỏi bộ ca — miễn không thể âm
thầm che một hồi quy thật hay một ca đã đổi.

**Step 4 — probe sống trên hạ tầng thật (backend + 4 MCP của worktree, exit 0):**

```
[rag]   kho từ chối đúng câu tất định: True | kho không trích lạc đề: True |
        thấy footer: {'sales': True, 'accounting': True, 'admin': True} | PASS
[mixed] marker đúng 1 lần: True (đếm=1) | kết bằng câu tất định: True |
        phần ERP trước đó không rỗng: True | không trích lạc đề: True | PASS
```

warehouse / rag (nguyên văn):
```
Tài liệu về việc này thuộc phạm vi Kế toán / Bán hàng; vai Kho không được xem. Bạn có thể hỏi trực tiếp phòng Kế toán hoặc Bán hàng.
```

warehouse / mixed (nguyên văn):
```
Hiện tại, sản phẩm [E-COM07] Large Cabinet đang có tồn kho là 0.

Về chính sách chiết khấu cho khách hàng Azure Interior, hệ thống ERP hiện không có dữ liệu về các cấp độ chiết khấu, do đó tôi không thể cung cấp thông tin về mức giảm giá phần trăm cho khách hàng này.

Tài liệu về việc này thuộc phạm vi Kế toán / Bán hàng; vai Kho không được xem. Bạn có thể hỏi trực tiếp phòng Kế toán hoặc Bán hàng.
```

sales / mixed (nguyên văn — đối chứng, vai được phép thấy mọi thứ):
```
Theo chính sách, sản phẩm [E-COM07] Large Cabinet hiện có số lượng tồn kho là 0.

Về mức giảm giá, khách hàng Azure Interior thuộc cấp Thân thiết sẽ được chiết khấu 5% trên tổng giá trị đơn hàng theo chính sách chiết khấu theo cấp. Ngoài ra, nếu đơn hàng có giá trị từ 50 triệu đồng trở lên và được thanh toán trong thời hạn quy định, đơn hàng sẽ được cộng thêm 2% chiết khấu số lượng (với tổng chiết khấu tối đa không vượt quá 15%), đồng thời áp dụng điều kiện khách hàng không có công nợ quá hạn tại thời điểm lập đơn và không mua hàng khuyến mãi hay hàng đã giảm giá.

📄 Nguồn: kho tài liệu chung
• Chính sách chiết khấu theo cấp khách hàng › Mục 2 — Mức chiết khấu theo cấp (discount_policy.docx)
• Chính sách chiết khấu theo cấp khách hàng › Mục 3 — Chiết khấu theo số lượng (discount_policy.docx)
• Chính sách chiết khấu theo cấp khách hàng › Mục 4 — Điều kiện áp dụng (discount_policy.docx)
```

Một lượt được trả lời bởi **gemini-3.5-flash-lite** ("model bạn chọn đang quá tải") —
probe chạy một phần dưới model dự phòng, không phải model chính đã ghim.

**Phát hiện đọc bằng mắt (máy KHÔNG bắt được):** đoạn giữa của câu trả lời mixed vai
kho là do model fusion TỰ VIẾT, và nó SAI: *"hệ thống ERP hiện không có dữ liệu về
các cấp độ chiết khấu"* — không đúng, tài liệu bị chặn THEO VAI, ERP không hề thiếu
dữ liệu. Người dùng đọc HAI lời giải thích mâu thuẫn nhau, cái SAI đứng trước, cái
ĐÚNG (câu tất định) đứng sau. Oracle không bắt được vì đoạn đó không chứa
`DENIED_MARKER` (đếm vẫn = 1, đúng cấu trúc) — đây chính là lỗ hổng reviewer Task 4
đã cảnh báo và là lý do bắt buộc đọc nguyên văn thay vì tin mỗi con số PASS.

Ruling: GHI LÀ HẠN CHẾ ĐÃ BIẾT + việc mở, KHÔNG sửa trong nhánh này. Lời hứa của spec
(câu từ chối tất định, đúng phòng ban, tới được người dùng) ĐÃ ĐẠT trên cả hai tuyến;
đoạn phụ sai là vấn đề PROMPT của fuse, mà đổi prompt ở repo này bắt buộc A/B có số đo
(tiền lệ `fuse-prompt-obligation-penalty`) — ngoài phạm vi plan đã duyệt.

**Chưa xác nhận — ghi là gap, không phải sự thật đã kiểm:** tuyến thật của câu mixed
trong probe KHÔNG được xác nhận độc lập qua Langfuse/log backend. Bằng chứng duy nhất
là câu trả lời chứa cả dữ liệu ERP thật LẪN câu từ chối — nhất quán với tuyến mixed,
nhưng router là một LLM và không trace nào được soi. Đây là "chưa đo được đường
mixed", không phải "đã xác nhận".

**Dọn hạ tầng (đã xác nhận):** dừng đúng các tiến trình khởi bởi probe (so PID trước/
sau), xoá bản chép `.env`, gỡ junction MCP, giữ junction `backend/.venv`; 8002-8006
trống lại; không đụng tiến trình có trước.

### Khó khăn / giả thuyết bị bác — ghi vào repo (không chỉ scratch)

1. **Kỳ vọng của plan "luật hạng-1 bắt 10/10" bị BÁC bởi số đo thật (5/10).** Mã
   Task 1-7 đúng với đặc tả nó nhận được — 7 vòng review độc lập đều xác nhận vậy;
   đặc tả (kỳ vọng của plan) sai. Chủ dự án sau đó chọn top-3 từ chính bảng k đo
   được ở trên, không phải chọn trước rồi đo để xác nhận.
2. **Câu spec §3/§4 "SQL giữ byte-for-byte như 19b đã khẳng định" không còn đúng
   NGHĨA ĐEN** sau khi Task 1 làm `_COLS` thêm `c.visibility` vào MỌI truy vấn kể cả
   đường admin. Bất biến ràng buộc THẬT — đường admin không có mệnh đề lọc, không
   chạy lượt bóng, không thêm truy vấn — vẫn giữ nguyên; một cột thêm vào hàng đã có
   sẵn (không join, không mệnh đề, không câu SQL thứ tư) không phạm bất biến đó. Câu
   chữ đã được sửa ở §3/§4 trong nhiệm vụ ghi chép này (ruling của controller
   2026-09-22); mã không đổi.
3. **Mẫu hình lặp lại nhiều lần trên nhánh này: cổng XANH trong khi CẤU TRÚC không
   thể ĐỎ — đây là bài học chính của nhánh.** Bốn ví dụ cụ thể, mỗi cái bị phát hiện
   và sửa trước khi merge:
   - Task 3: mồi nhử `_LLMKhongDuocGoi` bị fixture `chunks=[]` làm `synthesize()`
     ngắn mạch TRƯỚC khi tới LLM — 2 vòng sửa mới ra được cổng bắt đúng hình dạng
     nguy hiểm thật ("cổng CHẠY, hành động [gọi LLM] CŨNG chạy" dù nội dung câu trả
     lời vẫn đúng); cách sửa cuối là assert THẲNG một cờ `bi_goi` được set trước khi
     mồi nhử ném lỗi, không suy luận từ nội dung.
   - Task 1 (G2): một assert là HẰNG ĐÚNG vì helper test tự gieo sẵn cả ba khoá
     (`dense`/`sparse`/`fold`) nên không đột biến nào của mã có thể làm nó đỏ; sửa
     bằng dựng dict động (giống helper anh em) rồi đột biến bằng một chân biến mất
     THẬT (`RAG_FOLD_ENABLED=0`).
   - Task 4 (H1): assert `doc_context == []` không thể đỏ vì fixture test hardcode
     sẵn `chunks=[]` — production thật trả về chunk lạc đề CÙNG `hidden_classes`, và
     dập đúng chunk đó là mục đích của cả tính năng; sửa bằng fixture dựng từ chunk
     lạc đề thật (`_CHUNK_VUOT_SAN`).
   - Task 5: một test integration chỉ xanh nhờ Postgres TỰ CHỌN thứ tự khi hai chân
     hoà điểm tuyệt đối trên từ khoá của câu hỏi fixture; đảo thứ tự INSERT (thực
     nghiệm, khôi phục ngay sau) LẬT test đó sang ĐỎ mà không đổi một byte mã — sự
     mong manh là quan sát được, không chỉ suy luận. Sửa bằng đổi sang câu hỏi độc
     quyền từ vựng (kiểm bằng `to_tsvector`/`to_tsquery` thật), không đụng fixture.

   Không phải review bỏ sót — mỗi cái đều bị chính reviewer hoặc implementer phát
   hiện trong lúc làm nhiệm vụ liên quan; ghi lại vì đây là hình dạng lỗi có thể tái
   phát ở nhiệm vụ khác, và vì repo yêu cầu khó khăn phải nằm trong repo, không chỉ
   trong ghi chú scratch.
4. **Một câu sai còn nằm trong git log, đã bị bác nhưng KHÔNG bị xoá.** Thân commit
   `ce68dc1` (Task 4) viết rằng mồi nhử `_LLMKhongDuocGoi` "còn sống" — sai, và bị
   chính commit `568de7a` ngay sau đó BÁC BỎ bằng sửa thật. Lịch sử KHÔNG được viết
   lại (`ce68dc1` không phải HEAD tại thời điểm phát hiện, môi trường không dùng
   rebase tương tác) — người đọc `git log` của nhánh này sau đây không nên tin câu
   "còn sống" trong thân `ce68dc1`; câu đúng là câu trong `568de7a`.
