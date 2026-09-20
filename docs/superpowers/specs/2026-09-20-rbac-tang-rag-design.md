# RBAC tầng RAG (mục 19b) — thiết kế

**Ngày**: 2026-09-20. **Nhánh**: chưa mở (spec trước, plan sau).
**Trạng thái**: THIẾT KẾ ĐÃ DUYỆT — chủ dự án chốt phương án A và bộ nghiệm thu ngày 2026-09-20; chờ plan.

Đóng mục **19b** của `docs/trang-thai-chung.md`, hoãn có điều kiện từ 2026-08-22, mở lại 2026-09-19.
Nền: `docs/odoo-mcp-server-nghien-cuu-2026-09-19.md` §5 mục 7 (`check_domain_balance`) và
§2.2/§2.6 (ivnvxd gating `ir.attachment`; apexive: nguồn RAG của Odoo AI native không áp record rule,
chưa có lộ trình vá).

---

## 1. Đề bài, đo được

**Lỗ hổng có thật.** Đo sống 2026-08-22 qua cổng vào production (`POST /v1/chat/completions` kèm
`x-openwebui-user-id` của vai kho): vai `warehouse` hỏi *"chính sách chiết khấu"* và nhận đủ bậc
5%/10%, cộng thêm 2%, trần 15%, điều kiện công nợ.

**Nguyên nhân cơ học.** `rag_chunks.visibility` (`src/rag/schema.sql:30`, `text NOT NULL DEFAULT
'all'`) tồn tại từ tháng 7 nhưng **không ai đọc, không ai ghi**: `grep -rn visibility backend/src`
chỉ khớp đúng dòng schema. `retrieve()` (`src/rag/retrieve.py:242`) không có tham số lọc;
`make_rag_node(llm)` (`src/agents/nodes.py:91`) và `make_gather_docs_node()`
(`src/agents/fanout.py:83`) không nhận `role_cfg`. Một cột ngủ hai tháng — đó là kết cục của
"thiết kế trước, dùng sau".

**Corpus lúc thiết kế (đo 2026-09-19, `rag_documents`/`rag_chunks` thật):**

| nhóm | tài liệu | chunk | ghi chú |
|---|---|---|---|
| PDF luật (`seed/law/`) | 9 | 3 857 | công khai |
| nội bộ — thương mại | 4 | 24 | `bang_gia.xlsx` 8, `sla.docx` 6, `discount_policy.docx` 5, `payment_policy.docx` 5 |
| nội bộ — quy trình | 4 | 20 | `policy.docx`, `sop.docx`, `sales_process.docx`, `warehouse_outbound.docx` |
| **SID** (báo cáo tài chính bán niên) | 1 | 660 | nạp tay bằng CLI `ingest_path` lúc test OCR bậc 3 — **rác test trong corpus sản xuất** |
| **tổng** | **18** | **4 561** | **4 561/4 561 = `'all'`** |

**Vì sao làm ngay dù dữ liệu mỏng.** Lỗ không phải giả thuyết; 8 tài liệu gắn nhãn tay trong một
buổi, còn 80 tài liệu thì gắn nhãn hồi tố mới là phần đau; code ép trong `retrieve()` cùng một cỡ dù
corpus 8 hay 800. Phần bền là choke point, không phải bảng phân loại.

**Bộ retrieval có 10/109 ca (3 easy, 7 hard) mong đợi chunk từ 4 tài liệu thương mại** — đo bằng
`RETRIEVAL_CASES` đối chiếu `expected_labels`. Hệ quả kép: eval **phải** truyền vai (không thì cổng
dương FAIL giả), và có sẵn một **cổng âm** tất định (§7).

## 2. Quyết định chủ dự án đã chốt (2026-09-19 → 20)

1. **4 tài liệu thương mại → `accounting` + `sales` + `admin`; `warehouse` bị chặn.** Thay quyết định
   22/08 (`accounting` + `admin`) vì vai `sales` được thêm ngày 23/08 và nhân viên bán hàng cần bảng
   giá/chiết khấu/điều khoản/SLA để báo giá.
