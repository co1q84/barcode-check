import csv
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import font, ttk
from unittest.mock import patch

from openpyxl import load_workbook

from barcode_check.app import BarcodeCheckApp
from barcode_check.batch import Outcome
from barcode_check.settings import BaseRow, Settings, SettingsReadError, SettingsSaveCancelled, SettingsStore


class MainWindowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        store = SettingsStore(self.folder / "settings.json")
        store.save(Settings((BaseRow("001", "甲厂", "00"), BaseRow("001", "乙厂", "02"), BaseRow("002", "甲厂", "03"))))
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.app = BarcodeCheckApp(self.root, store=store)
        sound = patch("barcode_check.app.winsound", create=True)
        self.windows_sound = sound.start()
        self.addCleanup(sound.stop)
        self.root.update()

    def start(self, quantity=""):
        self.app.code.set("001")
        self.app.manufacturer.set("甲厂")
        self.app.quantity.set(quantity)
        self.app.batch_button.invoke()
        self.root.update()

    def scan(self, barcode, *, acknowledge=False):
        if acknowledge:
            self.root.after(70, self.press_dialog_button, "继续扫码")
        self.app.scan_entry.focus_force()
        self.app.scan_entry.insert(0, barcode)
        self.app.scan_entry.event_generate("<Return>")
        self.root.update()
        if acknowledge:
            self.assertTrue(self.dialog_found)

    def scan_for_sorting(self, barcode):
        entry = self.app.sorting_page.scan_entry
        entry.focus_force()
        entry.insert(0, barcode)
        entry.event_generate("<Return>")
        self.root.update()

    def press_dialog_button(self, title):
        def find(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, ttk.Button) and widget.cget("text") == title:
                    widget.invoke()
                    return True
                if find(widget):
                    return True
            return False

        if not find(self.root):
            self.dialog_found = False
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Toplevel):
                    widget.destroy()
        else:
            self.dialog_found = True

    def test_scan_enter_updates_count_and_newest_first_then_restores_focus(self):
        self.start("3")
        self.scan("0001")
        self.scan("0002")
        self.scan("0001", acknowledge=True)
        rows = self.app.records_tree.get_children()
        self.assertNotIn("source", self.app.records_tree["columns"])
        self.assertEqual([self.app.records_tree.set(row, "number") for row in rows], ["3", "2", "1"])
        self.assertEqual(self.app.records_tree.set(rows[0], "result"), Outcome.DUPLICATE)
        self.assertEqual(self.app.records_tree.set(rows[1], "barcode"), "0002")
        self.assertEqual(self.app.records_tree.set(rows[1], "manufacturer"), "甲厂")
        self.assertEqual(self.app.batch.count, 2)
        self.assertEqual(self.app.progress_detail.get(), "还差 1 件")
        self.assertEqual(self.root.focus_get(), self.app.scan_entry)

    def test_sorting_recognizes_without_blocking_and_updates_grouped_summary(self):
        sorting = self.app.sorting_page
        self.root.geometry("820x580")
        self.app.mode_tabs.select(sorting)
        self.root.update()
        self.assertLessEqual(abs(sorting.scan_region.winfo_width() - sorting.summary_region.winfo_width()), 1)
        self.assertTrue(sorting.summary_tree.winfo_ismapped())
        self.assertTrue(sorting.records_tree.winfo_ismapped())
        self.assertEqual(
            [sorting.summary_tree.heading(column, "text") for column in sorting.summary_tree["columns"]],
            ["编码", "厂家", "数量"],
        )
        sorting.batch_button.invoke()
        self.root.update()
        for barcode in ("0001", "0201", "0301"):
            self.scan_for_sorting(barcode)
        self.assertEqual((sorting.manufacturer_text.get(), sorting.code_text.get()), ("甲厂", "002"))
        self.assertEqual(sorting.summary_tree.item(sorting.summary_tree.selection()[0], "values"), ("002", "甲厂", "1"))

        self.scan_for_sorting("0001")
        self.assertEqual((sorting.manufacturer_text.get(), sorting.code_text.get()), ("甲厂", "001"))
        self.assertEqual(sorting.result_status.get(), "本批已扫过")
        self.scan_for_sorting("9999")
        self.assertEqual((sorting.manufacturer_text.get(), sorting.code_text.get()), ("未识别", "—"))
        self.assertEqual(sorting.total_text.get(), "5 次")
        self.assertEqual(sorting.pending_text.get(), "待确认 1 次")
        self.assertEqual(sorting.summary_total.get(), "合计 3 件")
        self.assertEqual([
            sorting.summary_tree.item(row, "values") for row in sorting.summary_tree.get_children()
        ], [("001", "甲厂", "1"), ("001", "乙厂", "1"), ("002", "甲厂", "1")])
        self.assertEqual(sorting.records_tree.set(sorting.records_tree.get_children()[0], "result"), "待确认")
        self.assertIsNone(self.root.grab_current())
        self.assertEqual(self.root.focus_get(), sorting.scan_entry)
        self.windows_sound.MessageBeep.assert_not_called()

    def test_sorting_manufacturer_and_code_share_center_in_all_result_states(self):
        sorting = self.app.sorting_page
        self.root.geometry("820x580")
        self.app.mode_tabs.select(sorting)
        self.root.update()
        sorting.batch_button.invoke()

        def center_x(widget):
            return widget.winfo_rootx() + widget.winfo_width() / 2

        for barcode in ("0001", "0001", "9999"):
            with self.subTest(barcode=barcode, total=sorting.total_text.get()):
                self.scan_for_sorting(barcode)
                panel = sorting.result_panel
                manufacturer = sorting.manufacturer_label
                code = sorting.code_label
                for label in (manufacturer, code):
                    self.assertAlmostEqual(center_x(label), center_x(panel), delta=1)
                group_center_y = (manufacturer.winfo_rooty() + code.winfo_rooty() + code.winfo_height()) / 2
                panel_center_y = panel.winfo_rooty() + panel.winfo_height() / 2
                self.assertAlmostEqual(group_center_y, panel_center_y, delta=1)

    def test_sorting_detail_pagination_and_independent_batch_on_mode_switch(self):
        self.start()
        self.scan("0001")
        sorting = self.app.sorting_page
        self.app.mode_tabs.select(sorting)
        self.root.update()
        sorting.batch_button.invoke()
        for number in range(1, 22):
            self.scan_for_sorting(f"00{number:03d}")
        self.root.update()
        tree = sorting.records_tree
        self.assertTrue(sorting.next_page_button.winfo_ismapped())
        self.assertEqual([tree.set(row, "number") for row in tree.get_children()], list(map(str, range(21, 1, -1))))
        sorting.next_page_button.invoke()
        self.assertEqual([tree.set(row, "number") for row in tree.get_children()], ["1"])
        self.root.update()
        x, y, width, height = tree.bbox(tree.get_children()[0], "action")
        confirm = self.root.after(120, self.press_dialog_button, "删除记录")
        try:
            tree.event_generate("<ButtonRelease-1>", x=x + width // 2, y=y + height // 2)
        finally:
            self.root.after_cancel(confirm)
        self.assertTrue(self.dialog_found)
        self.assertTrue(sorting.next_page_button.instate(["disabled"]))
        self.assertEqual(tree.set(tree.get_children()[-1], "number"), "1")
        self.scan_for_sorting("00001")
        sorting.next_page_button.invoke()
        self.scan_for_sorting("00022")
        self.assertEqual(tree.set(tree.get_children()[0], "number"), "22")

        self.app.mode_tabs.select(self.app.validation_page)
        self.root.update()
        self.assertEqual(self.app.batch.count, 1)
        self.assertEqual(self.root.focus_get(), self.app.scan_entry)
        self.app.mode_tabs.select(sorting)
        self.root.update()
        self.assertEqual(sorting.total_text.get(), "22 次")
        self.assertEqual(self.root.focus_get(), sorting.scan_entry)
        sorting.page_size_box.set("50")
        sorting.page_size_box.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(len(tree.get_children()), 22)
        self.assertEqual(self.app.page_size_box.get(), "50")
        self.assertEqual(SettingsStore(self.folder / "settings.json").load().records_per_page, 50)

        sorting.batch_button.invoke()
        self.assertTrue(sorting.scan_entry.instate(["disabled"]))
        self.assertEqual(sorting.summary_total.get(), "合计 22 件")
        with patch("barcode_check.sorting_ui.messagebox.askyesno", side_effect=(False, True)):
            sorting.batch_button.invoke()
            self.assertEqual(sorting.summary_total.get(), "合计 22 件")
            sorting.batch_button.invoke()
        self.assertTrue(sorting.scan_entry.instate(["!disabled"]))
        self.assertEqual(sorting.summary_total.get(), "合计 0 件")
        self.assertEqual(sorting.summary_tree.get_children(), ())
        self.assertTrue(sorting.records_tree.winfo_ismapped())
        self.assertEqual(self.app.batch.count, 1)

    def test_next_scan_after_mouse_pagination_in_either_mode(self):
        self.start()
        sorting = self.app.sorting_page
        for page, scan in ((self.app, self.scan), (sorting, self.scan_for_sorting)):
            with self.subTest(page=type(page).__name__):
                if page is sorting:
                    self.app.mode_tabs.select(sorting)
                    self.root.update()
                    sorting.batch_button.invoke()
                for number in range(1, 22):
                    scan(f"00{number:03d}")

                button = page.next_page_button
                x, y = button.winfo_width() // 2, button.winfo_height() // 2
                button.event_generate("<Enter>", x=x, y=y)
                button.event_generate("<ButtonPress-1>", x=x, y=y)
                button.event_generate("<ButtonRelease-1>", x=x, y=y)
                self.root.update()
                self.assertEqual(page._record_page, 1)
                focused = self.root.focus_get()
                for key in "00022":
                    focused.event_generate(f"<KeyPress-{key}>")
                focused.event_generate("<Return>")
                self.root.update()
                self.assertEqual(page.batch.record_count, 22)
                self.assertEqual(page._record_page, 0)

    def test_sorting_deleting_rows_recounts_summary_and_releases_barcode(self):
        sorting = self.app.sorting_page
        self.app.mode_tabs.select(sorting)
        self.root.update()
        sorting.batch_button.invoke()
        for barcode in ("0001", "0001", "9999"):
            self.scan_for_sorting(barcode)
        tree = sorting.records_tree
        for expected_total, expected_pending, expected_summary in ((2, 0, 1), (1, 0, 1), (0, 0, 0)):
            tree.selection_set(tree.get_children()[-1 if expected_total == 1 else 0])
            self.root.update()
            confirm = self.root.after(120, self.press_dialog_button, "删除记录")
            try:
                sorting.delete_button.invoke()
            finally:
                self.root.after_cancel(confirm)
            self.assertTrue(self.dialog_found)
            self.assertEqual(sorting.total_text.get(), f"{expected_total} 次")
            self.assertEqual(sorting.pending_text.get(), f"待确认 {expected_pending} 次")
            self.assertEqual(sorting.summary_total.get(), f"合计 {expected_summary} 件")
            self.assertEqual([tree.set(iid, "number") for iid in tree.get_children()],
                             [str(number) for number in range(expected_total, 0, -1)])
            if expected_total == 1:
                self.assertEqual(tree.set(tree.get_children()[0], "result"), "已识别")
        self.assertEqual(sorting.summary_tree.get_children(), ())
        self.scan_for_sorting("0001")
        self.assertEqual(sorting.summary_total.get(), "合计 1 件")

    def test_sorting_export_includes_all_pages_of_details(self):
        sorting = self.app.sorting_page
        self.app.mode_tabs.select(sorting)
        self.root.update()
        sorting.batch_button.invoke()
        for number in range(1, 22):
            self.scan_for_sorting(f"00{number:03d}")
        sorting.next_page_button.invoke()
        self.assertEqual(len(sorting.records_tree.get_children()), 1)
        sorting.batch_button.invoke()
        output = self.folder / "sorting.csv"
        with patch("barcode_check.sorting_ui.filedialog.asksaveasfilename", return_value=str(output)):
            sorting.export_button.invoke()
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 21)
        self.assertEqual((rows[0]["序号"], rows[0]["条码"], rows[0]["厂家"], rows[0]["物料编码"]),
                         ("21", "00021", "甲厂", "001"))
        self.assertEqual((rows[-1]["序号"], rows[-1]["条码"]), ("1", "00001"))

    def test_each_scan_exception_blocks_input_until_acknowledged(self):
        self.start("1")
        self.scan("0001")
        for barcode, outcome in (
            ("00\n01", Outcome.INVALID), ("9999", Outcome.UNKNOWN), ("0301", Outcome.WRONG_CODE),
            ("0201", Outcome.WRONG_MANUFACTURER), ("0001", Outcome.DUPLICATE), ("0002", Outcome.EXCESS),
        ):
            with self.subTest(outcome=outcome):
                observations = []

                def acknowledge():
                    dialog = self.root.grab_current()
                    observations.append((isinstance(dialog, tk.Toplevel), self.app.scan_entry.instate(["disabled"])))
                    self.press_dialog_button("继续扫码")

                callback = self.root.after(70, acknowledge)
                try:
                    self.scan(barcode)
                finally:
                    self.root.after_cancel(callback)
                self.assertEqual(observations, [(True, True)])
                self.assertTrue(self.dialog_found)
                self.assertEqual(self.app.batch.count, 1)
                self.assertEqual(self.app.batch.records[0].outcome, outcome)
                self.assertEqual(self.root.focus_get(), self.app.scan_entry)
        self.assertEqual(self.windows_sound.MessageBeep.call_count, 6)

    def test_warning_flashes_and_ignores_scanner_keys_and_window_close(self):
        self.start("1")
        self.scan("0001")
        observations = {}

        def check_while_blocked():
            dialog = self.root.grab_current()
            if dialog is None:
                return
            body = dialog.winfo_children()[0]
            heading = body.winfo_children()[0]
            actions = body.winfo_children()[-1]
            button = actions.winfo_children()[0]
            observations["first_color"] = heading.cget("background")
            observations["settings_appearance"] = self.app.settings_button.instate(["!disabled"])
            with patch("barcode_check.settings_ui.SettingsWindow") as settings_window:
                self.app.settings_button.invoke()
            observations["settings_opened"] = settings_window.called
            button.focus_force()
            for key in ("<KeyPress-0>", "<space>", "<Return>", "<KP_Enter>", "<Escape>"):
                if dialog.winfo_exists():
                    button.event_generate(key)
            if dialog.winfo_exists():
                self.root.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
            observations["still_blocked"] = (
                bool(dialog.winfo_exists()), self.app.scan_entry.instate(["disabled"]), self.app.scan_text.get(),
            )
            if dialog.winfo_exists():
                def confirm_after_flash():
                    observations["second_color"] = heading.cget("background")
                    button.event_generate("<Control-Return>")

                self.root.after(850, confirm_after_flash)

        check = self.root.after(70, check_while_blocked)
        fallback = self.root.after(1800, self.press_dialog_button, "继续扫码")
        try:
            self.scan("0002")
        finally:
            self.root.after_cancel(check)
            self.root.after_cancel(fallback)
        self.assertEqual(observations["still_blocked"], (True, True, ""))
        self.assertTrue(observations["settings_appearance"])
        self.assertFalse(observations["settings_opened"])
        self.assertNotEqual(observations["first_color"], observations["second_color"])
        self.assertFalse(getattr(self, "dialog_found", False))
        self.assertEqual(self.app.batch.record_count, 2)
        self.assertEqual(self.root.focus_get(), self.app.scan_entry)
        self.windows_sound.MessageBeep.assert_called_once_with(self.windows_sound.MB_ICONHAND)

    def test_scan_exception_highlights_both_sections_and_plays_windows_sound_once(self):
        self.start("3")
        self.scan("0001")
        style = ttk.Style(self.root)

        def backgrounds():
            return (
                style.lookup(self.app.scan_panel.cget("style"), "background"),
                str(self.app.amount_label.cget("background")),
            )

        normal = backgrounds()
        self.scan("9999", acknowledge=True)
        error = backgrounds()
        self.assertNotEqual(error, normal)
        self.assertEqual(error[0], error[1])
        self.windows_sound.MessageBeep.assert_called_once_with(self.windows_sound.MB_ICONHAND)
        self.scan("0001", acknowledge=True)
        self.assertNotEqual(backgrounds(), normal)
        self.assertNotEqual(backgrounds(), error)
        self.assertEqual(self.windows_sound.MessageBeep.call_count, 2)
        self.scan("0002")
        self.assertEqual(backgrounds(), normal)
        self.assertEqual(self.windows_sound.MessageBeep.call_count, 2)

    def test_warning_sound_plays_after_the_centered_dialog_owns_input(self):
        self.start()
        observations = []

        def check_sound(_kind):
            dialog = self.root.grab_current()
            if not isinstance(dialog, tk.Toplevel):
                observations.append(None)
                return
            owner_x = self.root.winfo_rootx() + self.root.winfo_width() / 2
            owner_y = self.root.winfo_rooty() + self.root.winfo_height() / 2
            dialog_x = dialog.winfo_rootx() + dialog.winfo_width() / 2
            dialog_y = dialog.winfo_rooty() + dialog.winfo_height() / 2
            observations.append((dialog.winfo_viewable(), abs(owner_x - dialog_x), abs(owner_y - dialog_y)))

        self.windows_sound.MessageBeep.side_effect = check_sound
        self.scan("NOT-RECOGNIZED", acknowledge=True)
        self.assertEqual(len(observations), 1)
        self.assertIsNotNone(observations[0])
        visible, dx, dy = observations[0]
        self.assertTrue(visible)
        self.assertLessEqual(max(dx, dy), 2)

    def test_scan_feedback_emphasizes_manufacturer_names_on_match_and_mismatch(self):
        self.start("3")
        self.scan("0001")
        feedback = self.app.feedback_box

        def emphasized_names():
            ranges = feedback.tag_ranges("manufacturer")
            return [feedback.get(start, end) for start, end in zip(ranges[::2], ranges[1::2])]

        self.assertIn("核验通过 · 厂家 甲厂", feedback.get("1.0", "end-1c"))
        self.assertEqual(emphasized_names(), ["甲厂"])
        self.scan("0201", acknowledge=True)
        self.assertIn("厂家不符 · 应为 甲厂，识别为 乙厂", feedback.get("1.0", "end-1c"))
        self.assertEqual(emphasized_names(), ["甲厂", "乙厂"])
        emphasis = font.Font(root=self.root, font=feedback.tag_cget("manufacturer", "font"))
        normal = font.Font(root=self.root, font=feedback.tag_cget("body", "font"))
        self.assertEqual(emphasis.actual("weight"), "bold")
        self.assertGreater(emphasis.actual("size"), normal.actual("size"))
        self.assertGreaterEqual(normal.actual("size"), 18)
        self.assertEqual(feedback.tag_cget("center", "justify"), "center")
        panel = feedback.master
        self.assertLessEqual(abs(2 * feedback.winfo_y() + feedback.winfo_height() - panel.winfo_height()), 2)
        feedback.event_generate("<Button-1>", x=15, y=10)
        self.assertEqual(self.root.focus_get(), self.app.scan_entry)

    def test_delete_record_from_its_action_cell_and_refill_quantity(self):
        self.start("2")
        self.scan("0001")
        self.root.update()
        tree = self.app.records_tree
        x, y, width, height = tree.bbox(tree.get_children()[0], "action")
        self.root.after(100, self.press_dialog_button, "删除记录")
        tree.event_generate("<ButtonRelease-1>", x=x + width // 2, y=y + height // 2)
        self.assertTrue(self.dialog_found)
        self.assertEqual(self.app.batch.count, 0)
        self.scan("0001")
        self.assertEqual(self.app.batch.records[0].outcome, Outcome.ACCEPTED)

    def test_long_barcode_keeps_record_detail_and_delete_confirmation_in_view(self):
        self.start()
        barcode = "00" + "A" * 2000
        self.scan(barcode)
        tree = self.app.records_tree
        unselected_height = tree.winfo_height()
        tree.selection_set(tree.get_children()[0])
        self.root.update()
        observations = []

        def check_confirmation():
            dialog = next(window for window in self.root.winfo_children() if isinstance(window, tk.Toplevel))
            observations.append((dialog.winfo_ismapped(), dialog.winfo_height() < self.root.winfo_height()))
            self.press_dialog_button("删除记录")

        self.root.after(100, check_confirmation)
        self.app.delete_button.invoke()
        self.assertEqual(observations, [(True, True)])
        self.assertTrue(self.dialog_found)
        self.assertEqual(self.app.batch.record_count, 0)
        self.scan(barcode)
        tree.selection_set(tree.get_children()[0])
        self.root.update()
        self.assertGreater(tree.winfo_height(), unselected_height - 90)
        detail = self.app.record_detail
        self.assertIn(barcode, detail.get("1.0", "end-1c"))
        detail.yview_scroll(1, "pages")
        self.assertNotEqual(detail.index("@0,0"), "1.0")

    def test_export_includes_records_from_other_pages(self):
        self.start()
        self.scan("0001")
        for number in range(2, 22):
            self.scan(f"00{number:03d}")
        self.app.next_page_button.invoke()
        self.assertEqual(len(self.app.records_tree.get_children()), 1)
        output = self.folder / "output.csv"
        with patch("barcode_check.app.filedialog.asksaveasfilename", return_value=str(output)):
            self.app.export_menu.invoke(1)
        exported = output.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(len(exported), 22)
        self.assertTrue(exported[1].startswith("00021,"))
        self.assertTrue(exported[-1].startswith("0001,"))

    def test_both_modes_default_to_excel_workbooks_with_text_barcodes(self):
        self.start()
        barcode = "0001234567890123456789"
        self.scan(barcode)
        sorting = self.app.sorting_page
        self.app.mode_tabs.select(sorting)
        self.root.update()
        sorting.batch_button.invoke()
        self.scan_for_sorting(barcode)

        for export, column, module in (
            (lambda: self.app.export_menu.invoke(0), "A", "app"), (sorting.export_button.invoke, "B", "sorting_ui"),
        ):
            with self.subTest(mode=module):
                if module == "app":
                    self.app.mode_tabs.select(self.app.validation_page)
                else:
                    self.app.mode_tabs.select(sorting)
                self.root.update()
                output = self.folder / f"{module}.xlsx"
                with patch(f"barcode_check.{module}.filedialog.asksaveasfilename", return_value=str(output)) as dialog:
                    export()
                self.assertEqual(dialog.call_args.kwargs["defaultextension"], ".xlsx")
                workbook = load_workbook(output)
                try:
                    cell = workbook.active[f"{column}2"]
                    self.assertEqual((cell.value, cell.data_type), (barcode, "s"))
                finally:
                    workbook.close()

    def test_shortage_can_return_to_scan_then_finish_with_shortage(self):
        self.start("2")
        self.scan("0001")
        self.root.after(100, self.press_dialog_button, "继续扫码")
        self.app.batch_button.invoke()
        self.assertTrue(self.dialog_found)
        self.assertFalse(self.app.batch.finished)
        self.root.after(100, self.press_dialog_button, "结束并标记不足")
        self.app.batch_button.invoke()
        self.assertTrue(self.dialog_found)
        self.assertTrue(self.app.batch.finished)
        self.assertEqual(self.app.batch.remaining, 1)
        self.assertEqual(self.windows_sound.MessageBeep.call_count, 2)

    def test_settings_suspends_scanning_and_owns_focus_until_closed(self):
        self.start()
        settings_button = self.app.settings_button
        sorting = self.app.sorting_page
        for page, scan_entry in ((self.app.validation_page, self.app.scan_entry), (sorting, sorting.scan_entry)):
            with self.subTest(page=str(page)):
                self.app.mode_tabs.select(page)
                if page is sorting:
                    sorting.batch_button.invoke()
                self.root.update()
                self.assertLessEqual(settings_button.winfo_rooty() + settings_button.winfo_height(), page.winfo_rooty())
                scan_entry.focus_force()
                observations = []

                def close_settings(retries=60):
                    window = next(widget for widget in self.root.winfo_children() if isinstance(widget, tk.Toplevel))
                    grabbed = self.root.grab_current() is window
                    if not grabbed and retries:
                        self.root.after(25, close_settings, retries - 1)
                        return
                    owner_x = self.root.winfo_rootx() + self.root.winfo_width() / 2
                    owner_y = self.root.winfo_rooty() + self.root.winfo_height() / 2
                    window_x = window.winfo_rootx() + window.winfo_width() / 2
                    window_y = window.winfo_rooty() + window.winfo_height() / 2
                    centered = abs(owner_x - window_x) <= 2 and abs(owner_y - window_y) <= 2
                    observations.append((grabbed, scan_entry.instate(["disabled"]), centered))
                    window.destroy()

                close = self.root.after(50, close_settings)
                try:
                    settings_button.invoke()
                finally:
                    self.root.after_cancel(close)
                self.root.update()
                self.assertEqual(observations, [(True, True, True)])
                self.assertTrue(scan_entry.instate(["!disabled"]))
                self.assertEqual(self.root.focus_get(), scan_entry)

    def test_invalid_settings_recovery_requires_confirmation_and_keeps_original(self):
        path = self.folder / "legacy.json"
        original = b'{"version":1}'
        path.write_bytes(original)
        store = SettingsStore(path)
        with self.assertRaises(SettingsReadError):
            store.load()
        self.app.store = store

        with patch("barcode_check.app.messagebox.askyesno", side_effect=(False, True)) as confirm, patch(
            "barcode_check.app.messagebox.showinfo"
        ) as saved, patch("barcode_check.app.messagebox.showerror") as error:
            self.assertFalse(self.app._save_page_size(50))
            self.assertEqual(path.read_bytes(), original)
            confirm.assert_not_called()
            error.assert_called_once()

            with self.assertRaises(SettingsSaveCancelled):
                self.app._save_settings(self.app.settings, allow_recovery=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(self.folder.glob("legacy-backup-*.json")), [])
            self.app._save_settings(self.app.settings, allow_recovery=True)

        self.assertEqual(confirm.call_count, 2)
        saved.assert_called_once()
        backups = list(self.folder.glob("legacy-backup-*.json"))
        self.assertEqual([backup.read_bytes() for backup in backups], [original])
        self.assertEqual(SettingsStore(path).load(), self.app.settings)

    def test_new_batch_keeps_records_if_export_is_canceled(self):
        self.start()
        self.scan("0001")
        self.app.batch_button.invoke()
        self.root.after(100, self.press_dialog_button, "导出并继续")
        with patch("barcode_check.app.filedialog.asksaveasfilename", return_value=""):
            self.app.batch_button.invoke()
        self.assertTrue(self.dialog_found)
        self.assertEqual(self.app.batch.records[0].barcode, "0001")

        self.root.after(100, self.press_dialog_button, "直接新建批次")
        self.app.batch_button.invoke()
        self.assertTrue(self.dialog_found)
        self.assertIsNone(self.app.batch)
        self.assertEqual(self.app.records_tree.get_children(), ())
        self.start()
        self.scan("0001")
        self.assertEqual(self.app.batch.records[0].outcome, Outcome.ACCEPTED)

    def test_record_pagination_keeps_newest_first_and_handles_deleted_last_page(self):
        self.assertEqual(tuple(map(str, self.app.page_size_box["values"])), ("20", "50", "100"))
        self.assertEqual(int(self.app.records_tree["height"]), 20)
        self.assertEqual(self.app.page_size_box.get(), "20")
        self.app.page_size_box.set("50")
        self.app.page_size_box.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(SettingsStore(self.folder / "settings.json").load().records_per_page, 50)
        self.app.page_size_box.set("20")
        self.app.page_size_box.event_generate("<<ComboboxSelected>>")
        self.root.update()

        self.start()
        for number in range(1, 22):
            self.scan(f"00{number:03d}")

        tree = self.app.records_tree
        self.assertEqual(tree.heading("number", "text"), "序号")
        for column in tree["columns"]:
            self.assertEqual(str(tree.heading(column, "anchor")), "center")
            self.assertEqual(str(tree.column(column, "anchor")), "center")

        def visible_records():
            return [(int(tree.set(row, "number")), tree.set(row, "barcode")) for row in tree.get_children()]

        self.assertEqual(visible_records(), [(number, f"00{number:03d}") for number in range(21, 1, -1)])
        self.assertEqual(self.app.page_status.get(), "第 1 / 2 页  ·  序号 21–2")
        self.app.next_page_button.invoke()
        self.assertEqual(visible_records(), [(1, "00001")])
        self.assertEqual(self.app.page_status.get(), "第 2 / 2 页  ·  序号 1")

        self.app.page_size_box.set("50")
        self.app.page_size_box.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(visible_records(), [(number, f"00{number:03d}") for number in range(21, 0, -1)])
        self.assertTrue(self.app.next_page_button.instate(["disabled"]))
        self.app.page_size_box.set("20")
        self.app.page_size_box.event_generate("<<ComboboxSelected>>")
        self.root.update()

        self.app.next_page_button.invoke()
        self.app.previous_page_button.invoke()
        self.assertEqual(visible_records()[0], (21, "00021"))
        self.app.next_page_button.invoke()
        self.scan("00022")
        self.assertEqual(visible_records()[0], (22, "00022"))

        self.app.next_page_button.invoke()
        self.assertEqual(visible_records(), [(2, "00002"), (1, "00001")])
        for remaining in ([(1, "00001")], [(number, f"00{number + 2:03d}") for number in range(20, 0, -1)]):
            tree.selection_set(tree.get_children()[0])
            self.root.update()
            self.root.after(100, self.press_dialog_button, "删除记录")
            self.app.delete_button.invoke()
            self.assertTrue(self.dialog_found)
            self.assertEqual(visible_records(), remaining)
        self.assertTrue(self.app.next_page_button.instate(["disabled"]))
        self.assertEqual(self.app.batch.count, 20)
