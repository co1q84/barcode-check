import csv
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from .batch import barcode_preview
from .records_csv import RECORD_EXPORT_FILETYPES, export_sorting_records
from .settings import DEFAULT_RECORDS_PER_PAGE, RECORD_PAGE_SIZES
from .sorting import SortingBatch, SortingRecord
from .theme import (
    BG, MUTED, PRIMARY, PRIMARY_SOFT, SUCCESS, SUCCESS_SOFT, TEXT, UI_FONT,
    WARN, WARN_SOFT, grid_table,
)


SUMMARY_COLUMNS = (
    ("code", "编码", 96, True), ("manufacturer", "厂家", 144, True), ("quantity", "数量", 64, False),
)
DETAIL_COLUMNS = (
    ("number", "序号", 62, False), ("barcode", "条码", 180, True), ("manufacturer", "厂家", 110, True),
    ("code", "物料编码", 100, True), ("time", "时间", 88, False), ("result", "识别状态", 128, False),
    ("action", "操作", 62, False),
)


def _two_line_preview(text, typeface, width):
    lines = []
    for suffix in ("", "…"):
        if typeface.measure(text) <= width:
            lines.append(text)
            break
        low, high = 0, len(text)
        while low < high:
            midpoint = (low + high + 1) // 2
            if typeface.measure(text[:midpoint] + suffix) <= width:
                low = midpoint
            else:
                high = midpoint - 1
        lines.append(text[:low].rstrip() + suffix)
        text = text[low:].lstrip()
    return "\n".join(lines)


