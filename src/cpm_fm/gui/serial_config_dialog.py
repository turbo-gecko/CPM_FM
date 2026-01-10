# serial_config_dialog.py
import tkinter as tk
from tkinter import ttk
import serial.tools.list_ports


class SerialConfigDialog:
    def __init__(self, parent, app):
        self.parent = parent  # This is the App instance
        self.app = app        # App instance (for set_status)

        top = self.top = tk.Toplevel(parent)
        top.title("Serial Configuration")
        top.geometry("300x350")

        # Port Settings
        port_frame = ttk.LabelFrame(top, text="Port Settings")
        port_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        # Configure grid columns inside port_frame for proper expansion
        port_frame.columnconfigure(0, weight=1)  # Label column
        port_frame.columnconfigure(1, weight=1)  # Entry column

        # Terminal Comm Port
        ttk.Label(port_frame, text="Terminal Comm Port:").grid(
            row=0, column=0, padx=5, pady=2, sticky="w")

        self.term_port_var = tk.StringVar()
        ports = serial.tools.list_ports.comports()
        self.term_port_combo = ttk.Combobox(port_frame, textvariable=self.term_port_var,
                                            values=[
                                                port.device for port in ports],
                                            state='readonly')
        self.term_port_combo.grid(row=0, column=1, padx=5, pady=2, sticky="e")
        self.term_port_combo.set(self.app.serial_config['terminal_port'])

        # Transfer Comm Port
        ttk.Label(port_frame, text="Transport Comm Port:").grid(
            row=1, column=0, padx=5, pady=2, sticky="w")

        self.trans_port_var = tk.StringVar()
        ports = serial.tools.list_ports.comports()
        self.trans_port_combo = ttk.Combobox(port_frame, textvariable=self.trans_port_var,
                                             values=[
                                                 port.device for port in ports],
                                             state='readonly')
        self.trans_port_combo.grid(row=1, column=1, padx=5, pady=2, sticky="e")
        self.trans_port_combo.set(self.app.serial_config['transport_port'])

        # Speed
        ttk.Label(port_frame, text="Speed:").grid(
            row=2, column=0, padx=5, pady=2, sticky="w")
        self.speed_var = tk.StringVar()
        speeds = ['300', '1200', '2400', '4800', '9600', '14400', '19200',
                  '38400', '57600', '115200', '230400', '460800', '921600']
        self.speed_combo = ttk.Combobox(port_frame, textvariable=self.speed_var,
                                        values=speeds, state='readonly')
        self.speed_combo.grid(row=2, column=1, padx=5, pady=2, sticky="e")
        self.speed_combo.set(self.app.serial_config['speed'])

        # Data bits
        ttk.Label(port_frame, text="Data:").grid(
            row=3, column=0, padx=5, pady=2, sticky="w")
        self.data_var = tk.StringVar()
        data_bits = ['7', '8']
        self.data_combo = ttk.Combobox(port_frame, textvariable=self.data_var,
                                       values=data_bits, state='readonly')
        self.data_combo.grid(row=3, column=1, padx=5, pady=2, sticky="e")
        self.data_combo.set(self.app.serial_config['data'])

        # Parity (incomplete in citation — add rest as needed)
        ttk.Label(port_frame, text="Parity:").grid(
            row=4, column=0, padx=5, pady=2, sticky="w")
        self.parity_var = tk.StringVar()
        parity_options = ['NONE', 'EVEN', 'ODD']
        self.parity_combo = ttk.Combobox(port_frame, textvariable=self.parity_var,
                                         values=parity_options, state='readonly')
        self.parity_combo.grid(row=4, column=1, padx=5, pady=2, sticky="e")
        self.parity_combo.set(self.app.serial_config['parity'])

        # Stop bits
        ttk.Label(port_frame, text="Stop Bits:").grid(
            row=5, column=0, padx=5, pady=2, sticky="w")
        self.stopbit_var = tk.StringVar()
        stopbits = ['1', '2']
        self.stopbit_combo = ttk.Combobox(port_frame, textvariable=self.stopbit_var,
                                          values=stopbits, state='readonly')
        self.stopbit_combo.grid(row=5, column=1, padx=5, pady=2, sticky="e")
        self.stopbit_combo.set(self.app.serial_config['stopbits'])

        # Flow Control
        ttk.Label(port_frame, text="Flow Control:").grid(
            row=6, column=0, padx=5, pady=2, sticky="w")
        self.flow_var = tk.StringVar()
        flow_options = ['NONE', 'XON/XOFF', 'RTS/CTS', 'DSR/DTR']
        self.flow_combo = ttk.Combobox(port_frame, textvariable=self.flow_var,
                                       values=flow_options, state='readonly')
        self.flow_combo.grid(row=6, column=1, padx=5, pady=2, sticky="e")
        self.flow_combo.set(self.app.serial_config['flow'])

        # Transmit Delay
        delay_frame = ttk.LabelFrame(top, text="Transmit Delay")
        delay_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        # Configure grid columns inside delay_frame for proper expansion
        delay_frame.columnconfigure(0, weight=1)  # Label column
        delay_frame.columnconfigure(1, weight=1)  # Entry column

        ttk.Label(delay_frame, text="msec/char:").grid(row=0,
                                                       column=0, sticky='w', padx=5, pady=2)
        self.msec_char = tk.StringVar(
            value=self.app.serial_config['msec_char'])
        ttk.Entry(delay_frame, textvariable=self.msec_char,
                  width=10).grid(row=0, column=1, padx=5, pady=2, sticky="e")

        ttk.Label(delay_frame, text="msec/line:").grid(row=1,
                                                       column=0, sticky='w', padx=5, pady=2)
        self.msec_line = tk.StringVar(
            value=self.app.serial_config['msec_line'])
        ttk.Entry(delay_frame, textvariable=self.msec_line,
                  width=10).grid(row=1, column=1, padx=5, pady=2, sticky="e")

        # Buttons
        btn_frame = ttk.Frame(top)
        btn_frame.pack(pady=(20, 10))

        ok_btn = ttk.Button(btn_frame, text="OK", command=self.on_ok)
        ok_btn.grid(row=0, column=0, padx=5)
        cancel_btn = ttk.Button(
            btn_frame, text="Cancel", command=self.on_cancel)
        cancel_btn.grid(row=0, column=1, padx=5)

    def on_ok(self):
        # Here you would save the selected settings to self.top.result or similar
        self.app.serial_config['terminal_port'] = self.term_port_var.get()
        self.app.serial_config['transport_port'] = self.trans_port_var.get()
        self.app.serial_config['speed'] = self.speed_var.get()
        self.app.serial_config['data'] = self.data_var.get()
        self.app.serial_config['parity'] = self.parity_var.get()
        self.app.serial_config['stopbits'] = self.stopbit_var.get()
        self.app.serial_config['flow'] = self.flow_var.get()
        self.app.serial_config['msec_char'] = self.msec_char.get()
        self.app.serial_config['msec_line'] = self.msec_line.get()

        self.app.set_status("Serial settings updated")
        self.top.destroy()

    def on_cancel(self):
        self.app.set_status("Serial settings NOT updated")
        self.top.destroy()
