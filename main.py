import tkinter as tk
from tkinter import messagebox
import cv2
import numpy as np
import mss
import threading
import time

class ScreenRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Gravador de Tela")
        self.root.geometry("300x120")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.recording = False
        self.paused = False
        self.selection = None
        self.sct = mss.MSS()
        self.video_writer = None

        self.overlay = None
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.border_overlay = None

        self.setup_ui()

    def setup_ui(self):
        frame = tk.Frame(self.root)
        frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        self.btn_select = tk.Button(frame, text="Selecionar Área", command=self.start_selection, width=15)
        self.btn_select.grid(row=0, column=0, padx=5, pady=5)

        self.btn_start = tk.Button(frame, text="Iniciar", command=self.start_recording, state=tk.DISABLED, width=15)
        self.btn_start.grid(row=0, column=1, padx=5, pady=5)

        self.btn_pause = tk.Button(frame, text="Pausar", command=self.pause_recording, state=tk.DISABLED, width=15)
        self.btn_pause.grid(row=1, column=0, padx=5, pady=5)

        self.btn_cancel = tk.Button(frame, text="Cancelar/Parar", command=self.stop_recording, state=tk.DISABLED, width=15)
        self.btn_cancel.grid(row=1, column=1, padx=5, pady=5)

    def start_selection(self):
        self.root.withdraw()
        self.overlay = tk.Toplevel()
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-alpha", 0.3)
        self.overlay.config(cursor="cross")

        self.canvas = tk.Canvas(self.overlay, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.overlay.bind("<Escape>", lambda e: self.cancel_selection())

    def cancel_selection(self):
        self.overlay.destroy()
        self.root.deiconify()

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2)

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        end_x, end_y = event.x, event.y
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        self.selection = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
        self.overlay.destroy()
        self.root.deiconify()

        self.show_border()

        if self.selection["width"] > 10 and self.selection["height"] > 10:
            self.btn_start.config(state=tk.NORMAL)
        else:
            self.selection = None
            messagebox.showwarning("Aviso", "Área de seleção muito pequena ou inválida.")

    def show_border(self):
        if self.border_overlay:
            self.border_overlay.destroy()
        
        self.border_overlay = tk.Toplevel(self.root)
        self.border_overlay.overrideredirect(True)
        self.border_overlay.attributes("-topmost", True)
        try:
            self.border_overlay.attributes("-transparentcolor", "black")
        except tk.TclError:
            pass
        self.border_overlay.config(bg="black")
        
        w = self.selection["width"]
        h = self.selection["height"]
        x = self.selection["left"]
        y = self.selection["top"]
        
        self.border_overlay.geometry(f"{w}x{h}+{x}+{y}")
        canvas = tk.Canvas(self.border_overlay, bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(0, 0, w-1, h-1, outline="red", width=4)

    def start_recording(self):
        if not self.selection:
            return

        self.recording = True
        self.paused = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_select.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.NORMAL)

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        filename = f"gravacao_{int(time.time())}.avi"
        self.video_writer = cv2.VideoWriter(filename, fourcc, 20.0, (self.selection["width"], self.selection["height"]))

        self.record_thread = threading.Thread(target=self.record_loop, daemon=True)
        self.record_thread.start()

    def record_loop(self):
        while self.recording:
            if not self.paused:
                img = np.array(self.sct.grab(self.selection))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                self.video_writer.write(frame)
            time.sleep(0.05)

    def pause_recording(self):
        self.paused = not self.paused
        self.btn_pause.config(text="Retomar" if self.paused else "Pausar")

    def stop_recording(self):
        self.recording = False
        if self.video_writer:
            self.video_writer.release()

        self.btn_start.config(state=tk.NORMAL)
        self.btn_select.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_pause.config(text="Pausar")

        if self.border_overlay:
            self.border_overlay.destroy()
            self.border_overlay = None

if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenRecorder(root)
    root.mainloop()