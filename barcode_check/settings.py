import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable


RECORD_PAGE_SIZES = (20, 50, 100)
DEFAULT_RECORDS_PER_PAGE = 20


def _validate_setting_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\0\v\f\u0085\u2028\u2029"):
        raise ValueError(f"{label}须为非空的单行文本。")
    if value != value.strip():
        raise ValueError(f"{label}不能含首尾空白。")
    try:
        length = len(value.encode("utf-16-le")) // 2
    except UnicodeEncodeError as error:
        raise ValueError(f"{label}含有无效字符。") from error
    if length > 32767:
        raise ValueError(f"{label}超过 Excel 单元格的字符上限。")


@dataclass(frozen=True)
class BaseRow:
    code: str
    manufacturer: str
    prefix: str

    def __post_init__(self):
        _validate_setting_text(self.code, "编码")
        _validate_setting_text(self.manufacturer, "厂家")
        _validate_setting_text(self.prefix, "条码前缀")

    @property
    def key(self) -> tuple[str, str]:
        return self.code, self.manufacturer


@dataclass(frozen=True)
class Settings:
    rows: tuple[BaseRow, ...] = ()
    records_per_page: int = DEFAULT_RECORDS_PER_PAGE
    codes: tuple[str, ...] = field(init=False, repr=False, compare=False)
    manufacturers: tuple[str, ...] = field(init=False, repr=False, compare=False)
    _ordered_rows: tuple[BaseRow, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if type(self.records_per_page) is not int or self.records_per_page not in RECORD_PAGE_SIZES:
            raise ValueError("每页条数须为 20、50 或 100。")
        rows = tuple(self.rows)
        keys = set()
        prefix_owners = {}
        for row in rows:
            if row.key in keys:
                raise ValueError(f"编码「{row.code}」和厂家「{row.manufacturer}」的组合已存在。")
            keys.add(row.key)
            if row.prefix in prefix_owners:
                owner = prefix_owners[row.prefix]
                raise ValueError(f"条码前缀「{row.prefix}」已用于编码「{owner.code}」和厂家「{owner.manufacturer}」。")
            prefix_owners[row.prefix] = row
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "codes", tuple(dict.fromkeys(row.code for row in rows)))
        object.__setattr__(self, "manufacturers", tuple(dict.fromkeys(row.manufacturer for row in rows)))
        object.__setattr__(self, "_ordered_rows", tuple(sorted(rows, key=lambda row: -len(row.prefix))))

    def match(self, barcode: str) -> BaseRow | None:
        return next((row for row in self._ordered_rows if barcode.startswith(row.prefix)), None)


def edit_row(settings: Settings, original: BaseRow | None, replacement: BaseRow) -> Settings:
    rows = list(settings.rows)
    if original is None:
        rows.append(replacement)
    else:
        try:
            rows[rows.index(original)] = replacement
        except ValueError as error:
            raise ValueError("该基表记录已不存在，请重新选择。") from error
    return replace(settings, rows=tuple(rows))


def delete_rows(settings: Settings, selected: Iterable[BaseRow]) -> Settings:
    selected_rows = set(selected)
    return replace(settings, rows=tuple(row for row in settings.rows if row not in selected_rows))


def user_settings_path() -> Path:
    roaming = os.environ.get("APPDATA")
    directory = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    return directory / "barcode-check" / "settings.json"


@contextmanager
def _write_lock(path: Path):
    with path.open("a+b") as file:
        if os.name == "nt":
            import msvcrt

            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else user_settings_path()
        self._revision: bytes | None = None

    def _read(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def load(self) -> Settings:
        data = self._read()
        if data is None:
            self._revision = None
            return Settings()
        try:
            value = json.loads(data)
            version = value.get("version") if isinstance(value, dict) else None
            if type(version) is not int or version != 2:
                raise ValueError("设置版本不符合当前条码基表格式。")
            stored_rows = value.get("rows")
            if not isinstance(stored_rows, list):
                raise ValueError("缺少有效的条码基表数据。")
            rows = tuple(BaseRow(**item) for item in stored_rows)
            settings = Settings(rows, records_per_page=value["records_per_page"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"无法读取设置文件「{self.path}」：{error}") from error
        self._revision = data
        return settings

    def save(self, settings: Settings) -> None:
        payload = {
            "version": 2,
            "rows": [asdict(row) for row in settings.rows],
            "records_per_page": settings.records_per_page,
        }
        data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock(self.path.with_suffix(".lock")):
            if self._read() != self._revision:
                raise ValueError("设置文件已有变更。请关闭程序后重新打开，再保存设置。")
            temporary_path = None
            try:
                with NamedTemporaryFile(dir=self.path.parent, prefix="settings-", suffix=".tmp", delete=False) as file:
                    temporary_path = Path(file.name)
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                temporary_path.replace(self.path)
                self._revision = data
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
