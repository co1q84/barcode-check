import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable


RECORD_PAGE_SIZES = (20, 50, 100)
DEFAULT_RECORDS_PER_PAGE = 20
BARCODE_INPUT_PADDING = " \t\r\n"


def _validate_setting_text(value: str, label: str, padding: str | None = None) -> None:
    if not isinstance(value, str) or not value.strip(padding) or any(c in value for c in "\r\n\0\v\f\u0085\u2028\u2029"):
        raise ValueError(f"{label}须为非空的单行文本。")
    if value != value.strip(padding):
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
        _validate_setting_text(self.prefix, "条码前缀", BARCODE_INPUT_PADDING)

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


class SettingsReadError(ValueError):
    """The file was read but its contents could not be used."""


class SettingsSaveCancelled(Exception):
    """The user canceled a save that needs confirmation."""


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else user_settings_path()
        self._revision: bytes | None = None
        self._invalid_revision = False

    def _read(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def load(self) -> Settings:
        data = self._read()
        if data is None:
            self._revision = None
            self._invalid_revision = False
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
        except (KeyError, TypeError, ValueError, RecursionError) as error:
            self._revision = data
            self._invalid_revision = True
            raise SettingsReadError(f"无法读取设置文件「{self.path}」：{error}") from error
        self._revision = data
        self._invalid_revision = False
        return settings

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock(self.path.with_suffix(".lock")):
            self._verify_revision()
            if self._invalid_revision:
                raise SettingsReadError("当前设置文件无法读取。请先备份原文件并恢复设置。")
            self._replace(settings)

    def recover(self, settings: Settings) -> Path:
        """Back up the invalid file observed by load and save its replacement."""
        with _write_lock(self.path.with_suffix(".lock")):
            original = self._verify_revision()
            if not self._invalid_revision or original is None:
                raise ValueError("当前设置无需恢复。")
            backup = self._write_copy(original, f"{self.path.stem}-backup-", self.path.suffix)
            self._replace(settings)
            return backup

    def _verify_revision(self) -> bytes | None:
        data = self._read()
        if data != self._revision:
            raise ValueError("设置文件已有变更。请关闭程序后重新打开，再保存设置。")
        return data

    def _replace(self, settings: Settings) -> None:
        payload = {
            "version": 2,
            "rows": [asdict(row) for row in settings.rows],
            "records_per_page": settings.records_per_page,
        }
        data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        temporary_path = self._write_copy(data, "settings-", ".tmp")
        try:
            temporary_path.replace(self.path)
            self._revision = data
            self._invalid_revision = False
        finally:
            temporary_path.unlink(missing_ok=True)

    def _write_copy(self, data: bytes, prefix: str, suffix: str) -> Path:
        path = None
        try:
            with NamedTemporaryFile(dir=self.path.parent, prefix=prefix, suffix=suffix, delete=False) as file:
                path = Path(file.name)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            return path
        except BaseException:
            if path is not None:
                path.unlink(missing_ok=True)
            raise
