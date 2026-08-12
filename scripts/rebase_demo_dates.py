# scripts/rebase_demo_dates.py
"""Rải lại mốc thời gian của dữ liệu demo cho giống một doanh nghiệp đang chạy.

VÌ SAO CẦN. Dữ liệu seed của Odoo cùng dữ liệu do dự án sinh ra đều mang ngày
trong quá khứ, còn thời gian thì trôi tiếp — nên đo ngày 2026-08-12 thấy 98/99
phiếu kho chưa xong đã trễ hạn và 31/31 activity đã quá hạn. Một ERP mà MỌI
thứ đều trễ trông như hệ thống hỏng, và nó làm hỏng mọi kịch bản demo chứ
không riêng câu hỏi về việc trễ.

VẤN ĐỀ NÀY QUAY LẠI. Sửa tay hôm nay thì tháng sau lại lệch. Nên script rải
ngày TƯƠNG ĐỐI so với hôm nay và chạy lại được bao nhiêu lần tuỳ ý — chạy
trước mỗi lần demo.

KHÔNG ĐỤNG:
  - Phiếu `done`/`cancel`: ngày của chúng là LỊCH SỬ. Viết lại dễ tạo mâu
    thuẫn (giao hàng sau ngày hoá đơn của chính nó).
  - `account.move`: đo 2026-08-12 thấy 12 chưa tới hạn / 16 quá hạn — đã là
    phân bố thực tế, không cần can thiệp.

ĐẢO NGƯỢC ĐƯỢC. Trước khi ghi, script dump (model, id, field, giá trị cũ) ra
JSON trong logs/ (thư mục đã gitignore). `--restore <file>` trả lại nguyên
trạng.

Chạy:
    python scripts/rebase_demo_dates.py                 # chỉ xem, KHÔNG ghi
    python scripts/rebase_demo_dates.py --apply
    python scripts/rebase_demo_dates.py --restore logs/rebase-backup-....json

ENV: ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD.
"""
import argparse
import collections
import datetime
import json
import os
import random
import sys
import xmlrpc.client
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = REPO_ROOT / "logs"

# Hình dạng đích (phương án A): giữ được CẢ HAI câu chuyện demo — "trong tầm
# kiểm soát" và "có vài việc cần xử lý, agent chỉ ra ngay". Đưa hết về tương
# lai sẽ khiến list_late_deliveries trả rỗng, tức mất một năng lực khi demo.
#
# Mỗi phần tử: (tỉ lệ, ngày sớm nhất, ngày muộn nhất) tương đối so với hôm nay.
SHAPE_PICKING = [
    (0.15, -14, -1),    # trễ, nhưng trễ gần — không phải trễ nửa năm
    (0.10, 0, 0),       # tới hạn hôm nay
    (0.75, 1, 21),      # sắp tới, rải 3 tuần
]
SHAPE_ACTIVITY = [
    (0.20, -10, -1),    # activity trễ là chuyện bình thường trong CRM
    (0.10, 0, 0),
    (0.70, 1, 14),
]

# Giờ làm việc — tránh mọi phiếu đều 00:00, trông như dữ liệu máy sinh.
WORK_HOURS = [8, 9, 10, 11, 13, 14, 15, 16]

SEED = 20260812   # cố định để chạy lại cho kết quả tái lập được


def connect():
    url = os.environ["ODOO_URL"]
    db = os.environ["ODOO_DB"]
    user = os.environ["ODOO_USERNAME"]
    pwd = os.environ["ODOO_PASSWORD"]
    uid = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common").authenticate(db, user, pwd, {})
    if not uid:
        sys.exit("Đăng nhập Odoo thất bại — kiểm tra ODOO_USERNAME/ODOO_PASSWORD.")
    obj = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object")
    return lambda model, method, args, kw=None: obj.execute_kw(
        db, uid, pwd, model, method, args, kw or {})


def _offsets(n, shape, rng):
    """n số ngày lệch, phân bổ theo `shape`, đã xáo trộn."""
    out = []
    for ratio, lo, hi in shape:
        for _ in range(round(n * ratio)):
            out.append(rng.randint(lo, hi))
    while len(out) < n:                      # bù sai số làm tròn
        out.append(rng.randint(*shape[-1][1:]))
    out = out[:n]
    rng.shuffle(out)
    return out


