import csv
import tempfile
import unittest
from pathlib import Path

from barcode_check.batch import Batch
from barcode_check.records_csv import export_records
from barcode_check.settings import BaseRow, Settings


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
