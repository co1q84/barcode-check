import struct
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from barcode_check.settings import BaseRow, Settings
from barcode_check.settings_xlsx import import_settings_workbook, write_settings_workbook


HEADERS = ("编码", "厂家", "条码前缀")


class SettingsWorkbookTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "基表.xlsx"

    def write_input(self, *rows, sheet_name="基表", extra_sheet=False):
        workbook = Workbook()
        self.addCleanup(workbook.close)
        workbook.active.title = sheet_name
        for row in rows:
            workbook.active.append(row)
        if extra_sheet:
            workbook.create_sheet("附表")
        workbook.save(self.path)

    def change_xml(self, change_sheet, *, shared_string=None):
        with ZipFile(self.path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        sheet_part = "xl/worksheets/sheet1.xml"
        parts[sheet_part] = change_sheet(parts[sheet_part].decode()).encode()
        if shared_string is not None:
            parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
                b"</Types>",
                b'<Override PartName="/xl/sharedStrings.xml" '
                b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                b"</Types>",
            )
            parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
                b"</Relationships>",
                b'<Relationship Id="rId9" Target="sharedStrings.xml" '
                b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings"/>'
                b"</Relationships>",
            )
            parts["xl/sharedStrings.xml"] = (
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<si><t>{shared_string}</t></si></sst>"
            ).encode()
        with ZipFile(self.path, "w") as archive:
            for name, data in parts.items():
                archive.writestr(name, data)

    def test_template_contains_a_single_empty_text_formatted_base_table(self):
        write_settings_workbook(self.path)

        workbook = load_workbook(self.path)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook.sheetnames, ["基表"])
        sheet = workbook.active
        self.assertEqual(tuple(cell.value for cell in sheet[1]), HEADERS)
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual([cell.number_format for cell in sheet[2]], ["@", "@", "@"])
        with self.assertRaisesRegex(ValueError, "没有可导入"):
            import_settings_workbook(self.path, Settings())

    def test_data_round_trips_leading_zeros_and_formula_like_text(self):
        rows = (BaseRow("00120", "甲厂", "0007"), BaseRow("=0008", "乙厂", "=0700"))

        write_settings_workbook(self.path, rows)

        workbook = load_workbook(self.path)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook.active["A2"].value, "00120")
        self.assertEqual(workbook.active["C2"].value, "0007")
        self.assertEqual(workbook.active["A3"].data_type, "s")
        self.assertEqual(workbook.active["C3"].data_type, "s")
        self.assertEqual(import_settings_workbook(self.path, Settings()).rows, rows)

    def test_import_accepts_integer_identifiers_and_trims_text_fields(self):
        self.write_input(
            HEADERS,
            (" 0007\r\n", " 甲 厂\t", 51685528),
            (None, None, None),
            (None, None, None),
            (None, None, None),
            (None, None, None),
            (None, None, None),
            (123456789012345, "乙厂", " 51685528**H\n"),
        )

        updated = import_settings_workbook(self.path, Settings())

        self.assertEqual(updated.rows, (
            BaseRow("0007", "甲 厂", "51685528"),
            BaseRow("123456789012345", "乙厂", "51685528**H"),
        ))
        self.assertEqual(updated.match("51685528**H123"), updated.rows[1])

    def test_preserves_literal_escape_markers_and_barcode_separators(self):
        row = BaseRow("001", "甲厂", "00_x000D_x0041_01" + chr(29) + "AXx005F_")
        write_settings_workbook(self.path, (row,))
        self.assertEqual(import_settings_workbook(self.path, Settings()).rows, (row,))
        with ZipFile(self.path) as archive:
            data = archive.read("xl/worksheets/sheet1.xml")
            self.assertIn(b"00_x005F_x000D_x005F_x0041_01_x001D_AXx005F_", data)

    def test_import_preserves_escaped_separators_at_prefix_edges(self):
        self.write_input(HEADERS, (" 001 ", " 甲厂 ", " LEADING "), ("002", "乙厂", "TRAILING"))
        self.change_xml(lambda sheet: sheet.replace("LEADING", "_x001D_AA").replace("TRAILING", "AA_x001D_"))

        updated = import_settings_workbook(self.path, Settings())

        self.assertEqual(
            [(row.code, row.manufacturer, row.prefix) for row in updated.rows],
            [("001", "甲厂", "\x1dAA"), ("002", "乙厂", "AA\x1d")],
        )
        self.assertEqual(updated.match("\x1dAAother"), updated.rows[0])
        self.assertEqual(updated.match("AA\x1dother"), updated.rows[1])
        self.assertIsNone(updated.match("AAother"))

    def test_shared_string_text_is_exact_and_rejects_invalid_reference_or_line_break(self):
        for value, index, message in (
            ("AXx005F_01", 0, None),
            ("P_x005F_x000D_01", 0, None),
            ("P_x000D_01", 0, "第 2 行.*条码前缀.*单行"),
            ("P01", 9, "第 2 行.*文本索引"),
            ("P01", -1, "第 2 行.*文本索引"),
        ):
            with self.subTest(value=value, index=index):
                self.write_input(HEADERS, ("001", "甲厂", "SHARED"))
                self.change_xml(
                    lambda sheet: sheet.replace(
                        '<c r="C2" t="inlineStr"><is><t>SHARED</t></is></c>',
                        f'<c r="C2" t="s"><v>{index}</v></c>',
                    ),
                    shared_string=value,
                )
                if message is None:
                    expected = value.replace("_x005F_x", "_x")
                    self.assertEqual(import_settings_workbook(self.path, Settings()).rows[0].prefix, expected)
                else:
                    with self.assertRaisesRegex(ValueError, message):
                        import_settings_workbook(self.path, Settings())

    def test_rejects_duplicate_worksheet_row_instead_of_skipping_it(self):
        self.write_input(HEADERS, ("001", "甲厂", "01"), ("002", "乙厂", "02"))
        self.change_xml(lambda sheet: sheet.replace('<row r="3"', '<row r="2"'))
        with self.assertRaisesRegex(ValueError, "第 2 行.*行号"):
            import_settings_workbook(self.path, Settings())

    def test_valid_rows_append_in_excel_order_and_keep_existing_page_size(self):
        original = BaseRow("001", "甲厂", "01")
        current = Settings((original,), records_per_page=50)
        self.write_input(HEADERS, ("001", "乙厂", "010"), (None, None, None), ("002", "甲厂", "009"))

        updated = import_settings_workbook(self.path, current)

        self.assertEqual(updated.rows, (original, BaseRow("001", "乙厂", "010"), BaseRow("002", "甲厂", "009")))
        self.assertEqual(updated.records_per_page, 50)
        self.assertEqual(current.rows, (original,))

    def test_rejects_corrupt_files_and_workbooks_without_exact_sheet_and_headers(self):
        self.path.write_bytes(b"not a workbook")
        with self.assertRaisesRegex(ValueError, "工作簿"):
            import_settings_workbook(self.path, Settings())

        for headers, sheet_name, extra_sheet, message in (
            (HEADERS, "Sheet1", False, "仅.*基表"),
            (HEADERS, "基表", True, "仅.*基表"),
            (("厂家", "编码", "条码前缀"), "基表", False, "第 1 行.*表头"),
            (HEADERS + ("备注",), "基表", False, "第 1 行.*表头"),
            (("编码 ", "厂家", "条码前缀"), "基表", False, "第 1 行.*表头"),
        ):
            with self.subTest(headers=headers, sheet_name=sheet_name, extra_sheet=extra_sheet):
                self.write_input(headers, sheet_name=sheet_name, extra_sheet=extra_sheet)
                with self.assertRaisesRegex(ValueError, message):
                    import_settings_workbook(self.path, Settings())

    def test_unreadable_compressed_sheet_reports_a_workbook_error(self):
        self.write_input(HEADERS, ("001", "甲厂", "AA"))
        with ZipFile(self.path) as archive:
            header = archive.getinfo("xl/worksheets/sheet1.xml").header_offset
        data = bytearray(self.path.read_bytes())
        filename_length, extra_length = struct.unpack_from("<HH", data, header + 26)
        compressed_start = header + 30 + filename_length + extra_length
        data[compressed_start] |= 0b110  # DEFLATE block type 3 is invalid.
        self.path.write_bytes(data)
        original = Settings((BaseRow("002", "乙厂", "BB"),))

        with self.assertRaisesRegex(ValueError, "无法读取 Excel 工作簿"):
            import_settings_workbook(self.path, original)

        self.assertEqual(original.rows, (BaseRow("002", "乙厂", "BB"),))

    def test_rejects_missing_nontext_multiline_and_extra_fields_at_actual_row_without_appending(self):
        original = BaseRow("001", "甲厂", "01")
        current = Settings((original,))
        for invalid, message in (
            ((12.5, "乙厂", "02"), "第 4 行.*编码.*文本"),
            ((-12, "乙厂", "02"), "第 4 行.*编码.*文本"),
            ((1234567890123456, "乙厂", "02"), "第 4 行.*编码.*文本"),
            ((date(2024, 1, 1), "乙厂", "02"), "第 4 行.*编码.*文本"),
            (("002", 12, "02"), "第 4 行.*厂家.*文本"),
            (("002", date(2024, 1, 1), "02"), "第 4 行.*厂家.*文本"),
            (("002", "乙厂", "=1+2"), "第 4 行.*条码前缀.*文本"),
            (("002", "乙厂", None), "第 4 行.*条码前缀.*空"),
            (("002", "乙厂", " \t "), "第 4 行.*条码前缀.*空"),
            (("002", "乙厂", "02\n03"), "第 4 行.*条码前缀.*单行"),
            (("002", "乙厂", "02", "备注"), "第 4 行.*三列"),
        ):
            with self.subTest(invalid=invalid):
                self.write_input(HEADERS, ("004", "丁厂", "04"), (None, None, None), invalid)
                with self.assertRaisesRegex(ValueError, message):
                    import_settings_workbook(self.path, current)
                self.assertEqual(current.rows, (original,))

    def test_rejects_a_numeric_value_with_a_text_like_zero_padded_display_format(self):
        workbook = Workbook()
        self.addCleanup(workbook.close)
        sheet = workbook.active
        sheet.title = "基表"
        sheet.append(HEADERS)
        sheet.append((12, "甲厂", "010"))
        sheet["A2"].number_format = "0000"
        workbook.save(self.path)

        with self.assertRaisesRegex(ValueError, "第 2 行.*编码.*文本"):
            import_settings_workbook(self.path, Settings())

    def test_rejects_duplicate_code_and_manufacturer_even_when_the_row_is_identical(self):
        existing = BaseRow("001", "甲厂", "01")
        current = Settings((existing,))
        for prefix in ("01", "03"):
            with self.subTest(prefix=prefix):
                self.write_input(HEADERS, ("002", "乙厂", "02"), ("001", "甲厂", prefix))
                with self.assertRaisesRegex(ValueError, "第 3 行.*编码和厂家.*已存在"):
                    import_settings_workbook(self.path, current)
                self.assertEqual(current.rows, (existing,))

        self.write_input(HEADERS, ("2\r\n", "乙厂", "02"), (2, "乙厂", "03"))
        with self.assertRaisesRegex(ValueError, "第 3 行.*编码和厂家.*重复"):
            import_settings_workbook(self.path, Settings())

    def test_rejects_an_exact_prefix_already_owned_by_another_row(self):
        current = Settings((BaseRow("001", "甲厂", "01"),))
        self.write_input(HEADERS, ("002", "乙厂", "01"))
        with self.assertRaisesRegex(ValueError, "第 2 行.*条码前缀.*已存在"):
            import_settings_workbook(self.path, current)

        self.write_input(HEADERS, ("002", "乙厂", "02"), ("003", "丙厂", "02"))
        with self.assertRaisesRegex(ValueError, "第 3 行.*条码前缀.*重复"):
            import_settings_workbook(self.path, current)
