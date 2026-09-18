# Mở rộng nhóm `hard` của bộ `retrieval` — thiết kế

**Ngày**: 2026-09-18. **Nhánh**: `worktree-so-sanh-reranker` (làm tiếp trên nhánh, chưa merge).
**Trạng thái**: ĐÃ THI HÀNH VÀ ĐO XONG (2026-09-18) — Task 1–7 hoàn tất trên nhánh; kết luận theo quy tắc §8 là **XÁC NHẬN** (xem §11), production chưa đổi gì.

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
- **Nghiệp vụ: 1 ca mỗi tệp CÒN nút chưa gán nhãn.** Đo 2026-09-18: `policy.docx` đã bị 64 ca
  cũ gán nhãn cả 5/5 mục → 0 nút; sáu tệp kia còn nút → **6 ca**. Trần là 36 nút, phần lớn đã có
  ca cũ chạm.
- **Luật: 45 − (số ca nghiệp vụ) = 39 ca**, chia theo tỉ lệ số nút sau lọc, phần dư lớn nhất,
  sàn 1 mỗi luật. Script tính; lệch ±1 so với ước tính là bình thường và **không sửa tay**.
- **Tái lập:** script loại nút "đã có nhãn" bằng cách đọc **`_CORE` (64 ca cũ)**, KHÔNG đọc
  `RETRIEVAL_CASES` — nếu không, sau khi nối bộ mở rộng thì 45 nút mới cũng thành "đã có nhãn"
  và chạy lại script ra bộ khác. Cổng nghiệm thu: chạy lại script sau đóng băng phải cho JSON
  y hệt.

Trong mỗi tầng: sắp xếp nút theo `(basename, section_path)`; với N nút chọn k nút tại chỉ số
`floor(offset + i·N/k)`, `i = 0..k−1`, `offset = ((seed mod 1000)/1000)·(N/k)`.
**`seed = 20260918`**, ghi ở đây và trong docstring của `HARD_EXPANSION_CASES`.

**Bảng phân bổ thật** (chạy `python -m evals.sample_hard_sections` trên corpus 2026-09-18,
in ra stderr; thay cho ước tính trước khi lọc ở trên):

| basename | ca | pool sau lọc |
|---|---:|---:|
| policy.docx | 0 | 0 |
| discount_policy.docx | 1 | 2 |
| payment_policy.docx | 1 | 3 |
| sla.docx | 1 | 3 |
| sop.docx | 1 | 1 |
| sales_process.docx | 1 | 4 |
| warehouse_outbound.docx | 1 | 2 |
| boluat-danssu.pdf | 15 | 700 |
| boluat-thuongmai.pdf | 7 | 331 |
| boluat-laodong.pdf | 4 | 221 |
| luat-doanhnghiep.pdf | 4 | 218 |
| luat-quanlythue.pdf | 3 | 153 |
| luat-baohiemxahoi.pdf | 3 | 141 |
| luat-dautu.pdf | 1 | 59 |
| luat-thuexuatnhapkhau.pdf | 1 | 23 |
| luat-thuegtgt.pdf | 1 | 18 |
| **tổng** | **45** | |

6 ca nghiệp vụ (đúng ước tính), 39 ca luật — khớp `45 − 6 = 39`.

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

**Kết quả (Task 5, 2026-09-18):** 45 ca viết thành công (0 bỏ, xem `backend/evals/hard_expansion_cases.py`); toàn bộ 45 qua cổng overlap ≤ 0,40. Final: **`n_hard = 62`** (17 cũ + 45 mới).

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

## 10. Ghi chép thực thi

Toàn bộ số dưới đây đọc từ 6 JSON trong `backend/evals/results/reranker-2026-09-18-mo-rong/`
(commit `d2e37cd`; golden set đóng băng ở `0398c04`, trước mọi JSON theo `git log`). Ba bảng
đầu chép nguyên từ `README.md` của thư mục đó — đã được kiểm chứng ở Task 6, không tính lại tay.

### 10.1 Bảng 6 chân trên bộ mở rộng (109 ca, `n_hard = 62`)

