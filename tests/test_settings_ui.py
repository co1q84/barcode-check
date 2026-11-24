import tkinter as tk
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from barcode_check.settings import BaseRow, SettingsStore
from barcode_check.settings_ui import BaseRowEditor, SettingsWindow
from barcode_check.theme import configure_theme


class SettingsWindowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.store = SettingsStore(self.folder / "settings.json")
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        configure_theme(self.root)
        self.window = SettingsWindow(self.root, self.store.load(), self.store.save)
        self.root.update()

    def editor(self):
        return next(child for child in self.window.winfo_children() if isinstance(child, BaseRowEditor))

    def add_row(self, code, manufacturer, prefix):
        self.window.new_button.invoke()
        editor = self.editor()
        editor.code.set(code)
        editor.manufacturer.set(manufacturer)
        editor.prefix.set(prefix)
        editor.save_button.invoke()
        self.root.update()

    def test_trial_and_save_trim_padding_from_base_row_entries(self):
        self.window.new_button.invoke()
        editor = self.editor()
        body = editor.winfo_children()[0]
        for row, value in enumerate(("0007\r\n", " 甲 厂\t", "51685528**H\n")):
            entry = body.grid_slaves(row=row, column=1)[0]
            entry.insert(0, value)

        editor.sample.set("51685528**H123\r\n")
        editor.try_button.invoke()
        self.assertEqual(editor.trial.cget("text"), "命中前缀 51685528**H · 编码 0007 · 厂家 甲 厂")
        self.assertFalse(self.store.path.exists())

        editor.save_button.invoke()
        self.assertFalse(editor.winfo_exists())
        self.assertEqual(self.store.load().rows, (BaseRow("0007", "甲 厂", "51685528**H"),))

    def test_trial_and_save_reject_blank_or_multiline_base_row_fields(self):
        self.window.new_button.invoke()
        editor = self.editor()
        editor.manufacturer.set("甲厂")
        editor.prefix.set("51685528**H")
        editor.sample.set("51685528**H123")

        for code in (" \t\r\n", "00\n07\r\n"):
            with self.subTest(code=code):
                editor.code.set(code)
                editor.try_button.invoke()
                self.assertIn("编码须为非空的单行文本", editor.trial.cget("text"))
                editor.save_button.invoke()
                self.assertIn("编码须为非空的单行文本", editor.error.get())
                self.assertFalse(self.store.path.exists())

    def test_single_table_add_edit_search_and_batch_delete(self):
        table = self.window.table
        self.assertEqual([table.heading(col, "text") for col in table["columns"]], ["编码", "厂家", "条码前缀"])
        self.add_row("001", "甲厂", "00")
        self.add_row("001", "乙厂", "02")
        self.add_row("001", "乙厂", "03")
        editor = self.editor()
        self.assertIn("组合已存在", editor.error.get())
        editor.close()

        self.window.search.set("乙厂")
        rows = table.get_children()
        self.assertEqual(len(rows), 1)
        table.selection_set(rows[0])
        self.root.update()
        self.window.edit_button.invoke()
        editor = self.editor()
        editor.prefix.set("023")
        editor.sample.set("023001")
        editor.try_button.invoke()
        self.assertIn("命中前缀 023", editor.trial.cget("text"))
        editor.sample.set("\u3000023001")
        editor.try_button.invoke()
        self.assertIn("没有命中", editor.trial.cget("text"))
        editor.save_button.invoke()
        self.assertEqual(self.window.settings.match("023001"), BaseRow("001", "乙厂", "023"))

        table.selection_set(table.get_children())
        self.root.update()
        with patch("barcode_check.settings_ui.messagebox.askyesno", return_value=True):
            self.window.delete_button.invoke()
        self.assertEqual(self.store.load().rows, (BaseRow("001", "甲厂", "00"),))

    def test_excel_buttons_save_only_a_fully_valid_workbook(self):
        template = self.folder / "template.xlsx"
        with patch("barcode_check.settings_ui.filedialog.asksaveasfilename", return_value=str(template)):
            self.window.template_button.invoke()
        workbook = load_workbook(template)
        sheet = workbook["基表"]
        self.assertEqual(tuple(cell.value for cell in sheet[1]), ("编码", "厂家", "条码前缀"))
        for line, code, prefix in ((2, 51685528, "000"), (3, "51685528\n", "001")):
            for column, value in enumerate((code, "甲厂", prefix), 1):
                sheet.cell(line, column, value)
        incoming = self.folder / "incoming.xlsx"
        workbook.save(incoming)
        with patch("barcode_check.settings_ui.filedialog.askopenfilename", return_value=str(incoming)):
            with patch("barcode_check.settings_ui.messagebox.showerror") as error:
                self.window.import_button.invoke()
        error.assert_called_once()
        self.assertTrue(error.call_args.args[1].startswith("第 3 行"))
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.window.settings.rows, ())

        sheet.delete_rows(3)
        workbook.save(incoming)
        workbook.close()
        with patch("barcode_check.settings_ui.filedialog.askopenfilename", return_value=str(incoming)):
            self.window.import_button.invoke()
        self.assertEqual(self.store.load().rows, (BaseRow("51685528", "甲厂", "000"),))
        saved_bytes = self.store.path.read_bytes()
        with patch("barcode_check.settings_ui.filedialog.askopenfilename", return_value=str(incoming)):
            with patch("barcode_check.settings_ui.messagebox.showerror") as error:
                self.window.import_button.invoke()
        self.assertIn("基表", error.call_args.args[1])
        self.assertEqual(self.store.path.read_bytes(), saved_bytes)
        output = self.folder / "export.xlsx"
        with patch("barcode_check.settings_ui.filedialog.asksaveasfilename", return_value=str(output)):
            self.window.export_button.invoke()
        exported = load_workbook(output)
        try:
            self.assertEqual(tuple(cell.value for cell in exported["基表"][2]), ("51685528", "甲厂", "000"))
        finally:
            exported.close()