2. **4 tài liệu quy trình giữ `all`.** Quy trình nội bộ mọi nhân viên đọc được.
3. **Corpus chung chỉ chứa tri thức tổ chức** (`src/rag/seed/`). Tài liệu người dùng gửi đi endpoint
   trích xuất (`main.py:222-250`: ghi tạm → trích → **xoá tạm** → trả text) → kho vector riêng của
   Open WebUI, gắn user/chat. **Không bao giờ** vào `rag_documents`. Trục phân quyền của tài liệu cá
   nhân là *chủ sở hữu*, không phải *vai*.
4. **SID gỡ khỏi corpus**, không gắn nhãn. Nó đã gây ô nhiễm chéo thật (2026-09-19: Ollama của Open
   WebUI tắt → "No sources found" → backend đổi nguồn sang corpus chung → trả số của SID cho câu hỏi
   về NTC). Gỡ SID đồng thời **làm tan #35** (336 chunk breadcrumb lỗi đi theo tệp, tiết kiệm 25 lượt
   VLM ~70k token).
5. **Phương án A**: nhãn là *lớp* trong DB, vai→lớp trong code (§3). Bác B (danh sách vai trong DB:
   thêm vai = backfill toàn bộ, parse chuỗi trong SQL nóng) và C (cột trên `rag_documents` + JOIN
   vào 3 chân nóng khi cột chunk đã có sẵn).
6. **Admin không bị lọc.**

## 3. Mô hình nhãn

- Cột `rag_chunks.visibility` giữ nguyên, **không đổi schema**. Giá trị là **lớp**:
  `'all'` | `'commercial'`.
- Mới `src/rag/visibility.py`:

  ```python
  VISIBILITY_CLASSES = frozenset({"all", "commercial"})
  DOC_VISIBILITY = {
      "discount_policy.docx": "commercial",
      "bang_gia.xlsx": "commercial",
      "payment_policy.docx": "commercial",
      "sla.docx": "commercial",
  }
  DEFAULT_VISIBILITY = frozenset({"all"})

  class _Unrestricted:
      """Sentinel: không lọc. KHÔNG phải None — None là 'mất vai' → fail-closed."""
      __slots__ = ()
      def __repr__(self): return "UNRESTRICTED"

  UNRESTRICTED = _Unrestricted()

  def class_for(source_file: str) -> str:
      # Tách trên CẢ '/' lẫn '\': rag_documents.source_file đang lưu
      # "src/rag/seed\bang_gia.xlsx"; os.path.basename trên Linux (CI) sẽ trả
      # "seed\bang_gia.xlsx" → nhãn sai lặng lẽ.
      return DOC_VISIBILITY.get(re.split(r"[\\/]", source_file)[-1], "all")

  def resolve(visibility) -> frozenset | _Unrestricted:
      """None hoặc rỗng → DEFAULT_VISIBILITY. Chỉ sentinel mới mở."""
      if visibility is UNRESTRICTED:
          return UNRESTRICTED
      return frozenset(visibility) if visibility else DEFAULT_VISIBILITY
  ```

  **Vì sao sentinel không phải `None`**: một caller lỡ viết
  `visibility=role_cfg.rag_visibility if role_cfg else None` phải rơi về *thấy ít nhất*. Nếu `None`
  nghĩa là "không lọc" thì mất vai = mở toang — đúng chiều sai mà mục 17b đã lộ. Nên `None` **và**
  rỗng đều là fail-closed; muốn mở phải cầm đúng đối tượng `UNRESTRICTED`.

  Khoá theo **basename** — cùng cách `retrieval_cases.py` neo nhãn, và `rag_documents.source_file`
  hiện lưu cả `src/rag/seed\…` lẫn `D:/downloads/…`. Tệp không có trong bảng → `'all'`.
- `src/agents/roles.py`: `RoleCfg` thêm trường `rag_visibility: frozenset | _Unrestricted`
  (mặc định `DEFAULT_VISIBILITY` — hồ sơ nào quên khai thì *thấy ít nhất*). `admin`
  (`unrestricted=True`, `roles.py:101`) → `UNRESTRICTED`; `accounting`, `sales` →
  `{all, commercial}`; `warehouse` → `{all}`. **Vai biết lớp, lớp không biết vai** — `agents/` import
  `rag.visibility` (chiều cho phép), `src/rag/` không import `src/agents/`.

## 4. Đường ép trong `retrieve()`

- Chữ ký: `retrieve(query, k=TOP_K, conn=None, aux_queries=(), *, visibility=None)`; dòng đầu
  `visibility = resolve(visibility)`.
