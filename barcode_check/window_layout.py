import ctypes
import tkinter as tk
from ctypes import wintypes


_MONITOR_DEFAULTTOPRIMARY = 1
_MONITOR_DEFAULTTONEAREST = 2
_SPI_GETWORKAREA = 0x0030
_WS_OVERLAPPEDWINDOW = 0x00CF0000
_MIN_CLIENT_WIDTH = 820
_MIN_CLIENT_HEIGHT = 580


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("monitor", wintypes.RECT),
        ("work", wintypes.RECT),
        ("flags", wintypes.DWORD),
    ]


def configure_main_window(root: tk.Tk) -> None:
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    work_area = (0, 0, screen_width, screen_height)
    frame_width, frame_height = 0, 0
    if root.tk.call("tk", "windowingsystem") == "win32":
        work_area, (frame_width, frame_height) = _windows_desktop_metrics(screen_width, screen_height)

    left, top, right, bottom = work_area
    work_width, work_height = right - left, bottom - top
    work_units = min(work_width // 4, work_height // 3)
    preferred_width, preferred_height = screen_width * 4 // 5, screen_height * 4 // 5
    preferred_units = min(preferred_width // 4, preferred_height // 3)
    layout_units = max(
        (_MIN_CLIENT_WIDTH + frame_width + 3) // 4,
        (_MIN_CLIENT_HEIGHT + frame_height + 2) // 3,
    )
    units = min(work_units, max(preferred_units, layout_units))
    outer_width, outer_height = units * 4, units * 3
    width, height = max(1, outer_width - frame_width), max(1, outer_height - frame_height)
    x = left + (work_width - outer_width) // 2
    y = top + (work_height - outer_height) // 2

    root.minsize(min(width, _MIN_CLIENT_WIDTH), min(height, _MIN_CLIENT_HEIGHT))
    root.geometry(f"{width}x{height}+{x}+{y}")


def center_dialog(window: tk.Toplevel, parent: tk.Misc, width: int, height: int) -> None:
    owner = parent.winfo_toplevel()
    owner.update_idletasks()
    left, top = owner.winfo_rootx(), owner.winfo_rooty()
    owner_width, owner_height = owner.winfo_width(), owner.winfo_height()
    work_area = (0, 0, owner.winfo_screenwidth(), owner.winfo_screenheight())
    frame_width, frame_height = 0, 0
    if window.tk.call("tk", "windowingsystem") == "win32":
        user32 = ctypes.windll.user32
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        hwnd = int(owner.wm_frame(), 0)
        owner_rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(owner_rect)):
            left, top = owner_rect.left, owner_rect.top
            owner_width, owner_height = owner_rect.right - left, owner_rect.bottom - top
        monitor = user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        info = _windows_monitor_info(user32, monitor)
        if info is not None:
            work = info.work
            work_area = (work.left, work.top, work.right, work.bottom)
        frame_width, frame_height = _windows_frame_size(user32)

    work_left, work_top, work_right, work_bottom = work_area
    width_limit = max(1, work_right - work_left - frame_width)
    height_limit = max(1, work_bottom - work_top - frame_height)
    if width > width_limit or height > height_limit:
        width, height = min(width, width_limit), min(height, height_limit)
        min_width, min_height = window.minsize()
        if min_width > width_limit or min_height > height_limit:
            window.minsize(min(min_width, width_limit), min(min_height, height_limit))

    outer_width, outer_height = width + frame_width, height + frame_height
    x = left + (owner_width - outer_width) // 2
    y = top + (owner_height - outer_height) // 2
    x = max(work_left, min(x, work_right - outer_width))
    y = max(work_top, min(y, work_bottom - outer_height))
    # A literal + prefix keeps negative coordinates absolute in Tk geometry.
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.update_idletasks()


def _windows_desktop_metrics(screen_width, screen_height):
    user32 = ctypes.windll.user32
    work_area = (0, 0, screen_width, screen_height)
    user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    primary = user32.MonitorFromPoint(wintypes.POINT(0, 0), _MONITOR_DEFAULTTOPRIMARY)
    info = _windows_monitor_info(user32, primary)
    if info is not None:
        monitor, work = info.monitor, info.work
        # The paired rectangles share a coordinate space, even when Windows scales the display.
        scale_x = screen_width / (monitor.right - monitor.left)
        scale_y = screen_height / (monitor.bottom - monitor.top)
        work_area = (
            round((work.left - monitor.left) * scale_x),
            round((work.top - monitor.top) * scale_y),
            round((work.right - monitor.left) * scale_x),
            round((work.bottom - monitor.top) * scale_y),
        )
    else:
        work = wintypes.RECT()
        if user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
            if 0 <= work.left < work.right <= screen_width and 0 <= work.top < work.bottom <= screen_height:
                work_area = (work.left, work.top, work.right, work.bottom)

    return work_area, _windows_frame_size(user32)


def _windows_monitor_info(user32, monitor):
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MonitorInfo))
    info = _MonitorInfo(size=ctypes.sizeof(_MonitorInfo))
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return info
    return None


def _windows_frame_size(user32):
    frame = wintypes.RECT()
    user32.AdjustWindowRectEx(ctypes.byref(frame), _WS_OVERLAPPEDWINDOW, False, 0)
    return frame.right - frame.left, frame.bottom - frame.top
