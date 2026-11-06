"""Read item names from the player's own TOTK simplified Chinese game data."""

import json
from pathlib import Path
import re
import struct

from prepare_shader_seed import sarc


def _u32(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("游戏名称数据不完整。")
    return struct.unpack_from("<I", data, offset)[0]


def parse_item_names(data):
    if (len(data) < 32 or data[:8] != b"MsgStdBn" or
            data[8:10] != b"\xff\xfe" or data[12] != 1 or
            _u32(data, 18) != len(data)):
        raise ValueError("游戏名称文件格式不受支持。")
    sections = {}
    offset = 32
    for _ in range(struct.unpack_from("<H", data, 14)[0]):
        if offset + 16 > len(data):
            raise ValueError("游戏名称文件的段头不完整。")
        kind = data[offset:offset + 4]
        size = _u32(data, offset + 4)
        end = offset + 16 + size
        if end > len(data) or kind in sections:
            raise ValueError("游戏名称文件的段无效。")
        sections[kind] = data[offset + 16:end]
        offset = (end + 15) & ~15
    if b"LBL1" not in sections or b"TXT2" not in sections:
        raise ValueError("游戏名称文件缺少标签或文本段。")
    labels, texts = sections[b"LBL1"], sections[b"TXT2"]
    group_count = _u32(labels, 0)
    text_count = _u32(texts, 0)
    if group_count > (len(labels) - 4) // 8 or text_count > (len(texts) - 4) // 4:
        raise ValueError("游戏名称文件的索引无效。")
    names = {}
    for group in range(group_count):
        count = _u32(labels, 4 + group * 8)
        position = _u32(labels, 8 + group * 8)
        for _ in range(count):
            if position >= len(labels):
                raise ValueError("游戏名称标签越界。")
            length = labels[position]
            position += 1
            end = position + length
            if end + 4 > len(labels):
                raise ValueError("游戏名称标签不完整。")
            try:
                label = labels[position:end].decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("游戏名称标签编码无效。") from error
            index = _u32(labels, end)
            position = end + 4
            if index >= text_count:
                raise ValueError("游戏名称文本索引越界。")
            if not re.fullmatch(r"[A-Za-z0-9_]+_Name", label):
                continue
            start = _u32(texts, 4 + index * 4)
            stop = (_u32(texts, 8 + index * 4)
                    if index + 1 < text_count else len(texts))
            if start < 4 + text_count * 4 or stop < start or stop > len(texts):
                raise ValueError("游戏名称文本偏移无效。")
            try:
                name = texts[start:stop].decode("utf-16le").split("\0", 1)[0]
            except UnicodeDecodeError as error:
                raise ValueError("游戏名称文本编码无效。") from error
            if name and not any(ord(char) < 32 for char in name):
                item_id = label[:-5]
                if item_id in names and names[item_id] != name:
                    raise ValueError(f"游戏名称存在重复条目：{item_id}")
                names[item_id] = name
    if not names:
        raise ValueError("游戏名称文件没有可用名称。")
    return names


def read_game_item_names(romfs):
    try:
        from compression import zstd
    except ImportError as error:
        raise ValueError("读取游戏名称需要 Python 3.14 或更新版本。") from error
    romfs = Path(romfs).expanduser()
    try:
        index = json.loads((romfs / "index.json").read_text(encoding="utf-8"))
        files = {entry["path"]: entry for entry in index["files"]}
        candidates = sorted(path for path in files if
                            re.fullmatch(r"Mals/CNzh\.Product\.\d+\.sarc\.zs", path))
        if not candidates:
            raise ValueError("游戏数据中没有简体中文名称资源。")
        if len(candidates) != 1:
            raise ValueError("发现多个简体中文名称资源，无法确定版本。")
        with (romfs / "romfs.bin").open("rb") as image:
            def read(path):
                entry = files[path]
                image.seek(entry["offset"])
                data = image.read(entry["size"])
                if len(data) != entry["size"]:
                    raise ValueError(f"游戏资源不完整：{path}")
                return data

            dictionary_pack = zstd.decompress(read("Pack/ZsDic.pack.zs"))
            dictionaries = {}
            for content in sarc(dictionary_pack).values():
                dictionary = zstd.ZstdDict(content)
                dictionaries[dictionary.dict_id] = dictionary
            compressed = read(candidates[0])
        info = zstd.get_frame_info(compressed)
        if info.decompressed_size is None or info.decompressed_size > 32 * 1024 * 1024:
            raise ValueError("简体中文资源大小异常。")
        if info.dictionary_id and info.dictionary_id not in dictionaries:
            raise ValueError("简体中文资源所需的压缩字典不存在。")
        archive = zstd.decompress(
            compressed, zstd_dict=dictionaries.get(info.dictionary_id)
        )
        return parse_item_names(sarc(archive)["ActorMsg/PouchContent.msbt"])
    except (KeyError, TypeError, struct.error, UnicodeError, zstd.ZstdError) as error:
        raise ValueError(f"游戏资源索引或名称文件格式无效：{error}") from error
