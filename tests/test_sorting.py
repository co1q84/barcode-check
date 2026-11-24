import unittest

from barcode_check.settings import BaseRow, Settings
from barcode_check.sorting import SortingBatch


class SortingBatchTests(unittest.TestCase):
    def setUp(self):
        self.first_factory = BaseRow("0015", "甲厂", "00")
        self.second_factory = BaseRow("0015", "乙厂", "0002")
        self.other_code = BaseRow("0026", "甲厂", "0026")
        self.batch = SortingBatch(Settings((self.first_factory, self.second_factory, self.other_code)))

    def test_summary_groups_by_code_and_manufacturer_using_longest_prefix(self):
        for barcode, rule in (
            ("00010001", self.first_factory), ("00020001", self.second_factory),
            ("00260001", self.other_code), ("00010002", self.first_factory),
        ):
            with self.subTest(barcode=barcode):
                record = self.batch.scan(barcode)
                self.assertEqual(record.rule, rule)
                self.assertFalse(record.duplicate)

        self.assertEqual(self.batch.quantity_for(self.first_factory.key), 2)
        self.assertEqual(self.batch.quantity_for(self.second_factory.key), 1)
        self.assertEqual(self.batch.quantity_for(self.other_code.key), 1)
        self.assertEqual(self.batch.quantity_for(("0026", "乙厂")), 0)
        self.assertEqual(self.batch.recognized_count, 4)
        self.assertEqual(self.batch.pending_count, 0)

    def test_duplicates_and_pending_scans_appear_in_paginated_details(self):
        self.assertIsNone(self.batch.scan(" \t\r\n"))
        first = self.batch.scan("00010001")
        repeat = self.batch.scan(" \t00010001\r\n")
        unknown = self.batch.scan("9999")
        unknown_repeat = self.batch.scan("9999")
        invalid = self.batch.scan("0001\n0002")

        self.assertEqual(first.barcode, repeat.barcode)
        self.assertEqual(repeat.rule, self.first_factory)
        self.assertTrue(repeat.duplicate)
        self.assertFalse(unknown.duplicate)
        self.assertTrue(unknown_repeat.duplicate)
        self.assertIsNone(unknown.rule)
        self.assertIsNone(invalid.rule)
        self.assertEqual(invalid.barcode, "0001\n0002")
        self.assertEqual(self.batch.record_count, 5)
        self.assertEqual(self.batch.pending_count, 3)
        self.assertEqual(self.batch.recognized_count, 1)
        self.assertEqual(self.batch.quantity_for(self.first_factory.key), 1)
        self.assertEqual(self.batch.record_page(0, 2), (invalid, unknown_repeat))
        self.assertEqual(self.batch.record_page(2, 2), (unknown, repeat))
        self.assertEqual(self.batch.record_page(4, 2), (first,))
        self.assertEqual(self.batch.record_page(5, 2), ())
        self.assertEqual([record.id for record in self.batch.record_page(0, 5)], [5, 4, 3, 2, 1])

    def test_empty_settings_and_finished_batch_keep_pending_record(self):
        batch = SortingBatch(Settings())
        self.assertFalse(batch.finished)
        record = batch.scan("0123")
        self.assertIsNone(record.rule)
        self.assertEqual(batch.recognized_count, 0)
        self.assertEqual(batch.pending_count, 1)

        batch.finish()
        self.assertTrue(batch.finished)
        with self.assertRaises(ValueError):
            batch.scan("0456")
        self.assertEqual(batch.record_page(0, 20), (record,))

    def test_deleting_first_scan_promotes_earliest_repeat_and_last_deletion_releases_count(self):
        first = self.batch.scan("00010001")
        second = self.batch.scan("00010001")
        other = self.batch.scan("00010002")
        third = self.batch.scan("00010001")
        self.assertEqual(first.status, "已识别")
        self.assertEqual(second.status, "本批已扫过")

        self.assertEqual(self.batch.delete(first.id), first)
        self.assertIsNone(self.batch.record(first.id))
        promoted = self.batch.record(second.id)
        self.assertEqual(promoted.status, "已识别")
        self.assertTrue(second.duplicate)
        self.assertEqual(self.batch.record(third.id).status, "本批已扫过")
        self.assertEqual(self.batch.record_page(0, 2), (third, other))
        self.assertEqual(self.batch.record_page(2, 2), (promoted,))
        self.assertEqual(self.batch.quantity_for(self.first_factory.key), 2)
        self.assertEqual(self.batch.recognized_count, 2)

        self.batch.delete(third.id)
        self.assertEqual(self.batch.recognized_count, 2)
        self.batch.delete(second.id)
        self.assertEqual(self.batch.quantity_for(self.first_factory.key), 1)
        self.assertEqual(self.batch.recognized_count, 1)

        rescanned = self.batch.scan("00010001")
        self.assertEqual(rescanned.id, third.id + 1)
        self.assertEqual(rescanned.status, "已识别")
        self.assertEqual(self.batch.record_page(0, 20), (rescanned, other))
        self.assertEqual(self.batch.quantity_for(self.first_factory.key), 2)

        self.batch.delete(rescanned.id)
        self.batch.delete(other.id)
        self.assertEqual(self.batch.quantity_for(self.first_factory.key), 0)
        self.assertEqual(self.batch.recognized_count, 0)

    def test_deleting_pending_records_decrements_count_and_promotes_repeats(self):
        first = self.batch.scan("9999")
        repeated = self.batch.scan(" 9999 ")
        self.assertEqual(first.status, "待确认")
        self.assertEqual(repeated.status, "待确认 · 已扫过")

        self.batch.delete(first.id)
        self.assertEqual(self.batch.pending_count, 1)
        self.assertEqual(self.batch.record(repeated.id).status, "待确认")
        self.batch.delete(repeated.id)
        self.assertEqual(self.batch.pending_count, 0)
        self.assertEqual(self.batch.record_count, 0)
        self.assertEqual(self.batch.recognized_count, 0)
        self.assertFalse(self.batch.scan("9999").duplicate)

    def test_cannot_delete_missing_or_finished_records(self):
        record = self.batch.scan("00010001")
        with self.assertRaises(ValueError):
            self.batch.delete(record.id + 1)
        self.batch.finish()
        with self.assertRaises(ValueError):
            self.batch.delete(record.id)
        self.assertEqual(self.batch.record_page(0, 20), (record,))
