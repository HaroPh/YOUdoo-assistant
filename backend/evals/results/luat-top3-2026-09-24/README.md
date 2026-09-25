# Luật "báo bị chặn": lưới {luật cũ, luật mới} × k ∈ 1…6 (2026-09-24)

**Kết luận: GIỮ NGUYÊN luật hiện tại và `HIDDEN_TOP_K = 3`.** Luật thay thế
được đề xuất đã bị số đo BÁC BỎ. Chủ dự án chốt giữ ngày 2026-09-24.

## Câu hỏi

Bench ngoài 2026-09-23 đo được luật hiện tại từ chối oan **40,6% / 43,4%** câu
mà vai `kho` ĐÃ tìm đúng đáp án (235 và 196 ca trong số đó đáp án ở **hạng 1**).
Luật không bao giờ hỏi "phần thấy được đã đủ trả lời chưa" — nó thấy một lớp bị
giấu trong top-k lượt bóng là thay cả câu trả lời bằng lời từ chối.

Luật đề xuất đảo câu hỏi:

| | hỏi gì | từ chối khi |
|---|---|---|
| **cũ** (đang chạy) | có **bất kỳ thứ BỊ GIẤU** nào trong top-k lượt bóng? | có |
| **mới** (đề xuất) | có **bất kỳ thứ THẤY ĐƯỢC** nào trong top-k lượt bóng? | **không** có |

Lập luận: lọc chỉ bỏ bớt hàng, nên hạng của một chunk thấy được trong lượt bóng
luôn ≥ hạng của nó trong lượt lọc; nếu kết quả tốt nhất của vai cũng nằm trong
top-k toàn cục thì không có gì hơn hẳn bị giữ lại.

**Lập luận này SAI, và số đo cho thấy sai ở đâu — xem "Vì sao luật mới hỏng".**

## Cách đo

`measure_grid.py` (bench ngoài) và `measure_grid_production.py` (corpus thật).
Mỗi câu dựng bảng xếp hạng lượt bóng **đúng một lần** — cùng `_prepare_queries`
+ `_fuse_legs` + RRF mà `retrieve()` dùng — rồi chấm cả 12 ô từ chính bảng đó.
Không chạy 12 lượt, nên không có chỗ cho hai lượt lệch nhau. Chỉ đọc, không gọi
LLM.

**TỰ CHỨNG (bản production).** Hàng `cũ` k=1 phải ra 5/10 · 0/99 và k=3 phải ra
9/10 · 0/99 — hai mốc đã đo của 19c. Công thức tự tính hạng bằng `_fuse_legs`,
KHÔNG đọc hằng `HIDDEN_TOP_K` hiện hành, nên đây là kiểm chéo thật. **Đã ĐẠT.**

Kiểm chéo thứ hai, ngầm: tại k=1 hai luật phải cho số **giống hệt nhau** (với
một phần tử, "có thứ bị giấu" ≡ "không có thứ thấy được"). Đúng ở cả ba bảng.

Thời gian: TVPL 1.000 câu **27 phút**; Zalo 788 câu **108 phút** (corpus
140.948 chunk); production 109 ca ~11 phút.

## Kết quả

Rò rỉ = **0** ở mọi ô, mọi bộ.

### tvpl — 273 câu thương mại, 727 câu khác (mật độ commercial 27,4% chunk)

| k | cũ: bắt | cũ: oan | mới: bắt | mới: oan |
|---:|---:|---:|---:|---:|
| 1 | 83,2% | 5,1% | 83,2% | 5,1% |
| 2 | 92,7% | 25,4% | 61,9% | 1,9% |
| 3 | **96,0%** | **40,9%** | 47,6% | 1,0% |
| 4 | 97,8% | 53,5% | 37,4% | 0,3% |
| 5 | 97,8% | 62,7% | 32,2% | 0,3% |
| 6 | 98,5% | 68,6% | 26,4% | 0,1% |

### zalo — 157 câu thương mại, 631 câu khác (mật độ 40,0% chunk)

| k | cũ: bắt | cũ: oan | mới: bắt | mới: oan |
|---:|---:|---:|---:|---:|
| 1 | 88,5% | 7,9% | 88,5% | 7,9% |
| 2 | 95,5% | 29,3% | 75,8% | 3,0% |
| 3 | **97,5%** | **43,1%** | 59,9% | 2,2% |
| 4 | 98,7% | 52,0% | 51,0% | 1,3% |
| 5 | 100% | 57,2% | 42,7% | 0,8% |
| 6 | 100% | 62,9% | 36,3% | 0,6% |

