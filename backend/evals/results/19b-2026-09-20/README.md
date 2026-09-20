# Hai lượt đo của cổng ÂM 19b (RBAC tầng RAG)

Hai JSON này là **đầu vào của cổng ÂM** — `evals/compare_visibility.py` so chúng
với nhau để chứng minh vai bị chặn không còn chạm 4 tài liệu thương mại. Khác
các thư mục kết quả cũ, hai tệp này **tự khai** vai đã đo (khoá `role`, thêm ở
19b Task 7), nên không cần ghi chú thủ công để biết chúng là gì.

Sinh sau khi migration 009 đã chạy trên DB thật (17 tài liệu / 3 901 chunk;
24 chunk `commercial`; tệp SID đã gỡ). Chạy lại trên corpus khác sẽ ra số khác.

| tệp | `--role` | r@20 | r@6 | mrr | lat_p50 |
|---|---|---|---|---|---|
| `admin.json` | `admin` | 0,9771 | 0,9633 | 0,7996 | 528 ms |
| `warehouse.json` | `warehouse` | 0,8853 | 0,8716 | 0,7248 | 521 ms |

Lệnh sinh (cwd = `backend/`, `.env` đã nạp):

```powershell
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role admin     > evals/results/19b-2026-09-20/admin.json
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role warehouse > evals/results/19b-2026-09-20/warehouse.json
.venv\Scripts\python.exe -m evals.compare_visibility evals/results/19b-2026-09-20/admin.json evals/results/19b-2026-09-20/warehouse.json
```

Kết quả cổng ÂM: `CỔNG ÂM PASS — thương mại 10 ca (lộ 0), khác 99 ca (kém đi 0)`, exit 0.

Chênh lệch 0,9771 − 0,8853 = 0,0918 ≈ 10/109 = 0,0917: phần sụt **đúng bằng** 10 ca
thương mại rơi về 0, không ca nào khác mất — kiểm chéo số học độc lập với dòng PASS.
