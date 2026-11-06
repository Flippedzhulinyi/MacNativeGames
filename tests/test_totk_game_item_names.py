import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "games/totk/scripts"))
import game_item_names
import save_editor_core


def build_msbt(entries):
    label_data = bytearray(struct.pack("<III", 1, len(entries), 12))
    text_data = bytearray(struct.pack("<I", len(entries)) + b"\0" * (4 * len(entries)))
    for index, (label, text) in enumerate(entries):
        encoded = label.encode("utf-8")
        label_data.extend(bytes([len(encoded)]) + encoded + struct.pack("<I", index))
        struct.pack_into("<I", text_data, 4 + 4 * index, len(text_data))
        text_data.extend(text.encode("utf-16le") + b"\0\0")

    def section(kind, data):
        result = kind + struct.pack("<I", len(data)) + b"\0" * 8 + data
        return result + b"\0" * (-len(result) % 16)

    sections = section(b"LBL1", label_data) + section(b"TXT2", text_data)
    header = bytearray(32)
    header[:10] = b"MsgStdBn\xff\xfe"
    header[12] = 1
    struct.pack_into("<H", header, 14, 2)
    struct.pack_into("<I", header, 18, len(header) + len(sections))
    return bytes(header) + sections


class GameItemNamesTest(unittest.TestCase):
    def test_extracts_names_and_ignores_descriptions_and_control_codes(self):
        data = build_msbt([
            ("Animal_Insect_B_Name", "毅力青蛙"),
            ("Item_Enemy_121_Name", "吉波得的肝脏"),
            ("Item_Enemy_121_Caption", "描述"),
            ("NotAnItem_Name", "\x0e控制"),
            ("Empty_Name", ""),
        ])
        self.assertEqual(game_item_names.parse_item_names(data), {
            "Animal_Insect_B": "毅力青蛙",
            "Item_Enemy_121": "吉波得的肝脏",
        })

    def test_rejects_truncated_or_malformed_data(self):
        valid = build_msbt([("BeeHome_Name", "精力蜂的蜂蜜")])
        for data in (valid[:-1], b"not an msbt", valid[:32] + b"\0" * (len(valid) - 32)):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                game_item_names.parse_item_names(data)

    def test_rejects_bad_label_and_text_offsets(self):
        valid = build_msbt([("BeeHome_Name", "精力蜂的蜂蜜")])
        for offset in (32 + 16 + 8, 32 + 16 + 12 + 1 + len("BeeHome_Name")):
            data = bytearray(valid)
            struct.pack_into("<I", data, offset, 0xFFFFFFFF)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                game_item_names.parse_item_names(bytes(data))

    def test_game_names_update_inventory_labels_and_keep_unknown_fallback(self):
        self.addCleanup(save_editor_core.set_game_item_names, {})
        save_editor_core.set_game_item_names({
            "Item_Enemy_121": "吉波得的肝脏", "NormalArrow": "木箭",
        })
        item = save_editor_core.InventoryItem("Item_Enemy_121", "Material", 0, 2)
        self.assertEqual(item.label, "吉波得的肝脏 · 素材 · 2/999")
        self.assertIn("炸弹花", save_editor_core.InventoryItem("BombFruit", "Material", 1, 1).label)
        self.assertIn("普通箭", save_editor_core.InventoryItem("NormalArrow", "Arrow", 0, 1).label)
        self.assertIn("未收录名称", save_editor_core.InventoryItem("Unknown", "Material", 2, 1).label)
        save_editor_core.set_game_item_names({})
        self.assertIn("未收录名称", item.label)


if __name__ == "__main__":
    unittest.main()
