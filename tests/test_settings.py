import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from barcode_check.settings import BaseRow, Settings, SettingsStore, delete_rows, edit_row


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings((BaseRow("001", "甲厂", "01"), BaseRow("002", "乙厂", "012")))

    def test_match_uses_longest_prefix(self):
        self.assertEqual(self.settings.match("01299"), BaseRow("002", "乙厂", "012"))
        self.assertIsNone(self.settings.match("999"))

    def test_duplicate_pair_and_duplicate_exact_prefix_are_rejected(self):
        for row in (BaseRow("002", "乙厂", "05"), BaseRow("003", "乙厂", "01")):
            with self.subTest(row=row), self.assertRaises(ValueError):
                edit_row(self.settings, None, row)

    def test_edit_and_delete_update_matching_and_target_choices(self):
        original = self.settings.rows[0]
        renamed = edit_row(self.settings, original, BaseRow("0001", "丙厂", original.prefix))
        self.assertEqual(renamed.match("0100").code, "0001")
        self.assertEqual(renamed.match("0100").manufacturer, "丙厂")
        self.assertEqual(self.settings.match("0100").code, "001")
        reduced = delete_rows(renamed, (renamed.rows[0],))
        self.assertEqual(reduced.codes, ("002",))
        self.assertEqual(reduced.manufacturers, ("乙厂",))
        self.assertIsNone(reduced.match("0100"))

    def test_save_creates_settings_below_roaming_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, APPDATA=directory):
            path = Path(directory) / "barcode-check" / "settings.json"
            store = SettingsStore()
            self.assertEqual(store.load(), Settings())
            self.assertFalse(path.parent.exists())
            store.save(self.settings)
            self.assertTrue(path.is_file())
            self.assertEqual(SettingsStore().load(), self.settings)

    def test_corrupt_settings_are_reported_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_bytes(b"{invalid}")
            store = SettingsStore(path)
            with self.assertRaises(ValueError):
                store.load()
            with self.assertRaises(ValueError):
                store.save(self.settings)
            self.assertEqual(path.read_bytes(), b"{invalid}")

    def test_save_refuses_to_overwrite_another_instances_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            first = SettingsStore(path)
            second = SettingsStore(path)
            first.load()
            second.load()
            first.save(self.settings)
            with self.assertRaises(ValueError):
                second.save(Settings((BaseRow("003", "丙厂", "09"),)))
            self.assertEqual(second.load(), self.settings)

    def test_reports_an_unsupported_settings_version_and_does_not_overwrite_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            payload = {
                "version": 1, "codes": ["001"], "manufacturers": ["甲厂"],
                "rules": [{"prefix": "00", "code": "001", "manufacturer": "甲厂"}],
            }
            data = json.dumps(payload).encode("utf-8")
            path.write_bytes(data)
            store = SettingsStore(path)
            with self.assertRaisesRegex(ValueError, "设置版本"):
                store.load()
            with self.assertRaises(ValueError):
                store.save(self.settings)
            self.assertEqual(path.read_bytes(), data)

    def test_base_row_rejects_edge_whitespace_and_overlong_text(self):
        with self.assertRaisesRegex(ValueError, "编码.*首尾空白"):
            BaseRow("001 ", "甲厂", "01")
        with self.assertRaisesRegex(ValueError, "编码.*字符上限"):
            BaseRow("0" * 32768, "甲厂", "01")
