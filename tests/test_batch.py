import unittest

from barcode_check.batch import Batch, Outcome
from barcode_check.settings import BaseRow, Settings


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings((
            BaseRow("001", "甲厂", "00"), BaseRow("002", "甲厂", "02"), BaseRow("001", "乙厂", "03"),
        ))

    def test_only_valid_unique_scans_within_target_count(self):
        batch = Batch(self.settings, "001", "甲厂", 1)
        expected = (
            ("99", Outcome.UNKNOWN), ("020", Outcome.WRONG_CODE),
            ("030", Outcome.WRONG_MANUFACTURER), ("001", Outcome.ACCEPTED),
            ("001", Outcome.DUPLICATE), ("002", Outcome.EXCESS),
        )
        for barcode, outcome in expected:
            with self.subTest(barcode=barcode, outcome=outcome):
                self.assertEqual(batch.scan(barcode).outcome, outcome)
        self.assertEqual(batch.count, 1)
        self.assertEqual(batch.remaining, 0)
        self.assertEqual([record.barcode for record in batch.records], ["002", "001", "001", "030", "020", "99"])
        self.assertEqual([record.manufacturer for record in batch.records], ["甲厂", "甲厂", "甲厂", "乙厂", "甲厂", ""])

    def test_delete_accepted_record_releases_quantity_and_duplicate_key(self):
        batch = Batch(self.settings, "001", "甲厂", 2)
        accepted = batch.scan("001")
        duplicate = batch.scan("001")
        batch.delete(duplicate.id)
        self.assertEqual(batch.count, 1)
        batch.delete(accepted.id)
        self.assertEqual(batch.remaining, 2)
        self.assertEqual(batch.scan("001").outcome, Outcome.ACCEPTED)

    def test_no_quantity_limit_and_explicit_short_finish(self):
        unlimited = Batch(self.settings, "001", "甲厂")
        for barcode in ("001", "002", "003"):
            self.assertEqual(unlimited.scan(barcode).outcome, Outcome.ACCEPTED)
        self.assertIsNone(unlimited.remaining)
        unlimited.finish()
        with self.assertRaises(ValueError):
            unlimited.scan("004")
        limited = Batch(self.settings, "001", "甲厂", 2)
        limited.scan("001")
        with self.assertRaises(ValueError):
            limited.finish()
        limited.finish(allow_shortage=True)
        self.assertTrue(limited.finished)
        self.assertEqual(limited.remaining, 1)

    def test_invalid_targets_cannot_start(self):
        for code, manufacturer, target in (("001", "甲厂", 0), ("999", "甲厂", 1), ("002", "乙厂", 1)):
            with self.subTest(code=code, manufacturer=manufacturer, target=target), self.assertRaises(ValueError):
                Batch(self.settings, code, manufacturer, target)