### production — 10 ca thương mại, 99 ca khác (mật độ 24/3.901 = **0,6%** chunk)

| k | cũ: bắt | cũ: oan | mới: bắt | mới: oan |
|---:|---:|---:|---:|---:|
| 1 | 5/10 | 0/99 | 5/10 | 0/99 |
| 2 | 6/10 | 0/99 | **1/10** | 0/99 |
| 3 | **9/10** | **0/99** | 1/10 | 0/99 |
| 4 | 9/10 | 0/99 | 1/10 | 0/99 |
| 5 | 9/10 | 1/99 | 1/10 | 0/99 |
| 6 | 10/10 | 1/99 | **0/10** | 0/99 |

## Vì sao luật mới hỏng

Trên production, luật mới ở `k ≥ 2` chỉ bắt **1/10** — gần như **không bao giờ
từ chối**, tức làm chết tính năng 19c.

Cơ chế: corpus production **98,9% là PDF luật** (lớp `all`). Kể cả với câu hỏi
mà đáp án đúng nằm ở tài liệu thương mại, lượt bóng vẫn gần như luôn có một
chunk luật lọt vào top-2. Luật mới nhìn thấy chunk thấy được đó rồi kết luận
"vai này không bị thiệt".

Tiền đề sai nằm ở đây: **một chunk được XẾP HẠNG cao không có nghĩa nó TRẢ LỜI
được câu hỏi.** Đây đúng lớp lỗi đã khiến `passes_floor` bị loại khỏi vai trò
này ngay từ đầu (nó trả True khi *bất kỳ* chunk nào có `sparse_score`) — dùng
một đại lượng xếp hạng/tương tự làm đại diện cho "đã trả lời được chưa".

Luật mới chỉ "hoạt động" ở bench vì mật độ cao đủ để top-k toàn là chunk bị
giấu. Nói cách khác nó phụ thuộc mật độ theo đúng chiều SAI: tắt bảo vệ đúng
lúc corpus chủ yếu là tài liệu công khai.

## Vì sao `k = 3` là đúng cho hôm nay

Trên nhãn THẬT, mật độ THẬT: **9/10 bắt, 0/99 từ chối oan**. Không có khiếm
khuyết production nào để sửa.

Con số 40–43% là thứ xảy ra ở mật độ **cao gấp 45–65 lần** production. Đúng như
README bench tự ghi: đó là *stress test cơ chế, không phải dự báo production*.

Đổi k về 1 sẽ kéo bắt đúng từ 9/10 xuống 5/10 **ngay hôm nay** để đổi lấy việc
giảm một tỉ lệ oan hiện đang bằng **không**.

## Ngày nào phải xem lại — và lấy số ở đâu

Điều kiện kích hoạt trùng đúng điều kiện mở lại 19b: **corpus có nhiều tài liệu
nội bộ**. Khi mật độ `commercial` tăng đáng kể, tỉ lệ oan sẽ leo theo bảng trên.

Hai bảng bench ở đây LÀ bảng chọn k cho ngày đó — không cần đo lại. Đường cong
đánh đổi, gộp cả hai luật (chúng trùng nhau tại k=1):

```
oan thấp ←                                                → bắt cao
mới k=6    mới k=4    mới k=2    k=1        cũ k=2     cũ k=3
26–36%     37–51%     62–76%     83–89%     93–96%     96–98%   bắt đúng
0,1–0,6%   0,3–1,3%   1,9–3,0%   5,1–7,9%   25–29%     41–43%   oan
                                  ↑                        ↑
                        đổi k, KHÔNG đổi luật         đang chạy
```

Lưu ý khi đọc: nhãn `commercial` của bench là **giả lập** (bộ từ khoá
`evals/vlegal_bench_roles.py`), nên tỉ lệ tuyệt đối không mang thẳng sang được;
thứ mang sang được là **hình dạng đường cong** và thứ tự các điểm.

## Chạy lại

```bash
cd backend
export DATABASE_URL=...  OLLAMA_URL=http://127.0.0.1:11435   # KHÔNG dùng OLLAMA_URL trong .env
python evals/results/luat-top3-2026-09-24/measure_grid.py tvpl warehouse
python evals/results/luat-top3-2026-09-24/measure_grid.py zalo warehouse
python evals/results/luat-top3-2026-09-24/measure_grid_production.py   # có tự chứng
```
