# Mở rộng nhóm `hard` của bộ `retrieval` — thiết kế

**Ngày**: 2026-09-18. **Nhánh**: `worktree-so-sanh-reranker` (làm tiếp trên nhánh, chưa merge).
**Trạng thái**: thiết kế đã duyệt qua thảo luận (phần A, B, C), chưa viết code.

Tiếp nối `2026-09-17-so-sanh-reranker-design.md`. Spec đó kết luận "4B đáng đi tiếp"; spec
này trả lời câu hỏi chủ dự án đặt ra sau đó: **với cỡ mẫu hiện tại, số đó có đáng tin không.**

---

## 1. Đề bài, đo được

Kiểm định ghép cặp trên `per_case` của 6 chân đo ngày 2026-09-17/18 (hoán vị chính xác +
bootstrap 20 000 lượt), so với production (`bge-reranker-v2-m3`, hoà 1:1):

| chân | nhóm | n | chênh TB (RR) | CI95 | p hoán vị | thắng/hoà/thua |
|---|---|---|---|---|---|---|
| 4B hoà | hard | 17 | +0,106 | [−0,011; +0,224] | 0,117 | 8/8/1 |
| **4B override** | **hard** | **17** | **+0,250** | **[+0,059; +0,436]** | **0,027** | 8/8/1 |
| 0.6B override | hard | 17 | +0,142 | [−0,035; +0,322] | 0,150 | 8/6/3 |
| 0.6B override | trap | 16 | −0,075 | [−0,242; +0,071] | 0,438 | 2/11/3 |

Ba kết luận:

1. **Chỉ một ô trong 12 phép so có CI không cắt 0**, và với 12 phép so thì ngưỡng Bonferroni
   là 0,0042 — ô đó cũng không qua. Kết luận "4B thắng rõ" của spec trước là **quá lời**.
2. **Lý do loại 0.6B ở cổng 2 của spec trước (`trap` tụt) cũng nằm trong nhiễu** (p = 0,438).
3. Trong 17 ca `hard` chỉ **9 ca thực sự đổi thứ hạng**; bỏ 3 ca ảnh hưởng nhất thì chênh
   lệch tụt +0,250 → +0,137. Với sd ≈ 0,395, để sai số chuẩn xuống 0,05 cần **~62 ca `hard`**.

Đây là vấn đề **cỡ mẫu**, tách khỏi vấn đề **corpus nhỏ** (18 tài liệu / 4 870 chunk): reranker
luôn chấm đúng 20 ứng viên, corpus nhỏ chỉ làm 20 ứng viên đó ít lẫn nhau hơn. Spec này chữa
cỡ mẫu; corpus là việc khác.

## 2. Hai quyết định chủ dự án đã chốt

- **Đo lại cả 6 chân** trên bộ mở rộng (không chỉ 2 chân quyết định). Giá: ~30–40 phút GPU
  liên tục, hai chân 4B nặng nhất, xếp chạy cuối.
- **Lấy mẫu tất định + agent mù viết câu** — không tự chọn tay. Tiền lệ trong dự án
  (`feedback_gate_sample_selection`): 7 trang tự chọn đạt 1,000, 21 trang còn lại của cùng tài
  liệu chỉ 0,537.

## 3. Cổng `hard` — từ phán đoán thành số đo

Thước: `overlap(question, section_paths) -> float` = |tokens(q) ∩ tokens(lá)| / |tokens(lá)|, trong đó
`tokens(s)` = tập các `\w+` của `fold_vi(s).lower()` có độ dài > 1, và `lá` là phần sau dấu
`›` cuối cùng của `section_path`. `section_paths` là mọi nhãn của ca; nhiều nhãn thì lấy max.

Hiệu chỉnh trên 64 ca hiện có (đo 2026-09-18):

| nhóm | n | trung vị | p25 | p75 |
|---|---|---|---|---|
| easy | 31 | 0,67 | 0,60 | 0,78 |
| hard | 17 | 0,33 | 0,20 | 0,50 |
| trap | 16 | 0,64 | 0,50 | 0,75 |

**Ngưỡng chọn: ≤ 0,40.** Loại 28/31 ca easy; 10/17 ca hard cũ qua được. Không sạch tuyệt đối —
vài ca `hard` cũ được gán bằng ngữ nghĩa (overlap tới 0,83) — nên cổng **chỉ áp lên ca MỚI**:
ca mới phải xa tiêu đề ít nhất bằng ca `hard` trung bình hiện tại. Cổng sống ở
`evals/hard_gate.py` (một hàm, thuần), dùng chung cho agent viết câu và cho test hợp đồng.

