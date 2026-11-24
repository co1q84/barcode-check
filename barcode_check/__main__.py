import tkinter as tk

from barcode_check.app import BarcodeCheckApp


def main():
    root = tk.Tk()
    BarcodeCheckApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
