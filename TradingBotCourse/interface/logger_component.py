import tkinter as tk
from datetime import datetime

from interface.style import *

class Logger(tk.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger_text = tk.Text(
            self, 
            height=10, width=16, 
            state=tk.DISABLED, 
            bg=BG_COLOR, fg=FG_COLOR_2, font=GLOBAL_FONT)
        self.logger_text.pack(side=tk.TOP)

    def add_log(self, message: str):
        self.logger_text.configure(state=tk.NORMAL)
        self.logger_text.insert("1.0", f"{datetime.utcnow().strftime('%a %H:%M:%S :: ')}{message} \n")
        self.logger_text.configure(state=tk.DISABLED)