import tkinter as tk
from tkinter import scrolledtext

class TerminalDialog:
    def __init__(self, parent, app):
        self.parent = parent  # This is the App instance
        self.app = app        # App instance (for set_status)

        top = self.top = tk.Toplevel(parent)
        top.title("Terminal Window")
        top.geometry("600x400")
        self.top.resizable(True, True)

        # Initialize the UI components
        self.create_widgets()

    def create_widgets(self):
        # Multiline text area for receiving data (read-only)
        self.recv_text = scrolledtext.ScrolledText(
            self.top,
            wrap=tk.WORD,
            state='normal',
            height=15,
            font=("Courier", 10)
        )
        self.recv_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.recv_text.insert(tk.END, "Terminal dialog started. Type a message below and click Send.\n\n")
        self.recv_text.config(state='disabled')  # Make it read-only

        # Frame to hold the input field and send button
        self.input_frame = tk.Frame(self.top)
        self.input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)

        # Single-line text entry for sending data
        self.entry = tk.Entry(self.input_frame, font=("Courier", 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        # Send button
        self.send_button = tk.Button(
            self.input_frame,
            text="Send",
            command=self.send_message,
            font=("Courier", 10),
            bg="#4CAF50",
            fg="white",
            activebackground="#45a049"
        )
        self.send_button.pack(side=tk.RIGHT)

        # Bind Enter key to send message
        self.top.bind('<Return>', lambda event: self.send_message())

    def send_message(self):
        message = self.entry.get().strip()
        if message:
            # Enable text area temporarily to insert message
            self.recv_text.config(state='normal')
            self.recv_text.insert(tk.END, "You: " + message + "\n")
            self.recv_text.config(state='disabled')  # Re-disable after insertion

            # Clear the input field
            self.entry.delete(0, tk.END)

    def receive_message(self, text):
        """External method to add received messages (e.g., from a server or other source)"""
        self.recv_text.config(state='normal')
        self.recv_text.insert(tk.END, "Other: " + text + "\n")
        self.recv_text.config(state='disabled')

    def run(self):
        """Start the GUI event loop"""
        self.top.mainloop()


# Example usage:
if __name__ == "__main__":
    root = tk.Tk()
    app = TerminalDialog(root)
    app.run()
