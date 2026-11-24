import csv
import tkinter as tk
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

try:
    import winsound
except ImportError:
    winsound = None

from .batch import BARCODE_INPUT_PADDING, Batch, Outcome, Record
from .records_csv import export_records
from .settings import DEFAULT_RECORDS_PER_PAGE, RECORD_PAGE_SIZES, Settings, SettingsStore
from .theme import (
    BG, BORDER, ERROR, ERROR_SOFT, MUTED, PRIMARY, PRIMARY_SOFT, SUCCESS, SUCCESS_SOFT,
    SCAN_ALERT_ERROR, SCAN_ALERT_WARNING, SURFACE, TEXT, UI_FONT, WARN, WARN_SOFT, configure_theme,
)


RECORD_COLUMNS = (
    ("barcode", "条码", 190, True), ("manufacturer", "厂家", 125, True), ("time", "时间", 92, False),
    ("result", "结果", 86, False),
    ("detail", "说明", 230, True), ("action", "操作", 64, False),
)
FEEDBACK_COLORS = {
    "neutral": (BG, MUTED), "info": (PRIMARY_SOFT, PRIMARY), "success": (SUCCESS_SOFT, SUCCESS),
    "warning": (WARN_SOFT, WARN), "error": (ERROR_SOFT, ERROR),
}
SCAN_ALERT_BACKGROUNDS = {"warning": SCAN_ALERT_WARNING, "error": SCAN_ALERT_ERROR}
FEEDBACK_BODY_FONT = (UI_FONT, 18)
FEEDBACK_MANUFACTURER_FONT = (UI_FONT, 24, "bold")


def _table(parent, columns, *, height):
    frame = ttk.Frame(parent, style="White.TFrame")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree = ttk.Treeview(frame, columns=[column[0] for column in columns], show="headings",
                        selectmode="browse", height=height, style="Records.Treeview")
    for key, name, width, stretch in columns:
        tree.heading(key, text=name, anchor="w")
        tree.column(key, width=width, minwidth=70 if stretch else width, stretch=stretch, anchor="w")
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    return frame, tree


