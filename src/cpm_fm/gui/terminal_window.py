import tkinter as tk
from tkinter import scrolledtext


class TerminalWindow(tk.Toplevel):
    """
    Non-modal Terminal window (SRS docs/cpm_fm_requirements.md, UIR-060-UIR-067;
    receive/transmit behaviour FR-090-FR-098).
    """

    def __init__(self, parent, send_callback, clear_callback=None):
        super().__init__(parent)
        self.title("Terminal")
        self.send_callback = send_callback
        # Invoked when the Clear button is pressed, so the owner can clear the
        # receive/transmit data buffers alongside the display (FR-090/FR-092).
        self.clear_callback = clear_callback

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

    def create_widgets(self):
        # Receive Area
        self.receive_area = scrolledtext.ScrolledText(self, state="disabled", wrap=tk.WORD)
        self.receive_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Control Frame
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        self.btn_clear = tk.Button(ctrl_frame, text="Clear", command=self.clear_text)
        self.btn_clear.pack(side=tk.LEFT)

        self.var_local_echo = tk.BooleanVar(value=False)
        self.chk_echo = tk.Checkbutton(ctrl_frame, text="Local Echo", variable=self.var_local_echo)
        self.chk_echo.pack(side=tk.LEFT, expand=True)

        self.var_autoscroll = tk.BooleanVar(value=True)
        self.chk_scroll = tk.Checkbutton(
            ctrl_frame, text="Autoscroll", variable=self.var_autoscroll
        )
        self.chk_scroll.pack(side=tk.RIGHT)

        # Transmit Frame
        tx_frame = tk.Frame(self)
        tx_frame.pack(fill=tk.X, padx=10, pady=10)

        self.tx_entry = tk.Entry(tx_frame)
        self.tx_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.tx_entry.bind("<Return>", lambda e: self.send_text())

        self.btn_send = tk.Button(tx_frame, text="Send", command=self.send_text)
        self.btn_send.pack(side=tk.RIGHT)

    def clear_text(self):
        self.receive_area.configure(state="normal")
        self.receive_area.delete("1.0", tk.END)
        self.receive_area.configure(state="disabled")
        if self.clear_callback:
            self.clear_callback()

    def send_text(self):
        text = self.tx_entry.get()
        if text:
            self.send_callback(text)
            self.tx_entry.delete(0, tk.END)

    def write_text(self, text):
        """Appends text to the receive area."""
        self.receive_area.configure(state="normal")
        self.receive_area.insert(tk.END, text)
        if self.var_autoscroll.get():
            self.receive_area.see(tk.END)
        self.receive_area.configure(state="disabled")

    def hide_window(self):
        # Requirements say non-modal, often these stay alive in background
        self.withdraw()
