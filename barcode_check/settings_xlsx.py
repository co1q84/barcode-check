import re
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree.ElementTree import ParseError, iterparse
from zipfile import BadZipFile

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText
from openpyxl.reader.excel import ExcelReader
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.utils.escape import unescape
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.xml.constants import REL_NS, SHARED_STRINGS, SHEET_MAIN_NS

from .settings import BaseRow, Settings


COLUMNS = ("编码", "厂家", "条码前缀")
_SHEET_NAME = "基表"
_NON_TEXT = object()
_XSTRING_ESCAPE = re.compile(r"_(?=x[0-9A-Fa-f]{4}_)|[\x00-\x08\x0b-\x1f\ufffe\uffff]")


def _escape_text(value: str) -> str:
    return _XSTRING_ESCAPE.sub(lambda match: f"_x{ord(match[0]):04X}_", value)


def write_settings_workbook(path: Path, rows: Iterable[BaseRow] = ()) -> None:
    if path.suffix.lower() != ".xlsx":
        raise ValueError("请使用 .xlsx 文件名。")
    workbook = Workbook()
    temporary_path = None
    try:
        sheet = workbook.active
        sheet.title = _SHEET_NAME
        sheet.freeze_panes = "A2"
        sheet.row_dimensions[1].height = 24
        heading_fill = PatternFill("solid", fgColor="EAF0F8")
        heading_font = Font(bold=True, color="17263B")
        heading_alignment = Alignment(vertical="center")
        for column, (label, width) in enumerate(zip(COLUMNS, (23, 33, 38)), 1):
            heading = sheet.cell(1, column, label)
            heading.fill = heading_fill
            heading.font = heading_font
            heading.alignment = heading_alignment
            dimension = sheet.column_dimensions[heading.column_letter]
            dimension.width = width
            dimension.number_format = "@"
            sheet.cell(2, column).number_format = "@"

        for line, row in enumerate(rows, 2):
            values = (row.code, row.manufacturer, row.prefix)
            for column, value in enumerate(values, 1):
                escaped = _escape_text(value)
                # Escapes can make the XML longer than the decoded Excel cell limit.
                cell = sheet.cell(line, column, CellRichText(escaped) if escaped != value else value)
                cell.data_type = "s"
                cell.number_format = "@"
        sheet.auto_filter.ref = f"A1:C{sheet.max_row}"

        with NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as file:
            temporary_path = Path(file.name)
        workbook.save(temporary_path)
        temporary_path.replace(path)
    finally:
        workbook.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def import_settings_workbook(path: Path, settings: Settings) -> Settings:
    if path.suffix.lower() != ".xlsx":
        raise ValueError("请选择 .xlsx 文件。")
    try:
        reader = ExcelReader(path, read_only=True, keep_links=False)
        with reader.archive:
            try:
                reader.read_manifest()
                reader.read_workbook()
                sheets = reader.parser.sheets
                relationships = reader.parser.rels
            except (TypeError, ValueError, AttributeError) as error:
                raise ValueError("无法读取 Excel 工作簿。请选择有效的 .xlsx 文件。") from error
            if len(sheets) != 1 or sheets[0].name != _SHEET_NAME:
                raise ValueError("Excel 工作簿仅允许一张名为「基表」的工作表。")
            sheet = relationships[sheets[0].id]
            if sheet.Type != f"{REL_NS}/worksheet":
                raise ValueError("「基表」须为 Excel 工作表。")
            shared_part = reader.package.find(SHARED_STRINGS)
            shared_strings = []
            if shared_part is not None:
                with reader.archive.open(shared_part.PartName.lstrip("/")) as source:
                    shared_strings = [_xml_text(item) for item in _xml_children(source, "sst", "si")]
            with reader.archive.open(sheet.Target) as source:
                return _import_rows(_worksheet_rows(source, shared_strings), settings)
    except (BadZipFile, InvalidFileException, KeyError, ParseError) as error:
        raise ValueError("无法读取 Excel 工作簿。请选择有效的 .xlsx 文件。") from error


def _tag(name: str) -> str:
    return f"{{{SHEET_MAIN_NS}}}{name}"