class SortingPage(ttk.Frame):
    def __init__(self, parent, *, settings, save_page_size, pause_scanning, show_dialog):
        super().__init__(parent)
        self._settings = settings
        self._save_page_size = save_page_size
        self._pause_scanning = pause_scanning
        self._show_dialog = show_dialog
        self.batch: SortingBatch | None = None
        self._paused = False
        self._record_page = 0
        self._summary_rows: dict[tuple[str, str], str] = {}
        self.scan_text = tk.StringVar(self)
        self.manufacturer_text = tk.StringVar(self, "等待扫码")
        self.code_text = tk.StringVar(self, "—")
        self.result_status = tk.StringVar(self)
        self.total_text = tk.StringVar(self, "0 次")
        self.pending_text = tk.StringVar(self, "待确认 0 次")
        self.summary_total = tk.StringVar(self, "合计 0 件")
        self.record_summary = tk.StringVar(self)
        self.page_status = tk.StringVar(self)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_scan()
        self._build_records()
        self._refresh_controls()
        self._show_record_page(0)

    def _build_scan(self):
        panel = ttk.Frame(self, style="Card.TFrame", padding=(14, 8, 14, 10))
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        panel.columnconfigure((0, 1), weight=1, uniform="sorting")

        toolbar = ttk.Frame(panel, style="White.TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="连续扫码", style="WhiteSection.TLabel").pack(side="left")
        self.state_label = ttk.Label(toolbar, style="BatchState.TLabel")
        self.state_label.pack(side="left", padx=(12, 0))
        self.batch_button = ttk.Button(toolbar, width=12, style="Primary.TButton", command=self._batch_action)
        self.batch_button.pack(side="right")

        scan = self.scan_region = ttk.Frame(panel, style="White.TFrame")
        scan.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        scan.columnconfigure(0, weight=1)
        scan.rowconfigure(1, weight=1)
        self.scan_entry = ttk.Entry(scan, style="Scan.TEntry", textvariable=self.scan_text, font=(UI_FONT, 12))
        self.scan_entry.grid(row=0, column=0, sticky="ew")
        self.scan_entry.bind("<Return>", self._submit_scan)
        self.scan_entry.bind("<KP_Enter>", self._submit_scan)

        self.result_panel = tk.Frame(scan, background=BG, padx=10, pady=6)
        self.result_panel.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.result_panel.columnconfigure(0, weight=1)
        self.result_panel.rowconfigure((0, 2), weight=1, uniform="result_space")
        self.result_values = tk.Frame(self.result_panel, background=BG)
        self.result_values.grid(row=1, column=0, sticky="ew")
        self.result_values.columnconfigure(0, weight=1)
        self._manufacturer_font = font.Font(root=self, family=UI_FONT, size=24, weight="bold")
        self._compact_manufacturer_font = font.Font(root=self, family=UI_FONT, size=20, weight="bold")
        self._code_font = font.Font(root=self, family=UI_FONT, size=15, weight="bold")
        self.manufacturer_label = tk.Label(
            self.result_values, text=self.manufacturer_text.get(), font=self._manufacturer_font, padx=0, pady=0,
        )
        self.manufacturer_label.grid(row=0, column=0, sticky="ew")
        self.code_caption = tk.Label(self.result_values, text="物料编码", padx=0, pady=0)
        self.code_caption.grid(row=1, column=0, pady=(2, 0))
        self.code_label = tk.Label(
            self.result_values, text=self.code_text.get(), font=self._code_font, padx=0, pady=0,
        )
        self.code_label.grid(row=2, column=0, sticky="ew")
        self.status_label = tk.Label(self.result_panel, textvariable=self.result_status, padx=0, pady=0)
        self.status_label.grid(row=2, column=0, sticky="s", pady=(3, 0))
        self.status_label.grid_remove()
        self.result_panel.bind("<Configure>", self._fit_result)
        self._result_colors(BG, MUTED)
        self._build_summary(panel)

    def _build_summary(self, parent):
        top_inset = 2
        region = self.summary_region = ttk.Frame(parent, style="Card.TFrame", padding=(10, top_inset, 10, 5))
        region.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        region.columnconfigure(0, weight=1)
        region.rowconfigure(1, weight=1)
        header = ttk.Frame(region, style="White.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        header.rowconfigure(0, minsize=self.scan_entry.winfo_reqheight() - top_inset)
        ttk.Label(header, text="分流汇总", style="WhiteSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.summary_total, style="WhiteSection.TLabel").grid(row=0, column=1, sticky="e")

        summary, self.summary_tree = grid_table(
            region, SUMMARY_COLUMNS, height=4, style="Summary.Treeview", auto_scrollbar=True,
        )
        summary.grid(row=1, column=0, sticky="new")
        self.empty_summary = ttk.Label(summary, text="暂无已识别的条码", style="WhiteMuted.TLabel")
        self.empty_summary.place(relx=0.5, rely=0.5, anchor="center")

        totals = ttk.Frame(region, style="White.TFrame")
        totals.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(totals, text="本批已扫", style="WhiteMuted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Label(totals, textvariable=self.total_text, style="White.TLabel").pack(side="left")
        self.pending_label = ttk.Label(totals, textvariable=self.pending_text, style="WhiteMuted.TLabel")
        self.pending_label.pack(side="right")

    def _build_records(self):
        panel = ttk.Frame(self, style="Card.TFrame")
        panel.grid(row=1, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(panel, style="White.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", padx=14, pady=7)
        ttk.Label(toolbar, text="扫码明细", style="WhiteSection.TLabel").pack(side="left")
        ttk.Label(toolbar, textvariable=self.record_summary, style="WhiteMuted.TLabel").pack(side="left", padx=12)
        self.delete_button = ttk.Button(toolbar, text="删除选中", style="Table.TButton", command=self._delete_selected)
        self.delete_button.pack(side="right")
        self.export_button = ttk.Button(toolbar, text="导出记录", style="Table.TButton", command=self._export)
        self.export_button.pack(side="right", padx=7)

        details, self.records_tree = grid_table(panel, DETAIL_COLUMNS, height=DEFAULT_RECORDS_PER_PAGE)
        details.grid(row=1, column=0, sticky="nsew")
        self.records_tree.tag_configure("pending", background=WARN_SOFT, foreground=WARN)
        self.records_tree.bind("<<TreeviewSelect>>", self._refresh_record_controls)
        self.records_tree.bind("<ButtonRelease-1>", self._row_action)
        self.records_tree.bind("<Delete>", self._delete_selected)
        self.empty_records = ttk.Label(details, text="开始分流后，扫码明细将在这里显示。", style="WhiteMuted.TLabel")
        self.empty_records.place(relx=0.5, rely=0.5, anchor="center")
        self._build_pagination(panel)

    def _build_pagination(self, parent):
        footer = ttk.Frame(parent, style="White.TFrame")
        footer.grid(row=2, column=0, sticky="ew", padx=14, pady=7)
        ttk.Label(footer, textvariable=self.page_status, style="WhiteMuted.TLabel").pack(side="left")
        self.next_page_button = ttk.Button(footer, text="下一页", width=7, style="Table.TButton",
                                           command=lambda: self._navigate_record_page(self._record_page + 1))
        self.next_page_button.pack(side="right")
        self.previous_page_button = ttk.Button(footer, text="上一页", width=7, style="Table.TButton",
                                               command=lambda: self._navigate_record_page(self._record_page - 1))
        self.previous_page_button.pack(side="right", padx=(0, 6))
        self.page_size_box = ttk.Combobox(footer, values=RECORD_PAGE_SIZES, state="readonly", width=4,
                                         justify="center", style="Table.TCombobox")
        self.page_size_box.set(str(self._settings().records_per_page))
        self.page_size_box.pack(side="right", padx=(6, 12))
        self.page_size_box.bind("<<ComboboxSelected>>", self._change_page_size)
        ttk.Label(footer, text="每页条数", style="WhiteMuted.TLabel").pack(side="right")

    @property
    def _running(self):
        return self.batch is not None and not self.batch.finished

    @property
    def has_records(self):
        return self.batch is not None and self.batch.record_count > 0

    def confirm_discard(self, action):
        return not self.has_records or messagebox.askyesno(
            action, f"本批有 {self.batch.record_count} 条分流记录。确认{action}并清空本批记录？",
            parent=self.winfo_toplevel(), default="no",
        )

    def set_paused(self, paused):
        self._paused = paused
        self._refresh_controls()

    def focus_scan(self):
        if self._running and not self._paused and self.winfo_ismapped():
            self.scan_entry.focus_set()

    def _refresh_controls(self):
        self.scan_entry.state(["!disabled" if self._running and not self._paused else "disabled"])
        self.batch_button.state(["disabled" if self._paused else "!disabled"])
        self._refresh_record_controls()
        if self._running:
            self.batch_button.configure(text="结束分流")
            self.state_label.configure(text="分流中", background=PRIMARY_SOFT, foreground=PRIMARY)
        elif self.batch is not None:
            self.batch_button.configure(text="新建分流")
            self.state_label.configure(text="已结束", background=SUCCESS_SOFT, foreground=SUCCESS)
        else:
            self.batch_button.configure(text="开始分流")
            self.state_label.configure(text="待开始", background=BG, foreground=MUTED)

    def _refresh_record_controls(self, _event=None):
        can_delete = self._running and not self._paused and self.records_tree.selection()
        self.delete_button.state(["!disabled" if can_delete else "disabled"])
        self.export_button.state(["!disabled" if self.has_records and not self._paused else "disabled"])

    def _batch_action(self):
        if self._running:
            self.batch.finish()
            self.scan_text.set("")
            self._show_record_page(self._record_page)
        elif self.confirm_discard("新建分流"):
            settings = self._settings()
            self.batch = SortingBatch(settings)
            self._summary_rows.clear()
            self.summary_tree.delete(*self.summary_tree.get_children())
            self.empty_summary.place(relx=0.5, rely=0.5, anchor="center")
            self._reset_result()
            if not settings.rows:
                self._set_result_status("基表为空，扫描将记为待确认")
            self._show_record_page(0)
            self._update_totals()
        self._refresh_controls()
        self.focus_scan()

    def _reset_result(self):
        self.manufacturer_text.set("等待扫码")
        self.code_text.set("—")
        self._set_result_status("")
        self._result_colors(BG, MUTED)
        self._fit_result()

    def _set_result_status(self, text):
        self.result_status.set(text)
        if text:
            self.status_label.grid()
        else:
            self.status_label.grid_remove()

    def _fit_result(self, _event=None):
        width = max(120, self.result_panel.winfo_width() - 20)
        manufacturer = self.manufacturer_text.get()
        typeface = self._manufacturer_font
        if typeface.measure(manufacturer) > width * 2:
            typeface = self._compact_manufacturer_font
        self.manufacturer_label.configure(font=typeface, text=_two_line_preview(manufacturer, typeface, width))
        self.code_label.configure(text=_two_line_preview(self.code_text.get(), self._code_font, width))

    def _result_colors(self, background, foreground, *, supporting=None, status=None):
        self.result_panel.configure(background=background)
        self.result_values.configure(background=background)
        self.manufacturer_label.configure(background=background, foreground=foreground)
        self.code_caption.configure(background=background, foreground=supporting or foreground)
        self.code_label.configure(background=background, foreground=foreground)
        self.status_label.configure(background=background, foreground=status or supporting or foreground)

    def _submit_scan(self, _event=None):
        if not self._running or self._paused:
            return "break"
        barcode = self.scan_text.get()
        self.scan_text.set("")
        record = self.batch.scan(barcode)
        if record is None:
            return "break"
        self._show_result(record)
        if record.rule is not None and not record.duplicate:
            self._update_summary_row(record.rule)
        self._update_totals()
        self._show_scanned_record(record)
        self._refresh_record_controls()
        self.focus_scan()
        return "break"

    def _show_result(self, record):
        if record.rule is None:
            self.manufacturer_text.set("未识别")
            self.code_text.set("—")
            self._set_result_status("待确认")
            self._result_colors(WARN_SOFT, WARN)
        else:
            self.manufacturer_text.set(record.rule.manufacturer)
            self.code_text.set(record.rule.code)
            self._set_result_status("本批已扫过" if record.duplicate else "")
            self._result_colors(BG, TEXT, supporting=MUTED, status=PRIMARY if record.duplicate else MUTED)
        self._fit_result()

    def _update_summary_row(self, rule, *, highlight=True):
        quantity = self.batch.quantity_for(rule.key)
        iid = self._summary_rows.get(rule.key)
        if not quantity:
            if iid is not None:
                self.summary_tree.delete(iid)
                del self._summary_rows[rule.key]
            if not self._summary_rows:
                self.empty_summary.place(relx=0.5, rely=0.5, anchor="center")
            return
        self.empty_summary.place_forget()
        if iid is None:
            iid = self.summary_tree.insert("", "end", values=(*rule.key, quantity))
            self._summary_rows[rule.key] = iid
        else:
            self.summary_tree.set(iid, "quantity", quantity)
        if highlight:
            self.summary_tree.selection_set(iid)
            self.summary_tree.see(iid)

    def _update_totals(self):
        total = self.batch.record_count
        self.total_text.set(f"{total} 次")
        self.pending_text.set(f"待确认 {self.batch.pending_count} 次")
        self.pending_label.configure(foreground=WARN if self.batch.pending_count else MUTED)
        self.summary_total.set(f"合计 {self.batch.recognized_count} 件")
        self.record_summary.set(f"共 {total} 条" if total else "")
        if total:
            self.empty_records.place_forget()
        else:
            self.empty_records.configure(text="暂无扫码记录")
            self.empty_records.place(relx=0.5, rely=0.5, anchor="center")

    def set_page_size(self, size):
        self.page_size_box.set(str(size))
        self._show_record_page(0)

    def _change_page_size(self, _event=None):
        size = int(self.page_size_box.get())
        old_size = self._settings().records_per_page
        if size != old_size and not self._save_page_size(size):
            self.page_size_box.set(str(old_size))
        self.focus_scan()

    def _page_count(self):
        total = self.batch.record_count if self.batch else 0
        size = self._settings().records_per_page
        return max(1, (total + size - 1) // size)

    def _refresh_pagination(self):
        total = self.batch.record_count if self.batch else 0
        pages = self._page_count()
        size = self._settings().records_per_page
        status = f"第 {self._record_page + 1} / {pages} 页"
        if total:
            first = total - self._record_page * size
            last = max(1, first - size + 1)
            status += f"  ·  序号 {first}–{last}" if first != last else f"  ·  序号 {first}"
        self.page_status.set(status)
        self.previous_page_button.state(["!disabled" if self._record_page > 0 else "disabled"])
        self.next_page_button.state(["!disabled" if self._record_page + 1 < pages else "disabled"])

    def _navigate_record_page(self, page):
        self._show_record_page(page)
        self.focus_scan()

    def _show_record_page(self, page):
        self._record_page = max(0, min(page, self._page_count() - 1))
        self.records_tree.delete(*self.records_tree.get_children())
        if self.batch is not None:
            size = self._settings().records_per_page
            offset = self._record_page * size
            first = self.batch.record_count - offset
            for index, record in enumerate(self.batch.record_page(offset, size)):
                self._insert_record(record, "end", first - index)
        self.records_tree.yview_moveto(0)
        self._refresh_pagination()
        self._refresh_record_controls()

    def _show_scanned_record(self, record):
        if self._record_page:
            self._show_record_page(0)
            return
        self._insert_record(record, 0, self.batch.record_count)
        rows = self.records_tree.get_children()
        if len(rows) > self._settings().records_per_page:
            self.records_tree.delete(rows[-1])
        self.records_tree.yview_moveto(0)
        self._refresh_pagination()

    def _insert_record(self, record: SortingRecord, index, number):
        rule = record.rule
        self.records_tree.insert("", index, iid=str(record.id), tags=("pending",) if rule is None else (), values=(
            number, record.barcode, rule.manufacturer if rule else "—", rule.code if rule else "—",
            f"{record.recorded_at:%H:%M:%S}", record.status, "删除" if self._running else "",
        ))

    def _row_action(self, event):
        if self.records_tree.identify_region(event.x, event.y) == "cell":
            column = self.records_tree.identify_column(event.x)
            if self.records_tree.column(column, "id") == "action":
                self._delete_record(self.records_tree.identify_row(event.y))
                return "break"
        return None

    def _delete_selected(self, _event=None):
        selected = self.records_tree.selection()
        if selected:
            self._delete_record(selected[0])
        return "break"

    def _delete_record(self, iid):
        if not iid or not self._running or self._paused:
            return
        record = self.batch.record(int(iid))
        if record is None:
            return
        choice = self._show_dialog(
            "删除扫码记录", "删除这条记录？", f"条码 {barcode_preview(record.barcode)}\n删除后将更新分流汇总与已扫次数。",
            (("取消", None, "TButton"), ("删除记录", "delete", "Danger.TButton")),
        )
        if choice != "delete":
            return
        self.batch.delete(record.id)
        if record.rule is not None:
            self._update_summary_row(record.rule, highlight=False)
        latest = self.batch.record_page(0, 1)
        if latest:
            self._show_result(latest[0])
        else:
            self._reset_result()
        self._update_totals()
        self._show_record_page(self._record_page)
        self.focus_scan()

    def _export(self):
        if not self.has_records or self._paused:
            return False
        parent = self.winfo_toplevel()
        with self._pause_scanning():
            filename = filedialog.asksaveasfilename(
                parent=parent, title="导出分流明细", initialfile="条码分流记录.xlsx", defaultextension=".xlsx",
                filetypes=RECORD_EXPORT_FILETYPES,
            )
            if not filename:
                return False
            try:
                export_sorting_records(Path(filename), self.batch)
            except (OSError, csv.Error, ValueError) as error:
                messagebox.showerror("导出失败", str(error), parent=parent)
                return False
            self.record_summary.set(f"共 {self.batch.record_count} 条  ·  已导出")
            return True
