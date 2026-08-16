"""bao-gia-chiet-khau: SKILL.md + logic.py. Trọng tâm là BẤT BIẾN TIỀN BẠC —
% chiết khấu và đơn giá luôn tính trong code, model không bao giờ truyền số
tiền. Hàm thuần port nguyên từ
D:\\Project\\backend\\src\\agents\\skill_agentic_discount_quote.py:42-60."""
import pytest

from src.agents.skill_loader import (SKILLS_DIR, build_skill_tools,
                                     load_skill_specs)
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "bao-gia-chiet-khau" / "SKILL.md")


def _logic():
    """Nạp logic.py qua ĐÚNG đường loader dùng (không import thẳng) — nếu hợp
    đồng nạp hỏng thì test này hỏng theo, đúng ý."""
    from src.agents.skill_loader import _load_entry_module
    return _load_entry_module(SPEC)


def test_manifest_uses_entry_not_declarative_write():
    assert SPEC.entry == "logic.py"
    assert SPEC.declares_tools == ("create_discount_quote",)
    assert SPEC.write_tools == ()          # luật 9: write XOR entry


def test_description_has_both_clauses():
    assert "Chọn worker này khi" in SPEC.description
    assert "KHÔNG chọn khi" in SPEC.description


@pytest.mark.parametrize("tier,total,expected", [
    ("thuong", 1_000_000, 0.0),
    ("than_thiet", 1_000_000, 0.05),
    ("doi_tac", 1_000_000, 0.10),
    ("thuong", 50_000_000, 0.02),          # bonus ngưỡng 50tr
    ("than_thiet", 50_000_000, 0.07),
    ("doi_tac", 50_000_000, 0.12),         # 0.10+0.02 phải là 0.12, không 0.12000000000000001
])
def test_compute_discount_pct(tier, total, expected):
    assert _logic().compute_discount_pct(tier, total) == expected


def test_discount_pct_never_exceeds_cap():
    logic = _logic()
    for tier in ("thuong", "than_thiet", "doi_tac"):
        assert logic.compute_discount_pct(tier, 10**12) <= 0.15


def test_tier_aliases_map_natural_vietnamese():
    logic = _logic()
    from src.agents.skill_gate import _fold
    for typed, expected in [("Đối tác chiến lược", "doi_tac"),
                            ("thân thiết", "than_thiet"),
                            ("Khách thường", "thuong")]:
        assert logic._TIER_ALIASES.get(_fold(typed).strip()) == expected


def test_loader_accepts_entry_and_binds_only_declared_tools():
    from langchain_core.tools import tool as lc_tool

    @lc_tool("create_quotation")
    async def create_quotation(partner_id: int, lines: list) -> str:
        """fake MCP create_quotation."""
        return "{}"

    names = {t.name for t in build_skill_tools(SPEC, [create_quotation])}
    assert names == {"ask_human", "create_discount_quote"}
    # create_quotation THÔ không bao giờ tới tay model
    assert "create_quotation" not in names


def test_all_three_skills_load_from_real_directory():
    specs = load_skill_specs()
    assert [s.name for s in specs] == ["bao-gia-chiet-khau", "giao-hang", "nhap-kho"]
