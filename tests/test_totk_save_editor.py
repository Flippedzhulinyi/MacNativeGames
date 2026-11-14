import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "games/totk/scripts"))
import save_editor_core as editor


def build_progress(duplicate_item=False, lightroots=False, extras=False):
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
    if extras:
        devices = [editor.DEVICE_IDS[0]] + [""] * 59
        arrays.extend([
            (3, "Pouch.SpecialParts.Content.StockNum", [3] + [-1] * 59),
            (3, "Pouch.SpecialParts.Content.UseOrder", [-1] * 60),
            (17, "Pouch.SpecialParts.Content.Name", devices),
            (3, "Pouch.KeyItem.Content.StockNum", [5, 6, -1, -1]),
            (17, "Pouch.KeyItem.Content.Name",
             ["Energy_Material_01", "Obj_KorokNuts", "", ""]),
            (1, "AutoBuilder.Draft.Content.IsFavorite", [0] * 30),
            (3, "AutoBuilder.Draft.Content.Index", [-1] * 30),
            (11, "AutoBuilder.Draft.Content.CameraPos", [(0.0, 0.0, 0.0)] * 30),
            (11, "AutoBuilder.Draft.Content.CameraAt", [(0.0, 0.0, 0.0)] * 30),
            (19, "AutoBuilder.Draft.Content.CombinedActorInfo", [bytes(6688)] * 30),
        ])
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
    entries = []
    current_type = -1
    all_fields = [(kind, name) for kind, name, _ in arrays]
    all_fields.append((2, editor._RUPEE_FIELD))
    for kind, name in sorted(all_fields, key=lambda array: array[0]):
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
        elif kind == 1:
            payload.extend(struct.pack("<I", sum(v << i for i, v in enumerate(contents))))
        elif kind == 11:
            for value in contents:
                payload.extend(struct.pack("<3f", *value))
        elif kind == 19:
            for value in contents:
                payload.extend(struct.pack("<I", len(value)) + value)
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

    def test_key_item_limits_and_material_special_maximum(self):
        progress = self.slot_dir / "progress.sav"
        progress.write_bytes(build_progress(extras=True))
        key_items = editor.read_extra_items(progress, "KeyItem")
        self.assertEqual([(i.item_id, i.maximum) for i in key_items],
                         [("Energy_Material_01", 999999), ("Obj_KorokNuts", 1000)])
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            editor.set_item_quantity(self.slot(), "Obj_KorokNuts", "KeyItem", 1000,
                                     profile=self.profile, slot_dir=self.game_lock)
            editor.set_item_quantity(self.slot(), "Energy_Material_01", "KeyItem", 999999,
                                     profile=self.profile, slot_dir=self.game_lock)
        for item, value in (("Obj_KorokNuts", 1001), ("Energy_Material_01", 1000000),
                            ("Parasail", 1)):
            with self.subTest(item=item), self.assertRaises(ValueError):
                editor.set_item_quantity(self.slot(), item, "KeyItem", value,
                                         profile=self.profile, slot_dir=self.game_lock)
        data = bytearray(progress.read_bytes())
        names, stocks, _ = editor._inventory_layout(data)["Material"]
        data[names:names + 64] = b"Item_Ore_L".ljust(64, b"\0")
        struct.pack_into("<i", data, stocks, 1001)
        progress.write_bytes(data)
        self.assertEqual(editor.read_inventory(progress)[1].maximum, 999999)
        self.assertTrue(editor.discover_saves(self.profile))

    def test_complete_devices_preserves_other_data_and_backup(self):
        progress = self.slot_dir / "progress.sav"
        original = build_progress(extras=True)
        progress.write_bytes(original)
        layout = editor._extra_pouch_layout(original, "SpecialParts")
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.complete_devices(self.slot(), profile=self.profile,
                                             slot_dir=self.game_lock)
        self.assertEqual(result["added"], 26)
        self.assertEqual((result["backup"] / "progress.sav").read_bytes(), original)
        devices = editor.read_extra_items(progress, "SpecialParts")
        self.assertEqual({i.item_id for i in devices}, set(editor.DEVICE_IDS))
        self.assertTrue(all(i.quantity == 999 for i in devices))
        after = bytearray(progress.read_bytes())
        names, stocks, count, orders = layout
        for i in range(count):
            after[names + 64*i:names + 64*(i+1)] = original[names + 64*i:names + 64*(i+1)]
            after[stocks + 4*i:stocks + 4*(i+1)] = original[stocks + 4*i:stocks + 4*(i+1)]
            after[orders + 4*i:orders + 4*(i+1)] = original[orders + 4*i:orders + 4*(i+1)]
        self.assertEqual(bytes(after), original)
        self.assertFalse(editor.complete_devices(
            self.slot(), profile=self.profile, slot_dir=self.game_lock)["changed"])

    def test_devices_refuse_unknown_duplicate_insufficient_and_stale(self):
        progress = self.slot_dir / "progress.sav"
        original = build_progress(extras=True)
        names, stocks, count, orders = editor._extra_pouch_layout(original, "SpecialParts")
        for case in ("unknown", "duplicate", "insufficient"):
            data = bytearray(original)
            if case == "unknown":
                data[names:names+64] = b"SpObj_unknown".ljust(64, b"\0")
            elif case == "duplicate":
                data[names+64:names+128] = editor.DEVICE_IDS[0].encode().ljust(64, b"\0")
                struct.pack_into("<i", data, stocks + 4, 1)
            else:
                for i in range(1, count):
                    struct.pack_into("<i", data, orders + 4*i, 123)
            progress.write_bytes(data)
            with self.subTest(case=case), self.assertRaises(ValueError):
                editor.complete_devices(self.slot(), profile=self.profile, slot_dir=self.game_lock)
            self.assertEqual(progress.read_bytes(), bytes(data))
        progress.write_bytes(original)
        slot = self.slot()
        progress.write_bytes(original + b"x")
        with self.assertRaisesRegex(ValueError, "发生了变化"):
            editor.complete_devices(slot, profile=self.profile, slot_dir=self.game_lock)
        self.assertFalse(self.backup_root.exists())

    def test_import_blueprint_checks_favorite_space_and_payload(self):
        progress = self.slot_dir / "progress.sav"
        original = build_progress(extras=True)
        progress.write_bytes(original)
        payload = b"CmbAct" + bytes(6688 - 6) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}):
            with mock.patch.object(editor, "DATA_DIR", self.backup_root):
                result = editor.import_blueprint(self.slot(), "test", payload,
                                                 profile=self.profile, slot_dir=self.game_lock)
            self.assertEqual(result["index"], 0)
            self.assertEqual((result["backup"] / "progress.sav").read_bytes(), original)
            data = progress.read_bytes()
            indices, camera, target, favorite, blobs, _ = editor._blueprint_layout(data)
            self.assertEqual(struct.unpack_from("<i", data, indices)[0], 0)
            self.assertEqual(editor._read_u32(data, favorite), 1)
            self.assertEqual(data[blobs+4:blobs+4+6688], payload[:6688])
            self.assertEqual(data[camera:camera+12], payload[6688:6700])
            self.assertEqual(data[target:target+12], payload[6700:6712])
            with self.assertRaisesRegex(ValueError, "校验失败"):
                editor.import_blueprint(self.slot(), "test", payload[:-1],
                                        profile=self.profile, slot_dir=self.game_lock)
            full = bytearray(original)
            struct.pack_into("<30i", full, indices, *range(30))
            progress.write_bytes(full)
            with self.assertRaisesRegex(ValueError, "必须确认"):
                editor.import_blueprint(self.slot(), "test", payload,
                                        profile=self.profile, slot_dir=self.game_lock)
            self.assertEqual(progress.read_bytes(), bytes(full))
            full = bytearray(original)
            struct.pack_into("<I", full, favorite, 255)
            progress.write_bytes(full)
            with self.assertRaisesRegex(ValueError, "收藏已满"):
                editor.import_blueprint(self.slot(), "test", payload,
                                        profile=self.profile, slot_dir=self.game_lock)

    def test_blueprint_overwrite_uses_history_order_and_preserves_other_records(self):
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, camera, target, favorite, blobs, _ = editor._blueprint_layout(original)
        order = list(range(6, -1, -1)) + list(range(29, 6, -1))
        struct.pack_into("<30i", original, indices, *order)
        struct.pack_into("<I", original, favorite, (1 << order.index(29)) | (1 << order.index(28)))
        for i in range(30):
            original[blobs + i * 6692 + 4:blobs + i * 6692 + 6688 + 4] = bytes([i + 1]) * 6688
        progress.write_bytes(original)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}), \
                mock.patch.object(editor, "DATA_DIR", self.backup_root):
            slot = self.slot()
            selected = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
            self.assertEqual((selected.slot_index, selected.history_index), (order.index(27), 27))
            with self.assertRaisesRegex(ValueError, "必须确认"):
                editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock)
            wrong = editor.BlueprintTarget(order.index(26), 26, slot.digest)
            with self.assertRaisesRegex(ValueError, "重新确认"):
                editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock, wrong)
            self.assertEqual(progress.read_bytes(), bytes(original))
            result = editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock, selected)
            self.assertEqual(result["replaced_history_index"], 27)
            self.assertEqual((result["backup"] / "progress.sav").read_bytes(), bytes(original))
            expected = bytearray(original)
            i = selected.slot_index
            struct.pack_into("<I", expected, favorite, editor._read_u32(original, favorite) | (1 << i))
            expected[blobs + i * 6692 + 4:blobs + i * 6692 + 6692] = payload[:6688]
            expected[camera + i * 12:camera + (i + 1) * 12] = payload[6688:6700]
            expected[target + i * 12:target + (i + 1) * 12] = payload[6700:6712]
            self.assertEqual(progress.read_bytes(), bytes(expected))
            slot = self.slot()
            next_target = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
            self.assertEqual(next_target.history_index, 26)
            editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock, next_target)
            self.assertEqual(editor.preview_blueprint_target(
                self.slot(), self.profile, self.game_lock).history_index, 25)
            self.assertEqual(len(list(result["backup"].parent.iterdir())), 1)

    def test_blueprint_target_validation_and_stale_confirmation(self):
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, _, _, favorite, _, _ = editor._blueprint_layout(original)
        values = list(range(30))
        values[4] = -1
        struct.pack_into("<30i", original, indices, *values)
        progress.write_bytes(original)
        slot = self.slot()
        selected = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
        self.assertEqual((selected.slot_index, selected.history_index), (4, None))
        for case in ("duplicate", "negative", "favorite_empty"):
            data = bytearray(original)
            if case == "duplicate":
                struct.pack_into("<i", data, indices, 1)
            elif case == "negative":
                struct.pack_into("<i", data, indices, -2)
            else:
                struct.pack_into("<I", data, favorite, 1 << 4)
            progress.write_bytes(data)
            with self.subTest(case=case), self.assertRaises(editor.SaveFormatError):
                editor.preview_blueprint_target(self.slot(), self.profile, self.game_lock)
            self.assertEqual(progress.read_bytes(), bytes(data))
        progress.write_bytes(original)
        slot = self.slot()
        selected = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
        progress.write_bytes(original + b"x")
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}):
            with self.assertRaisesRegex(ValueError, "发生了变化"):
                editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock, selected)
            with self.assertRaisesRegex(ValueError, "重新确认"):
                editor.import_blueprint(self.slot(), "test", payload, self.profile, self.game_lock, selected)
        self.assertEqual(progress.read_bytes(), bytes(original) + b"x")
        self.assertFalse(self.backup_root.exists())

    def test_blueprint_preview_and_overwrite_refuse_game_lock(self):
        import fcntl
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, _, _, _, _, _ = editor._blueprint_layout(original)
        struct.pack_into("<30i", original, indices, *range(30))
        progress.write_bytes(original)
        slot = self.slot()
        selected = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}), \
                (self.game_lock / "lock").open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "游戏正在运行"):
                editor.preview_blueprint_target(slot, self.profile, self.game_lock)
            with self.assertRaisesRegex(ValueError, "游戏正在运行"):
                editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock, selected)
        self.assertEqual(progress.read_bytes(), bytes(original))
        self.assertFalse(self.backup_root.exists())

    def test_blueprint_overwrite_restore_on_failed_verification(self):
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, _, _, _, _, _ = editor._blueprint_layout(original)
        struct.pack_into("<30i", original, indices, *range(30))
        progress.write_bytes(original)
        slot = self.slot()
        selected = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        read_bytes = Path.read_bytes
        reads = 0

        def corrupt_verification(path):
            nonlocal reads
            data = read_bytes(path)
            if path.resolve() == progress.resolve():
                reads += 1
                if reads == 2:
                    return data[:-1] + bytes([data[-1] ^ 1])
            return data

        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}), \
                mock.patch.object(editor, "DATA_DIR", self.backup_root), \
                mock.patch.object(Path, "read_bytes", corrupt_verification):
            with self.assertRaisesRegex(OSError, "已从备份恢复"):
                editor.import_blueprint(slot, "test", payload, self.profile, self.game_lock, selected)
        self.assertEqual(progress.read_bytes(), bytes(original))

    def test_blueprint_dialog_confirms_target_before_download(self):
        try:
            import offline_save_editor as gui
        except ModuleNotFoundError as error:
            if error.name == "tkinter":
                self.skipTest("tkinter is not installed")
            raise
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, _, _, _, _, _ = editor._blueprint_layout(original)
        struct.pack_into("<30i", original, indices, *range(30))
        progress.write_bytes(original)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试蓝图", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        app = mock.MagicMock()
        app.selected_slot = self.slot()
        app.offline_verified = True
        app.game_running = False
        app.profile = self.profile
        commands = {}

        def button(frame, text, command, **kwargs):
            commands[text] = command
            return mock.MagicMock()

        app._button.side_effect = button
        variable = mock.MagicMock()
        variable.get.return_value = "测试蓝图"
        real_preview = editor.preview_blueprint_target
        real_import = editor.import_blueprint

        def preview(slot, profile):
            return real_preview(slot, profile, self.game_lock)

        def import_blueprint(slot, blueprint_id, data, profile, target):
            return real_import(slot, blueprint_id, data, profile, self.game_lock, target)

        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}, clear=True), \
                mock.patch.object(editor, "DATA_DIR", self.backup_root), \
                mock.patch.object(editor, "preview_blueprint_target", side_effect=preview), \
                mock.patch.object(editor, "import_blueprint", side_effect=import_blueprint) as importer, \
                mock.patch.object(gui.tk, "Toplevel"), \
                mock.patch.object(gui.tk, "Frame"), \
                mock.patch.object(gui.tk, "Label"), \
                mock.patch.object(gui.tk, "StringVar", return_value=variable), \
                mock.patch.object(gui.ttk, "Combobox"), \
                mock.patch.object(gui, "_show_dialog", side_effect=[False, True, False, False]) as show, \
                mock.patch.object(gui, "urlopen") as download:
            download.return_value.__enter__.return_value.read.return_value = payload
            gui.SaveEditor.open_extra_actions(app)
            add = commands["下载并添加所选蓝图"]
            add()
            self.assertIn("历史编号 30", show.call_args.args[2])
            self.assertIn("连续导入不能逐次撤销", show.call_args.args[2])
            download.assert_not_called()
            importer.assert_not_called()
            self.assertEqual(progress.read_bytes(), bytes(original))
            add()
            download.assert_called_once()
            self.assertEqual(importer.call_args.kwargs["target"].history_index, 29)
            self.assertEqual(struct.unpack_from("<i", progress.read_bytes(), indices + 29 * 4)[0], 29)
            self.assertNotEqual(progress.read_bytes(), bytes(original))

    def test_local_blueprint_validation_and_import(self):
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, camera, target, favorite, blobs, _ = editor._blueprint_layout(original)
        struct.pack_into("<30i", original, indices, *range(30))
        struct.pack_into("<I", original, favorite, 1 << 29)
        progress.write_bytes(original)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        slot = self.slot()
        selected = editor.preview_blueprint_target(slot, self.profile, self.game_lock)
        self.assertEqual(selected.history_index, 28)
        invalid = (
            payload[:-1], payload + b"x", b"BadAct" + payload[6:],
            payload[:6688] + struct.pack("<6f", float("nan"), 2, 3, 4, 5, 6),
            payload[:6688] + struct.pack("<6f", 1, float("inf"), 3, 4, 5, 6),
        )
        for data in invalid:
            with self.subTest(length=len(data), header=data[:6]), self.assertRaises(ValueError):
                editor.import_local_blueprint(slot, data, self.profile, self.game_lock, selected)
            self.assertEqual(progress.read_bytes(), bytes(original))
        with self.assertRaisesRegex(ValueError, "必须确认"):
            editor.import_local_blueprint(slot, payload, self.profile, self.game_lock)
        self.assertFalse(self.backup_root.exists())
        with mock.patch.object(editor, "DATA_DIR", self.backup_root):
            result = editor.import_local_blueprint(slot, payload, self.profile, self.game_lock, selected)
        expected = bytearray(original)
        i = selected.slot_index
        struct.pack_into("<I", expected, favorite, (1 << 29) | (1 << i))
        expected[blobs + i * 6692 + 4:blobs + i * 6692 + 6692] = payload[:6688]
        expected[camera + i * 12:camera + (i + 1) * 12] = payload[6688:6700]
        expected[target + i * 12:target + (i + 1) * 12] = payload[6700:6712]
        self.assertEqual(progress.read_bytes(), bytes(expected))
        self.assertEqual((result["backup"] / "progress.sav").read_bytes(), bytes(original))

    def test_local_blueprint_dialog_selection_confirmation_and_import(self):
        try:
            import offline_save_editor as gui
        except ModuleNotFoundError as error:
            if error.name == "tkinter":
                self.skipTest("tkinter is not installed")
            raise
        progress = self.slot_dir / "progress.sav"
        original = bytearray(build_progress(extras=True))
        indices, _, _, _, _, _ = editor._blueprint_layout(original)
        struct.pack_into("<30i", original, indices, *range(30))
        progress.write_bytes(original)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint_file = self.root / "tank.cai"
        blueprint_file.write_bytes(payload)
        invalid_file = self.root / "invalid.cai"
        invalid_file.write_bytes(payload + b"x")
        cache = self.profile / "cache" / "0"
        (cache / "icon").mkdir(parents=True)
        (cache / "storage").mkdir()
        (cache / "storage" / "CacheStorageInfo.dat").write_bytes(b"metadata")
        app = mock.MagicMock()
        app.selected_slot = self.slot()
        app.offline_verified = True
        app.game_running = False
        app.profile = self.profile
        commands = {}

        def button(frame, text, command, **kwargs):
            commands[text] = command
            return mock.MagicMock()

        app._button.side_effect = button
        real_preview = editor.preview_blueprint_target
        real_import = editor.import_local_blueprint
        real_reset = editor.reset_thumbnail_cache

        def preview(slot, profile):
            return real_preview(slot, profile, self.game_lock)

        def import_local(slot, data, profile, target):
            return real_import(slot, data, profile, self.game_lock, target)

        with mock.patch.object(editor, "DATA_DIR", self.backup_root), \
                mock.patch.object(editor, "preview_blueprint_target", side_effect=preview), \
                mock.patch.object(editor, "import_local_blueprint", side_effect=import_local) as importer, \
                mock.patch.object(editor, "reset_thumbnail_cache",
                                  side_effect=lambda profile: real_reset(profile, self.game_lock)) as reset, \
                mock.patch.object(gui.tk, "Toplevel"), \
                mock.patch.object(gui.tk, "Frame"), \
                mock.patch.object(gui.tk, "Label"), \
                mock.patch.object(gui.tk, "StringVar"), \
                mock.patch.object(gui.ttk, "Combobox"), \
                mock.patch.object(gui.filedialog, "askopenfilename",
                                  side_effect=["", str(self.root / "missing.cai"),
                                               str(invalid_file), str(blueprint_file),
                                               str(blueprint_file)]), \
                mock.patch.object(gui, "_show_dialog",
                                  side_effect=[False, False, False, True, False, True, False]) as show, \
                mock.patch.object(gui, "urlopen") as download:
            gui.SaveEditor.open_extra_actions(app)
            add = commands["导入本地蓝图…"]
            add()
            show.assert_not_called()
            add()
            self.assertEqual(show.call_args.args[1], "蓝图未添加")
            add()
            self.assertIn("格式或长度", show.call_args.args[2])
            self.assertEqual(progress.read_bytes(), bytes(original))
            importer.assert_not_called()
            add()
            self.assertIn("tank.cai", show.call_args.args[2])
            self.assertIn("历史编号 30", show.call_args.args[2])
            self.assertEqual(progress.read_bytes(), bytes(original))
            importer.assert_not_called()
            add()
            self.assertEqual(importer.call_args.kwargs["target"].history_index, 29)
            self.assertEqual(importer.call_args.args[1], payload)
            self.assertNotEqual(progress.read_bytes(), bytes(original))
            download.assert_not_called()
            reset.assert_called_once_with(profile=self.profile)
            self.assertFalse(cache.exists())
            self.assertTrue(list((self.profile / "save-editor-cache-backups").glob("*/cache-0")))

    def test_reset_thumbnail_cache_preserves_all_files_and_save(self):
        cache = self.profile / "cache" / "0"
        (cache / "icon").mkdir(parents=True)
        (cache / "storage").mkdir()
        (cache / "icon" / "Draft_001.png").write_bytes(b"draft")
        (cache / "icon" / "Weapon_001.png").write_bytes(b"weapon")
        (cache / "storage" / "CacheStorageInfo.dat").write_bytes(b"metadata")
        manifest = editor._tree_manifest(cache)
        progress = (self.slot_dir / "progress.sav").read_bytes()
        backup = editor.reset_thumbnail_cache(self.profile, self.game_lock)
        self.assertFalse(cache.exists())
        self.assertEqual(editor._tree_manifest(backup), manifest)
        self.assertEqual((self.slot_dir / "progress.sav").read_bytes(), progress)
        with self.assertRaisesRegex(ValueError, "未找到缓存"):
            editor.reset_thumbnail_cache(self.profile, self.game_lock)
        self.assertEqual(editor._tree_manifest(backup), manifest)

    def test_reset_thumbnail_cache_refuses_lock_symlink_and_invalid_layout(self):
        import fcntl
        cache = self.profile / "cache" / "0"
        (cache / "icon").mkdir(parents=True)
        (cache / "storage").mkdir()
        metadata = cache / "storage" / "CacheStorageInfo.dat"
        metadata.write_bytes(b"metadata")
        manifest = editor._tree_manifest(cache)
        self.game_lock.mkdir()
        with (self.game_lock / "lock").open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "游戏正在运行"):
                editor.reset_thumbnail_cache(self.profile, self.game_lock)
        self.assertEqual(editor._tree_manifest(cache), manifest)
        metadata.unlink()
        with self.assertRaisesRegex(editor.SaveFormatError, "布局"):
            editor.reset_thumbnail_cache(self.profile, self.game_lock)
        metadata.write_bytes(b"metadata")
        (cache / "icon" / "link").symlink_to(metadata)
        with self.assertRaisesRegex(ValueError, "链接"):
            editor.reset_thumbnail_cache(self.profile, self.game_lock)
        self.assertTrue(cache.exists())

    def test_reset_thumbnail_cache_restores_after_verification_failure(self):
        cache = self.profile / "cache" / "0"
        (cache / "icon").mkdir(parents=True)
        (cache / "storage").mkdir()
        (cache / "storage" / "CacheStorageInfo.dat").write_bytes(b"metadata")
        manifest = editor._tree_manifest(cache)
        real_manifest = editor._tree_manifest

        def verify(path):
            if Path(path).name == "cache-0":
                raise OSError("test failure")
            return real_manifest(path)

        with mock.patch.object(editor, "_tree_manifest", side_effect=verify):
            with self.assertRaisesRegex(OSError, "已恢复原缓存"):
                editor.reset_thumbnail_cache(self.profile, self.game_lock)
        self.assertEqual(editor._tree_manifest(cache), manifest)

    def test_thumbnail_reset_dialog_requires_confirmation(self):
        try:
            import offline_save_editor as gui
        except ModuleNotFoundError as error:
            if error.name == "tkinter":
                self.skipTest("tkinter is not installed")
            raise
        cache = self.profile / "cache" / "0"
        (cache / "icon").mkdir(parents=True)
        (cache / "storage").mkdir()
        (cache / "storage" / "CacheStorageInfo.dat").write_bytes(b"metadata")
        app = mock.MagicMock()
        app.selected_slot = self.slot()
        app.offline_verified = True
        app.game_running = False
        app.profile = self.profile
        commands = {}

        def button(frame, text, command, **kwargs):
            commands[text] = command
            return mock.MagicMock()

        app._button.side_effect = button
        reset = editor.reset_thumbnail_cache
        with mock.patch.object(editor, "reset_thumbnail_cache",
                               side_effect=lambda profile: reset(profile, self.game_lock)) as action, \
                mock.patch.object(gui.tk, "Toplevel"), \
                mock.patch.object(gui.tk, "Frame"), \
                mock.patch.object(gui.tk, "Label"), \
                mock.patch.object(gui.tk, "StringVar"), \
                mock.patch.object(gui.ttk, "Combobox"), \
                mock.patch.object(gui, "_show_dialog", side_effect=[False, True, False]) as show:
            gui.SaveEditor.open_extra_actions(app)
            execute = commands["重建缩略图缓存…"]
            execute()
            self.assertIn("所有存档", show.call_args.args[2])
            action.assert_not_called()
            self.assertTrue(cache.exists())
            execute()
            action.assert_called_once_with(profile=self.profile)
            self.assertFalse(cache.exists())
            self.assertEqual(show.call_args.args[1], "缩略图缓存已重置")

    def test_new_actions_refuse_game_lock_and_restore_failed_verification(self):
        import fcntl
        progress = self.slot_dir / "progress.sav"
        original = build_progress(extras=True)
        progress.write_bytes(original)
        payload = b"CmbAct" + bytes(6682) + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        blueprint = ("测试", "https://example.invalid", hashlib.sha256(payload).hexdigest())
        self.game_lock.mkdir()
        with mock.patch.dict(editor.BLUEPRINTS, {"test": blueprint}):
            slot = self.slot()
            actions = (
                lambda: editor.complete_devices(slot, profile=self.profile, slot_dir=self.game_lock),
                lambda: editor.import_blueprint(slot, "test", payload,
                                                profile=self.profile, slot_dir=self.game_lock),
                lambda: editor.import_local_blueprint(slot, payload,
                                                      profile=self.profile, slot_dir=self.game_lock),
                lambda: editor.set_item_quantity(slot, "Obj_KorokNuts", "KeyItem", 1000,
                                                 profile=self.profile, slot_dir=self.game_lock),
            )
            with (self.game_lock / "lock").open("w") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                for action in actions:
                    with self.assertRaisesRegex(ValueError, "游戏正在运行"):
                        action()
            self.assertEqual(progress.read_bytes(), original)
            self.assertFalse(self.backup_root.exists())
            for action in actions:
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
                        action()
                self.assertEqual(progress.read_bytes(), original)

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