def _xml_children(source, parent_name: str, child_name: str):
    parent_tag, child_tag = _tag(parent_name), _tag(child_name)
    parent = None
    found_parent = False
    for event, node in iterparse(source, events=("start", "end")):
        if event == "start":
            if node.tag == parent_tag:
                if found_parent:
                    raise ValueError("Excel 工作簿含重复的数据区域。")
                parent = node
                found_parent = True
            continue
        if node is parent:
            parent = None
        elif node.tag == child_tag:
            try:
                if parent is None:
                    raise ValueError
                parent.remove(node)
            except ValueError as error:
                raise ValueError("Excel 工作簿的数据结构无效。") from error
            yield node
    if not found_parent:
        raise ValueError("Excel 工作簿缺少数据区域。")


def _xml_text(node) -> str:
    # Decode each OOXML text element before joining any formatted runs.
    namespace = {"s": SHEET_MAIN_NS}
    return "".join(
        unescape(text.text or "")
        for text in node.findall("s:t", namespace) + node.findall("s:r/s:t", namespace)
    )


def _cell_value(cell, line: int, shared_strings: list[str]) -> object:
    if cell.find(_tag("f")) is not None:
        return _NON_TEXT
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(_tag("is"))
        return _xml_text(inline) if inline is not None else None
    value = cell.findtext(_tag("v"))
    if cell_type == "s":
        try:
            index = int(value or "")
            if 0 <= index < len(shared_strings):
                return shared_strings[index]
        except ValueError:
            pass
        raise ValueError(f"第 {line} 行的 Excel 文本索引无效。")
    return _NON_TEXT if value else None


def _worksheet_rows(source, shared_strings: list[str]):
    previous_line = 0
    for row in _xml_children(source, "sheetData", "row"):
        try:
            line = int(row.get("r", str(previous_line + 1)))
        except ValueError as error:
            raise ValueError("Excel 工作表含无效的行号。") from error
        if not previous_line < line <= 1048576:
            raise ValueError(f"第 {line} 行的 Excel 行号重复、乱序或超出范围。")
        previous_line = line
        cells = {}
        column = 0
        for cell in row.findall(_tag("c")):
            reference = cell.get("r")
            try:
                cell_line, cell_column = coordinate_to_tuple(reference) if reference else (line, column + 1)
            except (KeyError, ValueError) as error:
                raise ValueError(f"第 {line} 行的 Excel 单元格位置无效。") from error
            if cell_line != line or not column < cell_column <= 16384:
                raise ValueError(f"第 {line} 行的 Excel 单元格位置重复、乱序或超出范围。")
            column = cell_column
            value = _cell_value(cell, line, shared_strings)
            if value is not None:
                cells[column] = value
        yield line, cells


def _import_rows(rows, settings: Settings) -> Settings:
    first_line, header = next(rows, (None, {}))
    if first_line != 1 or header != dict(enumerate(COLUMNS, 1)):
        raise ValueError("第 1 行的表头必须依次为「编码」「厂家」「条码前缀」。")

    existing_keys = {row.key for row in settings.rows}
    existing_prefixes = {row.prefix for row in settings.rows}
    key_lines = {}
    prefix_lines = {}
    additions = []
    for line, cells in rows:
        if not cells:
            continue
        if any(column > 3 for column in cells):
            raise ValueError(f"第 {line} 行只能填写基表的三列。")
        data = []
        for column, label in enumerate(COLUMNS, 1):
            value = cells.get(column)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"第 {line} 行「{label}」不能为空。")
            if not isinstance(value, str):
                raise ValueError(f"第 {line} 行「{label}」必须填写文本。")
            data.append(value)
        try:
            row = BaseRow(*data)
        except ValueError as error:
            raise ValueError(f"第 {line} 行，{error}") from error
        if row.key in existing_keys:
            raise ValueError(f"第 {line} 行的编码和厂家组合已存在于基表。")
        if row.key in key_lines:
            raise ValueError(f"第 {line} 行的编码和厂家组合与第 {key_lines[row.key]} 行重复。")
        if row.prefix in existing_prefixes:
            raise ValueError(f"第 {line} 行的条码前缀已存在于基表。")
        if row.prefix in prefix_lines:
            raise ValueError(f"第 {line} 行的条码前缀与第 {prefix_lines[row.prefix]} 行重复。")
        key_lines[row.key] = line
        prefix_lines[row.prefix] = line
        additions.append(row)

    if not additions:
        raise ValueError("基表没有可导入的数据。")
    return replace(settings, rows=settings.rows + tuple(additions))
