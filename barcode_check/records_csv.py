import csv
from pathlib import Path
from tempfile import NamedTemporaryFile

from .batch import Batch, Outcome


RECORD_HEADERS = ("条码", "时间", "结果", "说明", "目标编码", "目标厂家", "应扫数量", "批次状态", "厂家")


def export_records(path: Path, batch: Batch, *, accepted_only: bool) -> None:
    if not batch.finished:
        status = "核验中"
    else:
        status = "数量不足" if batch.remaining else "已结束"
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8-sig", dir=path.parent, suffix=".tmp", delete=False,
        ) as file:
            temporary_path = Path(file.name)
            writer = csv.writer(file)
            writer.writerow(RECORD_HEADERS)
            for record in batch.records:
                if accepted_only and record.outcome != Outcome.ACCEPTED:
                    continue
                writer.writerow((
                    record.barcode, record.recorded_at.isoformat(timespec="seconds"),
                    record.outcome, record.detail,
                    batch.code, batch.manufacturer, batch.target, status, record.manufacturer,
                ))
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
