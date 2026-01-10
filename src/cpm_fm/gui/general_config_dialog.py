# general_config_dialog.py
import tkinter as tk
from tkinter import ttk


class GeneralConfigDialog:
    def __init__(self, parent, app):
        self.parent = parent  # This is the App instance
        self.app = app        # App instance (for set_status)

        top = self.top = tk.Toplevel(parent)
        top.title("General Configuration")
        top.geometry("300x200")

        ttk.Label(top, text="General Settings (Placeholder)").pack(pady=20)

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=20)

        ok_btn = ttk.Button(btn_frame, text="OK", command=self.on_ok)
        ok_btn.grid(row=0, column=0, padx=5)

        cancel_btn = ttk.Button(
            btn_frame, text="Cancel", command=self.on_cancel)
        cancel_btn.grid(row=0, column=1, padx=5)

    def on_ok(self):
        self.app.set_status("General settings saved (stub)")
        self.top.destroy()

    def on_cancel(self):
        self.app.set_status("General settings NOT saved (stub)")
        self.top.destroy()
