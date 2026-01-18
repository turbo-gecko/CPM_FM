# general_config_dialog.py
import tkinter as tk
from tkinter import ttk


class GeneralConfigDialog:
    def __init__(self, parent, app):
        self.parent = parent  # This is the App instance
        self.app = app        # App instance (for set_status)
        
        # Create the dialog window
        top = self.top = tk.Toplevel(parent)
        top.title("General Config")
        top.geometry("400x350")
        top.resizable(False, False)

        # Main frame
        main_frame = ttk.Frame(top, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Terminal Commands group
        terminal_group = ttk.LabelFrame(main_frame, text="Terminal Commands", padding="5")
        terminal_group.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # List Files
        ttk.Label(terminal_group, text="List Files:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        self.list_files_entry = ttk.Entry(terminal_group, width=30)
        self.list_files_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5), pady=2)
        self.list_files_entry.insert(0, "DIR")
        
        # Change Disk
        ttk.Label(terminal_group, text="Change Disk:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        self.change_disk_entry = ttk.Entry(terminal_group, width=30)
        self.change_disk_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 5), pady=2)

        # Xmodem Commands group
        xmodem_group = ttk.LabelFrame(main_frame, text="Xmodem Commands", padding="5")
        xmodem_group.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Receive from Remote
        ttk.Label(xmodem_group, text="Receive from Remote:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        self.receive_entry = ttk.Entry(xmodem_group, width=30)
        self.receive_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5), pady=2)
        self.receive_entry.insert(0, "PCPUT $1")
        
        # Send to Remote
        ttk.Label(xmodem_group, text="Send to Remote:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        self.send_entry = ttk.Entry(xmodem_group, width=30)
        self.send_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 5), pady=2)
        self.send_entry.insert(0, "PCGET $1")

        # End of Line group
        eol_group = ttk.LabelFrame(main_frame, text="End of Line", padding="5")
        eol_group.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Radio buttons for End of Line
        self.eol_var = tk.StringVar(value="CR")  # Default is CR
        
        ttk.Radiobutton(eol_group, text="Carriage Return (CR)", variable=self.eol_var, value="CR").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(eol_group, text="Line Feed (LF)", variable=self.eol_var, value="LF").grid(row=1, column=0, sticky=tk.W)
        ttk.Radiobutton(eol_group, text="Carriage Return/Line Feed (CR/LF)", variable=self.eol_var, value="CRLF").grid(row=2, column=0, sticky=tk.W)

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        
        ok_btn = ttk.Button(button_frame, text="OK", command=self.on_ok)
        ok_btn.grid(row=0, column=0, padx=(0, 5))
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.on_cancel)
        cancel_btn.grid(row=0, column=1, padx=(5, 0))

        # Configure grid weights for resizing
        main_frame.columnconfigure(0, weight=1)
        terminal_group.columnconfigure(1, weight=1)
        xmodem_group.columnconfigure(1, weight=1)

    def on_ok(self):
        # Save the configuration values to app's general settings
        # This approach directly stores the config in the app object
        # as an alternative to accessing self.app.config.general_settings
        try:
            general_config = {
                'list_files': self.list_files_entry.get(),
                'change_disk': self.change_disk_entry.get(),
                'receive_from_remote': self.receive_entry.get(),
                'send_to_remote': self.send_entry.get(),
                'end_of_line': self.eol_var.get()
            }
            
            # Store in app object directly
            if not hasattr(self.app, 'general_settings'):
                self.app.general_settings = {}
            
            self.app.general_settings.update(general_config)
            
            self.app.set_status("General settings saved")
        except Exception as e:
            self.app.set_status(f"Error saving settings: {str(e)}")
        
        self.top.destroy()

    def on_cancel(self):
        self.app.set_status("General settings NOT saved")
        self.top.destroy()