| chân | r@6 | r@20 | mrr | easy | **hard62** | trap | p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| no-rerank | 0,8838 | 0,9771 | 0,6551 | 0,7673 | 0,5697 | 0,7682 | 497 |
| bge-v2-m3 | 0,9633 | 0,9771 | 0,8058 | 0,8968 | 0,7392 | 0,8875 | 712 |
| qwen3-0.6b | 0,9419 | 0,9771 | 0,8066 | 0,8807 | 0,7647 | 0,8250 | 1182 |
| qwen3-4b | 0,9541 | 0,9771 | 0,8123 | 0,8836 | 0,7563 | 0,8906 | 23946 |
| qwen3-0.6b-override | 0,9587 | 0,9771 | 0,8638 | 0,9258 | 0,8460 | 0,8125 | 1154 |
| qwen3-4b-override | 0,9679 | 0,9771 | 0,8921 | 0,9382 | 0,8681 | 0,8958 | 4568 |

`errors = 0` và `methods_seen` đúng ở cả 6 chân (`dense+fold-rrf` cho no-rerank,
`dense+fold-rrf+rerank` cho 5 chân còn lại). `p50` của hai chân 4B là đường `device_map=auto`
tràn CPU (stderr: "Some parameters are on the meta device because they were offloaded to the
cpu") — không đại diện triển khai, xem Giới hạn.

### 10.2 Đối chứng hạ tầng `old-64` (§7)

Mỗi chân so `per_case` với chân cùng tên trong `reranker-2026-09-17/` trên 64 câu cũ.

| chân | n | ca `recall_at_final` khác | `hard17 mrr` cũ | mới | lệch |
|---|---:|---:|---:|---:|---:|
| no-rerank | 64 | 0 | 0,5403 | 0,5403 | 0,0000 |
| bge-v2-m3 | 64 | 0 | 0,5755 | 0,5755 | 0,0000 |
| qwen3-0.6b | 64 | 0 | 0,6196 | 0,6196 | 0,0000 |
| qwen3-4b | 64 | 0 | 0,6814 | 0,6814 | 0,0000 |
| qwen3-0.6b-override | 64 | 0 | 0,7173 | 0,7173 | 0,0000 |
| qwen3-4b-override | 64 | 0 | 0,8255 | 0,8255 | 0,0000 |

Cổng §7 đạt ở mức chặt nhất (0 ca khác, lệch 0,0000): hạ tầng truy xuất không trôi giữa hai
vòng đo, kể cả khi hai chân 4B chạy với `RERANK_GPU_BUDGET` khác vòng trước.

### 10.3 Cổng R12 — `recall@6` trên 45 câu MỚI không dưới chân tắt rerank (thêm giữa chừng, xem Khó khăn)

| chân | `r@6` new45 | `mrr` new45 | |
|---|---:|---:|---|
| no-rerank | 0,8667 | 0,5809 | mốc |
| bge-v2-m3 | 0,9556 | 0,8010 | đạt |
| qwen3-0.6b | 0,9333 | 0,8196 | đạt |
| qwen3-4b (chạy lại) | 0,9333 | 0,7847 | đạt |
| qwen3-0.6b-override | 0,9556 | 0,8946 | đạt |
| qwen3-4b-override | 0,9556 | 0,8843 | đạt |

### 10.4 Kiểm định ghép cặp — đầu ra nguyên văn (Task 7, 2026-09-18)

`evals.retrieval_stats` chỉ đọc JSON (hoán vị chính xác + bootstrap 20 000 lượt, seed cố định);
`n`, `chenh_TB`, `p`, `thang/hoa/thua` tất định, biên CI có thể lệch ±0,005 giữa máy.
`new-45-questions.json` sinh từ `HARD_EXPANSION_CASES` (45 câu, chỉ để lọc câu), commit cùng lượt.

```
$ cd backend; R=evals/results/reranker-2026-09-18-mo-rong
$ S="python -m evals.retrieval_stats"
== CHINH: hard-62, 4B override vs bge hoa ==
$ $S $R/bge-v2-m3.json $R/qwen3-4b-override.json --difficulty hard
n=62  chenh_TB=+0.1290  CI95=[+0.060,+0.202]  p=0.0007  thang/hoa/thua=18/42/2
== new-45 rieng ==
$ $S $R/bge-v2-m3.json $R/qwen3-4b-override.json --questions-from $R/new-45-questions.json
n=45  chenh_TB=+0.0832  CI95=[+0.022,+0.149]  p=0.0146  thang/hoa/thua=10/34/1
== cong 3-4: toan bo ca ==
$ $S $R/bge-v2-m3.json $R/qwen3-4b-override.json
n=109  chenh_TB=+0.0864  CI95=[+0.038,+0.137]  p=0.0010  thang/hoa/thua=24/80/5
== hard-62: qwen3-0.6b vs bge ==
$ $S $R/bge-v2-m3.json $R/qwen3-0.6b.json --difficulty hard
n=62  chenh_TB=+0.0256  CI95=[-0.024,+0.075]  p=0.3208  thang/hoa/thua=11/46/5
  VANG (other mat, base giu): Ai đó không phải chủ nhưng đang được lâu dài khai thác, thu lợi từ một tài sản, có được cho bên khác thuê lại phần khai thác ấy không?
== hard-62: qwen3-4b vs bge ==
$ $S $R/bge-v2-m3.json $R/qwen3-4b.json --difficulty hard
n=62  chenh_TB=+0.0172  CI95=[-0.025,+0.059]  p=0.4440  thang/hoa/thua=11/47/4
  VANG (other mat, base giu): Ai đó không phải chủ nhưng đang được lâu dài khai thác, thu lợi từ một tài sản, có được cho bên khác thuê lại phần khai thác ấy không?
== hard-62: qwen3-0.6b-override vs bge ==
$ $S $R/bge-v2-m3.json $R/qwen3-0.6b-override.json --difficulty hard
n=62  chenh_TB=+0.1068  CI95=[+0.029,+0.189]  p=0.0101  thang/hoa/thua=18/38/6
  VANG (other mat, base giu): bên bán phải đóng gói hàng ra sao trước khi chuyển đi?
```

Phép so "toàn bộ ca" của `qwen3-4b-override` **không in dòng `VANG` nào** (CLI in một dòng
mỗi ca `other` mất top-6 mà `base` còn giữ — kiểm lại thẳng trên `per_case`: 0 ca; chiều
ngược lại bge mất/4B giữ: 1 ca). Trường `recall_at_6` đọc từ JSON: `bge-v2-m3` 0,9633,
`qwen3-4b-override` 0,9679.

### 10.5 Bốn chân so với `bge` hoà trên `hard-62` (một bảng)

| chân (other) | n | chênh TB (RR) | CI95 | p hoán vị | thắng/hoà/thua | ca `VANG` |
|---|---:|---:|---|---:|---|---:|
| qwen3-0.6b (hoà) | 62 | +0,0256 | [−0,024; +0,075] | 0,3208 | 11/46/5 | 1 |
| qwen3-4b (hoà) | 62 | +0,0172 | [−0,025; +0,059] | 0,4440 | 11/47/4 | 1 |
| qwen3-0.6b-override | 62 | +0,1068 | [+0,029; +0,189] | 0,0101 | 18/38/6 | 1 |
| **qwen3-4b-override** | **62** | **+0,1290** | **[+0,060; +0,202]** | **0,0007** | **18/42/2** | **0** |

Đọc bảng: hai chân **hoà** (blend) của Qwen3 không khác bge trên `hard-62` (CI cắt 0, p > 0,3)
— tín hiệu "+0,106 4B hoà" ở §1 tan hẳn. Hai chân **override** đều dương; `0.6B override` sát
mép (p = 0,0101, hụt ngưỡng 0,01 của §8 một sợi tóc, và làm văng 1 ca `hard` bge còn giữ).
Chỉ `4B override` qua đủ cả bốn điều kiện.

### 10.6 `hard mrr` tách 17 ca cũ / 45 ca mới (đọc thẳng `per_case`)

| chân | `hard` cũ-17 | `hard` mới-45 | `hard-62` |
|---|---:|---:|---:|
| no-rerank | 0,5403 | 0,5809 | 0,5697 |
| bge-v2-m3 | 0,5755 | 0,8010 | 0,7392 |
| qwen3-0.6b | 0,6196 | 0,8196 | 0,7647 |
| qwen3-4b | 0,6814 | 0,7847 | 0,7563 |
| qwen3-0.6b-override | 0,7173 | 0,8946 | 0,8460 |
| qwen3-4b-override | 0,8255 | 0,8843 | 0,8681 |

Chênh `4B override − bge`: **+0,250** trên 17 cũ, **+0,083** trên 45 mới, **+0,129** trên 62.
`new-45` **đồng thuận về chiều** với `hard-62` (10 thắng / 1 thua, CI không cắt 0) nhưng **không
đạt ngưỡng p < 0,01** (p = 0,0146) — nói rõ ở §11.

### Khó khăn

- **Nút bỏ: 0.** `DROPPED_NODES` trong `hard_expansion_cases.py` rỗng — 45/45 nút được viết
  câu qua cổng overlap ≤ 0,40 trong ≤ 3 lần. Review trước đóng băng sửa 4 câu (`e55b22c`,
  16:08 — đảo vai chủ thể, tiền đề không có trong chunk); đóng băng `0398c04` lúc 16:22; JSON
  đầu tiên 16:28. Không câu nào bị chạm sau khi đã thấy số.
- **Chân bị ngắt / chạy lại: 1 chân (`qwen3-4b` hoà)**; Task 6 chạy vắt qua một lần máy reset
  (cạn RAM) cùng một lần chạm giới hạn tốc độ API của phiên agent — controller tự hoàn tất phần
  còn lại của Task 6.
- **Lượt `qwen3-4b` hoà đầu tiên (17:19, trước reset máy) qua MỌI kiểm tra cơ học** —
  `errors = 0`, `methods_seen` đúng, `rerank_model`/`rerank_mode` khớp, và qua trọn cổng đối
  chứng `old-64` của §7 (0 ca khác) — **mà vẫn hỏng**: trên 45 câu mới `r@6 = 0,6444`, thấp
  hơn cả chân tắt rerank (0,8667). Nguyên nhân: `run_eval` chạy 64 ca cũ TRƯỚC, 45 ca mới SAU;
  chân 4B tràn ~5 GB trọng số sang RAM CPU và máy cạn RAM giữa lượt. Đây KHÔNG phải fail-open:
  fail-open trả nguyên thứ tự RRF (`retrieve.py`: `scores is None → return chunks, False`) thì
  `r@6` sẽ bằng đúng chân tắt rerank 0,8667 và `methods_seen` mất `+rerank`; ở đây
  `methods_seen` vẫn đủ mà `r@6` tụt DƯỚI 0,8667 — reranker vẫn trả điểm, nhưng điểm sai.
  Lượt đó bị LOẠI, chạy lại cho `r@6 new-45 = 0,9333`.
  Điểm mù đây là **của thiết kế §7**: cổng đối chứng chỉ soi phần chạy đầu, một chân có thể
  "đúng 64 ca đầu, sai 45 ca sau" mà cổng vẫn xanh. Thêm cổng R12 (10.3) sau khi phát hiện.
- Hai chân 4B dùng `RERANK_GPU_BUDGET` khác nhau: hoà 4GiB (50 phút, GPU đầy 7,6/8,15 GB,
  p50 24 s — thrashing), override 3GiB (12,5 phút, p50 4,6 s). Chỗ đặt trọng số không đổi phép
  toán — bảng 10.2 chứng minh cả hai tái tạo số 2026-09-17 trên 64 ca cũ y hệt.

### Hướng chọn

- Không đo thêm, không đổi câu, không dời quy tắc: §8 đăng ký trước được áp nguyên (§11).
- Lượt 4B hỏng bị loại thay vì "vá" JSON; cổng R12 được thêm như cổng thứ hai, không thay
  cổng §7. R12 lấy mốc là chân `no-rerank` vì đó là mức sàn bất kỳ reranker sống nào phải
  vượt — thấp hơn nó nghĩa là reranker không chạy.
- `new-45-questions.json` (chỉ danh sách câu, `reciprocal_rank = 0` giả) được commit cùng kết
  luận để phép so `--questions-from` tái lập được mà không cần import mã.
- `--save-baseline` cho chân bge hoà: `baseline-bge-m3-retrieval.json` giờ phản ánh 109 ca.

### Giới hạn còn lại

- **`trap` vẫn n = 16, kém lực** — không mở rộng ở lượt này (§ "cố ý không làm"). Con số
  `trap` của 4B override (0,8958 so 0,8875 bge) chỉ nói "không tụt rõ", không nói "giữ".
- **Độ trễ 4B là artefact đường offload**: p50 4568 ms (3GiB) / 23946 ms (4GiB) đều không phải
  số triển khai; chưa có số nào cho 4B chạy trọn GPU hoặc lượng tử hoá.
- **Cổng lượng tử hoá 4B chưa chạy** và giờ là câu hỏi **độ trễ + giữ `trap`/`mrr`**, không còn
  là recall: trên 109 ca `r@20 = 0,9771` ở mọi chân (trần pool 20 ứng viên), 4B override
  `r@6 = 0,9679` — hết chỗ để recall tăng, chỉ còn thứ hạng trong top-6.
- **Cổng §7 mù với các ca chạy sau** (xem Khó khăn) — bài học thiết kế: cổng đối chứng hạ tầng
  phải phủ cả đầu lẫn cuối lượt chạy, hoặc eval phải xáo thứ tự ca. Lượt này vá bằng R12; lượt
  sau nên đưa vào `run_eval` hoặc test hợp đồng thay vì kiểm tay.
- **`0.6B override` chưa được xử lý**: p = 0,0101 là "hụt ngưỡng" chứ không phải "không có
  gì"; §8 chỉ đặt câu hỏi cho 4B override nên spec này không kết luận về 0.6B. Nếu cổng lượng
  tử hoá 4B thất bại về độ trễ, 0.6B override (chạy trọn GPU, p50 1154 ms) là ứng viên tiếp
  theo và cần quy tắc đăng ký trước riêng.
- Các giới hạn §9 giữ nguyên: cổng overlap chỉ đo từ vựng với tiêu đề; một nhãn mỗi ca; 45 câu
  chung một "giọng"; corpus 18 tài liệu.

## 11. Kết luận

**XÁC NHẬN.** Bốn điều kiện §8, kiểm từng điều trên số ở 10.4:

1. CI95 bootstrap của chênh lệch TB (`hard-62`) **[+0,060; +0,202] — không cắt 0** ✓
2. p hoán vị **0,0007 < 0,01** ✓
3. `recall@6` trên 109 ca: 4B override **0,9679 ≥ 0,9633** bge hoà ✓
4. Trên 109 ca: **0 ca** 4B override làm văng khỏi top-6 mà bge hoà còn giữ (không dòng `VANG`) ✓

Tín hiệu +0,25 `hard mrr` của `qwen3-4b-override` được xác nhận trên n=62: chênh +0,1290, CI95 [+0,060; +0,202], p=0,0007. Việc còn lại trước khi thay production: cổng lượng tử hoá (độ trễ + giữ `trap`/`mrr`) — không còn là câu hỏi recall.

Hai điều phải đọc kèm kết luận, không làm đổi kết luận:

1. **Độ lớn hiệu ứng co lại**: +0,25 trên 17 ca `hard` cũ → **+0,129** trên 62 ca. 17 ca cũ là
   chính những ví dụ đã thúc đẩy nhánh này và nghiêng về chỗ yếu của bge (`hard mrr` của bge:
   0,5755 trên 17 cũ so 0,8010 trên 45 mới, bảng 10.6). Mẫu tất định + agent mù đã gỡ độ
   nghiêng đó; con số đáng tin là +0,129, không phải +0,25.
2. **Trên 45 câu MỚI riêng** (phần duy nhất chưa ai nhìn trước khi đặt quy tắc): CI95
   [+0,022; +0,149] không cắt 0, 10 thắng / 34 hoà / 1 thua, **nhưng p = 0,0146 — không dưới
   ngưỡng 0,01 mà chính spec này đặt ra**. Chiều đồng thuận với `hard-62`, độ mạnh yếu hơn
   con số gộp. §8 quy định `new-45` là phần báo thêm, không phải phần quyết định, nên kết
   luận giữ nguyên — nhưng ai đọc con số +0,129 phải biết một phần lực của nó đến từ 17 ca
   đã bị nhìn.
