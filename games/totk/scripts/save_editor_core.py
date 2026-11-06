#!/usr/bin/env python3
"""Offline, byte-preserving edits to TOTK items and equipment durability."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import Optional

from equipment_durability_143 import EQUIPMENT_NAMES_ZH_CN, MAX_DURABILITY
from material_names_zh_cn import MATERIAL_NAMES_ZH_CN
from shrine_names_zh_cn import SHRINE_NAMES_ZH_CN

DATA_DIR = Path.home() / "Library/Application Support/MacNativeGames/TOTK"
DEFAULT_PROFILE = DATA_DIR / "profile"
GAME_SLOT_DIR = Path(os.environ.get("TOTK_GAME_SLOT_DIR", DATA_DIR / "game-slot"))
MAX_STACK = 999
MAX_RUPEES = 999_999
_RUPEE_FIELD = "PlayerStatus.CurrentRupee"
_LIGHTROOT_INDICES = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
    35, 36, 37, 39, 40, 41, 42, 44, 46, 47, 48, 49, 51, 53, 54, 56,
    57, 58, 59, 64, 65, 67, 68, 70, 72, 73, 74, 75, 76, 77, 78, 79,
    80, 81, 84, 85, 86, 87, 88, 89, 90, 91, 92, 94, 95, 96, 97, 98,
    100, 101, 102, 103, 104, 106, 107, 108, 111, 112, 113, 114, 115,
    116, 118, 119, 120, 122, 123, 124, 125, 126, 129, 130, 131, 132,
    133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 147,
)
_LIGHTROOT_OPEN = 0x1818EC02
_LIGHTROOT_CLOSE = 0x8A88C430
_MAGIC = 0x01020304
_TABLE_HEADER_SIZE = 32
_LABELS = {"NormalArrow": "普通箭", **MATERIAL_NAMES_ZH_CN}
_LOCATION_LABELS = {
    "MainField": "海拉鲁大陆",
    "HopesPlateau": "初始空岛",
    "MapArea_CentralHyrule": "中央海拉鲁",
    "MapArea_HyruleCastle": "海拉鲁城堡",
}
_EQUIPMENT_CATEGORY_LABELS = {
    "Weapon": "武器",
    "Shield": "盾牌",
    "Bow": "弓",
}
_DURABILITY_EFFECTS = {
    0xD5CAD39B,  # DurabilityUp
    0xB2C943EE,  # DurabilityUpPlus
}
_NO_EFFECT = 0xB6EEDE09
_EQUIPMENT_ID_PREFIXES = {
    "Weapon": ("Weapon_Sword_", "Weapon_Lsword_", "Weapon_Spear_"),
    "Shield": ("Weapon_Shield_",),
    "Bow": ("Weapon_Bow_",),
}


class SaveFormatError(ValueError):
    """The selected file is not a supported, safely editable TOTK save."""


def set_game_item_names(names):
    _LABELS.clear()
    _LABELS.update({**MATERIAL_NAMES_ZH_CN, **names, "NormalArrow": "普通箭"})


@dataclass(frozen=True)
class InventoryItem:
    item_id: str
    category: str
    index: int
    quantity: int
    maximum: int = MAX_STACK

    @property
    def label(self):
        display = _LABELS.get(self.item_id)
        if display is None:
            display = f"未收录名称（{self.item_id}）"
        category = "箭" if self.category == "Arrow" else "素材"
        return f"{display} · {category} · {self.quantity}/{self.maximum}"


@dataclass(frozen=True)
class RupeeBalance:
    quantity: int
    category: str = "Rupee"
    maximum: int = MAX_RUPEES

    @property
    def item_id(self):
        return _RUPEE_FIELD

    @property
    def index(self):
        return 0

    @property
    def label(self):
        return f"卢比 · {self.quantity}/{self.maximum}"


@dataclass(frozen=True)
class EquipmentItem:
    item_id: str
    category: str
    index: int
    durability: int
    maximum: Optional[int]

    @property
    def label(self):
        display = EQUIPMENT_NAMES_ZH_CN.get(self.item_id)
        if display is None:
            display = f"未收录名称（{self.item_id}）"
        category = _EQUIPMENT_CATEGORY_LABELS[self.category]
        if self.maximum is None:
            return f"{display} · {category} · 当前耐久 {self.durability} · 上限未知"
        maximum = str(self.maximum)
        return f"{display} · {category} · {self.durability}/{maximum}"


@dataclass(frozen=True)
class EquipmentTemplate:
    item_id: str
    category: str
    maximum: int

    @property
    def label(self):
        display = EQUIPMENT_NAMES_ZH_CN[self.item_id]
        category = _EQUIPMENT_CATEGORY_LABELS[self.category]
        return f"{display} · {category} · 新装备耐久 {self.maximum}"


@dataclass(frozen=True)
class SaveSlot:
    slot_id: str
    directory: Path
    progress_path: Path
    caption_path: Path
    display_name: str
    modified_at: float
    digest: str

    @property
    def label(self):
        stamp = datetime.fromtimestamp(self.modified_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return f"{self.display_name}  ·  {stamp}"


def _humanize_id(value):
    value = value.removeprefix("Item_")
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    value = value.replace("_", " ")
    return value.strip() or "未知物品"


def _rotl32(value, count):
    return ((value << count) | (value >> (32 - count))) & 0xFFFFFFFF


def field_hash(name):
    """TOTK save field names use MurmurHash3 x86_32 with seed zero."""
    data = name.encode("utf-8")
    value = 0
    offset = 0
    while offset + 4 <= len(data):
        word = int.from_bytes(data[offset:offset + 4], "little")
        word = _rotl32((word * 0xCC9E2D51) & 0xFFFFFFFF, 15)
        word = (word * 0x1B873593) & 0xFFFFFFFF
        value ^= word
        value = (_rotl32(value, 13) * 5 + 0xE6546B64) & 0xFFFFFFFF
        offset += 4
    tail = data[offset:]
    if tail:
        word = int.from_bytes(tail, "little")
        value ^= (_rotl32((word * 0xCC9E2D51) & 0xFFFFFFFF, 15) *
                  0x1B873593) & 0xFFFFFFFF
    value ^= len(data)
    value ^= value >> 16
    value = (value * 0x85EBCA6B) & 0xFFFFFFFF
    value ^= value >> 13
    value = (value * 0xC2B2AE35) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _read_u32(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise SaveFormatError("存档字段越界，文件可能损坏或格式不兼容。")
    return struct.unpack_from("<I", data, offset)[0]


def _parse_field_table(data):
    if len(data) < 40 or len(data) > 32 * 1024 * 1024:
        raise SaveFormatError("存档大小异常，无法安全读取。")
    if _read_u32(data, 0) != _MAGIC:
        raise SaveFormatError("不是可识别的 TOTK progress.sav 文件。")
    table_end = _read_u32(data, 8)
    if (table_end < 40 or table_end > len(data) or
            (table_end - _TABLE_HEADER_SIZE) % 8):
        raise SaveFormatError("存档字段表无效，拒绝修改。")

    fields = {}
    section = -1
    for offset in range(_TABLE_HEADER_SIZE, table_end, 8):
        key, value = struct.unpack_from("<II", data, offset)
        if key == 0:
            if value > 32 or value <= section:
                raise SaveFormatError("存档字段类型顺序无效。")
            section = value
            continue
        if section < 0 or key in fields:
            raise SaveFormatError("存档包含重复或无效字段。")
        fields[key] = (section, value)
    return fields


def _rupee_value_location(data):
    fields = _parse_field_table(data)
    key = field_hash(_RUPEE_FIELD)
    record = fields.get(key)
    if record is None or record[0] != 2:
        raise SaveFormatError(
            f"存档缺少可验证的卢比字段：{_RUPEE_FIELD}"
        )
    table_end = _read_u32(data, 8)
    for offset in range(_TABLE_HEADER_SIZE, table_end, 8):
        field_key, value = struct.unpack_from("<II", data, offset)
        if field_key == key:
            if value > MAX_RUPEES:
                raise SaveFormatError("存档中的卢比数量超出支持范围。")
            return offset + 4, value
    raise SaveFormatError(f"存档字段表中找不到卢比字段：{_RUPEE_FIELD}")


def read_rupees(progress_path):
    data = Path(progress_path).read_bytes()
    _, quantity = _rupee_value_location(data)
    return RupeeBalance(quantity)


def _lightroot_locations(data):
    fields = _parse_field_table(data)
    keys = {
        field_hash(f"ArrivalPointState.CheckPoint{index:03}")
        for index in _LIGHTROOT_INDICES
    }
    if len(keys) != 120:
        raise SaveFormatError("灯根字段列表无效，拒绝修改。")
    for key in keys:
        record = fields.get(key)
        if record is None or record[0] != 6:
            raise SaveFormatError("存档缺少可验证的灯根状态字段，拒绝修改。")
        if record[1] not in (_LIGHTROOT_OPEN, _LIGHTROOT_CLOSE):
            raise SaveFormatError("存档包含未知灯根状态，拒绝修改。")
    locations = {}
    for offset in range(_TABLE_HEADER_SIZE, _read_u32(data, 8), 8):
        key, value = struct.unpack_from("<II", data, offset)
        if key in keys:
            locations[offset + 4] = value
    if len(locations) != len(keys):
        raise SaveFormatError("存档灯根状态字段不完整，拒绝修改。")
    return locations


def read_lightroots(progress_path):
    locations = _lightroot_locations(Path(progress_path).read_bytes())
    return sum(value == _LIGHTROOT_OPEN for value in locations.values())


def _array_field(data, fields, name, expected_type, element_width):
    record = fields.get(field_hash(name))
    if record is None or record[0] != expected_type:
        raise SaveFormatError(f"存档缺少可验证的数组字段：{name}")
    offset = record[1]
    if offset < _read_u32(data, 8) or offset % 4:
        raise SaveFormatError(f"数组字段偏移无效：{name}")
    count = _read_u32(data, offset)
    if count <= 0 or count > 8192 or offset + 4 + count * element_width > len(data):
        raise SaveFormatError(f"数组长度无效：{name}")
    return offset + 4, count


def _read_string(data, offset, width):
    raw = data[offset:offset + width]
    if len(raw) != width:
        raise SaveFormatError("存档字符串超出文件范围。")
    value = raw.split(b"\0", 1)[0]
    try:
        return value.decode("ascii")
    except UnicodeDecodeError as error:
        raise SaveFormatError("背包中存在无法识别的物品名称。") from error


def _inventory_layout(data):
    fields = _parse_field_table(data)
    layout = {}
    ranges = []
    for category in ("Arrow", "Material"):
        names, name_count = _array_field(
            data, fields, f"Pouch.{category}.Content.Name", 17, 64
        )
        stocks, stock_count = _array_field(
            data, fields, f"Pouch.{category}.Content.StockNum", 3, 4
        )
        if name_count != stock_count or name_count % 2:
            raise SaveFormatError(
                f"{category} 背包数组不匹配，拒绝修改。"
            )
        ranges.extend((
            (names - 4, names + name_count * 64),
            (stocks - 4, stocks + stock_count * 4),
        ))
        layout[category] = (names, stocks, name_count // 2)
    for index, (start, end) in enumerate(ranges):
        if any(start < other_end and other_start < end
               for other_start, other_end in ranges[index + 1:]):
            raise SaveFormatError("背包字段存储区域重叠，拒绝修改。")
    return layout


def read_inventory(progress_path):
    data = Path(progress_path).read_bytes()
    layout = _inventory_layout(data)
    items = []
    for category, (names, stocks, regular_slots) in layout.items():
        for index in range(regular_slots):
            item_id = _read_string(data, names + index * 64, 64)
            quantity = struct.unpack_from("<i", data, stocks + index * 4)[0]
            if not item_id:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", item_id) or quantity < 0:
                raise SaveFormatError("背包物品记录无效，拒绝显示或修改。")
            if quantity > MAX_STACK:
                raise SaveFormatError(
                    f"{item_id} 的数量已超过游戏上限，拒绝修改。"
                )
            items.append(InventoryItem(item_id, category, index, quantity))
    return items


def _equipment_layout(data):
    fields = _parse_field_table(data)
    layout = {}
    ranges = []
    for category in ("Arrow", "Material"):
        names, name_count = _array_field(
            data, fields, f"Pouch.{category}.Content.Name", 17, 64
        )
        stocks, stock_count = _array_field(
            data, fields, f"Pouch.{category}.Content.StockNum", 3, 4
        )
        if name_count != stock_count or name_count % 2:
            raise SaveFormatError(f"{category} 背包数组不匹配，拒绝修改。")
        ranges.extend((
            (names - 4, names + name_count * 64),
            (stocks - 4, stocks + stock_count * 4),
        ))

    for category in ("Weapon", "Shield", "Bow"):
        prefix = f"Pouch.{category}.Content"
        names, name_count = _array_field(
            data, fields, f"{prefix}.Name", 17, 64
        )
        lives, life_count = _array_field(
            data, fields, f"{prefix}.Life", 3, 4
        )
        effects, effect_count = _array_field(
            data, fields, f"{prefix}.Effect.Type", 7, 4
        )
        values, value_count = _array_field(
            data, fields, f"{prefix}.Effect.Value", 3, 4
        )
        if (name_count != life_count or name_count != effect_count or
                name_count != value_count or name_count % 2):
            raise SaveFormatError(
                f"{category} 装备数组不匹配，拒绝修改。"
            )
        ranges.extend((
            (names - 4, names + name_count * 64),
            (lives - 4, lives + life_count * 4),
            (effects - 4, effects + effect_count * 4),
            (values - 4, values + value_count * 4),
        ))
        layout[category] = (
            names, lives, effects, values, name_count // 2
        )

    for index, (start, end) in enumerate(ranges):
        if any(start < other_end and other_start < end
               for other_start, other_end in ranges[index + 1:]):
            raise SaveFormatError("存档数组存储区域重叠，拒绝修改。")
    return layout


def _read_equipment(data):
    layout = _equipment_layout(data)
    items = []
    for category, (names, lives, effects, values, regular_slots) in layout.items():
        for index in range(regular_slots):
            item_id = _read_string(data, names + index * 64, 64)
            if not item_id:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", item_id):
                raise SaveFormatError("装备记录无效，拒绝显示或修改。")
            durability = struct.unpack_from("<i", data, lives + index * 4)[0]
            if durability < 0:
                raise SaveFormatError("装备耐久值无效，拒绝显示或修改。")
            maximum = MAX_DURABILITY.get(item_id)
            if maximum is not None:
                effect = _read_u32(data, effects + index * 4)
                bonus = struct.unpack_from("<i", data, values + index * 4)[0]
                if effect in _DURABILITY_EFFECTS:
                    if bonus < 0 or bonus > 1000:
                        raise SaveFormatError(
                            f"{item_id} 的耐久强化数据无效，拒绝修改。"
                        )
                    maximum += bonus
            items.append(EquipmentItem(
                item_id, category, index, durability, maximum
            ))
    return items


def read_equipment(progress_path):
    return _read_equipment(Path(progress_path).read_bytes())


def _humanize_location(value):
    if value in SHRINE_NAMES_ZH_CN:
        return SHRINE_NAMES_ZH_CN[value]
    if value in _LOCATION_LABELS:
        return _LOCATION_LABELS[value]
    if value.startswith("Cave_"):
        pieces = value[len("Cave_"):].split("_")
        region = " ".join(_humanize_id(part) for part in pieces)
        return f"{region} 洞窟"
    if value.startswith("MapArea_"):
        return _humanize_id(value[len("MapArea_"):])
    match = re.fullmatch(r"Dungeon(\d+)", value)
    if match:
        return f"神庙 {match.group(1)}"
    if value.endswith("_Underground"):
        return "地下区域"
    return _humanize_id(value)


def _caption_location(caption_path):
    path = Path(caption_path)
    if not path.is_file() or path.is_symlink():
        return "未知保存位置"
    raw = path.read_bytes()
    if len(raw) < 40 or _read_u32(raw, 0) != _MAGIC:
        return "未知保存位置"
    data_start = _read_u32(raw, 8)
    if data_start < 40 or data_start > len(raw):
        return "未知保存位置"
    strings = re.findall(rb"[A-Za-z][A-Za-z0-9_]{3,}", raw[data_start:])
    values = [value.decode("ascii", "ignore") for value in strings]
    location = None
    for value in values:
        match = re.search(
            r"(?:Cave_[A-Za-z0-9_]+|MapArea_[A-Za-z0-9_]+|"
            r"Dungeon\d{3}|[ED]CheckPoint\d{3}|HopesPlateau|MainField)",
            value,
        )
        if match:
            location = match.group(0)
            break
    if location is None:
        return "未知保存位置"
    checkpoint = re.fullmatch(r"([ED])CheckPoint(\d{3})", location)
    if checkpoint:
        label = f"检查点 {checkpoint.group(2)}"
    else:
        label = _humanize_location(location)
    if any(value == "Underground" or value.endswith("_Underground")
           for value in values):
        label += " · 地下"
    return label


def _profile_slots(profile):
    profile = Path(profile).expanduser()
    if profile.is_symlink() or not profile.is_dir():
        raise ValueError(f"存档资料夹不存在或不是普通资料夹：{profile}")
    save_root = profile / "save"
    if save_root.is_symlink() or not save_root.is_dir():
        raise ValueError("所选资料夹下没有 TOTK 的 save 目录。")
    slots = []
    for account in sorted(save_root.iterdir()):
        if account.is_symlink() or not account.is_dir():
            continue
        for directory in sorted(account.glob("slot_0[0-5]")):
            if directory.is_symlink() or not directory.is_dir():
                continue
            progress = directory / "progress.sav"
            caption = directory / "caption.sav"
            if (progress.is_symlink() or caption.is_symlink() or
                    not progress.is_file() or not caption.is_file()):
                continue
            _validate_tree(directory)
            data = progress.read_bytes()
            _inventory_layout(data)
            items = read_inventory(progress)
            if not items:
                continue
            modified_at = progress.stat().st_mtime
            slots.append(SaveSlot(
                directory.name, directory, progress, caption,
                _caption_location(caption), modified_at,
                hashlib.sha256(data).hexdigest(),
            ))
    return sorted(slots, key=lambda slot: slot.modified_at, reverse=True)


def discover_saves(profile=DEFAULT_PROFILE):
    return _profile_slots(profile)


@contextmanager
def game_lock(slot_dir=GAME_SLOT_DIR):
    slot_dir = Path(slot_dir).expanduser()
    if slot_dir.is_symlink():
        raise ValueError("游戏锁目录不能是符号链接。")
    slot_dir.mkdir(parents=True, exist_ok=True)
    lock_path = slot_dir / "lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("检测到游戏正在运行；请先完全退出游戏再修改存档。") from None
        yield
    finally:
        os.close(descriptor)


def _backup_slot(slot, backup_root):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = backup_root / slot.slot_id / stamp
    for path in (DATA_DIR, backup_root.parent, backup_root, destination.parent):
        if path.is_symlink():
            raise ValueError("备份路径不能包含符号链接。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if any(path.is_symlink() for path in
           (DATA_DIR, backup_root.parent, backup_root, destination.parent)):
        raise ValueError("备份路径不能包含符号链接。")
    try:
        shutil.copytree(slot.directory, destination)
        if _tree_manifest(slot.directory) != _tree_manifest(destination):
            raise OSError("存档备份校验失败，已取消修改。")
    except Exception:
        if destination.exists() and not destination.is_symlink():
            shutil.rmtree(destination)
        raise
    return destination


def _prune_previous_backups(slot_backup_dir, keep):
    removed = 0
    errors = []
    try:
        paths = sorted(slot_backup_dir.iterdir())
    except OSError as error:
        return removed, [f"无法扫描旧备份：{error}"]
    for path in paths:
        if path == keep or not re.fullmatch(r"\d{8}-\d{6}-\d{6}", path.name):
            continue
        if path.is_symlink() or not path.is_dir():
            errors.append(f"{path.name} 不是普通备份目录")
            continue
        try:
            shutil.rmtree(path)
            removed += 1
        except OSError as error:
            errors.append(f"{path.name}: {error}")
    return removed, errors


def _restore_backup(progress, backup_progress):
    descriptor, temporary = tempfile.mkstemp(
        prefix=".progress.sav.restore.", suffix=".tmp", dir=progress.parent
    )
    try:
        os.fchmod(descriptor, progress.stat().st_mode & 0o777)
        with os.fdopen(descriptor, "wb") as stream:
            with backup_progress.open("rb") as backup:
                shutil.copyfileobj(backup, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, progress)
        directory_fd = os.open(progress.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _validate_tree(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("存档槽不是普通资料夹。")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError(f"存档槽包含链接或特殊文件：{path.name}")


def _tree_manifest(root):
    root = Path(root)
    _validate_tree(root)
    manifest = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        manifest[relative + "/" if path.is_dir() else relative] = (
            None if path.is_dir() else _sha256(path)
        )
    return manifest


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save_edit_paths(slot, profile):
    raw_profile = Path(profile).expanduser()
    raw_directory = Path(slot.directory)
    if raw_profile.is_symlink() or raw_directory.is_symlink():
        raise ValueError("不支持符号链接存档资料夹。")
    profile = raw_profile.resolve()
    directory = raw_directory.resolve()
    if profile not in directory.parents:
        raise ValueError("存档槽不属于所选资料夹，拒绝修改。")
    _validate_tree(directory)
    progress = directory / "progress.sav"
    if progress.is_symlink() or not progress.is_file():
        raise ValueError("存档文件不存在或不是普通文件。")
    backup_root = DATA_DIR / "save-editor-backups" / hashlib.sha256(
        str(profile).encode("utf-8")
    ).hexdigest()[:16]
    return directory, progress, backup_root


def _commit_save_edit(slot, directory, progress, current, modified,
                      backup_root, verify):
    backup = _backup_slot(slot, backup_root)
    if _sha256(backup / "progress.sav") != hashlib.sha256(current).hexdigest():
        raise ValueError("备份期间存档发生变化，请重新扫描后再修改。")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".progress.sav.", suffix=".tmp", dir=directory
    )
    replaced = False
    try:
        os.fchmod(descriptor, progress.stat().st_mode & 0o777)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(modified)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, progress)
        replaced = True
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        if replaced:
            try:
                _restore_backup(progress, backup / "progress.sav")
            except Exception as restore_error:
                raise OSError(
                    "写入失败，且无法自动恢复备份；请使用已创建的备份恢复存档。"
                ) from restore_error
        raise

    try:
        verification = progress.read_bytes()
        if len(verification) != len(current) or not verify(verification):
            raise SaveFormatError("写入内容与预期不符。")
    except Exception as verification_error:
        try:
            _restore_backup(progress, backup / "progress.sav")
        except Exception as restore_error:
            raise OSError(
                "修改结果校验失败，且无法自动恢复备份；"
                "请使用已创建的备份恢复存档。"
            ) from restore_error
        raise OSError(
            "修改结果校验失败，已从备份恢复原存档。"
        ) from verification_error
    removed_backups, cleanup_errors = _prune_previous_backups(
        backup.parent, backup
    )
    return {
        "changed": True,
        "backup": backup,
        "removed_backups": removed_backups,
        "cleanup_errors": cleanup_errors,
    }


def set_item_quantity(slot, item_id, category, quantity,
                      profile=DEFAULT_PROFILE, slot_dir=GAME_SLOT_DIR,
                      item_index=None):
    if category == "Rupee":
        if item_id != _RUPEE_FIELD or item_index not in (None, 0):
            raise ValueError("卢比字段无效，请重新扫描存档。")
        return set_rupees(
            slot, quantity, profile=profile, slot_dir=slot_dir
        )
    if category not in ("Arrow", "Material"):
        raise ValueError("目前只支持箭和素材的数量修改。")
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValueError("数量必须是整数。")
    if quantity < 0 or quantity > MAX_STACK:
        raise ValueError(f"数量必须在 0 到 {MAX_STACK} 之间。")

    directory, progress, backup_root = _save_edit_paths(slot, profile)

    with game_lock(slot_dir):
        current = progress.read_bytes()
        if hashlib.sha256(current).hexdigest() != slot.digest:
            raise ValueError("存档在载入后发生了变化。请重新扫描后再修改。")
        layout = _inventory_layout(current)
        names, stocks, regular_slots = layout[category]
        if item_index is None:
            index = next(
                (i for i in range(regular_slots)
                 if _read_string(current, names + i * 64, 64) == item_id),
                None,
            )
        elif (isinstance(item_index, bool) or not isinstance(item_index, int) or
              item_index < 0 or item_index >= regular_slots or
              _read_string(current, names + item_index * 64, 64) != item_id):
            index = None
        else:
            index = item_index
        if index is None:
            raise ValueError("所选物品已不在该存档中，请重新扫描。")
        current_quantity = struct.unpack_from("<i", current, stocks + index * 4)[0]
        if current_quantity < 0 or current_quantity > MAX_STACK:
            raise ValueError("物品数量不在可支持范围内，拒绝修改。")
        if current_quantity == quantity:
            return {"changed": False, "quantity": quantity, "backup": None}

        modified = bytearray(current)
        struct.pack_into("<i", modified, stocks + index * 4, quantity)
        result = _commit_save_edit(
            slot, directory, progress, current, modified, backup_root,
            lambda data: (
                _inventory_layout(data) == layout and
                struct.unpack_from("<i", data, stocks + index * 4)[0] ==
                quantity
            ),
        )
        result["quantity"] = quantity
        return result


def set_equipment_durability(
        slot, item_id, category, durability, profile=DEFAULT_PROFILE,
        slot_dir=GAME_SLOT_DIR, item_index=None):
    if category not in ("Weapon", "Shield", "Bow"):
        raise ValueError("装备类别必须是武器、盾牌或弓。")
    if isinstance(durability, bool) or not isinstance(durability, int):
        raise ValueError("耐久必须是整数。")

    directory, progress, backup_root = _save_edit_paths(slot, profile)
    with game_lock(slot_dir):
        current = progress.read_bytes()
        if hashlib.sha256(current).hexdigest() != slot.digest:
            raise ValueError("存档在载入后发生了变化。请重新扫描后再修改。")
        layout = _equipment_layout(current)
        names, lives, _, _, regular_slots = layout[category]
        if item_index is None:
            index = next(
                (i for i in range(regular_slots)
                 if _read_string(current, names + i * 64, 64) == item_id),
                None,
            )
        elif (isinstance(item_index, bool) or not isinstance(item_index, int) or
              item_index < 0 or item_index >= regular_slots or
              _read_string(current, names + item_index * 64, 64) != item_id):
            index = None
        else:
            index = item_index
        if index is None:
            raise ValueError("所选装备已不在该存档中，请重新扫描。")

        item = next(
            equipment for equipment in _read_equipment(current)
            if equipment.category == category and equipment.index == index
        )
        if item.maximum is None:
            raise ValueError(
                f"没有 {item_id} 的可靠耐久上限数据，拒绝修改。"
            )
        if durability < 0 or durability > item.maximum:
            raise ValueError(
                f"耐久必须在 0 到 {item.maximum} 之间。"
            )
        current_durability = struct.unpack_from(
            "<i", current, lives + index * 4
        )[0]
        if current_durability == durability:
            return {
                "changed": False,
                "durability": durability,
                "backup": None,
            }

        modified = bytearray(current)
        struct.pack_into("<i", modified, lives + index * 4, durability)
        result = _commit_save_edit(
            slot, directory, progress, current, modified, backup_root,
            lambda data: (
                _equipment_layout(data) == layout and
                struct.unpack_from("<i", data, lives + index * 4)[0] ==
                durability
            ),
        )
        result["durability"] = durability
        return result


def set_rupees(slot, quantity, profile=DEFAULT_PROFILE,
               slot_dir=GAME_SLOT_DIR):
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValueError("卢比数量必须是整数。")
    if quantity < 0 or quantity > MAX_RUPEES:
        raise ValueError(f"卢比数量必须在 0 到 {MAX_RUPEES:,} 之间。")

    directory, progress, backup_root = _save_edit_paths(slot, profile)
    with game_lock(slot_dir):
        current = progress.read_bytes()
        if hashlib.sha256(current).hexdigest() != slot.digest:
            raise ValueError("存档在载入后发生了变化。请重新扫描后再修改。")
        value_offset, current_quantity = _rupee_value_location(current)
        if current_quantity == quantity:
            return {"changed": False, "quantity": quantity, "backup": None}

        modified = bytearray(current)
        struct.pack_into("<I", modified, value_offset, quantity)
        result = _commit_save_edit(
            slot, directory, progress, current, modified, backup_root,
            lambda data: (
                _rupee_value_location(data) == (value_offset, quantity)
            ),
        )
        result["quantity"] = quantity
        return result


def activate_lightroots(slot, profile=DEFAULT_PROFILE, slot_dir=GAME_SLOT_DIR):
    directory, progress, backup_root = _save_edit_paths(slot, profile)
    with game_lock(slot_dir):
        current = progress.read_bytes()
        if hashlib.sha256(current).hexdigest() != slot.digest:
            raise ValueError("存档在载入后发生了变化。请重新扫描后再修改。")
        locations = _lightroot_locations(current)
        activated = sum(value == _LIGHTROOT_CLOSE for value in locations.values())
        if not activated:
            return {"changed": False, "activated": 0, "backup": None}

        modified = bytearray(current)
        for offset, value in locations.items():
            if value == _LIGHTROOT_CLOSE:
                struct.pack_into("<I", modified, offset, _LIGHTROOT_OPEN)
        expected = bytes(modified)
        result = _commit_save_edit(
            slot, directory, progress, current, expected, backup_root,
            lambda data: (
                data == expected and
                all(value == _LIGHTROOT_OPEN
                    for value in _lightroot_locations(data).values())
            ),
        )
        result["activated"] = activated
        return result


def add_equipment(slot, item_id, category, profile=DEFAULT_PROFILE,
                  slot_dir=GAME_SLOT_DIR):
    if category not in _EQUIPMENT_ID_PREFIXES:
        raise ValueError("新增装备类别必须是武器、盾牌或弓。")
    if (item_id not in EQUIPMENT_NAMES_ZH_CN or
            item_id not in MAX_DURABILITY or
            not item_id.startswith(_EQUIPMENT_ID_PREFIXES[category])):
        raise ValueError("所选装备不属于该类别或没有已验证的游戏数据。")

    directory, progress, backup_root = _save_edit_paths(slot, profile)
    with game_lock(slot_dir):
        current = progress.read_bytes()
        if hashlib.sha256(current).hexdigest() != slot.digest:
            raise ValueError("存档在载入后发生了变化。请重新扫描后再修改。")
        layout = _equipment_layout(current)
        names, lives, effects, values, regular_slots = layout[category]
        index = None
        for candidate in range(regular_slots):
            name_offset = names + candidate * 64
            life_offset = lives + candidate * 4
            effect_offset = effects + candidate * 4
            value_offset = values + candidate * 4
            if (
                _read_string(current, name_offset, 64) == "" and
                struct.unpack_from("<i", current, life_offset)[0] == -1 and
                _read_u32(current, effect_offset) == _NO_EFFECT and
                struct.unpack_from("<i", current, value_offset)[0] == -1
            ):
                index = candidate
                break
        if index is None:
            raise ValueError(f"{_EQUIPMENT_CATEGORY_LABELS[category]}背包没有可用空位。")

        modified = bytearray(current)
        encoded_id = item_id.encode("ascii")
        if len(encoded_id) >= 64:
            raise ValueError("装备 ID 超出存档字段长度，拒绝添加。")
        name_offset = names + index * 64
        life_offset = lives + index * 4
        effect_offset = effects + index * 4
        value_offset = values + index * 4
        modified[name_offset:name_offset + 64] = (
            encoded_id + b"\0" * (64 - len(encoded_id))
        )
        struct.pack_into("<i", modified, life_offset, MAX_DURABILITY[item_id])
        struct.pack_into("<I", modified, effect_offset, _NO_EFFECT)
        struct.pack_into("<i", modified, value_offset, 0)

        def verify(data):
            if _equipment_layout(data) != layout:
                return False
            if (_read_string(data, name_offset, 64) != item_id or
                    struct.unpack_from("<i", data, life_offset)[0] !=
                    MAX_DURABILITY[item_id] or
                    _read_u32(data, effect_offset) != _NO_EFFECT or
                    struct.unpack_from("<i", data, value_offset)[0] != 0):
                return False
            original = bytearray(current)
            original[name_offset:name_offset + 64] = (
                encoded_id + b"\0" * (64 - len(encoded_id))
            )
            struct.pack_into("<i", original, life_offset, MAX_DURABILITY[item_id])
            struct.pack_into("<I", original, effect_offset, _NO_EFFECT)
            struct.pack_into("<i", original, value_offset, 0)
            return data == original

        result = _commit_save_edit(
            slot, directory, progress, current, modified, backup_root, verify
        )
        result.update({
            "item_id": item_id,
            "category": category,
            "index": index,
            "durability": MAX_DURABILITY[item_id],
        })
        return result


def inventory_for_slot(slot):
    return [*read_inventory(slot.progress_path),
            read_rupees(slot.progress_path)]


def equipment_for_slot(slot):
    return read_equipment(slot.progress_path)


def equipment_catalog(category):
    if category not in _EQUIPMENT_ID_PREFIXES:
        raise ValueError("装备类别必须是武器、盾牌或弓。")
    return tuple(sorted(
        (
            EquipmentTemplate(item_id, category, MAX_DURABILITY[item_id])
            for item_id in EQUIPMENT_NAMES_ZH_CN
            if item_id in MAX_DURABILITY and
            item_id.startswith(_EQUIPMENT_ID_PREFIXES[category])
        ),
        key=lambda item: item.label.casefold(),
    ))