## 4. Lấy mẫu — tất định, phân tầng, tái lập được

### 4.1 Lọc rác trước, bằng luật

Loại nút `(basename, section_path)` khi bất kỳ điều nào đúng:
- `section_path` rỗng;
- `basename` là báo cáo tài chính `SID_…BaoCaoTaiChinh…pdf` (100 nút, breadcrumb dạng
  `"Chương trình › 39 BIẾT KP"`, không gán nhãn được);
- lá sau chuẩn hoá (bỏ dấu câu, gộp khoảng trắng, lower, `fold_vi`) thuộc tập quốc hiệu/tiêu
  ngữ/từ loại văn bản trần: `quoc hoi`, `cong hoa xa hoi chu nghia viet nam`, `doc lap tu do
  hanh phuc`, `chu tich quoc hoi`, `luat`, `bo luat`, `nghi dinh`, `thong tu`;
- lá có < 3 token độ dài > 1 (mảnh câu, số điều trống);
- cặp `(basename, section_path)` đã là nhãn của một ca trong 64 ca hiện có.

Luật này nằm trong `evals/sample_hard_sections.py`, không nằm trong đầu ai.

### 4.2 Phân tầng và bước nhảy

Sau lọc còn ≈ 1 900 nút ở 9 PDF luật và 36 nút ở 7 `.docx` nghiệp vụ. Phân bổ **45 ca**:
- **7 ca nghiệp vụ**: đúng 1 mỗi tệp (`policy`, `discount_policy`, `payment_policy`, `sla`,
  `sop`, `sales_process`, `warehouse_outbound`). Trần là 36 nút, phần lớn đã có ca cũ chạm.
- **38 ca luật**: chia theo tỉ lệ số nút sau lọc, phần dư lớn nhất, sàn 1 mỗi luật. Ước tính
  trước khi lọc: dân sự 14, thương mại 7, lao động 4, doanh nghiệp 4, quản lý thuế 3, BHXH 3,
  đầu tư 1, XNK 1, GTGT 1. Script tính lại sau lọc; lệch ±1 là bình thường và **không sửa tay**.

Trong mỗi tầng: sắp xếp nút theo `(basename, section_path)`; với N nút chọn k nút tại chỉ số
`floor(offset + i·N/k)`, `i = 0..k−1`, `offset = ((seed mod 1000)/1000)·(N/k)`.
**`seed = 20260918`**, ghi ở đây và trong docstring của `HARD_EXPANSION_CASES`.

## 5. Viết câu — agent mù

Một agent MỚI nhận **đúng 45 nút** kèm toàn bộ `chunk_text` của mỗi nút, cùng hàm
`hard_gate.overlap`. Nó **không** nhận spec này, spec trước, kết quả đo nào, và không được biết
đang so reranker nào.

Với mỗi nút, agent viết:
- **một câu hỏi** bằng lời người dùng thường (không dùng từ ngữ của tiêu đề, không nêu số
  Điều/Mục), hỏi đúng một điều mà chunk trả lời được;
- **một dòng trích nguyên văn** từ chunk chứa câu trả lời — để người review kiểm "đáp án có
  thật ở đó";
- **điểm overlap** tự tính.

Overlap > 0,40 → viết lại, tối đa 3 lần; vẫn không qua → **bỏ nút đó và ghi vào danh sách
bỏ**, không thay bằng nút tự chọn. Nhãn của ca = chính nút đã lấy mẫu (một nhãn). Rủi ro chấp
nhận: một mục anh em trả lời được câu đó và xếp trên → RR bị phạt oan; bộ cũ cũng có rủi ro
này, ghi ở giới hạn.

## 6. Cấu trúc mã

