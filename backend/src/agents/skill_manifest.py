# backend/src/agents/skill_manifest.py
"""Đọc + validate CẤU TRÚC một file backend/skills/<tên>/SKILL.md.

Ranh giới trách nhiệm (cố ý tách khỏi loader có chủ đích): file này chỉ trả lời
"file này nói gì, có hợp lệ về cấu trúc không" — thuần stdlib + PyYAML, không
import LangChain, không biết gì về registry MCP. Ràng buộc cần registry thật
(tool có tồn tại không, tham số confirm có khớp schema tool không) nằm ở
skill_loader.py.

Triết lý validate giống assert_embedding_marker(): thà app không lên còn hơn
lên sai. Mọi luật dưới đây dính tới THẨM QUYỀN hoặc tính đúng đắn cấu trúc →
raise. Ngoại lệ DUY NHẤT là vế loại trừ trong description ("KHÔNG dùng khi"
HOẶC "KHÔNG chọn khi" — xem skill_loader.NEGATIVE_CLAUSE_MARKERS): nó là chất
lượng prompt, không phải thẩm quyền — một description tồi làm SOP bị chọn nhầm,
và lớp phủ quyết tất định (routing.decide_route) cùng confirm-gate vẫn chặn
hậu quả. Chặn cứng ở đó sẽ biến một lỗi soạn thảo thành sự cố ngừng dịch vụ,
sai tỉ lệ → chỉ cảnh báo (xem skill_loader.load_skill_specs)."""
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Trần bước cho ReAct loop của một skill (mỗi chu kỳ agent→tools = 2 bước).
# Flow hợp lệ dài nhất hiện tại (nhap-kho: hỏi PO → hỏi số lượng → tra PO →
# [flag | hỏi QC → receive] → chốt) ≈ 6 lượt model ≈ 13 bước; 15 cho headroom.
DEFAULT_MAX_STEPS = 15
MAX_STEPS_CAP = 25

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

MISSING_NEGATIVE_WARNING = (
    "skill %r: description thiếu vế loại trừ ('KHÔNG dùng khi' hoặc 'KHÔNG "
    "chọn khi') — SOP này dễ bị chọn nhầm cho câu hỏi VỀ quy trình. Vẫn nạp "
    "(xem docstring skill_manifest)."
)


class SkillManifestError(Exception):
    """SKILL.md sai cấu trúc/thẩm quyền — app KHÔNG được lên."""


@dataclass(frozen=True)
class WriteToolSpec:
    name: str            # tên tool MCP đã tồn tại — markdown KHÔNG định nghĩa tool mới
    confirm: str         # template câu xác nhận, nội suy tham số của chính tool đó
    fixed_args: dict = field(default_factory=dict)
    # fixed_args: tham số HẰNG do manifest ghim, model KHÔNG thấy và KHÔNG đặt
    # được. Có mặt vì wrapper viết tay cũ của nhap-kho ghim
    # model="purchase.order" cho flag_order_for_review — không có cơ chế này thì
    # skill đó không di trú nguyên vẹn được. Loader loại các khoá này khỏi
    # schema model nhìn thấy (skill_loader._visible_schema).


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    prose: str
    dir: Path
    read_tools: tuple[str, ...] = ()
    write_tools: tuple[WriteToolSpec, ...] = ()
    entry: str | None = None
    declares_tools: tuple[str, ...] = ()
    max_steps: int = DEFAULT_MAX_STEPS
    # frozen=True nhưng CÓ trường dict (WriteToolSpec.fixed_args): không bao giờ
    # hash SkillSpec/WriteToolSpec — chỉ dùng làm giá trị, không làm khoá dict.


def _require(cond, msg: str) -> None:
    if not cond:
        raise SkillManifestError(msg)


def _check_confirm_template(where: str, template: str) -> tuple[str, ...]:
    """Trả về tên các placeholder. Chỉ chấp nhận placeholder CÓ TÊN, không
    positional ({}, {0}), không attribute/index ({a.b}, {a[0]}) — câu xác nhận
    là thứ người dùng đọc trước khi cho ghi, không phải chỗ để chạy biểu thức."""
    names: list[str] = []
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as e:
        raise SkillManifestError(f"{where}: confirm không phải template hợp lệ: {e}")
    for _literal, fname, _spec, _conv in parsed:
        if fname is None:
            continue
        _require(fname != "", f"{where}: confirm dùng placeholder không tên '{{}}'")
        _require(fname.isidentifier(),
                 f"{where}: confirm chỉ được nội suy TÊN tham số, gặp '{{{fname}}}'")
        names.append(fname)
    return tuple(names)


