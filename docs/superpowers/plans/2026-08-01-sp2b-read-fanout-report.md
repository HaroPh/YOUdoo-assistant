# SP-2b — báo cáo số đo và xác minh sống

Plan: `docs/superpowers/plans/2026-08-01-sp2b-read-fanout.md`
Spec: `docs/superpowers/specs/2026-08-01-sp2b-read-fanout-design.md`

## Số đo TRƯỚC

Chạy trên `main` sạch tại commit `e9117d8 docs(plan): SP-2b — 10 task, fan-out đường đọc`, trước khi sửa dòng đầu tiên.
Model: đầu chuỗi catalog của vai tương ứng (không truyền `--model`).

### multi_source (vai `fusion`)
- verdict: `PASS`
- `both_source_coverage`: `0.75`
- `citation_validity`: `1.0`
- `fabricated_number`: `0`
- `lat_p50` / `lat_p95`: `1061` / `1484` ms
- log gốc: `logs/jobs/eval-gate-20260801T104522.json`

### intent (vai `router`)
- verdict: `PASS`
- `acc`: `0.9444444444444444`
- log gốc: `logs/jobs/eval-gate-20260801T105408.json`

### sop_select (vai `router`)
- verdict: `FAIL` (biết trước — gate tuyệt đối, 16/17 tồn dư từ SP-2a)
- `acc`: `0.9411764705882353`
- `hijack`: `0`
- log gốc: `logs/jobs/eval-gate-20260801T105851.json`
