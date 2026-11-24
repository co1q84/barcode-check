from dataclasses import dataclass, replace
from datetime import datetime
from itertools import islice

from .batch import BARCODE_INPUT_PADDING, is_valid_barcode
from .settings import BaseRow, Settings


@dataclass(frozen=True)
class SortingRecord:
    id: int
    barcode: str
    recorded_at: datetime
    rule: BaseRow | None
    duplicate: bool

    @property
    def status(self) -> str:
        if self.rule is None:
            return "待确认 · 已扫过" if self.duplicate else "待确认"
        return "本批已扫过" if self.duplicate else "已识别"


class SortingBatch:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._records: dict[int, SortingRecord] = {}
        self._record_ids_by_barcode: dict[str, dict[int, None]] = {}
        self._next_id = 1
        self._quantities: dict[tuple[str, str], int] = {}
        self._recognized_count = 0
        self._pending_count = 0
        self._finished = False

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def recognized_count(self) -> int:
        return self._recognized_count

    @property
    def pending_count(self) -> int:
        return self._pending_count

    def quantity_for(self, key: tuple[str, str]) -> int:
        return self._quantities.get(key, 0)

    def record(self, record_id: int) -> SortingRecord | None:
        return self._records.get(record_id)

    def record_page(self, offset: int, limit: int) -> tuple[SortingRecord, ...]:
        return tuple(islice(reversed(self._records.values()), offset, offset + limit))

    def scan(self, barcode: str) -> SortingRecord | None:
        self._require_active()
        barcode = barcode.strip(BARCODE_INPUT_PADDING)
        if not barcode:
            return None

        rule = self._settings.match(barcode) if is_valid_barcode(barcode) else None
        record_ids = self._record_ids_by_barcode.setdefault(barcode, {})
        duplicate = bool(record_ids)
        record = SortingRecord(self._next_id, barcode, datetime.now().astimezone(), rule, duplicate)
        self._records[record.id] = record
        record_ids[record.id] = None
        self._next_id += 1

        if rule is None:
            self._pending_count += 1
        elif not duplicate:
            key = rule.key
            self._quantities[key] = self.quantity_for(key) + 1
            self._recognized_count += 1
        return record

    def delete(self, record_id: int) -> SortingRecord:
        self._require_active()
        record = self.record(record_id)
        if record is None:
            raise ValueError("该条记录已不存在。")

        del self._records[record_id]
        record_ids = self._record_ids_by_barcode[record.barcode]
        del record_ids[record_id]
        if not record_ids:
            del self._record_ids_by_barcode[record.barcode]
        elif not record.duplicate:
            first_id = next(iter(record_ids))
            self._records[first_id] = replace(self._records[first_id], duplicate=False)

        if record.rule is None:
            self._pending_count -= 1
        elif not record_ids:
            key = record.rule.key
            quantity = self._quantities[key] - 1
            if quantity:
                self._quantities[key] = quantity
            else:
                del self._quantities[key]
            self._recognized_count -= 1
        return record

    def finish(self) -> None:
        self._require_active()
        self._finished = True

    def _require_active(self) -> None:
        if self.finished:
            raise ValueError("本批已结束，请开始新一批分流。")
