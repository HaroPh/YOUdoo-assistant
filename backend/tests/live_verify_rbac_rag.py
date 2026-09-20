"""Probe sống 19b: cùng câu hỏi, 4 vai, qua backend THẬT (spec §7).
Chạy TỪ backend/: python -m tests.live_verify_rbac_rag — cần backend :8002 (mã worktree),
YOUDOO_ROLE_MAP + YOUDOO_API_TOKEN trong env. Marker live; không vào pytest thường."""
import sys
import uuid

from tests.live_verify_common import chat, load_env, role_user_id

CAU_HOI = "Chính sách chiết khấu của công ty như thế nào?"
DAU_HIEU_LO = ("5%", "10%", "15%", "2%")


def main() -> int:
    load_env()
    ket = {}
    for vai in ("warehouse", "sales", "accounting", "admin"):
        uid = role_user_id(vai)
        if not uid:
            print(f"[ERR] không tìm thấy user id cho vai {vai} trong YOUDOO_ROLE_MAP")
            return 2
        tra_loi = chat([], f"19b-{vai}-{uuid.uuid4().hex[:6]}", CAU_HOI, user_id=uid)
        ket[vai] = tra_loi
        print(f"\n=== {vai} ===\n{tra_loi}\n")
    lo_kho = [d for d in DAU_HIEU_LO if d in ket["warehouse"]]
    thay = {v: any(d in ket[v] for d in DAU_HIEU_LO) for v in ("sales", "accounting", "admin")}
    ok = not lo_kho and all(thay.values())
    print(f"kho lộ: {lo_kho or 'không'} | thấy: {thay} | {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