def _bucket(iso_date, today):
    d = datetime.date.fromisoformat(iso_date[:10])
    delta = (d - today).days
    if delta < -30:
        return "trễ >30 ngày"
    if delta < 0:
        return "trễ 1-30 ngày"
    if delta == 0:
        return "hôm nay"
    if delta <= 7:
        return "tới trong 7 ngày"
    return "tới sau 7 ngày"


def _report(ten, cu, moi, today):
    print("\n%s (%d bản ghi)" % (ten, len(cu)))
    for nhan, bo in (("trước", cu), ("sau  ", moi)):
        dem = collections.Counter(_bucket(v, today) for v in bo.values())
        print("   %s: %s" % (nhan, dict(sorted(dem.items()))))


def plan_changes(call, today, rng):
    """Trả về (ke_hoach, cu) — ke_hoach: [(model, id, field, gia_tri_moi)]."""
    ke_hoach, cu = [], {}

    # ── stock.picking: chỉ phiếu CHƯA xong ──────────────────────────────────
    rows = call("stock.picking", "search_read",
                [[["state", "not in", ["done", "cancel"]]]],
                {"fields": ["scheduled_date"], "order": "id asc"})
    rows = [r for r in rows if r.get("scheduled_date")]
    offs = _offsets(len(rows), SHAPE_PICKING, rng)
    cu_p, moi_p = {}, {}
    for r, off in zip(rows, offs):
        ngay = today + datetime.timedelta(days=off)
        gio = rng.choice(WORK_HOURS)
        moi = "%s %02d:%02d:00" % (ngay.isoformat(), gio, rng.choice([0, 15, 30, 45]))
        ke_hoach.append(("stock.picking", r["id"], "scheduled_date", moi))
        cu_p[r["id"]] = r["scheduled_date"]
        moi_p[r["id"]] = moi
    cu["stock.picking"] = (cu_p, moi_p)

    # ── mail.activity: tất cả (không có khái niệm 'done' — xong là bị xoá) ──
    acts = call("mail.activity", "search_read", [[]],
                {"fields": ["date_deadline"], "order": "id asc"})
    acts = [a for a in acts if a.get("date_deadline")]
    offs = _offsets(len(acts), SHAPE_ACTIVITY, rng)
    cu_a, moi_a = {}, {}
    for a, off in zip(acts, offs):
        moi = (today + datetime.timedelta(days=off)).isoformat()
        ke_hoach.append(("mail.activity", a["id"], "date_deadline", moi))
        cu_a[a["id"]] = a["date_deadline"]
        moi_a[a["id"]] = moi
    cu["mail.activity"] = (cu_a, moi_a)

    return ke_hoach, cu


def apply_changes(call, ke_hoach):
    """Ghi từng bản ghi một. CỐ Ý không gộp write hàng loạt: gộp thì mọi bản
    ghi trong lô nhận CÙNG một giá trị, đúng thứ script này đi phá."""
    for model, rid, field, val in ke_hoach:
        call(model, "write", [[rid], {field: val}])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định chỉ xem)")
    ap.add_argument("--restore", metavar="FILE", help="trả lại giá trị cũ từ file backup")
    args = ap.parse_args()

    call = connect()
    today = datetime.date.today()

    if args.restore:
        data = json.loads(Path(args.restore).read_text(encoding="utf-8"))
        for model, rid, field, val in data["ban_ghi"]:
            call(model, "write", [[int(rid)], {field: val}])
        print("Đã trả lại %d bản ghi từ %s" % (len(data["ban_ghi"]), args.restore))
        return

    rng = random.Random(SEED)
    ke_hoach, cu = plan_changes(call, today, rng)

    print("Hôm nay: %s | tổng thay đổi dự kiến: %d" % (today, len(ke_hoach)))
    for ten, (c, m) in cu.items():
        _report(ten, c, m, today)

    if not args.apply:
        print("\n(chỉ xem — thêm --apply để ghi thật)")
        return

    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / ("rebase-backup-%s.json" % ts)
    ban_ghi_cu = [[model, rid, field, cu[model][0][rid]]
                  for model, rid, field, _ in ke_hoach]
    backup.write_text(json.dumps({"ngay": today.isoformat(), "ban_ghi": ban_ghi_cu},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nĐã lưu backup: %s" % backup)

    apply_changes(call, ke_hoach)
    print("Đã ghi %d bản ghi." % len(ke_hoach))
    print("Hoàn tác: python scripts/rebase_demo_dates.py --restore %s" % backup)


if __name__ == "__main__":
    main()
