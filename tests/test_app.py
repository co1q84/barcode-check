import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import font, ttk
from unittest.mock import patch

from barcode_check.app import BarcodeCheckApp
from barcode_check.batch import Outcome
from barcode_check.settings import BaseRow, Settings, SettingsStore


class MainWindowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        store = SettingsStore(self.folder / "settings.json")
        store.save(Settings((BaseRow("001", "甲厂", "00"), BaseRow("001", "乙厂", "02"))))
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

    def scan(self, barcode):
        self.app.scan_entry.focus_force()
        self.app.scan_entry.insert(0, barcode)
        self.app.scan_entry.event_generate("<Return>")
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
        self.scan("0001")
        rows = self.app.records_tree.get_children()
        self.assertNotIn("source", self.app.records_tree["columns"])
        self.assertEqual(self.app.records_tree.set(rows[0], "result"), Outcome.DUPLICATE)
        self.assertEqual(self.app.records_tree.set(rows[1], "barcode"), "0002")
        self.assertEqual(self.app.records_tree.set(rows[1], "manufacturer"), "甲厂")
        self.assertEqual(self.app.batch.count, 2)
        self.assertEqual(self.app.progress_detail.get(), "还差 1 件")
        self.assertEqual(self.root.focus_get(), self.app.scan_entry)

    def test_overflow_opens_dialog_without_counting_and_returns_focus(self):
        self.start("1")
        self.scan("0001")
        observations = []

        def scan_suffix_in_dialog():
            focused = self.root.focus_get()
            focused.event_generate("<space>")
            if focused.winfo_exists():
                focused.event_generate("<Return>")
            self.root.update_idletasks()
            observations.append(any(isinstance(widget, tk.Toplevel) for widget in self.root.winfo_children()))

        self.root.after(60, scan_suffix_in_dialog)
        self.root.after(200, self.press_dialog_button, "继续扫码")
        self.scan("0002")
        self.assertTrue(self.dialog_found)
        self.assertEqual(observations, [True])
        self.assertEqual(self.app.batch.count, 1)
        self.assertEqual(self.app.batch.records[0].outcome, Outcome.EXCESS)
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
        self.scan("9999")
        error = backgrounds()
        self.assertNotEqual(error, normal)
        self.assertEqual(error[0], error[1])
        self.windows_sound.MessageBeep.assert_called_once_with(self.windows_sound.MB_ICONHAND)
        self.scan("0001")
        self.assertNotEqual(backgrounds(), normal)
        self.assertNotEqual(backgrounds(), error)
        self.assertEqual(self.windows_sound.MessageBeep.call_count, 2)
        self.scan("0002")
        self.assertEqual(backgrounds(), normal)
        self.assertEqual(self.windows_sound.MessageBeep.call_count, 2)

    def test_scan_feedback_emphasizes_manufacturer_names_on_match_and_mismatch(self):
        self.start("3")
        self.scan("0001")
        feedback = self.app.feedback_box

        def emphasized_names():
            ranges = feedback.tag_ranges("manufacturer")
            return [feedback.get(start, end) for start, end in zip(ranges[::2], ranges[1::2])]

        self.assertIn("核验通过 · 厂家 甲厂", feedback.get("1.0", "end-1c"))
        self.assertEqual(emphasized_names(), ["甲厂"])
        self.scan("0201")
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
        self.app.scan_entry.focus_force()
        self.root.update()
        observations = []

        def close_settings():
            window = next(widget for widget in self.root.winfo_children() if isinstance(widget, tk.Toplevel))
            observations.append((self.root.grab_current() is window, self.app.scan_entry.instate(["disabled"])))
            window.destroy()

        self.root.after(100, close_settings)
        self.app._open_settings()
        self.root.update()
        self.assertEqual(observations, [(True, True)])
        self.assertTrue(self.app.scan_entry.instate(["!disabled"]))
        self.assertEqual(self.root.focus_get(), self.app.scan_entry)

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

        def visible_barcodes():
            return [tree.set(row, "barcode") for row in tree.get_children()]

        self.assertEqual(visible_barcodes(), [f"00{number:03d}" for number in range(21, 1, -1)])
        self.app.next_page_button.invoke()
        self.assertEqual(visible_barcodes(), ["00001"])
        self.app.previous_page_button.invoke()
        self.assertEqual(visible_barcodes()[0], "00021")
        self.app.next_page_button.invoke()
        self.scan("00022")
        self.assertEqual(visible_barcodes()[0], "00022")

        self.app.next_page_button.invoke()
        self.assertEqual(visible_barcodes(), ["00002", "00001"])
        for remaining in (["00001"], [f"00{number:03d}" for number in range(22, 2, -1)]):
            tree.selection_set(tree.get_children()[0])
            self.root.update()
            self.root.after(100, self.press_dialog_button, "删除记录")
            self.app.delete_button.invoke()
            self.assertTrue(self.dialog_found)
            self.assertEqual(visible_barcodes(), remaining)
        self.assertTrue(self.app.next_page_button.instate(["disabled"]))
        self.assertEqual(self.app.batch.count, 20)