def parse_skill_md(path: Path) -> SkillSpec:
    """Đọc 1 SKILL.md → SkillSpec đã validate cấu trúc. raise SkillManifestError."""
    path = Path(path)
    where = str(path)
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    _require(m is not None, f"{where}: thiếu frontmatter YAML (khối --- ... ---)")
    raw, prose = m.group(1), m.group(2).strip()

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise SkillManifestError(f"{where}: frontmatter không parse được: {e}")
    _require(isinstance(data, dict), f"{where}: frontmatter phải là mapping YAML")

    name = data.get("name")
    _require(isinstance(name, str) and name.strip(), f"{where}: thiếu 'name'")
    name = name.strip()
    _require(_NAME_RE.match(name), f"{where}: 'name' phải kebab-case, gặp {name!r}")
    _require(name == path.parent.name,
             f"{where}: 'name' ({name!r}) phải khớp tên thư mục "
             f"({path.parent.name!r}) — tên node graph lấy từ đây")

    description = data.get("description")
    _require(isinstance(description, str) and description.strip(),
             f"{where}: thiếu 'description'")
    description = " ".join(description.split())

    _require(prose, f"{where}: thiếu phần prose sau frontmatter "
                    "(prose LÀ system prompt của SOP)")

    tools = data.get("tools") or {}
    _require(isinstance(tools, dict), f"{where}: 'tools' phải là mapping")
    entry = data.get("entry")
    _require(entry is None or (isinstance(entry, str) and entry.strip()
             and "/" not in entry and "\\" not in entry and entry not in (".", "..")),
             f"{where}: 'entry' phải là TÊN FILE nằm trong chính thư mục skill "
             "(không đường dẫn, không '..') — nếu không, markdown chọn được file .py "
             "bất kỳ để thực thi, phá đúng bất biến thẩm quyền của loader")

    raw_write = tools.get("write") or []
    _require(not (raw_write and entry),
             f"{where}: có CẢ 'tools.write' lẫn 'entry' — hai đường sinh tool "
             "trong một skill là chỗ để lọt gate")

    raw_read = tools.get("read") or []
    _require(isinstance(raw_read, list) and all(isinstance(x, str) for x in raw_read),
             f"{where}: 'tools.read' phải là danh sách tên tool")

    _require(isinstance(raw_write, list), f"{where}: 'tools.write' phải là danh sách")
    write_tools = []
    for item in raw_write:
        _require(isinstance(item, dict), f"{where}: mỗi mục 'tools.write' phải là mapping")
        wname = item.get("name")
        _require(isinstance(wname, str) and wname.strip(),
                 f"{where}: mục 'tools.write' thiếu 'name'")
        confirm = item.get("confirm")
        _require(isinstance(confirm, str) and confirm.strip(),
                 f"{where}: tool ghi {wname!r} thiếu 'confirm'")
        _check_confirm_template(f"{where}/{wname}", confirm)
        fixed = item.get("fixed_args") or {}
        _require(isinstance(fixed, dict) and all(isinstance(k, str) for k in fixed),
                 f"{where}: tool ghi {wname!r} có 'fixed_args' không phải mapping tên→giá trị")
        write_tools.append(WriteToolSpec(wname.strip(), confirm, dict(fixed)))

    declares = data.get("declares_tools") or []
    _require(isinstance(declares, list) and all(isinstance(x, str) for x in declares),
             f"{where}: 'declares_tools' phải là danh sách tên tool")
    _require(bool(entry) == bool(declares),
             f"{where}: 'entry' và 'declares_tools' phải đi CÙNG NHAU — thiếu một "
             "vế nghĩa là logic.py có thể lặng lẽ mở thêm tool mà frontmatter không khai")

    max_steps = data.get("max_steps", DEFAULT_MAX_STEPS)
    _require(isinstance(max_steps, int) and not isinstance(max_steps, bool)
             and max_steps > 0,
             f"{where}: 'max_steps' phải là số nguyên dương")
    _require(max_steps <= MAX_STEPS_CAP,
             f"{where}: 'max_steps'={max_steps} vượt trần cứng {MAX_STEPS_CAP}")

    return SkillSpec(name=name, description=description, prose=prose,
                     dir=path.parent, read_tools=tuple(raw_read),
                     write_tools=tuple(write_tools), entry=entry,
                     declares_tools=tuple(declares), max_steps=max_steps)