| tệp | trách nhiệm |
|---|---|
| `backend/evals/hard_gate.py` | **Mới.** `overlap(question, section_paths) -> float`, thuần. |
| `backend/evals/sample_hard_sections.py` | **Mới.** Lọc rác §4.1 + lấy mẫu §4.2, đọc `rag_chunks`, in 45 nút + bảng phân bổ. |
| `backend/evals/retrieval_cases.py` | **Sửa.** Thêm `HARD_EXPANSION_CASES` (45 ca, docstring ghi seed + script); `RETRIEVAL_CASES = _CORE + HARD_EXPANSION_CASES`. 64 ca cũ không đổi một ký tự. |
| `backend/evals/retrieval_stats.py` | **Mới.** Hoán vị ghép cặp + bootstrap trên hai `per_case`, thuần; CLI so hai JSON theo nhóm. |
| `backend/tests/evals/test_hard_gate.py` | **Mới.** Thước overlap trên chuỗi giả. |
| `backend/tests/evals/test_retrieval_stats.py` | **Mới.** Kiểm định trên dữ liệu giả có đáp án biết trước. |
| `backend/tests/evals/test_retrieval_cases.py` | **Sửa.** Thêm: `n_hard ≥ 60`; mọi ca trong `HARD_EXPANSION_CASES` có overlap ≤ 0,40; 64 ca cũ giữ nguyên (băm nội dung). Test `integration` sẵn có gác nhãn tồn tại thật. |
| `backend/evals/results/reranker-2026-09-18-mo-rong/` | **Mới.** 6 JSON + README. |

`run_eval.py` **không đổi**: nó đã trả `per_case`, `rerank_model`, `rerank_mode`.

## 7. Đo

**Thứ tự bắt buộc:** cổng + script + 45 ca + test xanh + **commit** → rồi mới chạy chân đầu tiên.
Không sửa câu nào sau khi đã thấy số.

Sáu chân như spec trước (no-rerank; bge hoà; 0.6B hoà; 4B hoà; 0.6B override; 4B override),
mỗi chân một tiến trình, tuần tự, 4B với `RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=3GiB`.
Kiểm `methods_seen`/`errors` trước khi tin số.

Mỗi chân đọc ra **ba góc nhìn** từ `per_case`:
- `hard-62` (17 cũ + 45 mới): phép so quyết định;
- `old-64`: **đối chứng hạ tầng** — phải khớp lần đo 2026-09-17/18 của cùng chân (mọi ca
  `recall_at_final` giống hệt, `hard mrr` trên 17 ca cũ lệch ≤ 0,02). Đúng 1 ca khác → ghi tên ca và
  đi tiếp; nhiều hơn → hạ tầng đổi, **dừng và tìm
  nguyên nhân**, không đọc tiếp;
- `new-45`: phần bằng chứng **chưa bị nhìn trước**.

Cuối cùng `--save-baseline` cho chân bge hoà để baseline lưu trữ phản ánh 109 ca.

## 8. Quy tắc quyết định — đăng ký trước, không dời

**Phép so chính:** `hard-62`, ghép cặp `4B override` với `bge hoà`, trên `reciprocal_rank`.

**XÁC NHẬN** khi và chỉ khi tất cả:
1. CI95 bootstrap của chênh lệch TB **không cắt 0**;
2. p hoán vị **< 0,01** (nghiêm hơn 0,05 vì đây là lần nhìn thứ hai và sẽ báo 5 chân so với bge);
3. trên 109 ca: `recall@6` của 4B override ≥ của bge hoà;
4. trên 109 ca: không ca nào 4B override làm văng khỏi top-6 mà bge hoà còn giữ.

**KHÔNG XÁC NHẬN** (bất kỳ điều nào trên hỏng) → kết luận ghi thẳng: *giữ bge, dừng hướng đổi
reranker, chuyển sang cải thiện pool* (4B override đã chạm trần pool `recall@6 = recall@20`).
**Không có lựa chọn "đo thêm lần nữa".**

Báo thêm, không đổi quyết định: cùng phép so trên `new-45` riêng. Nếu `hard-62` xác nhận mà
`new-45` không, phải nói rõ — 17 ca cũ đã bị nhìn, chúng có thể đang kéo.

## 9. Giới hạn biết trước

- Cổng overlap chỉ đo **từ vựng với tiêu đề**; một câu có thể qua cổng mà vẫn dễ với dense
  retriever vì trùng từ với **thân** chunk. Chấp nhận: định nghĩa `hard` của bộ cũ cũng là "không
  mượn từ ngữ của tiêu đề".
- Một nhãn mỗi ca (§5). Mục anh em xếp trên sẽ bị chấm sai; bộ cũ cùng rủi ro.
- 45 câu do một agent viết → có "giọng" chung. Đây là cái giá của mù; nguồn câu hỏi thật của
  người dùng không tồn tại (hệ không lưu lịch sử chat).
- Corpus vẫn 18 tài liệu. Kết quả nói về **bộ đo này**; chiều có lẽ giữ khi corpus lớn, độ lớn
  thì không.
- Thời gian GPU ~35 phút liên tục; chủ dự án có thể lấy lại GPU giữa chừng — quy trình tạm
  dừng/tiếp tục đã chạy hai lần ở spec trước, dùng lại.
