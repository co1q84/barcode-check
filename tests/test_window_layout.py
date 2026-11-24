import unittest
from ctypes import wintypes
from unittest.mock import Mock, patch

from barcode_check.window_layout import center_dialog, configure_main_window


class MainWindowLayoutTests(unittest.TestCase):
    def make_root(self, width, height, window_system="win32"):
        root = Mock()
        root.winfo_screenwidth.return_value = width
        root.winfo_screenheight.return_value = height
        root.tk.call.return_value = window_system
        return root

    def configure_windows(self, screen, work_area):
        root = self.make_root(*screen)
        with patch("barcode_check.window_layout._windows_desktop_metrics", return_value=(work_area, (16, 39))):
            configure_main_window(root)
        return root

    def test_widescreen_initial_frame_is_bounded_by_eighty_percent_and_centered(self):
        root = self.configure_windows((1920, 1080), (0, 0, 1920, 1040))
        root.geometry.assert_called_once_with("1136x825+384+88")
        root.minsize.assert_called_once_with(820, 580)

    def test_four_three_desktop_and_side_taskbar(self):
        root = self.configure_windows((1600, 1200), (48, 0, 1600, 1200))
        root.geometry.assert_called_once_with("1264x921+184+120")
        root.minsize.assert_called_once_with(820, 580)

    def test_compact_widescreen_keeps_the_full_minimum_client_layout(self):
        root = self.configure_windows((1280, 720), (0, 0, 1280, 672))
        root.geometry.assert_called_once_with("820x588+222+22")
        root.minsize.assert_called_once_with(820, 580)

    def test_small_work_area_caps_initial_and_minimum_sizes(self):
        root = self.configure_windows((640, 480), (0, 0, 640, 440))
        root.geometry.assert_called_once_with("568x399+28+1")
        root.minsize.assert_called_once_with(568, 399)

    def test_non_windows_uses_tk_screen_bounds_without_win32_calls(self):
        root = self.make_root(1600, 900, "x11")
        with patch("barcode_check.window_layout._windows_desktop_metrics") as win32:
            configure_main_window(root)
        win32.assert_not_called()
        root.geometry.assert_called_once_with("960x720+320+90")
        root.minsize.assert_called_once_with(820, 580)


class DialogLayoutTests(unittest.TestCase):
    def center_windows_dialog(self, owner_bounds, work_area, size=(880, 550)):
        dialog = Mock()
        dialog.tk.call.return_value = "win32"
        dialog.minsize.return_value = (680, 400)
        owner = Mock()
        owner.winfo_toplevel.return_value = owner
        owner.winfo_screenwidth.return_value = 1280
        owner.winfo_screenheight.return_value = 720
        owner.wm_frame.return_value = "0x1234"
        user32 = Mock()
        user32.MonitorFromWindow.side_effect = lambda hwnd, flags: 42 if (hwnd, flags) == (0x1234, 2) else 0

        def get_window_rect(_hwnd, rect):
            rect._obj.left, rect._obj.top, rect._obj.right, rect._obj.bottom = owner_bounds
            return True

        def get_monitor_info(monitor, info):
            if monitor != 42:
                return False
            info._obj.work = wintypes.RECT(*work_area)
            return True

        user32.GetWindowRect.side_effect = get_window_rect
        user32.GetMonitorInfoW.side_effect = get_monitor_info
        with (
            patch("barcode_check.window_layout.ctypes.windll", create=True) as windll,
            patch("barcode_check.window_layout._windows_frame_size", return_value=(16, 39)),
        ):
            windll.user32 = user32
            center_dialog(dialog, owner, *size)
        return dialog

    def test_windows_dialog_centers_outer_frame_on_owner_when_it_fits(self):
        dialog = self.center_windows_dialog((222, 22, 1058, 649), (0, 0, 1280, 672))
        dialog.geometry.assert_called_once_with("880x550+192+41")
        dialog.minsize.assert_not_called()
        dialog.update_idletasks.assert_called_once()
        dialog.deiconify.assert_not_called()

    def test_windows_dialog_respects_the_left_edge_of_the_work_area(self):
        dialog = self.center_windows_dialog((0, 22, 836, 649), (0, 0, 1280, 672))
        dialog.geometry.assert_called_once_with("880x550+0+41")

    def test_windows_dialog_respects_right_and_bottom_taskbars(self):
        dialog = self.center_windows_dialog((500, 130, 1336, 757), (0, 0, 1232, 672))
        dialog.geometry.assert_called_once_with("880x550+336+83")

    def test_windows_dialog_uses_secondary_monitor_with_negative_origin(self):
        dialog = self.center_windows_dialog((-1270, -30, -450, 590), (-1232, 36, 0, 900))
        dialog.geometry.assert_called_once_with("880x550+-1232+36")

    def test_windows_dialog_shrinks_when_the_monitor_cannot_fit_it(self):
        dialog = self.center_windows_dialog((70, 36, 590, 424), (48, 20, 640, 440))
        dialog.geometry.assert_called_once_with("576x381+48+20")
        dialog.minsize.assert_called_with(576, 381)

    def test_non_windows_dialog_clamps_to_tk_screen_bounds(self):
        dialog = Mock()
        dialog.tk.call.return_value = "x11"
        owner = Mock()
        owner.winfo_toplevel.return_value = owner
        owner.winfo_rootx.return_value = 10
        owner.winfo_rooty.return_value = 550
        owner.winfo_width.return_value = 300
        owner.winfo_height.return_value = 200
        owner.winfo_screenwidth.return_value = 800
        owner.winfo_screenheight.return_value = 600

        center_dialog(dialog, owner, 400, 300)

        dialog.geometry.assert_called_once_with("400x300+0+300")
