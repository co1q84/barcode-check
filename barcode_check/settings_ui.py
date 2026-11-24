from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME
from .batch import is_valid_barcode
from .settings import BARCODE_INPUT_PADDING, BaseRow, Settings, SettingsSaveCancelled, delete_rows, edit_row
from .settings_xlsx import COLUMNS, import_settings_workbook, write_settings_workbook
from .theme import BG, ERROR, MUTED, SUCCESS, SURFACE
from .window_layout import center_dialog


EXCEL_FILETYPE = [("Excel 工作簿", "*.xlsx")]


def _desktop_size(window: tk.Misc, width: int, height: int) -> tuple[int, int]:
    scale = max(1, window.winfo_fpixels("1i") / 96)
    return (
        min(round(width * scale), window.winfo_screenwidth() - 48),
        min(round(height * scale), window.winfo_screenheight() - 80),
    )


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, settings: Settings, on_save: Callable[[Settings], None]):
        super().__init__(parent, background=BG)
        self.withdraw()
        self.title(f"设置 · {APP_NAME}")
        self.transient(parent)
        self.minsize(*_desktop_size(self, 680, 400))
        width, height = _desktop_size(self, 880, 550)
        self.settings = settings
        self.on_save = on_save
        self.visible_rows: dict[str, BaseRow] = {}
        self.search = tk.StringVar(master=self)
        self.status = tk.StringVar(master=self)
        self.notice = tk.StringVar(master=self)
        self.bind("<Escape>", lambda _event: self.destroy())

        area = ttk.Frame(self, padding=(16, 16, 16, 12))
        area.pack(fill="both", expand=True)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(2, weight=1)

        header = ttk.Frame(area)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)
        ttk.Label(header, text="条码基表", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 25))
        ttk.Label(header, text="搜索", style="Muted.TLabel").grid(row=0, column=1, padx=(0, 8))
        self.search_entry = ttk.Entry(header, textvariable=self.search)
        self.search_entry.grid(row=0, column=2, sticky="ew")
        self.clear_button = ttk.Button(header, text="清除", width=6, command=lambda: self.search.set(""))
        self.clear_button.grid(row=0, column=3, padx=(8, 0))

        toolbar = ttk.Frame(area)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        self.new_button = ttk.Button(toolbar, text="新增", width=6, style="Primary.TButton", command=self._new)
        self.new_button.pack(side="left")
        self.edit_button = ttk.Button(toolbar, text="编辑", width=6, command=self._edit)
        self.edit_button.pack(side="left", padx=(8, 0))
        self.delete_button = ttk.Button(toolbar, text="批量删除", width=8, style="Danger.TButton", command=self._delete)
        self.delete_button.pack(side="left", padx=(8, 0))
        self.template_button = ttk.Button(toolbar, text="导出 Excel 模板", command=lambda: self._export(template=True))
        self.template_button.pack(side="right")
        self.export_button = ttk.Button(toolbar, text="导出数据", command=self._export)
        self.export_button.pack(side="right", padx=(0, 8))
        self.import_button = ttk.Button(toolbar, text="导入数据", command=self._import)
        self.import_button.pack(side="right", padx=(0, 8))

        self._build_table(area)
        footer = ttk.Frame(area)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        ttk.Label(footer, textvariable=self.notice, foreground=SUCCESS).pack(side="left", padx=14)
        ttk.Button(footer, text="关闭", command=self.destroy).pack(side="right")
        self.search.trace_add("write", self._filter)
        self.refresh()
        center_dialog(self, parent, width, height)
        self.deiconify()
        self.search_entry.focus_set()

    def _build_table(self, parent):
        area = ttk.Frame(parent, style="White.TFrame")
        area.grid(row=2, column=0, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        columns = ("code", "manufacturer", "prefix")
        self.table = ttk.Treeview(area, columns=columns, show="headings", selectmode="extended", style="Grid.Treeview")
        for column, heading, width in zip(columns, COLUMNS, (160, 245, 310)):
            self.table.heading(column, text=heading, anchor="center")
            self.table.column(column, width=width, minwidth=90, stretch=True, anchor="center")
        vertical = ttk.Scrollbar(area, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.empty = ttk.Label(area, style="WhiteMuted.TLabel", anchor="center")
        self.table.bind("<<TreeviewSelect>>", self._update_selection)
        self.table.bind("<Double-1>", self._double_click)
        self.table.bind("<Return>", lambda _event: self._edit())
        self.table.bind("<Delete>", lambda _event: self._delete())
        self.table.bind("<Control-a>", self._select_all)

    def save_settings(self, settings: Settings) -> None:
        self.on_save(settings)
        self.settings = settings
        self.refresh()

    def _selected(self) -> tuple[BaseRow, ...]:
        return tuple(self.visible_rows[iid] for iid in self.table.selection() if iid in self.visible_rows)

    def refresh(self, *, keep_selection: bool = True) -> None:
        selected = {row.key for row in self._selected()} if keep_selection else set()
        self.table.delete(*self.table.get_children())
        self.visible_rows.clear()
        query = self.search.get().strip().casefold()
        for index, row in enumerate(self.settings.rows):
            fields = (row.code, row.manufacturer, row.prefix)
            if query and not any(query in value.casefold() for value in fields):
                continue
            iid = str(index)
            self.visible_rows[iid] = row
            self.table.insert("", "end", iid=iid, values=fields)
            if row.key in selected:
                self.table.selection_add(iid)
        self.empty.place_forget()
        if not self.visible_rows:
            self.empty.configure(text="没有匹配的记录。" if query else "基表为空。可新增记录，或用 Excel 模板导入数据。")
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        self.export_button.configure(state="normal" if self.settings.rows else "disabled")
        self.clear_button.configure(state="normal" if self.search.get() else "disabled")
        self.notice.set("")
        self._update_selection()

    def _filter(self, *_args: str) -> None:
        self.refresh(keep_selection=False)

    def _update_selection(self, _event=None) -> None:
        count = len(self._selected())
        self.edit_button.configure(state="normal" if count == 1 else "disabled")
        self.delete_button.configure(state="normal" if count else "disabled")
        self.status.set(f"显示 {len(self.visible_rows)} / {len(self.settings.rows)} 条 · 已选 {count} 条")

    def _select_all(self, _event) -> str:
        self.table.selection_set(self.table.get_children())
        return "break"

    def _double_click(self, event) -> None:
        iid = self.table.identify_row(event.y)
        if iid:
            self.table.selection_set(iid)
            self._edit()

    def _new(self) -> None:
        BaseRowEditor(self)

    def _edit(self) -> None:
        selected = self._selected()
        if len(selected) == 1:
            BaseRowEditor(self, selected[0])

    def _delete(self) -> None:
        selected = self._selected()
        if not selected or not messagebox.askyesno(
            "批量删除", f"确定删除已选的 {len(selected)} 条基表记录？", default="no", parent=self,
        ):
            return
        try:
            self.save_settings(delete_rows(self.settings, selected))
        except SettingsSaveCancelled:
            return
        except (OSError, ValueError) as error:
            messagebox.showerror("删除失败", str(error), parent=self)
            return
        self.notice.set(f"已删除 {len(selected)} 条")

    def _export(self, *, template: bool = False) -> None:
        title = "导出 Excel 模板" if template else "导出基表数据"
        filename = filedialog.asksaveasfilename(
            title=title, parent=self, defaultextension=".xlsx", filetypes=EXCEL_FILETYPE,
            initialfile="条码基表-模板.xlsx" if template else "条码基表.xlsx",
        )
        if not filename:
            return
        try:
            write_settings_workbook(Path(filename), () if template else self.settings.rows)
        except (OSError, ValueError) as error:
            messagebox.showerror("导出失败", str(error), parent=self)
            return
        self.notice.set("Excel 模板已导出" if template else f"已导出 {len(self.settings.rows)} 条")

    def _import(self) -> None:
        filename = filedialog.askopenfilename(title="导入基表数据", parent=self, filetypes=EXCEL_FILETYPE)
        if not filename:
            return
        try:
            updated = import_settings_workbook(Path(filename), self.settings)
            added = len(updated.rows) - len(self.settings.rows)
            self.save_settings(updated)
        except SettingsSaveCancelled:
            return
        except (OSError, ValueError) as error:
            messagebox.showerror("导入失败", str(error), parent=self)
            return
        self.notice.set(f"已导入 {added} 条")


class BaseRowEditor(tk.Toplevel):
    def __init__(self, owner: SettingsWindow, original: BaseRow | None = None):
        super().__init__(owner, background=SURFACE)
        self.withdraw()
        self.title("编辑基表记录" if original else "新增基表记录")
        self.transient(owner)
        self.owner = owner
        self.original = original
        self.previous_grab = owner.grab_current()
        self.previous_focus = owner.focus_get()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.minsize(*_desktop_size(self, 490, 295))
        self.resizable(True, False)

        self.code = tk.StringVar(master=self, value=original.code if original else "")
        self.manufacturer = tk.StringVar(master=self, value=original.manufacturer if original else "")
        self.prefix = tk.StringVar(master=self, value=original.prefix if original else "")
        self.sample = tk.StringVar(master=self)
        self.error = tk.StringVar(master=self)

        body = ttk.Frame(self, padding=18, style="White.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        for index, (label, variable) in enumerate(zip(COLUMNS, (self.code, self.manufacturer, self.prefix))):
            ttk.Label(body, text=label, style="White.TLabel").grid(row=index, column=0, sticky="w", padx=(0, 14), pady=3)
            entry = ttk.Entry(body, textvariable=variable, width=32)
            entry.grid(row=index, column=1, sticky="ew", pady=3)
            if index == 0:
                first_entry = entry
        ttk.Separator(body).grid(row=3, column=0, columnspan=2, sticky="ew", pady=11)

        ttk.Label(body, text="试扫条码", style="White.TLabel").grid(row=4, column=0, sticky="w")
        trial_field = ttk.Frame(body, style="White.TFrame")
        trial_field.grid(row=4, column=1, sticky="ew")
        trial_input = ttk.Entry(trial_field, textvariable=self.sample)
        trial_input.pack(side="left", fill="x", expand=True)
        trial_input.bind("<Return>", lambda _event: self._try_sample())
        self.try_button = ttk.Button(trial_field, text="试扫", command=self._try_sample)
        self.try_button.pack(side="right", padx=(8, 0))
        self.trial = ttk.Label(body, style="WhiteMuted.TLabel", wraplength=425)
        self.trial.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Label(body, textvariable=self.error, style="White.TLabel", foreground=ERROR, wraplength=425).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0),
        )
        footer = ttk.Frame(body, style="White.TFrame")
        footer.grid(row=7, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(footer, text="取消", command=self.close).pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(footer, text="保存", style="Primary.TButton", command=self._save)
        self.save_button.pack(side="left")

        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        first_entry.focus_set()
        first_entry.selection_range(0, "end")

    def _candidate(self) -> Settings:
        row = BaseRow(
            self.code.get().strip(),
            self.manufacturer.get().strip(),
            self.prefix.get().strip(BARCODE_INPUT_PADDING),
        )
        return edit_row(self.owner.settings, self.original, row)

    def _try_sample(self) -> None:
        self.error.set("")
        barcode = self.sample.get().strip(BARCODE_INPUT_PADDING)
        if not is_valid_barcode(barcode):
            self.trial.configure(text="请输入一条有效条码。", foreground=ERROR)
            return
        try:
            match = self._candidate().match(barcode)
        except ValueError as error:
            self.trial.configure(text=str(error), foreground=ERROR)
            return
        if match is None:
            self.trial.configure(text="这条条码没有命中已配置的前缀。", foreground=ERROR)
            return
        self.trial.configure(
            text=f"命中前缀 {match.prefix} · 编码 {match.code} · 厂家 {match.manufacturer}", foreground=SUCCESS,
        )

    def _save(self) -> None:
        try:
            self.owner.save_settings(self._candidate())
        except SettingsSaveCancelled:
            self.error.set("")
            return
        except (OSError, ValueError) as error:
            self.error.set(str(error))
            return
        self.close()

    def close(self) -> None:
        self.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()
