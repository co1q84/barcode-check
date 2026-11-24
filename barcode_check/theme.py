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
TABLE_GRID = "#DDE5EF"
TABLE_HEADING = "#EAF0F8"


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
    style.configure("Card.TFrame", background=SURFACE, borderwidth=1, relief="solid")
    style.configure("White.TLabel", background=SURFACE)
    style.configure("WhiteMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Section.TLabel", font=(UI_FONT, 12, "bold"))
    style.configure("WhiteSection.TLabel", background=SURFACE, font=(UI_FONT, 12, "bold"))
    style.configure("Scan.Card.TFrame", background=SURFACE)
    style.configure("Scan.TFrame", background=SURFACE)
    style.configure("ScanSection.TLabel", background=SURFACE, font=(UI_FONT, 12, "bold"))
    style.configure("ScanMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("BatchState.TLabel", padding=(8, 2))
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", padding=(16, 6), background=SURFACE, bordercolor=BORDER,
                    lightcolor=SURFACE, darkcolor=SURFACE)
    style.map("TNotebook.Tab", background=[("selected", PRIMARY_SOFT), ("active", PRIMARY_SOFT)],
              foreground=[("selected", PRIMARY)], padding=[("selected", (16, 6))],
              lightcolor=[("selected", PRIMARY_SOFT)])
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
    style.configure("Table.TButton", padding=(10, 4))
    style.configure("Table.TMenubutton", padding=(10, 4))
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
    style.configure("Table.TCombobox", padding=(6, 4))
    style.configure("TScrollbar", troughcolor=BG, background=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    arrowsize=11, arrowcolor=MUTED, gripcount=0)
    style.map("TScrollbar", background=[("pressed", "#A3B5CE"), ("active", "#BECDE0")])
    table_line_height = font.nametofont("TkDefaultFont", root).metrics("linespace")
    style.configure("Grid.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    borderwidth=1, rowheight=table_line_height + 11)
    style.configure("Records.Grid.Treeview", rowheight=table_line_height + 7)
    style.configure("Grid.Treeview.Cell", padding=(6, 0))
    style.configure("Grid.Treeview.Heading", font=(UI_FONT, 10, "bold"), background=TABLE_HEADING,
                    foreground=TEXT, relief="flat", padding=(7, 5))
    style.map("Grid.Treeview", background=[("selected", PRIMARY_SOFT)], foreground=[("selected", TEXT)],
              bordercolor=[("focus", PRIMARY)])
    style.configure("Summary.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    borderwidth=0, bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE,
                    rowheight=table_line_height + 4)
    style.configure("Summary.Treeview.Cell", padding=(4, 0))
    style.configure("Summary.Treeview.Heading", font=(UI_FONT, 10, "bold"), background=BG,
                    foreground=MUTED, relief="flat", padding=(6, 4))
    style.map("Summary.Treeview", background=[("selected", PRIMARY_SOFT)], foreground=[("selected", TEXT)])
    _configure_table_grid(root, style)


def grid_table(parent, columns, *, height, style="Records.Grid.Treeview", auto_scrollbar=False):
    frame = ttk.Frame(parent, style="White.TFrame")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree = ttk.Treeview(frame, columns=[column[0] for column in columns], show="headings",
                        selectmode="browse", height=height, style=style)
    for key, name, width, stretch in columns:
        tree.heading(key, text=name, anchor="center")
        tree.column(key, width=width, minwidth=70 if stretch else width, stretch=stretch, anchor="center")
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    def update_scrollbar(first, last):
        scrollbar.set(first, last)
        if float(first) == 0 and float(last) == 1:
            scrollbar.grid_remove()
        else:
            scrollbar.grid()

    tree.configure(yscrollcommand=update_scrollbar if auto_scrollbar else scrollbar.set)
    return frame, tree


def _configure_table_grid(root, style):
    if "Table.cell" not in style.element_names():
        right = tk.PhotoImage(master=root, width=1, height=64)
        right.put(TABLE_GRID, to=(0, 0, 1, 64))
        bottom = tk.PhotoImage(master=root, width=512, height=1)
        bottom.put(TABLE_GRID, to=(0, 0, 512, 1))
        empty = tk.PhotoImage(master=root, width=1, height=1)
        style.element_create("Table.right", "image", right, height=0)
        style.element_create("Table.bottom", "image", bottom, width=0)
        # Tk 8.6 insets each data cell by four pixels. Extend its layout to meet the heading edges.
        style.element_create("Table.cell", "image", empty, width=0, height=0, padding=(-4, 0), sticky="")
        root._table_grid_images = (right, bottom, empty)
    edges = [("Table.right", {"sticky": "nse"}), ("Table.bottom", {"sticky": "sew"})]
    style.layout("Grid.Treeview.Cell", [
        ("Table.cell", {"sticky": "nsew", "children": [*style.layout("Treeview.Cell"), *edges]}),
    ])
    style.layout("Grid.Treeview.Heading", [*style.layout("Treeview.Heading"), *edges])
    bottom_edge = edges[-1]
    style.layout("Summary.Treeview.Cell", [
        ("Table.cell", {"sticky": "nsew", "children": [*style.layout("Treeview.Cell"), bottom_edge]}),
    ])
    style.layout("Summary.Treeview.Heading", [*style.layout("Treeview.Heading"), bottom_edge])