class BarcodeCheckApp:
    def __init__(self, root: tk.Tk, *, store: SettingsStore | None = None):
        self.root = root
        self.store = store if store is not None else SettingsStore()
        self.batch: Batch | None = None
        self._paused = 0
        self._record_page = 0
        self._scan_tone = "neutral"
        self._feedback_width = 0
        self._record_by_iid: dict[str, Record] = {}
        settings_error = None
        try:
            self.settings = self.store.load()
        except (OSError, ValueError) as error:
            self.settings = Settings()
            settings_error = str(error)

        configure_theme(root)
        self._style = ttk.Style(root)
        root.title("条码核验")
        root.minsize(820, 580)
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.bind("<F2>", self._focus_scan)

        self.code = tk.StringVar(root)
        self.manufacturer = tk.StringVar(root)
        self.quantity = tk.StringVar(root)
        self.scan_text = tk.StringVar(root)
        self.progress_detail = tk.StringVar(root)
        self.progress_amount = tk.StringVar(root)
        self.record_summary = tk.StringVar(root)
        self.record_detail = tk.StringVar(root)
        self.page_status = tk.StringVar(root)

        self._build()
        self.code.trace_add("write", self._refresh_manufacturers)
        self._refresh_manufacturers()
        self._refresh_batch()
        if settings_error:
            self._feedback("设置读取失败", settings_error, "error")
        else:
            self._waiting_feedback()
        root.update_idletasks()
        width = min(1100, max(820, root.winfo_screenwidth() - 60))
        height = min(root.winfo_reqheight(), max(580, root.winfo_screenheight() - 90))
        root.geometry(f"{width}x{height}")

    def _build(self):
        content = ttk.Frame(self.root, padding=(24, 14, 24, 11))
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)

        self._build_target(content)
        self._build_scan(content)
        self._build_records(content)

    def _build_target(self, parent):
        panel = ttk.Frame(parent, style="White.TFrame", padding=(15, 9, 15, 11))
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        panel.columnconfigure(0, weight=2)
        panel.columnconfigure(1, weight=2)
        panel.columnconfigure(2, weight=1)
        ttk.Label(panel, text="核验目标", style="WhiteSection.TLabel").grid(row=0, column=0, sticky="w")
        self.batch_state = ttk.Label(panel, style="WhiteMuted.TLabel")
        self.batch_state.grid(row=0, column=3, columnspan=2, sticky="e", pady=(0, 2))

        fields = ("物料编码", "厂家", "应扫数量（可选）")
        for column, title in enumerate(fields):
            ttk.Label(panel, text=title, style="WhiteMuted.TLabel").grid(
                row=1, column=column, sticky="w", pady=(5, 3),
            )
        self.code_entry = ttk.Entry(panel, textvariable=self.code, width=18)
        self.manufacturer_box = ttk.Combobox(panel, textvariable=self.manufacturer, state="readonly", width=18)
        self.quantity_entry = ttk.Entry(panel, textvariable=self.quantity, width=13)
        for column, widget in enumerate((self.code_entry, self.manufacturer_box, self.quantity_entry)):
            widget.grid(row=2, column=column, sticky="ew", padx=(0, 12))
        self.batch_button = ttk.Button(panel, width=12, style="Primary.TButton", command=self._batch_action)
        self.batch_button.grid(row=2, column=3, sticky="e", padx=(0, 8))
        ttk.Button(panel, text="设置", width=6, command=self._open_settings).grid(row=2, column=4, sticky="e")

    def _build_scan(self, parent):
        panel = self.scan_panel = ttk.Frame(parent, style="ScanPanel.TFrame", padding=(15, 10, 15, 11))
        panel.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        panel.columnconfigure(0, weight=3, minsize=385)
        panel.columnconfigure(2, weight=1, minsize=208)
        scan = ttk.Frame(panel, style="ScanPanel.TFrame")
        scan.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        scan.columnconfigure(0, weight=1)
        ttk.Label(scan, text="连续扫码", style="ScanSection.TLabel").grid(row=0, column=0, sticky="w")
        self.scan_entry = ttk.Entry(scan, style="Scan.TEntry", textvariable=self.scan_text, font=(UI_FONT, 12))
        self.scan_entry.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        self.scan_entry.bind("<Return>", self._submit_scan)
        self.scan_entry.bind("<KP_Enter>", self._submit_scan)

        self._feedback_line_height = font.Font(root=self.root, font=FEEDBACK_MANUFACTURER_FONT).metrics("linespace")
        self.feedback_panel = tk.Frame(scan, height=self._feedback_line_height + 16, background=SURFACE)
        self.feedback_panel.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.feedback_box = tk.Text(
            self.feedback_panel, width=1, height=1, padx=10, pady=0, borderwidth=0, highlightthickness=0,
            font=FEEDBACK_MANUFACTURER_FONT, wrap="word", state="disabled", takefocus=False, cursor="arrow",
        )
        self.feedback_box.place(relwidth=1, rely=0.5, anchor="w", height=self._feedback_line_height)
        self.feedback_box.tag_configure("center", justify="center")
        self.feedback_box.tag_configure("body", font=FEEDBACK_BODY_FONT)
        self.feedback_box.tag_configure("manufacturer", font=FEEDBACK_MANUFACTURER_FONT)
        self.feedback_box.bind("<Button-1>", lambda _event: "break")
        self.feedback_box.bind("<Configure>", self._fit_feedback)

        ttk.Separator(panel, orient="vertical").grid(row=0, column=1, sticky="ns")
        progress = ttk.Frame(panel, style="ScanPanel.TFrame", padding=(17, 2, 0, 0))
        progress.grid(row=0, column=2, sticky="nsew")
        progress.columnconfigure(0, weight=1)
        ttk.Label(progress, text="有效数量", style="ScanMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.amount_label = tk.Label(progress, textvariable=self.progress_amount, background=SURFACE, foreground=TEXT,
                                     font=(UI_FONT, 26, "bold"), anchor="w", padx=0, pady=0)
        self.amount_label.grid(row=1, column=0, sticky="w", pady=(0, 2))
        ttk.Label(progress, textvariable=self.progress_detail, style="ScanMuted.TLabel").grid(
            row=2, column=0, sticky="w",
        )
        self.progress_bar = ttk.Progressbar(progress, mode="determinate")
        self.progress_bar.grid(row=3, column=0, sticky="ew", pady=(10, 0))

    def _build_records(self, parent):
        panel = ttk.Frame(parent)
        panel.grid(row=2, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(panel)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(toolbar, text="条码记录", style="Section.TLabel").pack(side="left")
        ttk.Label(toolbar, textvariable=self.record_summary, style="Muted.TLabel").pack(side="left", padx=(12, 0))
        self.delete_button = ttk.Button(toolbar, text="删除选中", command=self._delete_selected)
        self.delete_button.pack(side="right")
        self.export_button = ttk.Menubutton(toolbar, text="导出记录")
        self.export_button.pack(side="right", padx=7)
        self.export_menu = tk.Menu(self.export_button, tearoff=False)
        self.export_menu.add_command(label="仅通过", command=lambda: self._export(accepted_only=True))
        self.export_menu.add_command(label="全部记录", command=lambda: self._export(accepted_only=False))
        self.export_button.configure(menu=self.export_menu)
        table, self.records_tree = _table(panel, RECORD_COLUMNS, height=DEFAULT_RECORDS_PER_PAGE)
        table.grid(row=1, column=0, sticky="nsew")
        self.records_tree.tag_configure("accepted", foreground=TEXT)
        self.records_tree.tag_configure("duplicate", foreground=WARN, background="#FFFBF2")
        self.records_tree.tag_configure("rejected", foreground=ERROR, background="#FFF6F7")
        self.records_tree.bind("<<TreeviewSelect>>", self._update_record_detail)
        self.records_tree.bind("<ButtonRelease-1>", self._row_action)
        self.records_tree.bind("<Delete>", self._delete_selected)
        self.empty_records = ttk.Label(table, style="WhiteMuted.TLabel")

        detail = self.record_detail_label = ttk.Label(
            panel, textvariable=self.record_detail, style="Muted.TLabel", wraplength=760,
        )
        detail.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        detail.bind("<Configure>", lambda event: detail.configure(wraplength=max(200, event.width)))
        detail.grid_remove()

        pagination = ttk.Frame(panel)
        pagination.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        ttk.Label(pagination, textvariable=self.page_status, style="Muted.TLabel").pack(side="left")
        controls = ttk.Frame(pagination)
        controls.pack(side="right")
        ttk.Label(controls, text="每页条数", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.page_size_box = ttk.Combobox(controls, values=RECORD_PAGE_SIZES, state="readonly", width=5)
        self.page_size_box.set(str(self.settings.records_per_page))
        self.page_size_box.pack(side="left", padx=(0, 12))
        self.page_size_box.bind("<<ComboboxSelected>>", self._change_page_size)
        self.previous_page_button = ttk.Button(
            controls, text="上一页", command=lambda: self._show_record_page(self._record_page - 1),
        )
        self.previous_page_button.pack(side="left", padx=(0, 6))
        self.next_page_button = ttk.Button(
            controls, text="下一页", command=lambda: self._show_record_page(self._record_page + 1),
        )
        self.next_page_button.pack(side="left")

    @property
    def _running(self):
        return self.batch is not None and not self.batch.finished

    def _refresh_manufacturers(self, *_):
        if self.batch is not None:
            return
        code = self.code.get().strip()
        values = self.settings.manufacturers
        if code in self.settings.codes:
            assigned = {row.manufacturer for row in self.settings.rows if row.code == code}
            values = tuple(value for value in values if value in assigned)
        self.manufacturer_box.configure(values=values)
        if self.manufacturer.get() not in values:
            self.manufacturer.set("")

    def _refresh_controls(self):
        available = self._running and not self._paused
        editable = self.batch is None
        has_records = bool(self.batch and self.batch.record_count)
        self.code_entry.state(["!disabled" if editable else "disabled"])
        self.quantity_entry.state(["!disabled" if editable else "disabled"])
        self.manufacturer_box.state(["!disabled" if editable else "disabled"])
        self.scan_entry.state(["!disabled" if available else "disabled"])
        self.export_button.state(["!disabled" if has_records else "disabled"])
        can_delete = available and self.records_tree.selection()
        self.delete_button.state(["!disabled" if can_delete else "disabled"])

    def _refresh_batch(self):
        batch = self.batch
        self.batch_button.configure(text="结束核验" if self._running else "新建批次" if batch else "开始核验")
        if batch is None:
            self.batch_state.configure(text="待开始")
            self.progress_amount.set("0")
            self.progress_detail.set("等待开始核验")
            self.progress_bar.grid_remove()
            self.amount_label.configure(foreground=TEXT)
        else:
            self._refresh_progress(batch)
        total = batch.record_count if batch else 0
        anomalies = total - (batch.count if batch else 0)
        self.record_summary.set(f"共 {total} 条 · 异常 {anomalies} 条" if total else "")
        if total:
            self.empty_records.place_forget()
        else:
            self.empty_records.configure(text="暂无条码记录" if batch else "开始核验后，扫码记录将显示在这里。")
            self.empty_records.place(relx=0.5, rely=0.5, anchor="center")
        self._refresh_pagination()
        self._refresh_controls()

    def _refresh_progress(self, batch):
        self.batch_state.configure(text="已结束 · 数量不足" if batch.finished and batch.remaining else
                                   "已结束" if batch.finished else "核验中")
        if batch.target is None:
            self.progress_amount.set(f"{batch.count} 件")
            self.progress_detail.set("未设应扫数量")
            self.progress_bar.grid_remove()
        else:
            self.progress_amount.set(f"{batch.count} / {batch.target}")
            self.progress_detail.set(f"还差 {batch.remaining} 件" if batch.remaining else "数量已齐")
            self.progress_bar.configure(maximum=batch.target, value=batch.count)
            self.progress_bar.grid()
        self._refresh_amount_color()

    def _refresh_amount_color(self):
        batch = self.batch
        if self._scan_tone != "neutral":
            color = FEEDBACK_COLORS[self._scan_tone][1]
        elif batch and batch.remaining == 0:
            color = SUCCESS
        elif batch and batch.finished and batch.remaining:
            color = WARN
        else:
            color = TEXT
        self.amount_label.configure(foreground=color)

    def _feedback(self, title, message, kind="neutral"):
        background, foreground = FEEDBACK_COLORS[kind]
        self.feedback_panel.configure(background=background)
        self.feedback_box.configure(state="normal", background=background, foreground=foreground)
        self.feedback_box.delete("1.0", "end")
        self.feedback_box.insert("end", f"{title} · " if message else title, ("center", "body"))
        parts = ((message, "body"),) if isinstance(message, str) else message
        for text, tag in parts:
            self.feedback_box.insert("end", text, ("center", tag))
        self.feedback_box.configure(state="disabled")
        self._fit_feedback()
        self.feedback_box.yview_moveto(0)
        tone = kind if kind in SCAN_ALERT_BACKGROUNDS else "neutral"
        if tone != self._scan_tone:
            self._scan_tone = tone
            panel_background = SCAN_ALERT_BACKGROUNDS.get(tone, SURFACE)
            for style in ("ScanPanel.TFrame", "ScanSection.TLabel", "ScanMuted.TLabel"):
                self._style.configure(style, background=panel_background)
            self.amount_label.configure(background=panel_background)
        self._refresh_amount_color()

    def _fit_feedback(self, event=None):
        if event is not None:
            if event.width == self._feedback_width:
                return
            self._feedback_width = event.width
        if self.feedback_box.winfo_width() <= 1:
            return
        line_height = self._feedback_line_height
        content_height = self.feedback_box.count("1.0", "end", "update", "ypixels")
        text_height = min(content_height or line_height, 3 * line_height)
        self.feedback_panel.configure(height=max(line_height + 16, text_height + 10))
        self.feedback_box.place_configure(height=text_height)

    def _sound_exception(self):
        if winsound is not None:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
                return
            except RuntimeError:
                pass
        self.root.bell()

    def _waiting_feedback(self):
        if self.settings.rows:
            self._feedback("待开始", "设置核验目标后点击「开始核验」。")
        else:
            self._feedback("待配置", "请先在设置中添加条码基表记录。")

    def _focus_scan(self, _event=None):
        if self._running and not self._paused:
            self.scan_entry.focus_set()
        return "break"

    @contextmanager
    def _pause_scanning(self):
        self._paused += 1
        self._refresh_controls()
        try:
            yield
        finally:
            self._paused -= 1
            self._refresh_controls()
            if not self._paused:
                self._focus_scan()

    def _batch_action(self):
        if self.batch is None:
            self._start_batch()
        elif self._running:
            self._finish_batch()
        elif self._permit_discard("新建批次"):
            self.batch = None
            self._show_record_page(0)
            self._refresh_manufacturers()
            self._refresh_batch()
            self._waiting_feedback()
            self.code_entry.focus_set()

    def _start_batch(self):
        quantity = self.quantity.get().strip()
        try:
            if quantity and not quantity.isdecimal():
                raise ValueError
            target = int(quantity) if quantity else None
        except ValueError:
            self._feedback("无法开始", "应扫数量须为正整数，或留空。", "error")
            self.quantity_entry.focus_set()
            return
        try:
            batch = Batch(self.settings, self.code.get().strip(), self.manufacturer.get(), target)
        except ValueError as error:
            self._feedback("无法开始", str(error), "error")
            return
        self.batch = batch
        self.code.set(batch.code)
        self.quantity.set(str(batch.target) if batch.target is not None else "")
        self._refresh_batch()
        self._feedback("可以扫码", "请扫描本批第一件物料。", "info")
        self._focus_scan()

    def _finish_batch(self):
        if self.batch.remaining:
            shortage = f"应扫 {self.batch.target} 件，当前有效 {self.batch.count} 件，还差 {self.batch.remaining} 件。"
            self._feedback("数量不足", shortage, "warning")
            self._sound_exception()
            choice = self._dialog(
                "数量不足", "本批数量不足", shortage,
                (("继续扫码", None, "Primary.TButton"), ("结束并标记不足", "finish", "TButton")),
            )
            if choice != "finish":
                return
        self.batch.finish(allow_shortage=True)
        self._show_record_page(self._record_page)
        self.scan_text.set("")
        self._refresh_batch()
        if self.batch.remaining:
            self._feedback("已结束 · 数量不足", f"有效 {self.batch.count} 件，还差 {self.batch.remaining} 件。", "warning")
        else:
            self._feedback("核验结束", f"本批共 {self.batch.count} 件有效记录。", "success")

    def _submit_scan(self, _event=None):
        if not self._running or self._paused:
            return "break"
        barcode = self.scan_text.get()
        self.scan_text.set("")
        if not barcode.strip(BARCODE_INPUT_PADDING):
            return "break"
        record = self.batch.scan(barcode)
        self._show_scanned_record(record)
        self._refresh_batch()
        if record.outcome == Outcome.ACCEPTED:
            self._feedback("核验通过", (
                ("厂家 ", "body"), (record.manufacturer, "manufacturer"), (f" · {record.barcode}", "body"),
            ), "success")
        elif record.outcome == Outcome.WRONG_MANUFACTURER:
            self._feedback("厂家不符", (
                ("应为 ", "body"), (self.batch.manufacturer, "manufacturer"),
                ("，识别为 ", "body"), (record.manufacturer, "manufacturer"), ("。", "body"),
            ), "error")
        elif record.outcome == Outcome.DUPLICATE:
            self._feedback("重复条码", record.detail, "warning")
        else:
            self._feedback(record.outcome, record.detail, "error")
        if record.outcome != Outcome.ACCEPTED:
            self._sound_exception()
        if record.outcome == Outcome.EXCESS:
            self._dialog("超出应扫数量", "超出应扫数量", f"{record.detail}\n本次条码 {record.barcode}",
                         (("继续扫码", None, "Primary.TButton"),), tone="error")
        self._focus_scan()
        return "break"

    def _record_page_count(self):
        total = self.batch.record_count if self.batch else 0
        size = self.settings.records_per_page
        return max(1, (total + size - 1) // size)

    def _refresh_pagination(self):
        total = self.batch.record_count if self.batch else 0
        pages = self._record_page_count()
        offset = self._record_page * self.settings.records_per_page
        visible = f" · {offset + 1}–{min(offset + self.settings.records_per_page, total)} / {total} 条" if total else ""
        self.page_status.set(f"第 {self._record_page + 1} / {pages} 页{visible}")
        self.previous_page_button.state(["!disabled" if self._record_page > 0 else "disabled"])
        self.next_page_button.state(["!disabled" if self._record_page + 1 < pages else "disabled"])

    def _change_page_size(self, _event=None):
        size = int(self.page_size_box.get())
        if size == self.settings.records_per_page:
            return
        try:
            self._save_settings(replace(self.settings, records_per_page=size))
        except (OSError, ValueError) as error:
            self.page_size_box.set(str(self.settings.records_per_page))
            with self._pause_scanning():
                messagebox.showerror("无法保存每页条数", str(error), parent=self.root)
            return
        self._show_record_page(0)
        self._focus_scan()

    def _show_record_page(self, page):
        self._record_page = max(0, min(page, self._record_page_count() - 1))
        selected = self.records_tree.selection()
        self.records_tree.delete(*self.records_tree.get_children())
        self._record_by_iid.clear()
        if self.batch is not None:
            size = self.settings.records_per_page
            for record in self.batch.record_page(self._record_page * size, size):
                self._insert_record(record, "end")
        if selected and selected[0] in self._record_by_iid:
            self.records_tree.selection_set(selected[0])
        self.records_tree.yview_moveto(0)
        self._update_record_detail()
        self._refresh_pagination()

    def _show_scanned_record(self, record):
        if self._record_page:
            self._show_record_page(0)
            return
        self._insert_record(record, 0)
        children = self.records_tree.get_children()
        if len(children) > self.settings.records_per_page:
            self.records_tree.delete(children[-1])
            del self._record_by_iid[children[-1]]
        self.records_tree.yview_moveto(0)

    def _insert_record(self, record, index):
        tag = "accepted" if record.outcome == Outcome.ACCEPTED else "duplicate" if record.outcome == Outcome.DUPLICATE else "rejected"
        iid = str(record.id)
        self._record_by_iid[iid] = record
        self.records_tree.insert("", index, iid=iid, tags=(tag,), values=(
            record.barcode, record.manufacturer or "—", f"{record.recorded_at:%H:%M:%S}",
            record.outcome, record.detail, "删除" if self._running else "",
        ))

    def _update_record_detail(self, _event=None):
        selected = self.records_tree.selection()
        record = self._record_by_iid.get(selected[0]) if selected else None
        if record:
            manufacturer = f"  ·  厂家 {record.manufacturer}" if record.manufacturer else ""
            self.record_detail.set(f"{record.barcode}{manufacturer}  ·  {record.outcome}  ·  {record.detail}")
            self.record_detail_label.grid()
        else:
            self.record_detail.set("")
            self.record_detail_label.grid_remove()
        self._refresh_controls()

    def _row_action(self, event):
        column = self.records_tree.identify_column(event.x)
        if self._running and column and self.records_tree.column(column, "id") == "action":
            iid = self.records_tree.identify_row(event.y)
            if iid:
                self._delete_record(iid)
                return "break"
        return None

    def _delete_selected(self, _event=None):
        selection = self.records_tree.selection()
        if selection and self._running:
            self._delete_record(selection[0])
        return "break"

    def _delete_record(self, iid):
        record = self._record_by_iid[iid]
        choice = self._dialog(
            "删除条码记录", "删除这条记录？", f"条码 {record.barcode}\n删除后将更新本批有效数量。",
            (("取消", None, "TButton"), ("删除记录", "delete", "Danger.TButton")),
        )
        if choice == "delete":
            self.batch.delete(record.id)
            self._show_record_page(self._record_page)
            self._refresh_batch()
            self._feedback("已删除记录", "可以继续扫码。", "info")

    def _export(self, *, accepted_only):
        if not self.batch or not self.batch.record_count:
            return False
        with self._pause_scanning():
            title = "导出通过记录" if accepted_only else "导出全部记录"
            filename = filedialog.asksaveasfilename(
                parent=self.root, title=title, initialfile="条码核验记录.csv", defaultextension=".csv",
                filetypes=(("CSV 文件", "*.csv"),),
            )
            if not filename:
                return False
            try:
                export_records(Path(filename), self.batch, accepted_only=accepted_only)
            except (OSError, csv.Error) as error:
                messagebox.showerror("导出失败", str(error), parent=self.root)
                return False
            self._feedback("记录已导出", Path(filename).name, "success")
            return True

    def _open_settings(self):
        from .settings_ui import SettingsWindow

        with self._pause_scanning():
            window = SettingsWindow(self.root, self.settings, self._save_settings)
            window.wait_visibility()
            window.grab_set()
            self.root.wait_window(window)
        if self.batch is None and self.settings.rows:
            self.code_entry.focus_set()

    def _save_settings(self, settings):
        self.store.save(settings)
        self.settings = settings
        self._refresh_manufacturers()
        if self.batch is None:
            self._waiting_feedback()

    def _permit_discard(self, action):
        if not self.batch or not self.batch.record_count:
            return True
        choice = self._dialog(
            action, "本批还有记录", f"本批有 {self.batch.record_count} 条记录。{action}前可以导出全部记录。",
            (("取消", None, "TButton"), (f"直接{action}", "discard", "TButton"),
             ("导出并继续", "export", "Primary.TButton")),
        )
        return choice == "discard" or (choice == "export" and self._export(accepted_only=False))

    def _close(self):
        if not self._paused and self._permit_discard("关闭"):
            self.root.destroy()

    def _dialog(self, title, heading, message, actions, *, tone="neutral"):
        with self._pause_scanning():
            dialog = tk.Toplevel(self.root, background=SURFACE)
            dialog.withdraw()
            dialog.title(title)
            dialog.transient(self.root)
            dialog.resizable(False, False)
            body = ttk.Frame(dialog, padding=17, style="White.TFrame")
            body.pack(fill="both", expand=True)
            ttk.Label(body, text=heading, style="WhiteSection.TLabel", foreground=FEEDBACK_COLORS[tone][1]).pack(anchor="w")
            ttk.Label(body, text=message, style="White.TLabel", wraplength=410,
                      justify="left").pack(anchor="w", pady=(6, 0))
            selected = None

            def close(value=None):
                nonlocal selected
                selected = value
                dialog.destroy()

            buttons = ttk.Frame(body, style="White.TFrame")
            buttons.pack(side="bottom", anchor="e", pady=(14, 0))
            for text, value, style in actions:
                button = ttk.Button(buttons, text=text, style=style, command=lambda choice=value: close(choice))
                button.pack(side="left", padx=(6, 0))
            dialog.protocol("WM_DELETE_WINDOW", close)
            dialog.bind("<Escape>", lambda _event: close())
            # Initial focus stays off the buttons so barcode keystrokes cannot activate them.
            dialog.bind("<Return>", lambda _event: "break")
            dialog.bind("<KP_Enter>", lambda _event: "break")
            dialog.update_idletasks()
            width = max(dialog.winfo_reqwidth(), 360)
            height = dialog.winfo_reqheight()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
            dialog.geometry(f"{width}x{height}{x:+d}{y:+d}")
            dialog.deiconify()
            dialog.wait_visibility()
            dialog.grab_set()
            dialog.focus_set()
            self.root.wait_window(dialog)
            return selected