- **Fail-closed tại `retrieve()`, không ở caller.** Không truyền, truyền `None`, truyền rỗng → đều
  `{'all'}`. Muốn không lọc phải truyền đúng đối tượng `UNRESTRICTED`. Lý do: mục 17b từng lộ đường
  SOP mất cả vai lẫn user — "quên truyền" phải tương đương *thấy ít nhất*, không phải *thấy tất cả*.
- Thêm `AND c.visibility = ANY(%s)` vào **cả ba chân**, trước `LIMIT TOP_N`:
  - `_dense` (`retrieve.py:21-27`): `WHERE c.embedding IS NOT NULL AND c.visibility = ANY(%s)`
  - `_sparse` (`retrieve.py:54-59`): `WHERE c.ts_vector @@ … AND c.visibility = ANY(%s)`
  - `_lexical_fold` (`retrieve.py:117-121`): `WHERE c.ts_vector_fold @@ … AND c.visibility = ANY(%s)`

  Các lượt `aux_queries` (`retrieve.py:265-271`) đi qua đúng ba hàm này nên tự nhận. Lọc **trước**
  pool, không lọc sau: lọc sau vừa tốn chỗ trong 20 ứng viên vừa rò qua `total_candidates`.
- Khi `visibility is UNRESTRICTED`, ba chân **bỏ hẳn** mệnh đề (không truyền `ANY(VISIBILITY_CLASSES)`)
  — để SQL của đường admin bằng đúng SQL trước 19b, và cổng dương so được với baseline cũ.
- Không thêm chỉ số cho `visibility`: vai kho lọc 24/4 561 chunk. `lat_p50` trong eval sẽ nói có cần
  hay không (mốc 573 ms).

## 5. Vai đi vào retriever

Chỉ **hai** caller production (`grep "retrieve("` toàn `backend/src`); đường skill/SOP **không** gọi
`retrieve()` — chúng dùng tool `erp_query`.

| caller | đổi | nguồn vai |
|---|---|---|
| `nodes.py:91` `make_rag_node(llm)` | → `make_rag_node(llm, role_cfg=None)`; gọi `retrieve(..., visibility=_visibility_of(role_cfg))` | `graph.py:43` `build_graph(..., role_cfg=None, ...)` đã có, truyền xuống |
| `fanout.py:83` `make_gather_docs_node()` | → `make_gather_docs_node(role_cfg=None)`, cùng cách | như trên |

`_visibility_of(role_cfg)`: `role_cfg is None` → `None` (để `retrieve()` tự fail-closed — không
lặp lại luật ở caller); có vai → `role_cfg.rag_visibility`. **Hệ quả cố ý**: mọi test cũ gọi `build_graph()` không truyền vai vẫn chạy nhưng **không thấy**
4 tài liệu thương mại nữa. Test nào trông đợi chúng phải truyền vai — đó là hồi quy *đúng*, lộ ra chỗ
nào đang ngầm chạy như admin.

**Eval.** Ba bộ gọi `retrieve()` thật — `retrieval`, `synthesis_live`, `multiturn` — nhận `--role`
(`run_eval.py:1416`, mặc định `admin` → `UNRESTRICTED`, khớp mặc định hiện có). `--role warehouse`
sinh cổng âm. `role_config.ROLE_SENSITIVE_SETS` (`role_config.py:32`) là về **prompt**, không dùng
lại; thêm một tập riêng cho **visibility** để hai nghĩa không lẫn.

## 6. Ingest + migration 009

- `ingest.py:184` INSERT `rag_chunks` ghi thêm `visibility = class_for(source_file)` — lần nạp
  `seed/` sau tự đúng, không reset về `'all'`. Nhắc lại bẫy đã ghi: re-ingest là NO-OP nếu
  `content_hash` không đổi (không có dấu vân parser) — nên **backfill là bắt buộc**, không thể "nạp
  lại cho nó tự đúng".
