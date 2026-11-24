import tkinter as tk
from tkinter import font, ttk


UI_FONT = "Microsoft YaHei UI"
BG = "#F4F6FA"
SURFACE = "#FFFFFF"
BORDER = "#D6DFEB"
TEXT = "#17263B"
MUTED = "#53637A"
PRIMARY = "#235BB7"
PRIMARY_HOVER = "#194C9F"
PRIMARY_SOFT = "#EAF1FC"
ERROR = "#A42932"
ERROR_SOFT = "#FCEDEF"
SUCCESS = "#176347"
SUCCESS_SOFT = "#E9F5EF"
WARN = "#8B4B10"
WARN_SOFT = "#FFF3DE"
SCAN_ALERT_ERROR = "#FFDBDF"
SCAN_ALERT_WARNING = "#FFE6BB"


def configure_theme(root: tk.Tk) -> None:
    root.configure(background=BG)
    font.nametofont("TkDefaultFont", root).configure(family=UI_FONT, size=10)
    font.nametofont("TkTextFont", root).configure(family=UI_FONT, size=10)
    root.option_add("*Menu.font", (UI_FONT, 10))
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(UI_FONT, 10), background=BG, foreground=TEXT, bordercolor=BORDER)
    style.configure("TFrame", background=BG)
    style.configure("White.TFrame", background=SURFACE)
    style.configure("White.TLabel", background=SURFACE)
    style.configure("WhiteMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Section.TLabel", font=(UI_FONT, 12, "bold"))
    style.configure("WhiteSection.TLabel", background=SURFACE, font=(UI_FONT, 12, "bold"))
    style.configure("ScanPanel.TFrame", background=SURFACE)
    style.configure("ScanSection.TLabel", background=SURFACE, font=(UI_FONT, 12, "bold"))
    style.configure("ScanMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("TButton", padding=(11, 6), background=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE)
    style.map("TButton", background=[("disabled", BG), ("pressed", PRIMARY_SOFT), ("active", PRIMARY_SOFT)],
              foreground=[("disabled", MUTED)], bordercolor=[("focus", PRIMARY)])
    style.configure("Primary.TButton", background=PRIMARY, foreground=SURFACE, bordercolor=PRIMARY,
                    lightcolor=PRIMARY, darkcolor=PRIMARY, focuscolor=SURFACE)
    style.map("Primary.TButton", background=[("disabled", BG), ("pressed", PRIMARY_HOVER), ("active", PRIMARY_HOVER)],
              foreground=[("disabled", MUTED)], bordercolor=[("focus", PRIMARY_HOVER)])
    style.configure("Danger.TButton", foreground=ERROR)
    style.configure("TMenubutton", padding=(11, 6), background=SURFACE, arrowsize=5,
                    arrowcolor=MUTED, arrowpadding=(0, 0, 10, 0))
    style.map("TMenubutton", background=[("disabled", BG), ("active", PRIMARY_SOFT)],
              foreground=[("disabled", MUTED)])
    style.configure("TEntry", padding=(8, 6), fieldbackground=SURFACE, selectbackground=PRIMARY,
                    selectforeground=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE)
    style.map("TEntry", bordercolor=[("focus", PRIMARY)], fieldbackground=[("disabled", BG)],
              foreground=[("disabled", MUTED)])
    style.configure("Scan.TEntry", padding=(10, 9))
    style.configure("TCombobox", padding=(8, 6), arrowsize=13, background=BG, fieldbackground=SURFACE)
    style.map("TCombobox", bordercolor=[("focus", PRIMARY)],
              fieldbackground=[("disabled", BG), ("readonly", SURFACE)],
              foreground=[("disabled", MUTED)], selectbackground=[("readonly", SURFACE)],
              selectforeground=[("readonly", TEXT)])
    table_line_height = font.nametofont("TkDefaultFont", root).metrics("linespace")
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    borderwidth=1, rowheight=table_line_height + 11)
    style.configure("Records.Treeview", rowheight=table_line_height + 7)
    style.configure("Treeview.Heading", font=(UI_FONT, 10, "bold"), background="#EAF0F8",
                    foreground=TEXT, relief="flat", padding=(7, 6))
    style.map("Treeview", background=[("selected", PRIMARY_SOFT)], foreground=[("selected", TEXT)])
    style.configure("Horizontal.TProgressbar", background=PRIMARY, troughcolor="#DCE6F6", borderwidth=0,
                    lightcolor=PRIMARY, darkcolor=PRIMARY, thickness=6)
