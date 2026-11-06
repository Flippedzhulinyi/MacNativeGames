import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "games/totk/scripts"))
import save_editor_core as editor


def build_progress(duplicate_item=False, lightroots=False):
    arrow_names = ["NormalArrow", ""]
    arrow_counts = [18, -1]
    material_names = (
        ["BombFruit", "FireFruit", "BombFruit", "", "", ""]
        if duplicate_item else ["BombFruit", "FireFruit", "", ""]
    )
    material_counts = [4, 7, 9, 0, 0, 0][:len(material_names)]
    arrays = [
        (3, "Pouch.Arrow.Content.StockNum", arrow_counts),
        (3, "Pouch.Material.Content.StockNum", material_counts),
        (17, "Pouch.Arrow.Content.Name", arrow_names),
        (17, "Pouch.Material.Content.Name", material_names),
    ]
    equipment = {
        "Weapon": (
            ["Weapon_Sword_043", "Weapon_Sword_161", "", "", "", ""],
            [3, 10, -1, -1, -1, -1],
            [0xB2C943EE, 0xD5CAD39B, 0xB6EEDE09, 0xB6EEDE09,
             0xB6EEDE09, 0xB6EEDE09],
            [10, 5, -1, -1, -1, -1],
        ),
        "Shield": (
            ["Weapon_Shield_103", "", "", "", "", ""],
            [4, -1, -1, -1, -1, -1],
            [0xB6EEDE09] * 6,
            [0, -1, -1, -1, -1, -1],
        ),
        "Bow": (
            ["Weapon_Bow_002", "", "", "", "", ""],
            [1, -1, -1, -1, -1, -1],
            [0xB6EEDE09] * 6,
            [0, -1, -1, -1, -1, -1],
        ),
    }
    for category, (names, lives, effects, effect_values) in equipment.items():
        prefix = f"Pouch.{category}.Content"
        arrays.extend((
            (3, f"{prefix}.Life", lives),
            (3, f"{prefix}.Effect.Value", effect_values),
            (7, f"{prefix}.Effect.Type", effects),
            (17, f"{prefix}.Name", names),
        ))
    arrays.sort(key=lambda array: array[0])
    entries = [(2, 0, None),
               (2, editor.field_hash(editor._RUPEE_FIELD),
                editor._RUPEE_FIELD)]
    current_type = 2
    for kind, name, _ in sorted(arrays, key=lambda array: array[0]):
        if lightroots and current_type < 6 < kind:
            entries.append((6, 0, None))
            for index in editor._LIGHTROOT_INDICES:
                field = f"ArrivalPointState.CheckPoint{index:03}"
                entries.append((6, editor.field_hash(field), field))
            shrine = "ArrivalPointState.Dungeon001"
            entries.append((6, editor.field_hash(shrine), shrine))
            current_type = 6
        if kind != current_type:
            entries.append((kind, 0, None))
            current_type = kind
        entries.append((kind, editor.field_hash(name), name))
    table_end = 32 + len(entries) * 8
    payload = bytearray()
    offsets = {}
    for kind, name, contents in arrays:
        offsets[name] = table_end + len(payload)
        payload.extend(struct.pack("<I", len(contents)))
        if kind == 17:
            for value in contents:
                encoded = value.encode("ascii")
                payload.extend(encoded + b"\0" * (64 - len(encoded)))
        elif kind == 7:
            payload.extend(struct.pack("<" + "I" * len(contents), *contents))
        else:
            payload.extend(struct.pack("<" + "i" * len(contents), *contents))

    header = bytearray(32)
    struct.pack_into("<III", header, 0, editor._MAGIC, 0x49E946, table_end)
    table = bytearray()
    for section, key, name in entries:
        if key == 0:
            table.extend(struct.pack("<II", 0, section))
        elif section == 2:
            table.extend(struct.pack("<II", key, 515))
        elif section == 6:
            value = (editor._LIGHTROOT_OPEN if name.endswith(
                tuple(f"{index:03}" for index in range(6))
            ) else editor._LIGHTROOT_CLOSE)
            table.extend(struct.pack("<II", key, value))
        else:
            table.extend(struct.pack("<II", key, offsets[name]))
    return bytes(header + table + payload)


