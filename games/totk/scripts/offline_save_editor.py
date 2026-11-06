#!/usr/bin/env python3
"""A small native macOS window for offline edits to existing TOTK item stacks."""

import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import save_editor_core as core
from game_item_names import read_game_item_names


_CATEGORY_TO_STORAGE = {
    "素材": "Material",
    "箭": "Arrow",
    "武器": "Weapon",
    "盾牌": "Shield",
    "弓": "Bow",
    "卢比": "Rupee",
}

BG = "#F2F5F3"
CARD = "#FFFFFF"
INK = "#17221C"
MUTED = "#65736A"
GREEN = "#18794E"
GREEN_DARK = "#12613D"
LINE = "#E1E8E3"
PALE_GREEN = "#E6F3EB"
AMBER = "#FFF4DE"
NAME_SOURCE_CONFIG = core.DATA_DIR / "save-editor-romfs-path.txt"


def _show_dialog(parent, title, message, confirm=False, warning=False):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent.winfo_toplevel())
    dialog.resizable(False, False)
    dialog.configure(bg=BG)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    frame = tk.Frame(dialog, bg=CARD, padx=22, pady=20)
    frame.pack(fill="both", expand=True, padx=12, pady=12)
    color = "#76530B" if warning else INK
    tk.Label(
        frame, text=title, bg=CARD, fg=color,
        font=("SF Pro Display", 15, "bold"),
    ).pack(anchor="w")
    tk.Label(
        frame, text=message, bg=CARD, fg=INK,
        font=("SF Pro Text", 10), justify="left", wraplength=500,
    ).pack(fill="x", anchor="w", pady=(12, 18))
    buttons = tk.Frame(frame, bg=CARD)
    buttons.pack(fill="x")
    result = {"confirmed": False}

    def close(accepted=False):
        result["confirmed"] = accepted
        dialog.destroy()

    if confirm:
        tk.Button(
            buttons, text="取消", command=close, bg=PALE_GREEN, fg=GREEN_DARK,
            activebackground="#D9EADF", relief="flat", borderwidth=0,
            padx=14, pady=8, font=("SF Pro Text", 10, "bold"),
        ).pack(side="right")
        accept = tk.Button(
            buttons, text="继续", command=lambda: close(True), bg=GREEN,
            fg="white", activebackground=GREEN_DARK, relief="flat",
            borderwidth=0, padx=16, pady=8,
            font=("SF Pro Text", 10, "bold"),
        )
        accept.pack(side="right", padx=(0, 8))
        accept.focus_set()
        dialog.bind("<Return>", lambda _event: close(True))
        dialog.bind("<Escape>", lambda _event: close())
    else:
        done = tk.Button(
            buttons, text="确定", command=close, bg=GREEN, fg="white",
            activebackground=GREEN_DARK, relief="flat", borderwidth=0,
            padx=16, pady=8, font=("SF Pro Text", 10, "bold"),
        )
        done.pack(side="right")
        done.focus_set()
        dialog.bind("<Return>", lambda _event: close())
        dialog.bind("<Escape>", lambda _event: close())

    dialog.update_idletasks()
    parent_window = parent.winfo_toplevel()
    x = parent_window.winfo_rootx() + (
        parent_window.winfo_width() - dialog.winfo_reqwidth()
    ) // 2
    y = parent_window.winfo_rooty() + (
        parent_window.winfo_height() - dialog.winfo_reqheight()
    ) // 2
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    dialog.grab_set()
    dialog.wait_window()
    if parent_window.winfo_exists() and parent_window.winfo_viewable():
        parent_window.grab_set()
    return result["confirmed"]


class SaveEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("TOTK 离线存档修改器")
        self.root.geometry("980x790")
        self.root.minsize(900, 740)
        self.root.configure(bg=BG)
        self._center_window()
        self.profile = core.DEFAULT_PROFILE
        self.slots = []
        self.items = []
        self.selected_slot = None
        self.selected_item = None
        self.slot_by_label = {}
        self.item_by_label = {}
        self.game_running = False
        self.offline_verified = False

        self._configure_style()
        self._build()
        self.refresh_saves()
        self.load_game_names()
        self.root.after(200, self.check_game_status)

    def _configure_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TCombobox", padding=(12, 9), fieldbackground=CARD,
                        background=CARD, foreground=INK, arrowcolor=GREEN,
                        font=("SF Pro Text", 11))
        style.map("TCombobox", fieldbackground=[("readonly", CARD)],
                  foreground=[("readonly", INK)])
        style.configure("TSpinbox", padding=(9, 7), fieldbackground=CARD,
                        foreground=INK, arrowsize=13,
                        font=("SF Pro Text", 12))
        style.configure("Green.Horizontal.TProgressbar",
                        troughcolor=PALE_GREEN, background=GREEN,
                        bordercolor=PALE_GREEN, lightcolor=GREEN,
                        darkcolor=GREEN, thickness=9)

    def _center_window(self):
        self.root.update_idletasks()
        width, height = 980, 790
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self):
        header = tk.Frame(self.root, bg="#143D2B", height=148)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="HYRULE FIELD TOOLS     /     MAC", bg="#143D2B",
                 fg="#9AD7B3", font=("SF Pro Text", 9, "bold")).pack(
                     anchor="w", padx=38, pady=(22, 8))
        title_row = tk.Frame(header, bg="#143D2B")
        title_row.pack(fill="x", padx=38)
        tk.Label(title_row, text="离线存档修改器", bg="#143D2B", fg="white",
                 font=("SF Pro Display", 26, "bold")).pack(side="left")
        self.game_badge = tk.Label(
            title_row, text="●  正在检查游戏状态", bg="#24543D", fg="#D7F2E2",
            font=("SF Pro Text", 10, "bold"), padx=15, pady=9,
        )
        self.game_badge.pack(side="right", pady=4)
        tk.Label(
            header,
            text="只处理本机存档     ·     退出游戏后修改     ·     修改前自动备份",
            bg="#143D2B", fg="#C0D9C9", font=("SF Pro Text", 11),
        ).pack(anchor="w", padx=38, pady=(8, 0))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=36, pady=(15, 10))

        self._section_heading(body, "01", "选择存档",
                              "按游戏内保存位置和保存时间识别，不只显示槽位编号")
        save_card = self._card(body)
        row = tk.Frame(save_card, bg=CARD)
        row.pack(fill="x")
        self.save_var = tk.StringVar()
        self.save_combo = ttk.Combobox(
            row, textvariable=self.save_var, state="readonly", width=58
        )
        self.save_combo.pack(side="left", fill="x", expand=True)
        self.save_combo.bind("<<ComboboxSelected>>", self.on_save_selected)
        self.refresh_button = self._button(
            row, "重新扫描", self.refresh_saves, secondary=True
        )
        self.refresh_button.pack(side="left", padx=(10, 0))
        self.profile_button = self._button(
            row, "选择资料夹…", self.choose_profile, secondary=True
        )
        self.profile_button.pack(side="left", padx=(8, 0))
        self.profile_label = tk.Label(
            save_card, text="", bg=CARD, fg=MUTED,
            font=("SF Pro Text", 9), anchor="w",
        )
        self.profile_label.pack(fill="x", pady=(10, 0))
        names_row = tk.Frame(save_card, bg=CARD)
        names_row.pack(fill="x", pady=(8, 0))
        self.names_label = tk.Label(
            names_row, text="游戏素材名称：尚未加载", bg=CARD, fg=MUTED,
            font=("SF Pro Text", 9), anchor="w",
        )
        self.names_label.pack(side="left", fill="x", expand=True)
        self._button(
            names_row, "选择游戏名称数据…", self.choose_game_names, secondary=True
        ).pack(side="right")
        details_row = tk.Frame(save_card, bg=CARD)
        details_row.pack(fill="x", pady=(12, 0))
        self.save_details = tk.Label(
            details_row, text="正在扫描存档…", bg=PALE_GREEN, fg=GREEN_DARK,
            font=("SF Pro Text", 10), anchor="w", padx=12, pady=10,
        )
        self.save_details.pack(side="left", fill="x", expand=True)
        self.lightroots_button = self._button(
            details_row, "激活全部灯根…", self.activate_lightroots, secondary=True
        )
        self.lightroots_button.pack(side="left", padx=(8, 0))
        self.lightroots_button.configure(state="disabled")

        self._section_heading(body, "02", "选择物品或装备",
                              "编辑物品、卢比数量或已有装备耐久")
        inventory_card = self._card(body)
        inventory_row = tk.Frame(inventory_card, bg=CARD)
        inventory_row.pack(fill="x")

        tk.Label(inventory_row, text="类别", bg=CARD, fg=MUTED,
                 font=("SF Pro Text", 10, "bold")).grid(
                     row=0, column=0, sticky="w", padx=(0, 9))
        self.category_var = tk.StringVar(value="素材")
        self.category_combo = ttk.Combobox(
            inventory_row, textvariable=self.category_var, state="readonly",
            values=tuple(_CATEGORY_TO_STORAGE), width=12,
        )
        self.category_combo.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.category_combo.bind("<<ComboboxSelected>>", self.on_category_changed)

        tk.Label(inventory_row, text="物品", bg=CARD, fg=MUTED,
                 font=("SF Pro Text", 10, "bold")).grid(
                     row=0, column=2, sticky="w", padx=(0, 9))
        self.item_var = tk.StringVar()
        self.item_combo = ttk.Combobox(
            inventory_row, textvariable=self.item_var, state="readonly", width=42
        )
        self.item_combo.grid(row=0, column=3, sticky="ew")
        self.item_combo.bind("<<ComboboxSelected>>", self.on_item_selected)
        inventory_row.columnconfigure(3, weight=1)

        quantity_row = tk.Frame(inventory_card, bg=CARD)
        quantity_row.pack(fill="x", pady=(20, 0))
        self.quantity_title = tk.Label(
            quantity_row, text="设置数量", bg=CARD, fg=INK,
            font=("SF Pro Text", 12, "bold"),
        )
        self.quantity_title.pack(side="left")
        self.quantity_var = tk.StringVar()
        self.quantity_spin = ttk.Spinbox(
            quantity_row, from_=0, to=core.MAX_STACK, increment=1,
            textvariable=self.quantity_var, width=9, justify="center",
        )
        self.quantity_spin.pack(side="left", padx=(14, 8))
        self.maximum_label = tk.Label(
            quantity_row, text=f"上限 {core.MAX_STACK}", bg=CARD, fg=MUTED,
            font=("SF Pro Text", 10),
        )
        self.maximum_label.pack(side="left")
        self.maximum_button = self._button(
            quantity_row, "设为上限", self.set_to_maximum, secondary=True
        )
        self.maximum_button.pack(side="left", padx=(10, 0))
        self.maximum_button.configure(state="disabled")
        self.current_label = tk.Label(
            quantity_row, text="", bg=CARD, fg=MUTED,
            font=("SF Pro Text", 10), anchor="e",
        )
        self.current_label.pack(side="right")

        self.limit_bar = ttk.Progressbar(
            inventory_card, maximum=core.MAX_STACK,
            style="Green.Horizontal.TProgressbar",
        )
        self.limit_bar.pack(fill="x", pady=(14, 0))
        self.limit_note = tk.Label(
            inventory_card,
            text="物品数量范围 0–999；装备耐久按各自上限     ·     修改前备份整个存档槽",
            bg=CARD, fg=MUTED, font=("SF Pro Text", 9), anchor="w",
        )
        self.limit_note.pack(fill="x", pady=(8, 0))

        bottom = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                          highlightthickness=1, padx=16, pady=13)
        bottom.pack(fill="x", pady=(0, 0))
        self.status_var = tk.StringVar(
            value="请选择一个存档和物品。修改会写入所选存档，之后启动游戏即可读取。"
        )
        self.status_label = tk.Label(
            bottom, textvariable=self.status_var, bg=CARD, fg=MUTED,
            font=("SF Pro Text", 10), anchor="w", justify="left", wraplength=610,
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=(2, 14))
        self.apply_button = self._button(
            bottom, "备份并应用修改", self.apply_change, primary=True
        )
        self.apply_button.pack(side="right")
        self.apply_button.configure(state="disabled")
        self.add_equipment_button = self._button(
            bottom, "添加新装备…", self.open_add_equipment_dialog, secondary=True
        )
        self.add_equipment_button.pack(side="right", padx=(0, 9))
        self.add_equipment_button.configure(state="disabled")

        tk.Label(
            self.root,
            text="安全修改     ·     编辑物品、卢比与装备耐久     ·     每个存档槽仅保留最新备份",
            bg=BG, fg=MUTED, font=("SF Pro Text", 9),
        ).pack(anchor="w", padx=38, pady=(0, 15))

    def _section_heading(self, parent, number, title, subtitle):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 9))
        tk.Label(
            row, text=number, bg=PALE_GREEN, fg=GREEN_DARK,
            font=("SF Pro Text", 9, "bold"), padx=8, pady=4,
        ).pack(side="left", padx=(1, 11))
        tk.Label(row, text=title, bg=BG, fg=INK,
                 font=("SF Pro Display", 15, "bold")).pack(side="left")
        tk.Label(row, text=subtitle, bg=BG, fg=MUTED,
                 font=("SF Pro Text", 9)).pack(side="left", padx=(12, 0), pady=(3, 0))

    @staticmethod
    def _card(parent):
        frame = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                         highlightthickness=1, padx=18, pady=16)
        frame.pack(fill="x", pady=(0, 22))
        return frame

    @staticmethod
    def _button(parent, text, command, primary=False, secondary=False):
        if primary:
            button = tk.Button(
                parent, text=text, command=command, bg=GREEN, fg="white",
                activebackground=GREEN_DARK, activeforeground="white",
                disabledforeground="#DCE8E0", relief="flat", borderwidth=0,
                padx=19, pady=11, font=("SF Pro Text", 10, "bold"),
                cursor="pointinghand",
            )
        else:
            button = tk.Button(
                parent, text=text, command=command, bg=PALE_GREEN if secondary else CARD,
                fg=GREEN_DARK if secondary else INK, activebackground="#D9EADF",
                activeforeground=GREEN_DARK, relief="flat", borderwidth=0,
                padx=12, pady=9, font=("SF Pro Text", 9, "bold"),
                cursor="pointinghand",
            )
        return button

    def refresh_saves(self):
        previous = self.selected_slot.slot_id if self.selected_slot else None
        try:
            self.slots = core.discover_saves(self.profile)
        except (OSError, ValueError) as error:
            self.slots = []
            self.status_var.set(f"扫描失败：{error}")
        labels = []
        seen = set()
        for index, slot in enumerate(self.slots):
            label = slot.label
            if index == 0:
                label = f"最新保存  ·  {label}"
            if label in seen:
                label += f"  ·  存档 {slot.slot_id[-2:]}"
            seen.add(label)
            labels.append(label)
        self.slot_by_label = dict(zip(labels, self.slots))
        self.save_combo.configure(values=tuple(labels))
        self.profile_label.configure(text=f"存档资料夹：{self.profile}")
        if not self.slots:
            self.selected_slot = None
            self.save_var.set("")
            self.save_details.configure(
                text="没有找到可修改的存档。请选择正确的 TOTK profile 资料夹。",
                bg=AMBER, fg="#76530B",
            )
            self._set_inventory_enabled(False)
            self._update_apply_state()
            return
        selected = next(
            (slot for slot in self.slots if slot.slot_id == previous),
            self.slots[0],
        )
        self.save_var.set(labels[self.slots.index(selected)])
        self.on_save_selected()

    def choose_profile(self):
        selected = filedialog.askdirectory(
            parent=self.root, title="选择 TOTK profile（包含 save 资料夹）",
            initialdir=str(self.profile.parent),
        )
        if selected:
            self.profile = Path(selected)
            self.selected_slot = None
            self.refresh_saves()

    def load_game_names(self, romfs=None, remember=False):
        if romfs is None:
            if NAME_SOURCE_CONFIG.is_file():
                try:
                    romfs = Path(NAME_SOURCE_CONFIG.read_text(encoding="utf-8").strip())
                except (OSError, UnicodeError) as error:
                    self.names_label.configure(text=f"游戏名称配置读取失败：{error}", fg="#76530B")
                    return
            else:
                extracted = Path.home() / "Documents/Games/TOTK_build/totk/extracted"
                preferred = extracted / "v143" / "romfs"
                candidates = ([preferred] if preferred.is_dir() else
                              sorted(extracted.glob("v*/romfs")))
                if len(candidates) != 1:
                    self.names_label.configure(
                        text="游戏名称未加载：请点击右侧按钮选择 romfs 资料夹。",
                        fg="#76530B",
                    )
                    return
                romfs = candidates[0]
        try:
            names = read_game_item_names(romfs)
            if remember:
                NAME_SOURCE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
                NAME_SOURCE_CONFIG.write_text(str(Path(romfs).resolve()), encoding="utf-8")
        except (OSError, ValueError) as error:
            self.names_label.configure(
                text=f"游戏名称加载失败：{error}", fg="#76530B",
            )
            if remember:
                _show_dialog(self.root, "无法加载游戏名称", str(error))
            return
        core.set_game_item_names(names)
        self.names_label.configure(text=f"游戏素材名称已加载：{len(names)} 条", fg=GREEN_DARK)
        if self.selected_slot:
            self.load_items()

    def choose_game_names(self):
        selected = filedialog.askdirectory(
            parent=self.root,
            title="选择包含 index.json 和 romfs.bin 的 TOTK romfs 资料夹",
            initialdir=str(Path.home() / "Documents"),
        )
        if selected:
            self.load_game_names(Path(selected), remember=True)

    def on_save_selected(self, _event=None):
        self.selected_slot = self.slot_by_label.get(self.save_var.get())
        self.selected_item = None
        self.item_var.set("")
        self.quantity_var.set("")
        self.current_label.configure(text="")
        if not self.selected_slot:
            self._set_inventory_enabled(False)
            self._update_apply_state()
            return
        saved = self.selected_slot
        self.save_details.configure(
            text=f"游戏内保存位置：{saved.display_name}     ·     槽位 {saved.slot_id[-2:]}     ·     "
                 f"{Path(saved.progress_path).stat().st_size:,} bytes",
            bg=PALE_GREEN, fg=GREEN_DARK,
        )
        self.load_items()

    def on_category_changed(self, _event=None):
        self.load_items()

    def load_items(self):
        if not self.selected_slot:
            self._set_inventory_enabled(False)
            self._update_apply_state()
            return
        try:
            wanted = _CATEGORY_TO_STORAGE.get(self.category_var.get())
            if wanted in ("Weapon", "Shield", "Bow"):
                all_items = core.equipment_for_slot(self.selected_slot)
            else:
                all_items = core.inventory_for_slot(self.selected_slot)
        except (OSError, ValueError) as error:
            self.items = []
            self.item_by_label = {}
            self.item_combo.configure(values=())
            self.status_var.set(f"无法读取物品：{error}")
            self._set_inventory_enabled(False)
            self._update_apply_state()
            return
        self.items = sorted(
            (item for item in all_items if item.category == wanted),
            key=lambda item: item.label.casefold(),
        )
        item_labels = []
        seen_labels = set()
        for item in self.items:
            label = item.label
            if label in seen_labels:
                label += f"  ·  堆叠 {item.index + 1}"
            seen_labels.add(label)
            item_labels.append(label)
        self.item_by_label = dict(zip(item_labels, self.items))
        values = tuple(item_labels)
        self.item_combo.configure(values=values)
        self.selected_item = None
        self.item_var.set("")
        self.quantity_var.set("")
        is_equipment = wanted in ("Weapon", "Shield", "Bow")
        self.quantity_title.configure(
            text=("设置耐久" if is_equipment else
                  "设置卢比" if wanted == "Rupee" else "设置数量")
        )
        self.maximum_label.configure(text="选择条目后显示上限")
        self.current_label.configure(
            text=f"{len(self.items)} 件已有装备" if is_equipment
            else f"{len(self.items)} 种已有物品"
        )
        self.limit_bar.configure(value=0)
        self.limit_note.configure(
            text=("装备耐久上限按游戏数据和耐久强化词条计算"
                  if is_equipment else
                  "物品数量范围 0–999     ·     修改前备份整个存档槽")
        )
        self._set_inventory_enabled(bool(self.items))
        if not self.items:
            self.status_var.set("该类别在所选存档中没有可修改的已有物品。")
        self._update_apply_state()

    def on_item_selected(self, _event=None):
        self.selected_item = self.item_by_label.get(self.item_var.get())
        if not self.selected_item:
            self.quantity_var.set("")
            self.current_label.configure(text="")
            self._update_apply_state()
            return
        is_equipment = isinstance(self.selected_item, core.EquipmentItem)
        is_rupees = self.selected_item.category == "Rupee"
        value = (self.selected_item.durability if is_equipment
                 else self.selected_item.quantity)
        maximum = self.selected_item.maximum
        self.quantity_var.set(str(value))
        self.quantity_title.configure(
            text=("设置耐久" if is_equipment else
                  "设置卢比" if is_rupees else "设置数量")
        )
        if maximum is None:
            self.maximum_label.configure(text="上限未知，不能修改")
            self.current_label.configure(text=f"当前耐久 {value}")
            self.quantity_spin.configure(state="disabled")
            self.limit_bar.configure(maximum=1, value=0)
        else:
            self.quantity_spin.configure(from_=0, to=maximum, state="normal")
            self.maximum_label.configure(
                text=(f"耐久上限 {maximum}" if is_equipment else
                      f"卢比上限 {maximum:,}" if is_rupees else
                      f"数量上限 {maximum}")
            )
            self.current_label.configure(
                text=(f"当前耐久 {value}  /  上限 {maximum}"
                      if is_equipment else
                      f"当前卢比 {value:,}  /  上限 {maximum:,}"
                      if is_rupees else
                      f"当前数量 {value}  /  上限 {maximum}")
            )
            self.limit_bar.configure(
                maximum=maximum, value=min(value, maximum)
            )
        self.limit_note.configure(
            text=("装备耐久上限按游戏数据和耐久强化词条计算"
                  if is_equipment else
                  "卢比范围 0–999,999     ·     修改前备份整个存档槽"
                  if is_rupees else
                  "物品数量范围 0–999     ·     修改前备份整个存档槽")
        )
        self._update_apply_state()

    def _set_inventory_enabled(self, enabled):
        self.category_combo.configure(
            state="readonly" if self.selected_slot else "disabled"
        )
        self.item_combo.configure(state="readonly" if enabled else "disabled")
        item_has_limit = (
            self.selected_item is None or self.selected_item.maximum is not None
        )
        self.quantity_spin.configure(
            state="normal" if enabled and item_has_limit else "disabled"
        )

    def _update_apply_state(self):
        has_maximum = bool(
            self.selected_item and self.selected_item.maximum is not None
        )
        self.maximum_button.configure(
            state="normal" if has_maximum else "disabled"
        )
        active = bool(self.selected_slot and has_maximum and
                      self.offline_verified and not self.game_running)
        self.apply_button.configure(state="normal" if active else "disabled")
        can_add = bool(
            self.selected_slot and self.offline_verified and not self.game_running
        )
        self.add_equipment_button.configure(
            state="normal" if can_add else "disabled"
        )
        self.lightroots_button.configure(
            state="normal" if can_add else "disabled"
        )

    def set_to_maximum(self):
        if self.selected_item and self.selected_item.maximum is not None:
            self.quantity_var.set(str(self.selected_item.maximum))

    def activate_lightroots(self):
        if not self.selected_slot or not self.offline_verified or self.game_running:
            return
        slot = self.selected_slot
        try:
            opened = core.read_lightroots(slot.progress_path)
        except (OSError, ValueError) as error:
            _show_dialog(self.root, "无法读取灯根", str(error))
            self.status_var.set(f"无法读取灯根：{error}")
            return
        if opened == 120:
            _show_dialog(self.root, "灯根状态", "此存档的 120 个灯根均已激活。")
            return
        confirmed = _show_dialog(
            self.root,
            "激活全部灯根",
            f"存档 {slot.slot_id}：已激活 {opened}/120，将激活其余 {120 - opened} 个灯根。\n\n"
            "这会改变地底探索进度，可能影响传送和完成度；不会主动修改地面神庙。"
            "地图显示和游戏内效果需要读档验证。\n\n"
            "将先备份整个存档槽，成功后只保留此槽最新备份。"
            "游戏必须保持关闭，继续吗？",
            confirm=True,
        )
        if not confirmed:
            return
        try:
            result = core.activate_lightroots(slot, profile=self.profile)
        except (OSError, ValueError) as error:
            _show_dialog(self.root, "激活未完成", str(error))
            self.status_var.set(f"灯根未修改：{error}")
            self.refresh_saves()
            return
        self.refresh_saves()
        if not result["changed"]:
            self.status_var.set("全部灯根已激活，无需写入。")
            return
        self.status_var.set(
            f"已激活 {result['activated']} 个灯根；备份：{result['backup']}"
        )
        if result["cleanup_errors"]:
            _show_dialog(
                self.root,
                "激活完成，备份清理未完成",
                "存档已写入并验证，但部分旧备份未删除：\n" +
                "；".join(result["cleanup_errors"]),
                warning=True,
            )
        else:
            _show_dialog(
                self.root,
                "灯根已激活",
                f"已写入 {result['activated']} 个灯根状态，备份位于：\n"
                f"{result['backup']}\n\n请在游戏中确认地图和灯根效果。",
            )

    def open_add_equipment_dialog(self):
        if not self.selected_slot or not self.offline_verified or self.game_running:
            return
        slot = self.selected_slot
        dialog = tk.Toplevel(self.root)
        dialog.title("添加新装备")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        frame = tk.Frame(dialog, bg=CARD, padx=22, pady=20)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(
            frame, text="选择要加入背包的装备", bg=CARD, fg=INK,
            font=("SF Pro Display", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=f"目标存档：{slot.display_name} · 槽位 {slot.slot_id[-2:]}",
            bg=CARD, fg=MUTED, font=("SF Pro Text", 10),
        ).pack(anchor="w", pady=(5, 16))

        form = tk.Frame(frame, bg=CARD)
        form.pack(fill="x")
        tk.Label(form, text="类别", bg=CARD, fg=MUTED,
                 font=("SF Pro Text", 10, "bold")).grid(
                     row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 12))
        category_var = tk.StringVar(value="武器")
        category_combo = ttk.Combobox(
            form, textvariable=category_var, state="readonly",
            values=("武器", "盾牌", "弓"), width=12,
        )
        category_combo.grid(row=0, column=1, sticky="w", pady=(0, 12))
        tk.Label(form, text="装备", bg=CARD, fg=MUTED,
                 font=("SF Pro Text", 10, "bold")).grid(
                     row=1, column=0, sticky="w", padx=(0, 12))
        item_var = tk.StringVar()
        item_combo = ttk.Combobox(
            form, textvariable=item_var, state="readonly", width=48,
        )
        item_combo.grid(row=1, column=1, sticky="ew")
        form.columnconfigure(1, weight=1)

        note = tk.Label(
            frame,
            text="将添加一件全新普通装备：无强化词条、无融合物，耐久设为基础上限。"
                 "只使用空槽，不覆盖已有装备。",
            bg=PALE_GREEN, fg=GREEN_DARK, font=("SF Pro Text", 9),
            justify="left", wraplength=480, padx=11, pady=10,
        )
        note.pack(fill="x", pady=(16, 14))
        buttons = tk.Frame(frame, bg=CARD)
        buttons.pack(fill="x")

        choices = {}

        def load_catalog(_event=None):
            category = _CATEGORY_TO_STORAGE[category_var.get()]
            catalog = core.equipment_catalog(category)
            choices.clear()
            labels = []
            seen = set()
            for item in catalog:
                label = item.label
                if label in seen:
                    label = f"{label} · {item.item_id}"
                seen.add(label)
                labels.append(label)
                choices[label] = item
            item_combo.configure(values=tuple(labels))
            if catalog:
                item_var.set(labels[0])

        def add_selected():
            template = choices.get(item_var.get())
            if template is None:
                _show_dialog(dialog, "尚未选择装备", "请从下拉列表选择一件装备。")
                return
            confirmed = _show_dialog(
                dialog,
                "确认添加装备",
                f"将“{template.label}”添加到所选存档。\n\n"
                f"装备 ID：{template.item_id}\n"
                "修改前会备份整个存档槽；若对应类别没有空位，操作会取消且不会覆盖物品。继续吗？",
                confirm=True,
            )
            if not confirmed:
                return
            try:
                result = core.add_equipment(
                    slot, template.item_id, template.category,
                    profile=self.profile,
                )
            except (OSError, ValueError) as error:
                _show_dialog(dialog, "添加未完成", str(error))
                self.status_var.set(f"未添加装备：{error}")
                self.refresh_saves()
                return
            dialog.destroy()
            self.status_var.set(
                f"已添加：{template.label.split(' · ')[0]}；"
                f"新装备位于第 {result['index'] + 1} 格。"
                f"最新备份：{result['backup']}"
            )
            self.refresh_saves()
            self.category_var.set(next(
                label for label, value in _CATEGORY_TO_STORAGE.items()
                if value == template.category
            ))
            self.load_items()
            added = next(
                (item for item in self.items
                 if item.item_id == template.item_id and
                 item.index == result["index"]),
                None,
            )
            if added:
                self.item_var.set(added.label)
                self.on_item_selected()

        category_combo.bind("<<ComboboxSelected>>", load_catalog)
        self._button(
            buttons, "取消", dialog.destroy, secondary=True
        ).pack(side="right")
        self._button(
            buttons, "备份并添加", add_selected, primary=True
        ).pack(side="right", padx=(0, 8))
        load_catalog()
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() -
                                       dialog.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() -
                                       dialog.winfo_reqheight()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()

    def check_game_status(self):
        try:
            with core.game_lock():
                pass
        except ValueError as error:
            self.offline_verified = False
            self.game_running = "游戏正在运行" in str(error)
            if self.game_running:
                self.game_badge.configure(
                    text="●  游戏正在运行", bg="#6B3B30", fg="#FFE1D9"
                )
            else:
                self.game_badge.configure(
                    text="●  无法确认状态", bg="#6B3B30", fg="#FFE1D9"
                )
                self.status_var.set(f"无法确认游戏离线状态：{error}")
        except OSError as error:
            self.offline_verified = False
            self.game_running = False
            self.game_badge.configure(
                text="●  无法确认状态", bg="#6B3B30", fg="#FFE1D9"
            )
            self.status_var.set(f"无法确认游戏离线状态：{error}")
        else:
            self.game_running = False
            self.offline_verified = True
            self.game_badge.configure(
                text="●  离线就绪", bg="#24543D", fg="#D7F2E2"
            )
        self._update_apply_state()
        self.root.after(2500, self.check_game_status)

    def apply_change(self):
        if not self.selected_slot or not self.selected_item:
            return
        item = self.selected_item
        is_equipment = isinstance(item, core.EquipmentItem)
        is_rupees = item.category == "Rupee"
        measure = "耐久" if is_equipment else "卢比" if is_rupees else "数量"
        if item.maximum is None:
            _show_dialog(self.root, "无法修改", "没有这件装备的可靠耐久上限数据，拒绝修改。")
            return
        text = self.quantity_var.get().strip()
        if not text.isdecimal():
            _show_dialog(
                self.root,
                f"{measure}无效",
                f"请输入 0 到 {item.maximum} 之间的整数。",
            )
            return
        value = int(text)
        if not 0 <= value <= item.maximum:
            _show_dialog(
                self.root,
                f"超过{measure}上限",
                f"{item.label.split(' · ')[0]} 的{measure}只能在 0 到 "
                f"{item.maximum} 之间。",
            )
            return
        old_value = item.durability if is_equipment else item.quantity
        if value == old_value:
            self.status_var.set(f"{measure}没有变化，无需写入存档。")
            return
        confirmed = _show_dialog(
            self.root,
            "备份并应用修改",
            f"将 {item.label.split(' · ')[0]} 的{measure}从 {old_value} 改为 {value}。\n\n"
            "修改前会备份整个存档槽。游戏必须保持关闭，继续吗？",
            confirm=True,
        )
        if not confirmed:
            return
        self.apply_button.configure(state="disabled")
        self.root.update_idletasks()
        try:
            if is_equipment:
                result = core.set_equipment_durability(
                    self.selected_slot, item.item_id, item.category, value,
                    profile=self.profile, item_index=item.index,
                )
            else:
                result = core.set_item_quantity(
                    self.selected_slot, item.item_id, item.category, value,
                    profile=self.profile, item_index=item.index,
                )
        except (OSError, ValueError) as error:
            _show_dialog(self.root, "修改未完成", str(error))
            self.status_var.set(f"未修改：{error}")
            self.refresh_saves()
            return
        if result["changed"]:
            cleanup_errors = result["cleanup_errors"]
            if cleanup_errors:
                details = "；".join(cleanup_errors)
                self.status_var.set(
                    f"修改已完成，但有旧备份未能清理：{details}"
                )
                _show_dialog(
                    self.root,
                    "修改已完成，备份清理未完成",
                    f"存档已安全修改并验证通过，但有旧备份未删除：\n{details}\n\n"
                    "最新备份仍保留，可稍后手动检查备份目录。",
                    warning=True,
                )
            else:
                self.status_var.set(
                    f"已应用：{item.label.split(' · ')[0]} 的{measure}已设为 {value}。"
                    f"已清理旧备份 {result['removed_backups']} 份；最新备份："
                    f"{result['backup']}"
                )
            self.limit_note.configure(
                text=f"修改已写入并验证；旧备份已清理，最新备份保存在：{result['backup']}",
                fg=GREEN_DARK,
            )
        self.refresh_saves()
        self.category_var.set(next(
            label for label, category in _CATEGORY_TO_STORAGE.items()
            if category == item.category
        ))
        self.load_items()
        matching = next((candidate for candidate in self.items
                         if candidate.item_id == item.item_id and
                         candidate.index == item.index), None)
        if matching:
            self.item_var.set(matching.label)
            self.on_item_selected()


def main():
    root = tk.Tk()
    tk_version = tuple(
        int(part) for part in root.tk.call("info", "patchlevel").split(".")
    )
    if tk_version[:2] < (8, 6):
        root.deiconify()
        _show_dialog(
            root,
            "Tk 版本不兼容",
            f"当前 Tk 版本为 {'.'.join(map(str, tk_version))}，窗口可能无法正常显示。\n\n"
            "请安装带 Tk 8.6 或更新版本的 Python，例如运行 "
            "`brew install python-tk@3.14`，然后双击启动器。",
        )
        root.destroy()
        return
    SaveEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