- `backend/migrations/009_rag_visibility_backfill.sql` — idempotent, chạy tay theo lệ thư mục
  (`docs/getting-started.md:123-126`):
  1. `UPDATE rag_chunks SET visibility = 'commercial' WHERE visibility <> 'commercial' AND
     (source_file LIKE '%discount_policy.docx' OR … 4 basename)` — kỳ vọng **24** dòng.
  2. Đếm `rag_chunks` khớp `source_file LIKE '%BaoCaoTaiChinhBanNien%'` (để báo cáo), rồi
     `DELETE FROM rag_documents WHERE source_file LIKE '%BaoCaoTaiChinhBanNien%'` — chunk đi theo
     `ON DELETE CASCADE` (không có `DELETE FROM rag_chunks` riêng) — kỳ vọng **660** chunk, 1 tài
     liệu. **Thao tác phá huỷ duy nhất** của 19b: header migration ghi rõ, và migration in
     `count(*)` trước/sau bằng `RAISE NOTICE` để lượt chạy tay có bằng chứng.
  3. Ghi `rag_embedding_marker` không đụng.
- `DOC_VISIBILITY` xuất hiện **hai chỗ** (Python + SQL). Một test hợp đồng đọc file 009 và khẳng định
  bốn basename trong SQL **bằng đúng** `set(DOC_VISIBILITY)` — hai nguồn không được trôi.

## 7. Kiểm thử và nghiệm thu

**Unit** (`pytest -m "not integration and not live"`, không DB):
- `visibility.py`: `class_for` trả `'commercial'` cho 4 basename kể cả khi truyền đường dẫn đầy đủ
  Windows/POSIX; `'all'` cho tệp lạ; mọi giá trị `DOC_VISIBILITY` ∈ `VISIBILITY_CLASSES`.
- `RoleCfg.rag_visibility` cho 4 vai đúng §3; admin là `UNRESTRICTED`.
- `resolve()`: `None`, `frozenset()`, `set()` → `DEFAULT_VISIBILITY`; `UNRESTRICTED` → chính nó;
  một `_Unrestricted()` **khác** (không phải singleton) → vẫn fail-closed (so bằng `is`).
- `retrieve()` fail-closed: không truyền **và** truyền `None` → SQL chứa mệnh đề lọc với `['all']`
  (test **hình dạng chuỗi SQL** qua conn giả, cùng cách `test_sparse_van_chet.py`); `UNRESTRICTED` →
  SQL **không** chứa `visibility`; lọc có mặt ở **cả ba** chân.
- Hai node truyền đúng `visibility` (patch `retrieve`, bắt kwargs).
- Hợp đồng migration 009 ↔ `DOC_VISIBILITY`.

**Integration** (marker `integration`, Postgres, schema test): nạp fixture 2 tài liệu nhỏ (1 `all`,
1 `commercial`); `retrieve(visibility={'all'})` không trả chunk `commercial` trên cả ba chân (kiểm
`method` để chắc chân nào đã đóng góp); `UNRESTRICTED` trả cả hai. Không chạy song song với suite
khác (schema test là tài nguyên dùng chung).

**Cổng dương** — `run_eval --set retrieval --model bge-m3 --role admin --baseline
evals/baseline-bge-m3-retrieval.json` → **GATE PASS**. Mốc trước 19b (2026-09-19, corpus 4 561 chunk có
SID): r@20 0,9771 · r@6 0,9633 · mrr 0,8012 · 2 fails · lat_p50 573 ms. Sau khi gỡ SID kỳ vọng
không giảm (bớt 660 chunk nhiễu).

**Cổng âm** — cùng lệnh `--role warehouse`, so với lượt admin bằng `evals/compare_visibility.py`:
**10 ca thương mại** (đo 2026-09-20: 10/10 là *thuần* — mọi nhãn mong đợi thuộc 4 tệp, 0 ca lẫn)
phải có `recall_at_pool = 0` **sạch** (không phải "thấp"); **99 ca còn lại** có
`recall_at_pool` **không kém** lượt admin — bất biến đúng là `>=`, không phải "giống hệt": gỡ ứng
viên không-đáp-án khỏi pool 20 không thể đẩy đáp án ra ngoài, chỉ có thể kéo nó vào; còn
`recall_at_final` (top-6 sau rerank) chỉ báo cáo vì pool khác thì reranker thấy tập khác. Đây là
tính chất bảo mật đo thành số, tất định, không LLM, không quota. Ghi cả hai lượt vào §10.

**Probe sống** (worktree, **trước merge** — `feedback_test_before_merge`): backend thật + Open WebUI
user id của 4 vai, cùng câu *"chính sách chiết khấu"*: `warehouse` → không có 5%/10%/15%, có lời từ
chối/không tìm thấy; `sales`/`accounting`/`admin` → có. Ghi nguyên văn 4 câu trả lời vào §10.

