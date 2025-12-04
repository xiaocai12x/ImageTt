import os
import sys
import json
import time
import threading
import ctypes
from datetime import datetime
from io import BytesIO

# GUI
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageGrab, ImageTk, ImageOps, ImageEnhance, ImageDraw

# System
import keyboard
import pystray
from pystray import MenuItem as item
# 用于图片复制到剪贴板
import win32clipboard 

# OCR & AI
# 【修改】使用通用性更好的 onnxruntime
from rapidocr_onnxruntime import RapidOCR
import numpy as np
import pyperclip
from openai import OpenAI

# ---------------------------------------------------------
# 0. 高DPI适配
# ---------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception: pass

# ---------------------------------------------------------
# 全局视觉常量
# ---------------------------------------------------------
FONT_MAIN = ("Microsoft YaHei UI", 12)
FONT_BOLD = ("Microsoft YaHei UI", 12, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 10)
# 尝试加载 MDL2 图标字体，如果没有则回退
FONT_ICON = ("Segoe MDL2 Assets", 14)

COLOR_BG = "#1c1c1e"
COLOR_BLUE = "#007AFF"
COLOR_GREEN = "#34C759"
COLOR_ORANGE = "#FF9500"
COLOR_RED = "#FF3B30"

# ---------------------------------------------------------
# 1. 基础设施
# ---------------------------------------------------------
class LogManager:
    DIR = "logs"
    @staticmethod
    def init(enable):
        if not enable: return
        if not os.path.exists(LogManager.DIR): os.makedirs(LogManager.DIR)
        import glob
        files = sorted(glob.glob(os.path.join(LogManager.DIR, "*.log")), key=os.path.getctime)
        while len(files) >= 3:
            try: os.remove(files.pop(0))
            except: pass
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        sys.stdout = open(os.path.join(LogManager.DIR, f"log_{timestamp}.log"), "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout

class HistoryManager:
    DIR = "records"
    @staticmethod
    def save(text, enable):
        if not enable or not text.strip(): return
        if not os.path.exists(HistoryManager.DIR): os.makedirs(HistoryManager.DIR)
        import glob
        files = sorted(glob.glob(os.path.join(HistoryManager.DIR, "*.txt")), key=os.path.getctime)
        while len(files) >= 6:
            try: os.remove(files.pop(0))
            except: pass
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(HistoryManager.DIR, f"rec_{timestamp}.txt")
        with open(path, "w", encoding="utf-8") as f: f.write(text)

class Config:
    FILE = "config.json"
    SCREENSHOT_DIR = "printscreen"
    DEFAULT = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-coder",
        "use_ai": False,
        "always_on_top": True,
        "hotkey_snip": "f1",
        "hotkey_clip": "ctrl+f1",
        "enable_hotkeys": True,
        "enable_logging": False,
        "enable_history": True
    }
    @staticmethod
    def load():
        if not os.path.exists(Config.SCREENSHOT_DIR): os.makedirs(Config.SCREENSHOT_DIR)
        if not os.path.exists(Config.FILE):
            Config.save(Config.DEFAULT)
            return Config.DEFAULT.copy()
        try:
            with open(Config.FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in Config.DEFAULT.items():
                    if k not in data: data[k] = v
                return data
        except: return Config.DEFAULT.copy()
    @staticmethod
    def save(cfg):
        with open(Config.FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

# ---------------------------------------------------------
# 2. 贴图窗口 (增强版)
# ---------------------------------------------------------
class PinWindow(ctk.CTkToplevel):
    def __init__(self, master_app, image):
        super().__init__()
        self.app = master_app
        self.image = image
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        w, h = image.size
        self.geometry(f"{w}x{h}")
        
        self.tk_image = ctk.CTkImage(image, size=(w, h))
        self.lbl = ctk.CTkLabel(self, text="", image=self.tk_image, corner_radius=0)
        self.lbl.pack(fill="both", expand=True)
        
        self.lbl.bind("<Button-1>", self.start_move)
        self.lbl.bind("<B1-Motion>", self.do_move)
        self.lbl.bind("<Double-Button-1>", lambda e: self.destroy())
        
        # 右键菜单
        self.lbl.bind("<Button-3>", self.show_context_menu)
        self.menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white", activebackground=COLOR_BLUE)
        self.menu.add_command(label="📋 复制图像", command=self.copy_to_clipboard)
        self.menu.add_command(label="📝 识别文字 (OCR)", command=self.do_ocr)
        self.menu.add_command(label="💾 保存到本地", command=self.do_save)
        self.menu.add_separator()
        self.menu.add_command(label="❌ 关闭", command=self.destroy)
        
        self.focus_force()

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        x = self.winfo_x() + (event.x - self.x)
        y = self.winfo_y() + (event.y - self.y)
        self.geometry(f"+{x}+{y}")

    def show_context_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def do_save(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(Config.SCREENSHOT_DIR, f"{ts}.png")
        try:
            self.image.save(path)
            self.app.show_status_toast(f"已保存: {ts}.png", COLOR_GREEN)
        except: self.app.show_status_toast("保存失败", COLOR_RED)

    def do_ocr(self):
        self.app.show_status_toast("正在从贴图识别...", "white")
        threading.Thread(target=self.app._ocr_thread, args=(self.image,)).start()

    def copy_to_clipboard(self):
        try:
            output = BytesIO()
            # BMP format is safest for Windows Clipboard
            self.image.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:] # 去掉BMP文件头
            output.close()
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
            
            # 视觉反馈：闪烁一下
            self.attributes("-alpha", 0.7)
            self.after(100, lambda: self.attributes("-alpha", 1.0))
            self.app.show_status_toast("图像已复制", COLOR_GREEN)
        except Exception as e:
            print(f"复制失败: {e}")
            self.app.show_status_toast("复制失败", COLOR_RED)

# ---------------------------------------------------------
# 3. 截图遮罩层 (修复高亮逻辑)
# ---------------------------------------------------------
class SnippingTool(ctk.CTkToplevel):
    def __init__(self, master_app):
        super().__init__()
        self.app = master_app
        
        # 1. 物理截图
        self.full_img = ImageGrab.grab()
        # 保持引用防止被GC回收
        self.tk_full = ImageTk.PhotoImage(self.full_img)
        
        # 2. 变暗背景 (底层)
        enhancer = ImageEnhance.Brightness(self.full_img)
        self.dark_img = enhancer.enhance(0.5)
        self.tk_dark = ImageTk.PhotoImage(self.dark_img)

        # 3. 窗口设置 (使用伪透明技术防止黑屏)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        # 强制手动设置全屏，不使用 zoomed
        self.screen_w = self.winfo_screenwidth()
        self.screen_h = self.winfo_screenheight()
        self.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        
        self.configure(fg_color="black", cursor="cross")
        self.focus_force()

        # 4. 画布
        self.canvas = tk.Canvas(self, width=self.screen_w, height=self.screen_h, highlightthickness=0, cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        
        # 绘制暗背景作为底图
        self.canvas.create_image(0, 0, image=self.tk_dark, anchor="nw", tags="bg")

        self.start_x = None
        self.start_y = None
        self.selection_done = False
        self.toolbar_frame = None 

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", self.exit_snip)
        self.bind("<Button-3>", self.exit_snip)

    def on_press(self, event):
        if self.selection_done: return
        if self.toolbar_frame: 
            self.toolbar_frame.place_forget()
            self.toolbar_frame = None
        # 清除旧的选区和UI
        self.canvas.delete("ui")
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)

    def on_drag(self, event):
        if self.selection_done: return
        cur_x, cur_y = event.x, event.y
        self.canvas.delete("ui")
        
        # 计算坐标
        x1, x2 = sorted([self.start_x, cur_x])
        y1, y2 = sorted([self.start_y, cur_y])
        
        # 【关键】绘制亮色选区 (模拟 Snipaste 高亮)
        # 我们从原图(亮图)中切出这一块，贴在 Canvas 上
        crop = self.full_img.crop((x1, y1, x2, y2))
        self.tk_crop = ImageTk.PhotoImage(crop) # 必须存为 self 属性，否则会被GC回收不显示
        self.canvas.create_image(x1, y1, image=self.tk_crop, anchor="nw", tags="ui")
        
        # 蓝色边框
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=COLOR_BLUE, width=3, tags="ui")
        
        # 尺寸提示
        w, h = int(x2 - x1), int(y2 - y1)
        label = f" {w} × {h} px "
        
        # 标签位置：左上角
        mx, my = x1, y1
        self.canvas.create_rectangle(mx, my-30, mx+len(label)*11, my-5, fill="#1a1a1a", outline=COLOR_BLUE, width=1, tags="ui")
        self.canvas.create_text(mx+8, my-18, text=label, fill="white", anchor="w", font=FONT_BOLD, tags="ui")

    def on_release(self, event):
        if self.selection_done: return
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        self.x1, self.x2 = sorted([x1, x2])
        self.y1, self.y2 = sorted([y1, y2])

        if self.x2 - self.x1 < 10 or self.y2 - self.y1 < 10:
            self.canvas.delete("ui")
            return

        self.selection_done = True
        self.draw_final_selection()
        self.show_toolbar(self.x1, self.y2)

    def draw_final_selection(self):
        # 重绘最终的高亮图和边框
        crop = self.full_img.crop((self.x1, self.y1, self.x2, self.y2))
        self.tk_crop_final = ImageTk.PhotoImage(crop)
        self.canvas.create_image(self.x1, self.y1, image=self.tk_crop_final, anchor="nw", tags="ui")
        
        self.canvas.create_rectangle(self.x1, self.y1, self.x2, self.y2, outline=COLOR_BLUE, width=3, tags="ui")
        
        # 绘制锚点
        r = 5
        points = [(self.x1, self.y1), (self.x2, self.y1), (self.x1, self.y2), (self.x2, self.y2),
                  ((self.x1+self.x2)/2, self.y1), ((self.x1+self.x2)/2, self.y2),
                  (self.x1, (self.y1+self.y2)/2), (self.x2, (self.y1+self.y2)/2)]
        for px, py in points:
            self.canvas.create_oval(px-r, py-r, px+r, py+r, fill="white", outline=COLOR_BLUE, width=2, tags="ui")

    def show_toolbar(self, x, y):
        # 内嵌工具条 (防止被遮挡)
        if not self.toolbar_frame:
            self.toolbar_frame = ctk.CTkFrame(self, width=320, height=45, corner_radius=10, fg_color="#2c2c2e", border_width=1, border_color="#3a3a3c")
            btn_cfg = {"height": 32, "corner_radius": 6, "font": FONT_BOLD, "fg_color": "transparent"}
            
            ctk.CTkButton(self.toolbar_frame, text="📝 识字", width=70, hover_color=COLOR_BLUE, 
                          command=lambda: self.finish("ocr"), **btn_cfg).pack(side="left", padx=4, pady=6)
            ctk.CTkButton(self.toolbar_frame, text="📌 置顶", width=70, hover_color=COLOR_GREEN, 
                          command=lambda: self.finish("pin"), **btn_cfg).pack(side="left", padx=4, pady=6)
            ctk.CTkButton(self.toolbar_frame, text="💾 保存", width=70, hover_color=COLOR_ORANGE, 
                          command=lambda: self.finish("save"), **btn_cfg).pack(side="left", padx=4, pady=6)
            ctk.CTkButton(self.toolbar_frame, text="✕", width=32, hover_color=COLOR_RED, 
                          command=self.exit_snip, **btn_cfg).pack(side="right", padx=6, pady=6)
        
        screen_h = self.winfo_screenheight()
        toolbar_y = y + 10
        if toolbar_y + 60 > screen_h: toolbar_y = self.y1 - 60
        self.toolbar_frame.place(x=x, y=toolbar_y)
        self.toolbar_frame.lift()

    def finish(self, action):
        # 高DPI坐标修正
        phys_w, phys_h = self.full_img.size
        scale_x = phys_w / self.screen_w
        scale_y = phys_h / self.screen_h
        
        real_x1 = int(self.x1 * scale_x)
        real_y1 = int(self.y1 * scale_y)
        real_x2 = int(self.x2 * scale_x)
        real_y2 = int(self.y2 * scale_y)
        
        img = self.full_img.crop((real_x1, real_y1, real_x2, real_y2))
        self.destroy()
        self.app.on_process_request(img, action)

    def exit_snip(self, event=None):
        if self.toolbar_frame: self.toolbar_frame.destroy()
        self.destroy()
        self.app.deiconify()

# ---------------------------------------------------------
# 5. 核心引擎
# ---------------------------------------------------------
class Engine:
    def __init__(self):
        try: self.ocr = RapidOCR()
        except Exception as e:
            print(f"OCR Init Failed: {e}")
            self.ocr = None

    def run_ocr(self, img):
        if not self.ocr: return None
        try:
            img = img.convert("RGB")
            if np.array(img).mean() < 128: img = ImageOps.invert(img)
            result, _ = self.ocr(np.array(img))
            return "\n".join([line[1] for line in result]) if result else None
        except Exception as e:
            print(f"OCR Error: {e}")
            return None

    def run_ai(self, text, cfg):
        if not cfg["api_key"]: return text
        try:
            client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            resp = client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "system", "content": "修正OCR拼写错误，代码恢复缩进，只输出结果。"}, {"role": "user", "content": text}]
            )
            return resp.choices[0].message.content
        except Exception as e: return f"{text}\n\n[AI Error: {e}]"

