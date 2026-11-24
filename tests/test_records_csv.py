import csv
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils.escape import unescape

from barcode_check.batch import Batch
from barcode_check.records_csv import RECORD_HEADERS, SORTING_HEADERS, export_records, export_sorting_records
from barcode_check.settings import BaseRow, Settings
from barcode_check.sorting import SortingBatch


class RecordFileTests(unittest.TestCase):
    def test_export_can_include_anomalies_or_only_accepted_and_keeps_leading_zeros(self):
        settings = Settings((BaseRow("01", "甲厂", "0"), BaseRow("01", "乙厂", "1")))
        batch = Batch(settings, "01", "甲厂")
        batch.scan("00001")
        batch.scan("10001")
        batch.scan("999")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "记录.csv"
            export_records(path, batch, accepted_only=False)
            with path.open(encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                self.assertNotIn("来源", reader.fieldnames)
                rows = list(reader)
            self.assertEqual([row["条码"] for row in rows], ["999", "10001", "00001"])
            self.assertEqual([row["厂家"] for row in rows], ["", "乙厂", "甲厂"])
            self.assertEqual(rows[1]["目标厂家"], "甲厂")
            self.assertEqual(rows[2]["目标编码"], "01")
            export_records(path, batch, accepted_only=True)
            with path.open(encoding="utf-8-sig", newline="") as file:
                self.assertEqual([row["条码"] for row in csv.DictReader(file)], ["00001"])

    def test_validation_xlsx_keeps_identifiers_and_formula_like_values_as_text(self):
        code = "00012345678901234567890"
        barcode = "0004567890123456789012345"
        manufacturer = "=1+2"
        target = 1234567890123456
        batch = Batch(Settings((BaseRow(code, manufacturer, "0"),)), code, manufacturer, target)
        batch.scan(barcode)
        batch.scan("#VALUE!")
        batch.finish(allow_shortage=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "校验.XLSX"
            export_records(path, batch, accepted_only=False)
            with path.open("rb") as file:
                sheet = load_workbook(file).active
            self.assertEqual(tuple(cell.value for cell in sheet[1]), RECORD_HEADERS)
            for coordinate, value in (
                ("A2", "#VALUE!"), ("A3", barcode), ("E3", code), ("F3", manufacturer),
                ("G3", str(target)), ("I3", manufacturer),
            ):
                with self.subTest(cell=coordinate):
                    self.assertEqual(sheet[coordinate].value, value)
                    self.assertEqual(sheet[coordinate].data_type, "s")
                    self.assertEqual(sheet[coordinate].number_format, "@")
            self.assertEqual(sheet["C2"].value, "未识别")
            self.assertEqual(sheet["H3"].value, "数量不足")

            export_records(path, batch, accepted_only=True)
            with path.open("rb") as file:
                sheet = load_workbook(file).active
            self.assertEqual([row[0].value for row in sheet.iter_rows(min_row=2)], [barcode])

    def test_sorting_exports_keep_every_page_in_order_and_csv_raw(self):
        barcode = "000123456789012345678901"
        batch = SortingBatch(Settings((BaseRow("00042", "甲厂", "0"),)))
        formula_like = batch.scan("=1+2")
        discarded = batch.scan("discarded")
        accepted = [batch.scan(f"00{number:03d}") for number in range(20)]
        newest = batch.scan(barcode)
        batch.delete(discarded.id)
        expected = [newest, *reversed(accepted), formula_like]
        with tempfile.TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "分流.xlsx"
            export_sorting_records(workbook_path, batch)
            with workbook_path.open("rb") as file:
                sheet = load_workbook(file).active
            self.assertEqual(tuple(cell.value for cell in sheet[1]), SORTING_HEADERS)
            rows = list(sheet.iter_rows(min_row=2))
            self.assertEqual([row[0].value for row in rows], list(range(22, 0, -1)))
            self.assertEqual([row[1].value for row in rows], [record.barcode for record in expected])
            self.assertEqual([row[1].data_type for row in rows], ["s"] * 22)
            self.assertEqual([row[5].value for row in rows], [record.status for record in expected])
            self.assertEqual(sheet["D2"].value, "00042")
            self.assertEqual(sheet["D2"].number_format, "@")

            csv_path = workbook_path.with_suffix(".csv")
            export_sorting_records(csv_path, batch)
            self.assertTrue(csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with csv_path.open(encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                self.assertEqual(tuple(reader.fieldnames), SORTING_HEADERS)
                rows = list(reader)
            self.assertEqual([row["序号"] for row in rows], [str(i) for i in range(22, 0, -1)])
            self.assertEqual([row["条码"] for row in rows], [record.barcode for record in expected])
            self.assertEqual(rows[0]["物料编码"], "00042")

    def test_xlsx_preserves_invalid_scan_text_with_excel_escapes(self):
        batch = SortingBatch(Settings())
        barcode = "00\r\n12\u0000\u001d_x001D_\t34"
        batch.scan(barcode)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "分流.xlsx"
            export_sorting_records(path, batch)
            with ZipFile(path) as workbook:
                sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            cell = sheet.find(".//{*}c[@r='B2']")
            self.assertEqual(cell.attrib["t"], "inlineStr")
            self.assertEqual("".join(unescape(text.text) for text in cell.findall(".//{*}t")), barcode)

    def test_xlsx_limits_report_csv_option_without_replacing_existing_file(self):
        for barcode in ("0" + "条" * 32767, "0" + "😀" * 16384, "0" + "\n0" * 254):
            with self.subTest(length=len(barcode)), tempfile.TemporaryDirectory() as directory:
                batch = SortingBatch(Settings())
                batch.scan(barcode)
                path = Path(directory) / "分流.xlsx"
                path.write_bytes(b"previous file")
                with self.assertRaisesRegex(ValueError, "CSV"):
                    export_sorting_records(path, batch)
                self.assertEqual(path.read_bytes(), b"previous file")
                self.assertEqual(list(path.parent.iterdir()), [path])

                csv_path = path.with_suffix(".csv")
                export_sorting_records(csv_path, batch)
                with csv_path.open(encoding="utf-8-sig", newline="") as file:
                    self.assertEqual(list(csv.DictReader(file))[0]["条码"], barcode)
