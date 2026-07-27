import tkinter as tk
from tkinter import messagebox
import cv2
import numpy as np
import mss
import threading
import time
import os
import subprocess
import pyaudiowpatch as pyaudio
import wave
import imageio_ffmpeg

class ScreenRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Gravador de Tela")
        self.root.geometry("300x200")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.recording = False
        self.paused = False
        self.elapsed_time = 0
        self.timer_job = None
        self.selection = None
        self.sct = mss.MSS()
        self.video_writer = None
        self.filename = ""

        # Configurações de Áudio
        self.p = pyaudio.PyAudio()
        self.audio_format = pyaudio.paInt16
        self.audio_stream = None
        self.audio_frames = []
        self.audio_channels = 2
        self.audio_rate = 44100

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

        self.btn_fullscreen = tk.Button(frame, text="Tela Inteira", command=self.select_fullscreen, width=32)
        self.btn_fullscreen.grid(row=2, column=0, columnspan=2, padx=5, pady=5)

        self.lbl_timer = tk.Label(frame, text="00:00", font=("Arial", 12, "bold"))
        self.lbl_timer.grid(row=3, column=0, columnspan=2, pady=5)

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

    def select_fullscreen(self):
        monitor = self.sct.monitors[1]
        self.selection = {"top": monitor["top"], "left": monitor["left"], "width": monitor["width"], "height": monitor["height"]}
        self.show_border()
        self.btn_start.config(state=tk.NORMAL)

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
        self.btn_pause.config(text="Pausar")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.filename = f"gravacao_{int(time.time())}.mp4"
        
        self.rec_w = 1920
        self.rec_h = 1080
        
        self.video_writer = cv2.VideoWriter(self.filename, fourcc, 30.0, (self.rec_w, self.rec_h))

        try:
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            
            if not default_speakers["isLoopbackDevice"]:
                for loopback in self.p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break
                        
            self.audio_channels = default_speakers["maxInputChannels"]
            self.audio_rate = int(default_speakers["defaultSampleRate"])
            
            self.audio_stream = self.p.open(format=self.audio_format,
                channels=self.audio_channels,
                rate=self.audio_rate,
                frames_per_buffer=1024,
                input=True,
                input_device_index=default_speakers["index"]
            )
        except Exception as e:
            print(f"Erro ao inicializar áudio: {e}")
            self.audio_stream = None

        self.audio_frames = []

        self.record_thread = threading.Thread(target=self.record_loop, daemon=True)
        self.record_thread.start()

        if self.audio_stream:
            self.audio_thread = threading.Thread(target=self.record_audio_loop, daemon=True)
            self.audio_thread.start()
        
        self.start_time = time.time() - self.elapsed_time
        self.update_timer()

    def update_timer(self):
        if self.recording:
            if not self.paused:
                self.elapsed_time = int(time.time() - self.start_time)
                mins, secs = divmod(self.elapsed_time, 60)
                self.lbl_timer.config(text=f"{mins:02d}:{secs:02d}")
            self.timer_job = self.root.after(1000, self.update_timer)

    def record_loop(self):
        target_fps = 30.0
        frame_time = 1.0 / target_fps
        while self.recording:
            if not self.paused:
                start_loop = time.time()
                
                img = np.array(self.sct.grab(self.selection))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                frame = cv2.resize(frame, (self.rec_w, self.rec_h), interpolation=cv2.INTER_CUBIC)
                self.video_writer.write(frame)
                
                process_time = time.time() - start_loop
                sleep_time = frame_time - process_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def record_audio_loop(self):
        while self.recording:
            if not self.paused:
                try:
                    data = self.audio_stream.read(1024, exception_on_overflow=False)
                    self.audio_frames.append(data)
                except:
                    pass
            else:
                time.sleep(0.01)

    def pause_recording(self):
        self.paused = not self.paused
        self.btn_pause.config(text="Retomar" if self.paused else "Pausar")
        if self.paused:
            if self.timer_job:
                self.root.after_cancel(self.timer_job)
        else:
            self.start_time = time.time() - self.elapsed_time
            self.update_timer()

    def stop_recording(self):
        self.recording = False
        
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None
        self.elapsed_time = 0
        self.lbl_timer.config(text="00:00")

        self.btn_start.config(state=tk.DISABLED, text="Salvando...")
        self.btn_select.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_fullscreen.config(state=tk.DISABLED)

        threading.Thread(target=self.save_and_merge, daemon=True).start()

    def save_and_merge(self):
        if self.audio_stream:
            self.audio_stream.stop_stream()

        if hasattr(self, 'record_thread') and self.record_thread.is_alive():
            self.record_thread.join()
            
        if hasattr(self, 'audio_thread') and self.audio_thread.is_alive():
            self.audio_thread.join()

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        if self.audio_stream:
            self.audio_stream.close()
            self.audio_stream = None

        if not self.audio_frames:
            self.root.after(0, self.reset_ui)
            return

        try:
            temp_wav = self.filename.replace(".mp4", ".wav")
            wf = wave.open(temp_wav, 'wb')
            wf.setnchannels(self.audio_channels)
            wf.setsampwidth(self.p.get_sample_size(self.audio_format))
            wf.setframerate(self.audio_rate)
            wf.writeframes(b''.join(self.audio_frames))
            wf.close()

            final_filename = self.filename.replace("gravacao_", "final_")
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

            cmd = [
                ffmpeg_exe, "-y",
                "-i", self.filename,
                "-i", temp_wav,
                "-c:v", "copy",
                "-c:a", "aac",
                final_filename
            ]

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

            if os.path.exists(self.filename):
                os.remove(self.filename)
            if os.path.exists(temp_wav):
                os.remove(temp_wav)

        except Exception as e:
            print(f"Erro ao mesclar áudio e vídeo: {e}")
        finally:
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.btn_start.config(text="Iniciar")
        self.btn_select.config(state=tk.NORMAL)
        self.btn_fullscreen.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="Pausar")
        self.btn_cancel.config(state=tk.DISABLED)
        
        if self.border_overlay:
            self.border_overlay.destroy()
            self.border_overlay = None
            
        if self.selection:
            self.btn_start.config(state=tk.NORMAL)
        else:
            self.btn_start.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenRecorder(root)
    root.mainloop()