# ---------------------------------------------------------
# 6. 主程序
# ---------------------------------------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = Config.load()
        LogManager.init(self.cfg["enable_logging"])
        self.engine = Engine()
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        self.title("ImageTt")
        self.height_collapsed = 56
        self.height_expanded = 580
        self.geometry(f"360x{self.height_collapsed}")
        self.resizable(False, False)
        
        self.is_settings_open = False
        self.is_preview_open = False
        
        self.register_hotkeys()
        self.setup_tray()
        self.apply_topmost()

        self.top_frame = ctk.CTkFrame(self, fg_color="#1c1c1e", corner_radius=28)
        self.top_frame.pack(side="top", fill="x", padx=2, pady=2, ipady=3)

        # 1. 识字
        self.btn_clip = ctk.CTkButton(
            self.top_frame, text="识字", width=70, height=36,
            font=FONT_BOLD, fg_color=COLOR_BLUE, hover_color="#0056b3",
            corner_radius=18, command=self.start_clipboard_ocr
        )
        self.btn_clip.pack(side="left", padx=(10, 5))

        # 2. 截图
        self.btn_snip = ctk.CTkButton(
            self.top_frame, text="截图", width=70, height=36,
            font=FONT_BOLD, fg_color="#3a3a3c", hover_color="#48484a",
            corner_radius=18, command=self.start_snip
        )
        self.btn_snip.pack(side="left", padx=0)

        # 3. 状态
        self.lbl_status = ctk.CTkLabel(self.top_frame, text="Ready", text_color="gray", font=FONT_MAIN)
        self.lbl_status.pack(side="left", padx=10, fill="x", expand=True)
        self.lbl_status.bind("<Double-Button-1>", lambda e: self.toggle_preview_drawer())

        # 4. AI
        self.ai_var = ctk.BooleanVar(value=self.cfg["use_ai"])
        self.btn_ai = ctk.CTkCheckBox(
            self.top_frame, text="AI", width=45, 
            command=self.toggle_ai, variable=self.ai_var,
            font=FONT_BOLD, text_color="white",
            fg_color=COLOR_GREEN, hover_color="#2da84a",
            checkbox_width=20, checkbox_height=20
        )
        self.btn_ai.pack(side="right", padx=6)

        # 5. 置顶
        self.pin_color = COLOR_BLUE if self.cfg["always_on_top"] else "gray"
        self.btn_pin = ctk.CTkButton(
            self.top_frame, text="\uE718", width=32, height=32, 
            font=FONT_ICON, fg_color="transparent", text_color=self.pin_color, 
            hover_color="#2c2c2e", corner_radius=8,
            command=self.toggle_pin
        )
        self.btn_pin.pack(side="right", padx=0)

        # 6. 设置
        self.btn_set = ctk.CTkButton(
            self.top_frame, text="\uE713", width=32, height=32, 
            font=FONT_ICON, fg_color="transparent", text_color="gray", 
            hover_color="#2c2c2e", corner_radius=8,
            command=self.toggle_settings_drawer
        )
        self.btn_set.pack(side="right", padx=4)

        # 抽屉
        self.settings_frame = ctk.CTkScrollableFrame(self, fg_color="#1c1c1e", corner_radius=15)
        self.build_settings_ui()
        
        self.preview_frame = ctk.CTkFrame(self, fg_color="#1c1c1e", corner_radius=15)
        self.build_preview_ui()

    def build_settings_ui(self):
        p = self.settings_frame
        
        self.add_lbl("系统功能", p)
        self.v_hist = ctk.BooleanVar(value=self.cfg["enable_history"])
        ctk.CTkSwitch(p, text="保存历史记录", variable=self.v_hist, progress_color=COLOR_GREEN, font=FONT_MAIN).pack(fill="x", padx=10, pady=5)
        self.v_log = ctk.BooleanVar(value=self.cfg["enable_logging"])
        ctk.CTkSwitch(p, text="开启调试日志", variable=self.v_log, progress_color=COLOR_GREEN, font=FONT_MAIN).pack(fill="x", padx=10, pady=5)

        self.add_lbl("快捷键", p)
        self.v_hk_en = ctk.BooleanVar(value=self.cfg["enable_hotkeys"])
        ctk.CTkSwitch(p, text="启用热键", variable=self.v_hk_en, progress_color=COLOR_GREEN, font=FONT_MAIN).pack(fill="x", padx=10, pady=5)
        self.e_snip = self.mk_entry(p, self.cfg["hotkey_snip"])
        ctk.CTkLabel(p, text="^ 截图热键", font=FONT_SMALL, text_color="gray").pack(anchor="e", padx=10)
        self.e_clip = self.mk_entry(p, self.cfg["hotkey_clip"])
        ctk.CTkLabel(p, text="^ 剪贴板热键", font=FONT_SMALL, text_color="gray").pack(anchor="e", padx=10)

        self.add_lbl("AI 模型", p)
        self.e_key = self.mk_entry(p, self.cfg["api_key"], True)
        self.e_url = self.mk_entry(p, self.cfg["base_url"])
        self.e_model = self.mk_entry(p, self.cfg["model"])

        ctk.CTkButton(p, text="保存并生效", height=36, font=FONT_BOLD, 
                      fg_color=COLOR_BLUE, hover_color="#0056b3", corner_radius=18, 
                      command=self.save_settings).pack(fill="x", padx=10, pady=20)

    def build_preview_ui(self):
        p = self.preview_frame
        ctk.CTkLabel(p, text="识别结果预览", font=FONT_BOLD, text_color="gray").pack(anchor="w", padx=15, pady=(10,5))
        self.textbox = ctk.CTkTextbox(p, font=("Consolas", 11), wrap="none")
        self.textbox.pack(fill="both", expand=True, padx=10, pady=5)
        
        btn_frame = ctk.CTkFrame(p, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="清空", width=80, height=32, fg_color=COLOR_RED, hover_color="#c9342b",
                      command=lambda: self.textbox.delete("0.0", "end")).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="复制全部", height=32, font=FONT_BOLD,
                      fg_color=COLOR_GREEN, hover_color="#2da84a",
                      command=self.copy_preview).pack(side="left", padx=5, fill="x", expand=True)

    def add_lbl(self, text, p):
        ctk.CTkLabel(p, text=text, font=FONT_BOLD, text_color="gray").pack(anchor="w", padx=10, pady=(15,5))

    def mk_entry(self, p, val, pwd=False):
        e = ctk.CTkEntry(p, show="*" if pwd else "", font=FONT_MAIN, height=32)
        e.insert(0, val)
        e.pack(fill="x", padx=10, pady=2)
        return e

    def toggle_settings_drawer(self):
        if self.is_preview_open: self.toggle_preview_drawer()
        if self.is_settings_open:
            self.settings_frame.pack_forget()
            self.geometry(f"360x{self.height_collapsed}")
            self.btn_set.configure(text_color="gray")
            self.is_settings_open = False
        else:
            self.geometry(f"360x{self.height_expanded}")
            self.settings_frame.pack(fill="both", expand=True, padx=5, pady=5)
            self.btn_set.configure(text_color="white")
            self.is_settings_open = True

    def toggle_preview_drawer(self):
        if self.is_settings_open: self.toggle_settings_drawer()
        if self.is_preview_open:
            self.preview_frame.pack_forget()
            self.geometry(f"360x{self.height_collapsed}")
            self.is_preview_open = False
        else:
            self.geometry(f"360x{self.height_expanded}")
            self.preview_frame.pack(fill="both", expand=True, padx=5, pady=5)
            self.is_preview_open = True

    def update_preview_text(self, text):
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", text)
        if not self.is_preview_open:
            self.toggle_preview_drawer()

    def copy_preview(self):
        text = self.textbox.get("0.0", "end")
        pyperclip.copy(text)
        self.show_status("Copied!", COLOR_GREEN)

    def save_settings(self):
        self.cfg["enable_history"] = self.v_hist.get()
        self.cfg["enable_logging"] = self.v_log.get()
        self.cfg["enable_hotkeys"] = self.v_hk_en.get()
        self.cfg["hotkey_snip"] = self.e_snip.get()
        self.cfg["hotkey_clip"] = self.e_clip.get()
        self.cfg["api_key"] = self.e_key.get()
        self.cfg["base_url"] = self.e_url.get()
        self.cfg["model"] = self.e_model.get()
        Config.save(self.cfg)
        self.reload_config(self.cfg)
        self.toggle_settings_drawer()

    def apply_topmost(self):
        self.attributes("-topmost", self.cfg["always_on_top"])
        color = COLOR_BLUE if self.cfg["always_on_top"] else "gray"
        try: self.btn_pin.configure(text_color=color)
        except: pass

    def toggle_pin(self):
        self.cfg["always_on_top"] = not self.cfg["always_on_top"]
        Config.save(self.cfg)
        self.apply_topmost()

    def register_hotkeys(self):
        try:
            keyboard.unhook_all()
            if self.cfg.get("enable_hotkeys", True):
                keyboard.add_hotkey(self.cfg["hotkey_snip"], lambda: self.after(0, self.start_snip))
                keyboard.add_hotkey(self.cfg["hotkey_clip"], lambda: self.after(0, self.start_clipboard_ocr))
        except: pass

    def setup_tray(self):
        def on_exit(icon, item):
            icon.stop()
            self.quit()
        def on_show(icon, item):
            self.deiconify()
            self.attributes("-topmost", True)
        
        if os.path.exists("icon.png"):
            image = Image.open("icon.png")
        else:
            image = Image.new('RGB', (64, 64), color=(0, 122, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle((16, 16, 48, 48), fill="white")
        
        menu = (
            item('显示主界面', on_show),
            item('截图 (Snip)', lambda i,m: self.after(0, self.start_snip)),
            item('识字 (Clip)', lambda i,m: self.after(0, self.start_clipboard_ocr)),
            item('退出', on_exit)
        )
        self.tray = pystray.Icon("ImageTt", image, "ImageTt", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()
        self.protocol('WM_DELETE_WINDOW', self.withdraw)

    def reload_config(self, new_cfg):
        self.cfg = new_cfg
        self.apply_topmost()
        self.register_hotkeys()

    def toggle_ai(self):
        self.cfg["use_ai"] = self.ai_var.get()
        Config.save(self.cfg)

    def start_snip(self):
        self.withdraw()
        self.after(200, lambda: SnippingTool(self))

    def start_clipboard_ocr(self):
        try: img = ImageGrab.grabclipboard()
        except: 
            self.show_status("Clip Error", COLOR_RED)
            return
        if img is None:
            self.show_status("Clip Empty", COLOR_RED)
            return
        if isinstance(img, list):
            try: img = Image.open(img[0])
            except: 
                self.show_status("Invalid File", COLOR_RED)
                return
        self.on_process_request(img, "ocr")

    def on_process_request(self, img, action):
        self.deiconify()
        self.attributes("-topmost", True)
        if action == "save":
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(Config.SCREENSHOT_DIR, f"{ts}.png")
            img.save(path)
            self.show_status(f"Saved", COLOR_GREEN)
        elif action == "pin":
            PinWindow(self, img) # 传递 self 给 PinWindow
            self.show_status("Pinned", COLOR_BLUE)
        elif action == "ocr":
            self.show_status("Identifying...", "white")
            threading.Thread(target=self._ocr_thread, args=(img,)).start()

    def _ocr_thread(self, img):
        text = self.engine.run_ocr(img)
        if text:
            if self.cfg["use_ai"]:
                self.after(0, lambda: self.show_status("AI Fixing...", COLOR_ORANGE))
                text = self.engine.run_ai(text, self.cfg)
            pyperclip.copy(text)
            HistoryManager.save(text, self.cfg["enable_history"])
            self.after(0, lambda: self.update_preview_text(text))
            self.after(0, lambda: self.show_status("Copied!", COLOR_GREEN))
        else:
            self.after(0, lambda: self.show_status("Failed", COLOR_RED))

    def show_status(self, text, color):
        self.lbl_status.configure(text=text, text_color=color)
        if text not in ["Ready", "Identifying...", "AI Fixing..."]: 
            self.after(3000, lambda: self.lbl_status.configure(text="Ready", text_color="gray"))

    # 公共方法供 PinWindow 使用
    def show_status_toast(self, text, color):
        self.deiconify()
        self.show_status(text, color)

if __name__ == "__main__":
    app = App()
    app.mainloop()