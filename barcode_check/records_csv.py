import csv
from collections.abc import Iterable
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText

from .batch import Batch, Outcome
from .settings_xlsx import _escape_text
from .sorting import SortingBatch


RECORD_HEADERS = ("条码", "时间", "结果", "说明", "目标编码", "目标厂家", "应扫数量", "批次状态", "厂家")
SORTING_HEADERS = ("序号", "条码", "厂家", "物料编码", "时间", "识别状态")
RECORD_EXPORT_FILETYPES = (("Excel 工作簿", "*.xlsx"), ("原始 CSV（按文本导入）", "*.csv"))
_MAX_XLSX_DATA_ROWS = 1_048_575
_MAX_XLSX_CELL_LENGTH = 32_767
_MAX_XLSX_CELL_LINE_FEEDS = 253
_COLUMN_WIDTHS = {
    "序号": 8, "条码": 38, "时间": 29, "说明": 42, "目标编码": 26,
    "目标厂家": 20, "厂家": 20, "物料编码": 26, "识别状态": 20,
}


def export_records(path: Path, batch: Batch, *, accepted_only: bool) -> None:
    if not batch.finished:
        status = "核验中"
    else:
        status = "数量不足" if batch.remaining else "已结束"
    rows = (
        (
            record.barcode, record.recorded_at.isoformat(timespec="seconds"), record.outcome, record.detail,
            batch.code, batch.manufacturer, batch.target, status, record.manufacturer,
        )
        for record in batch.records
        if not accepted_only or record.outcome == Outcome.ACCEPTED
    )
    count = batch.count if accepted_only else batch.record_count
    _write_records(path, "校验记录", RECORD_HEADERS, rows, count)


def export_sorting_records(path: Path, batch: SortingBatch) -> None:
    total = batch.record_count
    rows = (
        (
            total - index, record.barcode, record.rule.manufacturer if record.rule else "",
            record.rule.code if record.rule else "", record.recorded_at.isoformat(timespec="seconds"), record.status,
        )
        for index, record in enumerate(batch.record_page(0, total))
    )
    _write_records(path, "分流记录", SORTING_HEADERS, rows, total)


def _write_records(
    path: Path, title: str, headers: tuple[str, ...], rows: Iterable[tuple[str | int | None, ...]], count: int,
) -> None:
    excel = path.suffix.lower() == ".xlsx"
    if excel and count > _MAX_XLSX_DATA_ROWS:
        raise ValueError(f"共有 {count} 条记录，超过 Excel 单工作表的记录上限。请改用原始 CSV 导出。")

    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as file:
            temporary_path = Path(file.name)
        if excel:
            _write_xlsx(temporary_path, title, headers, rows)
        else:
            with temporary_path.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(headers)
                writer.writerows(rows)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_xlsx(path, title, headers, rows):
    workbook = Workbook()
    try:
        sheet = workbook.active
        sheet.title = title
        sheet.append(headers)
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            sheet.column_dimensions[cell.column_letter].width = _COLUMN_WIDTHS.get(cell.value, 14)

        for row_number, row in enumerate(rows, 2):
            for column, value in enumerate(row, 1):
                if isinstance(value, int) and value >= 10 ** 15:
                    value = str(value)
                if isinstance(value, str):
                    if (
                        len(value.encode("utf-16-le")) > 2 * _MAX_XLSX_CELL_LENGTH
                        or value.count("\n") > _MAX_XLSX_CELL_LINE_FEEDS
                    ):
                        raise ValueError(
                            f"第 {row_number - 1} 条导出记录的「{headers[column - 1]}」超过 Excel 单元格限制。"
                            "请改用原始 CSV 导出。"
                        )
                    escaped = _escape_text(value)
                    # Escaped XML can exceed the decoded cell limit without losing any text.
                    cell = sheet.cell(row_number, column, CellRichText(escaped) if escaped != value else value)
                    cell.data_type = "s"
                    cell.number_format = "@"
                else:
                    sheet.cell(row_number, column, value)

        sheet.auto_filter.ref = sheet.dimensions
        workbook.save(path)
    finally:
        workbook.close()