def build_caption(location=b"Cave_CentralHyrule_0009", depth=b"Underground"):
    header = bytearray(32)
    table_end = 40
    struct.pack_into("<III", header, 0, editor._MAGIC, 0x49E946, table_end)
    return bytes(header + struct.pack("<II", 0, 0) +
                 location + b"\0" + depth + b"\0")


class TotkSaveEditor(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = self.root / "profile"
        self.slot_dir = self.profile / "save" / "0123456789abcdef" / "slot_03"
        self.slot_dir.mkdir(parents=True)
        (self.slot_dir / "progress.sav").write_bytes(build_progress())
        (self.slot_dir / "caption.sav").write_bytes(build_caption())
        (self.slot_dir / "footprint.sav").write_bytes(b"companion")
        self.game_lock = self.root / "game-slot"
        self.backup_root = self.root / "backups"

    def slot(self):
        return editor.discover_saves(self.profile)[0]

    def test_hash_and_inventory_decode(self):
        self.assertEqual(editor.field_hash("PlayerStatus.SavePos"), 0xC884818D)
        items = editor.read_inventory(self.slot_dir / "progress.sav")
        self.assertEqual([(i.item_id, i.category, i.quantity) for i in items], [
            ("NormalArrow", "Arrow", 18),
            ("BombFruit", "Material", 4),
            ("FireFruit", "Material", 7),
        ])
        self.assertIn("炸弹花", items[1].label)
        self.assertEqual(
            editor.InventoryItem("Item_Enemy_77", "Material", 0, 40).label,
            "波克布林的犄角 · 素材 · 40/999",
        )
        self.assertEqual(
            editor.InventoryItem("Animal_Insect_A", "Material", 0, 6).label,
            "速速青蛙 · 素材 · 6/999",
        )

        self.assertEqual(
            editor.InventoryItem("Item_Unknown_01", "Material", 0, 1).label,
            "未收录名称（Item_Unknown_01） · 素材 · 1/999",
        )

    def test_rupee_field_is_read_from_direct_scalar(self):
        balance = editor.read_rupees(self.slot_dir / "progress.sav")
        self.assertEqual(balance.quantity, 515)
        self.assertEqual(balance.maximum, 999999)
        self.assertEqual(balance.label, "卢比 · 515/999999")
        self.assertIn(balance, editor.inventory_for_slot(self.slot()))

    def test_rupee_edit_uses_backup_and_preserves_other_save_data(self):
        slot = self.slot()
        original = slot.progress_path.read_bytes()
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.set_rupees(
                slot, 999999, profile=self.profile, slot_dir=self.game_lock
            )
        self.assertTrue(result["changed"])
        self.assertEqual(result["quantity"], 999999)
        self.assertEqual(
            (Path(result["backup"]) / "progress.sav").read_bytes(), original
        )
        self.assertEqual(
            editor.read_rupees(slot.progress_path).quantity, 999999
        )

    def test_rupee_edit_rejects_out_of_range_values_without_backup(self):
        slot = self.slot()
        before = slot.progress_path.read_bytes()
        for value in (-1, 1000000, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                editor.set_rupees(
                    slot, value, profile=self.profile, slot_dir=self.game_lock
                )
        with self.assertRaises(ValueError):
            editor.set_item_quantity(
                slot, editor._RUPEE_FIELD, "Rupee", 1000000,
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertEqual(slot.progress_path.read_bytes(), before)
        self.assertFalse(self.backup_root.exists())

    def test_activate_lightroots_backs_up_and_changes_only_lightroot_values(self):
        progress = self.slot_dir / "progress.sav"
        original = build_progress(lightroots=True)
        progress.write_bytes(original)
        slot = self.slot()
        self.assertEqual(editor.read_lightroots(progress), 6)
        locations = editor._lightroot_locations(original)
        expected = bytearray(original)
        for offset in locations:
            struct.pack_into("<I", expected, offset, editor._LIGHTROOT_OPEN)
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.activate_lightroots(
                slot, profile=self.profile, slot_dir=self.game_lock
            )
        self.assertEqual(result["activated"], 114)
        self.assertEqual((result["backup"] / "progress.sav").read_bytes(), original)
        self.assertEqual(progress.read_bytes(), bytes(expected))
        self.assertEqual(editor.read_lightroots(progress), 120)
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            noop = editor.activate_lightroots(
                self.slot(), profile=self.profile, slot_dir=self.game_lock
            )
        self.assertFalse(noop["changed"])
        self.assertIsNone(noop["backup"])

    def test_lightroots_reject_missing_wrong_type_and_unknown_state(self):
        original = build_progress(lightroots=True)
        first_key = editor.field_hash("ArrivalPointState.CheckPoint000")
        for case in ("missing", "wrong_type", "unknown"):
            data = bytearray(original)
            for offset in range(32, editor._read_u32(data, 8), 8):
                if editor._read_u32(data, offset) == first_key:
                    if case == "missing":
                        struct.pack_into("<I", data, offset, 0x12345678)
                    elif case == "wrong_type":
                        type_marker = data.find(struct.pack("<II", 0, 6), 32)
                        struct.pack_into("<I", data, type_marker + 4, 5)
                    else:
                        struct.pack_into("<I", data, offset + 4, 0x12345678)
                    break
            progress = self.slot_dir / "progress.sav"
            progress.write_bytes(data)
            with self.subTest(case=case), self.assertRaises(editor.SaveFormatError):
                editor.activate_lightroots(
                    self.slot(), profile=self.profile, slot_dir=self.game_lock
                )
            self.assertEqual(progress.read_bytes(), data)
            self.assertFalse(self.backup_root.exists())

    def test_lightroots_refuse_stale_save_and_game_lock(self):
        import fcntl
        progress = self.slot_dir / "progress.sav"
        progress.write_bytes(build_progress(lightroots=True))
        slot = self.slot()
        progress.write_bytes(progress.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "发生了变化"):
            editor.activate_lightroots(
                slot, profile=self.profile, slot_dir=self.game_lock
            )
        slot = self.slot()
        self.game_lock.mkdir(exist_ok=True)
        with (self.game_lock / "lock").open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "游戏正在运行"):
                editor.activate_lightroots(
                    slot, profile=self.profile, slot_dir=self.game_lock
                )
        self.assertFalse(self.backup_root.exists())

    def test_lightroot_verification_failure_restores_original(self):
        progress = self.slot_dir / "progress.sav"
        original = build_progress(lightroots=True)
        progress.write_bytes(original)
        slot = self.slot()
        real_read_bytes = Path.read_bytes
        reads = 0

        def corrupt_verification(path):
            nonlocal reads
            data = real_read_bytes(path)
            if path.resolve() == progress.resolve():
                reads += 1
                if reads == 2:
                    return data[:-1] + bytes([data[-1] ^ 1])
            return data

        with mock.patch.object(editor, "DATA_DIR", self.backup_root), \
                mock.patch.object(Path, "read_bytes", corrupt_verification):
            with self.assertRaisesRegex(OSError, "已从备份恢复"):
                editor.activate_lightroots(
                    slot, profile=self.profile, slot_dir=self.game_lock
                )
        self.assertEqual(progress.read_bytes(), original)

    def test_equipment_decode_uses_per_item_maximum_and_durability_bonus(self):
        equipment = editor.read_equipment(self.slot_dir / "progress.sav")
        weapon = next(item for item in equipment
                      if item.category == "Weapon" and item.index == 0)
        reinforced_weapon = next(item for item in equipment
                                  if item.category == "Weapon" and item.index == 1)
        shield = next(item for item in equipment if item.category == "Shield")
        bow = next(item for item in equipment if item.category == "Bow")
        self.assertEqual((weapon.item_id, weapon.durability, weapon.maximum),
                         ("Weapon_Sword_043", 3, 18))
        self.assertEqual(weapon.label, "火把 · 武器 · 3/18")
        self.assertEqual(reinforced_weapon.maximum, 19)
        self.assertEqual((shield.durability, shield.maximum), (4, 20))
        self.assertEqual((bow.durability, bow.maximum), (1, 36))

    def test_equipment_edit_backs_up_and_verifies_new_durability(self):
        slot = self.slot()
        original = slot.progress_path.read_bytes()
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.set_equipment_durability(
                slot, "Weapon_Sword_043", "Weapon", 18,
                profile=self.profile, slot_dir=self.game_lock, item_index=0,
            )
        self.assertTrue(result["changed"])
        self.assertEqual(result["durability"], 18)
        self.assertEqual(Path(result["backup"]).joinpath("progress.sav").read_bytes(),
                         original)
        updated = next(
            item for item in editor.read_equipment(slot.progress_path)
            if item.category == "Weapon" and item.index == 0
        )
        self.assertEqual(updated.durability, 18)

    def test_add_equipment_uses_empty_slot_and_initializes_regular_state(self):
        slot = self.slot()
        original = slot.progress_path.read_bytes()
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.add_equipment(
                slot, "Weapon_Bow_001", "Bow",
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertTrue(result["changed"])
        self.assertEqual(result["index"], 1)
        self.assertEqual(result["durability"], 22)
        self.assertEqual(
            (Path(result["backup"]) / "progress.sav").read_bytes(), original
        )
        added = next(
            item for item in editor.read_equipment(slot.progress_path)
            if item.category == "Bow" and item.index == result["index"]
        )
        self.assertEqual(
            (added.item_id, added.durability, added.maximum),
            ("Weapon_Bow_001", 22, 22),
        )
        data = slot.progress_path.read_bytes()
        _, lives, effects, values, _ = editor._equipment_layout(data)["Bow"]
        self.assertEqual(
            editor._read_u32(data, effects + result["index"] * 4),
            editor._NO_EFFECT,
        )
        self.assertEqual(
            struct.unpack_from("<i", data, values + result["index"] * 4)[0],
            0,
        )

    def test_add_equipment_supports_weapon_and_shield_pouches(self):
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            for item_id, category in (
                ("Weapon_Sword_001", "Weapon"),
                ("Weapon_Shield_001", "Shield"),
            ):
                with self.subTest(category=category):
                    result = editor.add_equipment(
                        self.slot(), item_id, category,
                        profile=self.profile, slot_dir=self.game_lock,
                    )
                    self.assertTrue(result["changed"])
                    item = next(
                        equipment for equipment in editor.read_equipment(
                            self.slot_dir / "progress.sav"
                        )
                        if equipment.category == category and
                        equipment.index == result["index"]
                    )
                    self.assertEqual(item.item_id, item_id)
                    self.assertEqual(item.durability, item.maximum)

    def test_add_equipment_refuses_full_pouch_without_overwriting(self):
        data = bytearray((self.slot_dir / "progress.sav").read_bytes())
        names, lives, effects, values, slots = editor._equipment_layout(data)["Bow"]
        for index in range(slots):
            name_offset = names + index * 64
            if editor._read_string(data, name_offset, 64):
                continue
            item_id = b"Weapon_Bow_017"
            data[name_offset:name_offset + 64] = item_id + b"\0" * (64 - len(item_id))
            struct.pack_into("<i", data, lives + index * 4, 35)
            struct.pack_into("<i", data, values + index * 4, 0)
        self.slot_dir.joinpath("progress.sav").write_bytes(data)
        slot = self.slot()
        before = slot.progress_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "没有可用空位"):
            editor.add_equipment(
                slot, "Weapon_Bow_001", "Bow",
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertEqual(slot.progress_path.read_bytes(), before)
        self.assertFalse(self.backup_root.exists())

    def test_add_equipment_rejects_unknown_id_or_wrong_category(self):
        slot = self.slot()
        before = slot.progress_path.read_bytes()
        for item_id, category in (
            ("Weapon_Bow_999", "Bow"),
            ("Weapon_Bow_001", "Weapon"),
        ):
            with self.subTest(item_id=item_id, category=category):
                with self.assertRaisesRegex(ValueError, "没有已验证"):
                    editor.add_equipment(
                        slot, item_id, category,
                        profile=self.profile, slot_dir=self.game_lock,
                    )
        self.assertEqual(slot.progress_path.read_bytes(), before)
        self.assertFalse(self.backup_root.exists())

    def test_unknown_equipment_maximum_is_displayed_but_not_editable(self):
        data = bytearray((self.slot_dir / "progress.sav").read_bytes())
        fields = editor._parse_field_table(data)
        names, _ = editor._array_field(
            data, fields, "Pouch.Bow.Content.Name", 17, 64
        )
        unknown_id = b"Weapon_Bow_999"
        data[names:names + 64] = unknown_id + b"\0" * (64 - len(unknown_id))
        (self.slot_dir / "progress.sav").write_bytes(data)
        slot = self.slot()
        item = next(item for item in editor.read_equipment(slot.progress_path)
                    if item.category == "Bow")
        self.assertIsNone(item.maximum)
        self.assertIn("上限未知", item.label)
        with self.assertRaisesRegex(ValueError, "可靠耐久上限"):
            editor.set_equipment_durability(
                slot, item.item_id, item.category, 1,
                profile=self.profile, slot_dir=self.game_lock, item_index=item.index,
            )
        self.assertFalse(self.backup_root.exists())

    def test_equipment_durability_rejects_values_above_maximum_without_backup(self):
        slot = self.slot()
        for value in (-1, 19, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                editor.set_equipment_durability(
                    slot, "Weapon_Sword_043", "Weapon", value,
                    profile=self.profile, slot_dir=self.game_lock, item_index=0,
                )
        self.assertFalse(self.backup_root.exists())

    def test_discovery_uses_caption_location_and_saves_sorted(self):
        saves = editor.discover_saves(self.profile)
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0].display_name, "Central Hyrule 0009 洞窟 · 地下")
        self.assertNotEqual(saves[0].label, "slot_03")
        self.assertRegex(saves[0].label, r"\d{2}:\d{2}:\d{2}$")

    def test_caption_checkpoint_locations_are_readable(self):
        cases = (
            (b"ECheckPoint058", b"Highlands_Underground", "检查点 058 · 地下"),
            (b"DCheckPoint026", b"CentralHyrule", "检查点 026"),
        )
        for location, area, expected in cases:
            with self.subTest(location=location):
                caption = self.root / "caption-checkpoint.sav"
                caption.write_bytes(build_caption(location, area))
                self.assertEqual(editor._caption_location(caption), expected)

    def test_shrine_caption_uses_game_localized_name(self):
        self.assertEqual(
            editor._humanize_location("Dungeon026"), "里欧高可神庙"
        )
        self.assertEqual(
            editor._humanize_location("Dungeon068"), "巧克高尼神庙"
        )
        self.assertEqual(
            editor._humanize_location("Dungeon999"), "神庙 999"
        )

    def test_change_backs_up_full_slot_before_atomic_write(self):
        slot = self.slot()
        original = slot.progress_path.read_bytes()
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.set_item_quantity(
                slot, "BombFruit", "Material", 999,
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertTrue(result["changed"])
        self.assertEqual(result["quantity"], 999)
        backup = Path(result["backup"])
        self.assertEqual((backup / "progress.sav").read_bytes(), original)
        self.assertEqual((backup / "footprint.sav").read_bytes(), b"companion")
        edited_items = editor.read_inventory(slot.progress_path)
        bomb = next(item for item in edited_items if item.item_id == "BombFruit")
        self.assertEqual(bomb.quantity, 999)
        self.assertEqual((backup / "progress.sav").stat().st_size,
                         len(original))

    def test_successful_edit_keeps_only_latest_backup_for_that_slot(self):
        slot = self.slot()
        other_slot_backup = (
            self.backup_root / "save-editor-backups"
            / hashlib.sha256(str(self.profile.resolve()).encode("utf-8")).hexdigest()[:16]
            / "slot_04" / "20260101-000000-000000"
        )
        other_slot_backup.mkdir(parents=True)
        other_slot_backup.joinpath("keep.txt").write_text("unrelated")

        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            first = editor.set_item_quantity(
                slot, "BombFruit", "Material", 10,
                profile=self.profile, slot_dir=self.game_lock,
            )
            updated_slot = self.slot()
            second = editor.set_item_quantity(
                updated_slot, "BombFruit", "Material", 20,
                profile=self.profile, slot_dir=self.game_lock,
            )

        self.assertFalse(first["backup"].exists())
        self.assertEqual(second["removed_backups"], 1)
        self.assertEqual(second["cleanup_errors"], [])
        self.assertTrue(second["backup"].is_dir())
        self.assertEqual(len(list(second["backup"].parent.iterdir())), 1)
        previous_items = editor.read_inventory(second["backup"] / "progress.sav")
        previous_bomb = next(item for item in previous_items
                             if item.item_id == "BombFruit")
        self.assertEqual(previous_bomb.quantity, 10)
        self.assertEqual(other_slot_backup.joinpath("keep.txt").read_text(),
                         "unrelated")

    def test_refuses_symlink_backup_directory(self):
        slot = self.slot()
        before = slot.progress_path.read_bytes()
        data_dir = self.root / "app-data"
        data_dir.mkdir()
        target = self.root / "unexpected-backups"
        target.mkdir()
        (data_dir / "save-editor-backups").symlink_to(target)
        with mock.patch.object(editor, "DATA_DIR", data_dir):
            with self.assertRaisesRegex(ValueError, "符号链接"):
                editor.set_item_quantity(
                    slot, "BombFruit", "Material", 999,
                    profile=self.profile, slot_dir=self.game_lock,
                )
        self.assertEqual(slot.progress_path.read_bytes(), before)
        self.assertEqual(list(target.iterdir()), [])

    def test_restores_original_save_atomically_after_verification_failure(self):
        slot = self.slot()
        original = slot.progress_path.read_bytes()
        inventory_layout = editor._inventory_layout

        def reject_modified_save(data):
            if data != original:
                raise editor.SaveFormatError("synthetic verification failure")
            return inventory_layout(data)

        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            with mock.patch.object(
                    editor, "_inventory_layout", side_effect=reject_modified_save):
                with self.assertRaisesRegex(OSError, "已从备份恢复"):
                    editor.set_item_quantity(
                        slot, "BombFruit", "Material", 999,
                        profile=self.profile, slot_dir=self.game_lock,
                    )
        self.assertEqual(slot.progress_path.read_bytes(), original)
        self.assertFalse(list(self.slot_dir.glob(".progress.sav.restore.*.tmp")))

    def test_selects_exact_stack_when_item_ids_are_duplicated(self):
        (self.slot_dir / "progress.sav").write_bytes(
            build_progress(duplicate_item=True)
        )
        slot = self.slot()
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            editor.set_item_quantity(
                slot, "BombFruit", "Material", 999,
                profile=self.profile, slot_dir=self.game_lock, item_index=2,
            )
        bomb_stacks = [
            item for item in editor.read_inventory(slot.progress_path)
            if item.item_id == "BombFruit"
        ]
        self.assertEqual([item.quantity for item in bomb_stacks], [4, 999])

    def test_rejects_out_of_range_and_invalid_categories_without_writing(self):
        slot = self.slot()
        before = slot.progress_path.read_bytes()
        for quantity in (-1, 1000, True):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                editor.set_item_quantity(
                    slot, "BombFruit", "Material", quantity,
                    profile=self.profile, slot_dir=self.game_lock,
                )
        with self.assertRaises(ValueError):
            editor.set_item_quantity(
                slot, "BombFruit", "KeyItem", 10,
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertEqual(slot.progress_path.read_bytes(), before)
        self.assertFalse(self.backup_root.exists())

    def test_refuses_when_game_holds_the_shared_lock(self):
        slot = self.slot()
        self.game_lock.mkdir()
        with (self.game_lock / "lock").open("w") as stream:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "游戏正在运行"):
                editor.set_item_quantity(
                    slot, "BombFruit", "Material", 999,
                    profile=self.profile, slot_dir=self.game_lock,
                )
        self.assertEqual(
            hashlib.sha256(slot.progress_path.read_bytes()).hexdigest(),
            slot.digest,
        )

    def test_refuses_stale_save_snapshot(self):
        slot = self.slot()
        data = bytearray(slot.progress_path.read_bytes())
        data[-1] ^= 0x01
        slot.progress_path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "发生了变化"):
            editor.set_item_quantity(
                slot, "BombFruit", "Material", 999,
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertFalse(self.backup_root.exists())

    def test_ignores_temporary_pouch(self):
        slot = self.slot()
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.set_item_quantity(
                slot, "NormalArrow", "Arrow", 37,
                profile=self.profile, slot_dir=self.game_lock,
            )
        self.assertTrue(result["changed"])
        updated = slot.progress_path.read_bytes()
        fields = editor._parse_field_table(updated)
        offset, _ = editor._array_field(
            updated, fields, "Pouch.Arrow.Content.StockNum", 3, 4
        )
        self.assertEqual(struct.unpack_from("<ii", updated, offset), (37, -1))


if __name__ == "__main__":
    unittest.main()
