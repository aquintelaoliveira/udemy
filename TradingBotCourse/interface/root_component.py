import tkinter as tk

from interface.logger_component import Logger

from interface.style import *

class Root(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Trading Bot")

        self.configure(bg=BG_COLOR)

        self._left_frame = tk.Frame(self, bg=BG_COLOR)
        self._left_frame.pack(side=tk.LEFT)

        self._right_frame = tk.Frame(self, bg=BG_COLOR)
        self._right_frame.pack(side=tk.LEFT)

        self._logger_frame = Logger(self._left_frame, bg=BG_COLOR)
        self._logger_frame.pack(side=tk.TOP)
