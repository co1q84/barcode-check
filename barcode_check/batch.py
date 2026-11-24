from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from itertools import islice

from .settings import BaseRow, Settings


BARCODE_INPUT_PADDING = " \t\r\n"


def is_valid_barcode(barcode: str) -> bool:
    return bool(barcode) and not any(character in barcode for character in "\r\n\0")


class Outcome(StrEnum):
    ACCEPTED = "通过"
    INVALID = "条码无效"
    UNKNOWN = "未识别"
    WRONG_CODE = "编码不符"
    WRONG_MANUFACTURER = "厂家不符"
    DUPLICATE = "重复"
    EXCESS = "超量"


@dataclass(frozen=True)
class Record:
    id: int
    barcode: str
    recorded_at: datetime
    outcome: Outcome
    detail: str
    manufacturer: str = ""


class Batch:
    def __init__(self, settings: Settings, code: str, manufacturer: str, target: int | None = None):
        if not settings.rows:
            raise ValueError("请先在设置中添加条码基表记录。")
        if code not in settings.codes:
            raise ValueError("请输入已配置的物料编码。")
        if manufacturer not in settings.manufacturers:
            raise ValueError("请选择厂家。")
        if not any(row.code == code and row.manufacturer == manufacturer for row in settings.rows):
            raise ValueError("该编码和厂家没有对应的基表记录，请检查核验目标或设置。")
        if target is not None and (type(target) is not int or target < 1):
            raise ValueError("应扫数量须为正整数，或留空。")
        self.code = code
        self.manufacturer = manufacturer
        self.target = target
        self._settings = settings
        self._records: dict[int, Record] = {}
        self._accepted: dict[str, datetime] = {}
        self._next_id = 1
        self._finished = False

    @property
    def count(self) -> int:
        return len(self._accepted)

    @property
    def remaining(self) -> int | None:
        return None if self.target is None else self.target - self.count

    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(reversed(self._records.values()))

    def record_page(self, offset: int, limit: int) -> tuple[Record, ...]:
        return tuple(islice(reversed(self._records.values()), offset, offset + limit))

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def finished(self) -> bool:
        return self._finished

    def _require_active(self) -> None:
        if self.finished:
            raise ValueError("本批已结束，请开始新批核验。")

    def _judge(self, barcode: str) -> tuple[Outcome, str, BaseRow | None]:
        if not is_valid_barcode(barcode):
            return Outcome.INVALID, "请输入一条有效条码。", None
        rule = self._settings.match(barcode)
        if rule is None:
            return Outcome.UNKNOWN, "没有匹配的条码前缀，请检查条码或基表。", None
        if rule.code != self.code:
            return Outcome.WRONG_CODE, f"应为 {self.code}，识别为 {rule.code}。", rule
        if rule.manufacturer != self.manufacturer:
            return Outcome.WRONG_MANUFACTURER, f"应为 {self.manufacturer}，识别为 {rule.manufacturer}。", rule
        first_scan = self._accepted.get(barcode)
        if first_scan is not None:
            return Outcome.DUPLICATE, f"本批已录入，首次有效录入于 {first_scan:%H:%M:%S}。", rule
        if self.target is not None and self.count >= self.target:
            return Outcome.EXCESS, f"应扫 {self.target} 件，当前有效 {self.count} 件。本次未计入。", rule
        return Outcome.ACCEPTED, "核验通过。", rule

    def scan(self, barcode: str) -> Record:
        self._require_active()
        barcode = barcode.strip(BARCODE_INPUT_PADDING)
        outcome, detail, rule = self._judge(barcode)
        recorded_at = datetime.now().astimezone()
        manufacturer = rule.manufacturer if rule else ""
        record = Record(self._next_id, barcode, recorded_at, outcome, detail, manufacturer)
        self._records[record.id] = record
        if outcome == Outcome.ACCEPTED:
            self._accepted[barcode] = recorded_at
        self._next_id += 1
        return record

    def delete(self, record_id: int) -> Record:
        self._require_active()
        try:
            record = self._records.pop(record_id)
        except KeyError as error:
            raise ValueError("该条记录已不存在。") from error
        if record.outcome == Outcome.ACCEPTED:
            del self._accepted[record.barcode]
        return record

    def finish(self, *, allow_shortage: bool = False) -> None:
        self._require_active()
        if self.remaining and not allow_shortage:
            raise ValueError(f"还差 {self.remaining} 件。")
        self._finished = True

