#!/usr/bin/env python3
"""Prepare a CRC-checked, isolated Odyssey profile for a kingdom-load trial."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib


HEADER_SIZE = 0x10
TYPE_STRING = 0xA0
TYPE_ARRAY = 0xC0
TYPE_HASH = 0xC1
TYPE_BOOL = 0xD0
TYPE_INT = 0xD1
TYPE_FLOAT = 0xD2
TYPE_UINT = 0xD3
TYPE_INT64 = 0xD4
TYPE_UINT64 = 0xD5
TYPE_DOUBLE = 0xD6
TYPE_NULL = 0xFF

KINGDOMS = {
    0: "Cap Kingdom",
    1: "Cascade Kingdom",
    2: "Sand Kingdom",
    3: "Lake Kingdom",
    4: "Wooded Kingdom",
    5: "Cloud Kingdom",
    6: "Lost Kingdom",
    7: "Metro Kingdom",
    8: "Snow Kingdom",
    9: "Seaside Kingdom",
    10: "Luncheon Kingdom",
    11: "Ruined Kingdom",
    12: "Bowser's Kingdom",
    13: "Moon Kingdom",
    14: "Mushroom Kingdom",
}


@dataclass
class ValueRef:
    value: object
    offset: int
    node_type: int


class BymlV3:
    def __init__(self, data: bytes):
        if len(data) < HEADER_SIZE or struct.unpack_from("<I", data)[0] != zlib.crc32(data[4:]):
            raise ValueError("File1.bin CRC32 or minimum size is invalid")
        if struct.unpack_from("<I", data, 8)[0] != len(data):
            raise ValueError("File1.bin length header does not match")
        self.data = data
        self.byml = memoryview(data)[HEADER_SIZE:]
        magic, version, hash_offset, string_offset, self.root_offset = struct.unpack_from("<2sHIII", self.byml)
        if magic != b"YB" or version != 3:
            raise ValueError(f"unsupported File1.bin BYML header: {magic!r} v{version}")
        self.hash_keys = self._read_string_table(hash_offset)
        self.strings = self._read_string_table(string_offset)

    def _check(self, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.byml):
            raise ValueError("BYML offset is outside File1.bin")

    def _read_string_table(self, offset: int) -> list[str]:
        if offset == 0:
            return []
        self._check(offset, 4)
        count = struct.unpack_from("<I", self.byml, offset)[0] >> 8
        self._check(offset + 4, count * 4)
        result = []
        for index in range(count):
            relative = struct.unpack_from("<I", self.byml, offset + 4 + index * 4)[0]
            start = offset + relative
            self._check(start, 1)
            end = bytes(self.byml[start:]).find(b"\0")
            if end < 0:
                raise ValueError("unterminated BYML string")
            result.append(bytes(self.byml[start:start + end]).decode("utf-8", "strict"))
        return result

    def _value(self, node_type: int, offset: int, depth: int = 0):
        if depth > 64:
            raise ValueError("BYML nesting is too deep")
        self._check(offset, 4)
        raw = self.byml[offset:offset + 4]
        value = struct.unpack_from("<I", raw)[0]
        file_offset = HEADER_SIZE + offset
        if node_type == TYPE_NULL:
            return None
        if node_type == TYPE_BOOL:
            return ValueRef(bool(value), file_offset, node_type)
        if node_type == TYPE_INT:
            return ValueRef(struct.unpack_from("<i", raw)[0], file_offset, node_type)
        if node_type == TYPE_UINT:
            return ValueRef(value, file_offset, node_type)
        if node_type == TYPE_FLOAT:
            return ValueRef(struct.unpack_from("<f", raw)[0], file_offset, node_type)
        if node_type == TYPE_STRING:
            if value >= len(self.strings):
                raise ValueError("BYML string index is invalid")
            return ValueRef(self.strings[value], file_offset, node_type)
        if node_type == TYPE_ARRAY:
            return self._array(value, depth + 1)
        if node_type == TYPE_HASH:
            return self._hash(value, depth + 1)
        if node_type in (TYPE_INT64, TYPE_UINT64, TYPE_DOUBLE):
            self._check(value, 8)
            fmt = {TYPE_INT64: "<q", TYPE_UINT64: "<Q", TYPE_DOUBLE: "<d"}[node_type]
            return ValueRef(struct.unpack_from(fmt, self.byml, value)[0], HEADER_SIZE + value, node_type)
        raise ValueError(f"unsupported BYML node type {node_type:#x}")

    def _array(self, offset: int, depth: int):
        self._check(offset, 4)
        count = struct.unpack_from("<I", self.byml, offset)[0] >> 8
        type_offset = offset + 4
        value_offset = type_offset + ((count + 3) & ~3)
        self._check(type_offset, count)
        self._check(value_offset, count * 4)
        return [self._value(self.byml[type_offset + i], value_offset + i * 4, depth) for i in range(count)]

    def _hash(self, offset: int, depth: int = 0):
        self._check(offset, 4)
        count = struct.unpack_from("<I", self.byml, offset)[0] >> 8
        start = offset + 4
        self._check(start, count * 8)
        result = {}
        for index in range(count):
            key_type = struct.unpack_from("<I", self.byml, start + index * 8)[0]
            key_index = key_type & 0xFFFFFF
            if key_index >= len(self.hash_keys):
                raise ValueError("BYML hash key index is invalid")
            key = self.hash_keys[key_index]
            if key in result:
                raise ValueError(f"duplicate BYML key: {key}")
            result[key] = self._value(key_type >> 24, start + index * 8 + 4, depth)
        return result

    def parse(self):
        return self._hash(self.root_offset)


def get_ref(mapping: dict, key: str) -> ValueRef:
    value = mapping.get(key)
    if not isinstance(value, ValueRef):
        raise ValueError(f"missing or non-scalar BYML field: {key}")
    return value


def add_patch(patches: list[tuple[int, bytes]], ref: ValueRef, value, key: str) -> None:
    if ref.node_type == TYPE_INT:
        raw = struct.pack("<i", int(value))
    elif ref.node_type == TYPE_UINT:
        raw = struct.pack("<I", int(value))
    elif ref.node_type == TYPE_BOOL:
        raw = struct.pack("<I", 1 if value else 0)
    else:
        raise ValueError(f"unexpected node type for {key}: {ref.node_type:#x}")
    patches.append((ref.offset, raw))


def add_string_patch(patches: list[tuple[int, bytes]], ref: ValueRef, value: str,
                     strings: list[str], key: str) -> None:
    if ref.node_type != TYPE_STRING or value not in strings:
        raise ValueError(f"{key} is not present in the BYML string table")
    patches.append((ref.offset, struct.pack("<I", strings.index(value))))


def encode_string_table(strings: list[str]) -> bytes:
    encoded = [value.encode("utf-8") + b"\0" for value in strings]
    first = 8 + 4 * len(strings)
    offsets = []
    cursor = first
    for item in encoded:
        offsets.append(cursor)
        cursor += len(item)
    offsets.append(cursor)
    return (struct.pack("<I", (len(strings) << 8) | 0xC2)
            + struct.pack(f"<{len(offsets)}I", *offsets)
            + b"".join(encoded))


def parse_profile(profile: Path) -> tuple[Path, bytes, dict]:
    saves = list(profile.glob("save/*/File1.bin"))
    if len(saves) != 1:
        raise ValueError(f"expected exactly one File1.bin in profile; found {len(saves)}")
    data = saves[0].read_bytes()
    root = BymlV3(data).parse()
    return saves[0], data, root


def prepare(source: Path, destination: Path, target_world: int,
            target_stage: str | None = None, target_checkpoint: str | None = None,
            player_start: str | None = None) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() or source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("destination must be a new profile outside the source tree")
    if target_world not in KINGDOMS:
        raise ValueError("target world must be a supported kingdom ID (0..14)")
    if (target_stage is None) != (target_checkpoint is None):
        raise ValueError("--stage and --checkpoint must be supplied together")
    if player_start is not None and target_stage is None:
        raise ValueError("--player-start requires --stage and --checkpoint")

    source_save, original, root = parse_profile(source)
    byml = BymlV3(original)
    root = byml.parse()
    old_world = get_ref(root, "WorldId")
    progress = root.get("GameProgressData")
    world_info = root.get("WorldInfo")
    if not isinstance(progress, dict) or not isinstance(world_info, list):
        raise ValueError("File1.bin is missing GameProgressData or WorldInfo")
    unlock_count = get_ref(progress, "UnlockWorldNum")
    first_time = progress.get("IsFirstTimeWorld")
    if not isinstance(first_time, list) or target_world >= len(first_time):
        raise ValueError("IsFirstTimeWorld does not contain the target kingdom")

    target_entry = None
    empty_entry = None
    for entry in world_info:
        if not isinstance(entry, dict):
            continue
        world_id = get_ref(entry, "UnlockedWorldId").value
        if world_id == target_world:
            target_entry = entry
            break
        if world_id == -1 and empty_entry is None:
            empty_entry = entry
    if target_entry is None:
        target_entry = empty_entry
    if target_entry is None:
        raise ValueError("WorldInfo has no free slot for the target kingdom")

    patches: list[tuple[int, bytes]] = []
    target_ref = get_ref(target_entry, "UnlockedWorldId")
    if target_ref.value != target_world:
        add_patch(patches, target_ref, target_world, "UnlockedWorldId")
        add_patch(patches, get_ref(target_entry, "MainShineNo"), 1, "MainShineNo")
        scenario = get_ref(target_entry, "ScenarioNo")
        if scenario.value < 0:
            add_patch(patches, scenario, 1, "ScenarioNo")

    add_patch(patches, old_world, target_world, "WorldId")
    add_patch(patches, first_time[target_world], False, "IsFirstTimeWorld")
    if target_ref.value != target_world:
        add_patch(patches, unlock_count, unlock_count.value + 1, "UnlockWorldNum")
    if target_stage is not None:
        checkpoints = root.get("Checkpoint")
        matching_entry = next((entry for entry in checkpoints or [] if
            isinstance(entry, dict)
            and isinstance(entry.get("ObjId"), ValueRef)
            and isinstance(entry.get("StageName"), ValueRef)
            and entry["ObjId"].value == target_checkpoint
            and entry["StageName"].value == target_stage
        ), None)
        if matching_entry is None:
            matching_entry = next((entry for entry in checkpoints or [] if
                isinstance(entry, dict)
                and isinstance(entry.get("ObjId"), ValueRef)
                and isinstance(entry.get("StageName"), ValueRef)
                and entry["ObjId"].value == ""
                and entry["StageName"].value == ""
            ), None)
            if matching_entry is None:
                raise ValueError("checkpoint table has no empty slot for the target scene")
        strings = list(byml.strings)
        for value in (target_stage, target_checkpoint):
            if value not in strings:
                strings.append(value)
        add_string_patch(patches, get_ref(root, "StageName"), target_stage, strings, "StageName")
        add_string_patch(patches, get_ref(root, "CheckpointName"), target_checkpoint,
                         strings, "CheckpointName")
        add_string_patch(patches, get_ref(matching_entry, "StageName"), target_stage,
                         strings, "Checkpoint.StageName")
        add_string_patch(patches, get_ref(matching_entry, "ObjId"), target_checkpoint,
                         strings, "Checkpoint.ObjId")
    if player_start is not None:
        if player_start not in strings:
            strings.append(player_start)
        add_string_patch(patches, get_ref(root, "PlayerStartIdForSave"), player_start,
                         strings, "PlayerStartIdForSave")

    output = bytearray(original)
    for offset, raw in patches:
        output[offset:offset + len(raw)] = raw
    if target_stage is not None:
        output.extend(bytes((-len(output)) % 4))
        string_table_offset = len(output) - HEADER_SIZE
        output.extend(encode_string_table(strings))
        struct.pack_into("<I", output, HEADER_SIZE + 8, string_table_offset)
        struct.pack_into("<I", output, 8, len(output))
    struct.pack_into("<I", output, 0, zlib.crc32(output[4:]))

    reparsed = BymlV3(bytes(output)).parse()
    if get_ref(reparsed, "WorldId").value != target_world:
        raise ValueError("post-write WorldId verification failed")
    if struct.unpack_from("<I", output)[0] != zlib.crc32(output[4:]):
        raise ValueError("post-write CRC32 verification failed")

    shutil.copytree(source, destination, symlinks=True)
    output_save = destination / source_save.relative_to(source)
    temp_save = output_save.with_suffix(".bin.tmp")
    temp_save.write_bytes(output)
    temp_save.replace(output_save)
    if hashlib.sha256(source_save.read_bytes()).digest() != hashlib.sha256(original).digest():
        raise ValueError("source save changed during profile staging")

    return {
        "status": "candidate-prepared",
        "world_id": target_world,
        "kingdom": KINGDOMS[target_world],
        "source_world_id": old_world.value,
        "source_stage_name": get_ref(root, "StageName").value,
        "patched_fields": len(patches),
        "target_stage": target_stage,
        "target_checkpoint": target_checkpoint,
        "player_start": player_start,
        "crc32_valid": True,
        "source_unchanged": True,
        "profile": str(destination),
        "warning": "candidate only; boot and visually verify before using this method for other kingdoms",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_profile", type=Path)
    parser.add_argument("destination_profile", type=Path)
    parser.add_argument("--world-id", type=int, required=True)
    parser.add_argument("--stage")
    parser.add_argument("--checkpoint")
    parser.add_argument("--player-start")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_profile, args.destination_profile, args.world_id,
                             args.stage, args.checkpoint, args.player_start), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())