**Bất biến giữ nguyên**: `test_retrieval_cases.py` (nhãn đối chiếu `rag_chunks`) — 4 tài liệu
thương mại **vẫn trong corpus**, chỉ đổi lớp; bộ `retrieval` không đổi ca.

## 8. Cấu trúc mã

| tệp | thay đổi |
|---|---|
| `src/rag/visibility.py` | **mới** — §3 |
| `src/rag/retrieve.py` | `retrieve()` thêm `visibility`; ba chân thêm mệnh đề — §4 |
| `src/rag/ingest.py` | INSERT ghi `visibility` — §6 |
| `src/agents/roles.py` | `RoleCfg.rag_visibility` + 4 hồ sơ — §3 |
| `src/agents/nodes.py`, `src/agents/fanout.py`, `src/agents/graph.py` | truyền `role_cfg` xuống 2 node — §5 |
| `evals/run_eval.py`, `evals/role_config.py` | `--role` → visibility cho 3 bộ gọi `retrieve()` — §5 |
| `migrations/009_rag_visibility_backfill.sql` | **mới** — §6 |
| `tests/rag/…`, `tests/agents/…`, `tests/evals/…` | §7 |
| `docs/getting-started.md` | thêm 009 vào danh sách migration chạy tay |

## 9. Giới hạn biết trước / ngoài phạm vi

- **Fallback lặng lẽ sang corpus chung** khi Open WebUI không thấy nguồn (đường ô nhiễm NTC/SID) —
  lỗi riêng, ngoài 19b. Gỡ SID đóng *triệu chứng* đã gặp, không đóng *cơ chế*.
- **Nhãn theo mục/đoạn** — không làm; hạt tài liệu đủ cho 4 tệp hiện có.
- **Vệt kiểm toán "ai đã đọc bảng giá"** — đường đọc đã ghi vai từ 17b; không thêm gì ở 19b.
- **Chỉ số cho `visibility`** — chờ số `lat_p50` từ cổng dương.
- **Wire `retrieval` vào job đêm** — việc của #25 (cần quyết hạn mức).
- **Tài liệu người dùng** — thuộc Open WebUI theo quyết định §2.3; nếu sau này backend tự giữ kho
  riêng cho tài liệu cá nhân thì trục phân quyền là user/chat, thiết kế khác hẳn, spec khác.
- Thêm **vai mới** = sửa `RoleCfg` (code); thêm **lớp mới** = sửa `VISIBILITY_CLASSES` +
  `DOC_VISIBILITY` + một migration backfill nữa. Cả hai đều không đổi schema.

## 10. Ghi chép thực thi

Thi hành 2026-09-20, 10 task TDD, mỗi task một implementer + một review độc lập.

### Số đo

| Cổng | Kết quả |
|---|---|
| Suite unit (worktree, `not integration and not live`) | 2 859 passed, 1 skipped, 0 failed |
| Integration 19b (Postgres thật, chạy một mình) | 2 passed |
| Cổng DƯƠNG `--role admin` | `GATE PASS — model=0.963 baseline=0.963`, exit 0 |
| Cổng ÂM `compare_visibility` | `CỔNG ÂM PASS — thương mại 10 ca (lộ 0), khác 99 ca (kém đi 0)`, exit 0 |
| Probe sống 4 vai | PASS — kho không lộ, 3 vai còn lại đọc được |

Truy xuất, bộ `retrieval` 109 ca, `bge-m3` + rerank blend:

| | r@20 | r@6 | mrr | lat_p50 |
|---|---|---|---|---|
| Mốc trước 19b | 0,9771 | 0,9633 | 0,8012 | 573 ms |
| `admin` sau 19b | 0,9771 | 0,9633 | 0,7996 | 528 ms |
| `warehouse` sau 19b | 0,8853 | 0,8716 | 0,7248 | 521 ms |

`admin` **bằng đúng** mốc cũ ở hai chỉ số được gác. Phần sụt của `warehouse` là
0,9771 − 0,8853 = **0,0918 ≈ 10/109 = 0,0917** — đúng bằng 10 ca thương mại rơi về 0,
không ca nào khác mất. Đây là kiểm chéo số học độc lập với dòng PASS của cổng âm.
`lat_p50` giảm 573→528 ms vì pool nhỏ đi sau khi gỡ 660 chunk SID.

### Migration 009 trên DB thật

Trước: `[('all', 4561)]`, SID 1 tài liệu / 660 chunk, tổng 18 tài liệu / 4 561 chunk.
Sau: `[('all', 3877), ('commercial', 24)]`, SID 0/0, tổng 17 tài liệu / 3 901 chunk.
24 chunk `commercial` đúng 4 tệp: `bang_gia` 8, `discount_policy` 5, `payment_policy` 5, `sla` 6.

Trước khi chạy đã chụp ảnh `backup_pre009` (18 tài liệu / 4 561 chunk, đủ embedding).
**`backup_20260919` mà plan viện dẫn là ảnh CŨ** (4 870 chunk / 968 chunk SID, chụp trước lần
nạp lại corpus 19/09) — khôi phục từ đó sẽ trả về corpus cũ, không phải trạng thái trước 009.

### Probe sống — toàn văn rút gọn

Cùng câu hỏi "Chính sách chiết khấu của công ty như thế nào?", 4 vai, qua backend thật:

- `sales` / `accounting` / `admin`: trả đúng chính sách (3 cấp khách hàng, 5%/10%, cộng 2% cho
  đơn ≥ 50 triệu, trần 15%), chú thích nguồn 5 mục của `discount_policy.docx`.
- `warehouse`: trả về **chuyện bán cổ phần** trích `luat-doanhnghiep.pdf` Điều 126. Không có
  `5%`, `10%`, `15%`, `2%`, không có "chiết khấu theo cấp", không có `discount_policy`.
  Tức chunk thương mại **không vào tới retrieval**, chứ không phải LLM may mà không nhắc.

### Khó khăn và giới hạn còn lại

1. **Vai bị chặn không được BÁO là bị chặn.** `warehouse` nhận một câu trả lời lạc đề từ corpus
   công khai chứ không có thông điệp từ chối. Đúng thiết kế (lọc ở tầng retrieval), nhưng người
   dùng thật sẽ tưởng trợ lý hiểu sai câu hỏi. Đáng cân nhắc cho một mục sau.
2. **`synthesis_live` và `multiturn` chưa có cổng theo vai.** Hai bộ này đã nhận `--role` và JSON
   đã tự khai `role`, nhưng chưa có baseline/gate nào đọc nó. Một lượt đo sai vai ở hai bộ đó
   hiện chỉ phát hiện được bằng cách đọc khoá `role` trong tệp kết quả.
3. **`LIKE '%tên'` trong migration khớp rộng hơn `basename()` của Python.** `_` là ký tự đại diện
   trong `LIKE` nên `payment_policy.docx` cũng khớp `paymentXpolicy.docx`. Đã đo trên corpus thật:
   bắt đúng 4 tệp / 24 chunk, không thừa không sót. Rủi ro còn lại là một lần nạp **tương lai** có
   tệp tên kiểu `old_discount_policy.docx` sẽ bị gắn `commercial` oan — sai theo chiều giấu nhiều
   hơn, không phải chiều lộ.
4. **Không có ràng buộc cấu trúc cho chân retrieval thứ tư.** Nếu ai đó thêm một chân mới mà quên
   `_vis_clause`, không test nào hiện nay đỏ. An toàn đang dựa vào người viết nhớ.
5. **`jobs/resilience.py` nuốt mọi exception** (ADR-009 §2.2, có chủ đích). Một lỗi trong
   `_retrieve` biến thành `errors` + `per_case` rỗng chứ không nổ — chính cơ chế này đã biến một
   `TypeError` thành `assert 0 == 1` khó hiểu trong lúc thi hành Task 7.

### Giả thuyết bị bác trong lúc thi hành

- *"Test đỏ ở `tests/evals/` là có sẵn, không liên quan"* — SAI. Task 7 làm hỏng nó; lượt kiểm
  chứng của chính Task 7 đã bỏ qua đúng thư mục nó vừa sửa.
- *"Thêm module vào danh sách parametrize của `test_cli_utf8.py` là đủ để bắt lỗi cp1252"* — SAI.
  Test đó chỉ import và tự gọi `use_utf8_streams()`, không gọi `main()` của module, nên xanh cả
  trước lẫn sau khi sửa. Phải có test chạy CLI thật qua subprocess mới bắt được.
