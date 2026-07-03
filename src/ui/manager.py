import os
import sys
import shutil
import re
import subprocess
import zipfile
import threading
import hashlib
import socket
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

from src.utils import ProtonUtils
from src.config import SettingsManager
from src.runner import MICRO_PROTON_BIN
from src.ui.dialogs import SettingsDialog, AddAppDialog, DonateDialog, HelpDialog, ProtonDownloaderDialog

# Monkey patch CTkScrollableFrame to fix mouse wheel scrolling in python 3.14
try:
    old_init = ctk.CTkScrollableFrame.__init__
    def new_init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        if hasattr(self, "_parent_canvas") and self._parent_canvas.winfo_exists():
            def on_scroll(event):
                if event.num == 4:
                    self._parent_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self._parent_canvas.yview_scroll(1, "units")
                elif event.delta:
                    self._parent_canvas.yview_scroll(-int(event.delta/120), "units")
            self.bind("<Button-4>", on_scroll)
            self.bind("<Button-5>", on_scroll)
            self.bind("<MouseWheel>", on_scroll)
    ctk.CTkScrollableFrame.__init__ = new_init
except Exception as e:
    print(f"Warning: Failed to apply Python 3.14 mouse scroll patch: {e}")


def scan_apps():
    """Scans ~/.local/share/applications/ for apps managed by MicroProton."""
    apps = []
    if not os.path.exists(ProtonUtils.APPLICATIONS_DIR):
        return apps
        
    for filename in os.listdir(ProtonUtils.APPLICATIONS_DIR):
        if not filename.endswith(".desktop") or not filename.startswith("micro-proton-"):
            continue
            
        filepath = os.path.join(ProtonUtils.APPLICATIONS_DIR, filename)
        app_info = {
            "desktop_file": filepath,
            "filename": filename,
            "name": "",
            "exe": "",
            "icon": "",
            "prefix": "",
            "proton": "",
            "mangohud": False,
            "gamemode": False,
            "wined3d": False,
            "virtual_desktop": "",
            "unikey": False,
            "taskbar": False
        }
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            name_match = re.search(r"^Name=(.*)$", content, re.MULTILINE)
            exe_match = re.search(r"^X-MicroProton-Exe=(.*)$", content, re.MULTILINE)
            icon_match = re.search(r"^Icon=(.*)$", content, re.MULTILINE)
            exec_match = re.search(r"^Exec=(.*)$", content, re.MULTILINE)
            
            if name_match:
                app_info["name"] = name_match.group(1).strip()
            if exe_match:
                app_info["exe"] = exe_match.group(1).strip()
            if icon_match:
                app_info["icon"] = icon_match.group(1).strip()
                
            if exec_match:
                exec_line = exec_match.group(1).strip()
                app_info["mangohud"] = "--mangohud" in exec_line
                app_info["gamemode"] = "--gamemode" in exec_line
                app_info["wined3d"] = "--wined3d" in exec_line
                app_info["unikey"] = "--unikey" in exec_line
                app_info["taskbar"] = "--taskbar" in exec_line
                
                # Parse --prefix
                prefix_match = re.search(r'--prefix\s+"([^"]+)"', exec_line)
                if prefix_match:
                    app_info["prefix"] = prefix_match.group(1).strip()
                elif app_info["exe"]:
                    app_info["prefix"] = ProtonUtils.get_prefix_dir(app_info["exe"])
                    
                # Parse --proton
                proton_match = re.search(r'--proton\s+"([^"]+)"', exec_line)
                if proton_match:
                    app_info["proton"] = proton_match.group(1).strip()
                    
                # Parse --virtual-desktop
                vd_match = re.search(r'--virtual-desktop\s+"?([0-9]+x[0-9]+)"?', exec_line)
                if vd_match:
                    app_info["virtual_desktop"] = vd_match.group(1).strip()
                elif "--virtual-desktop" in exec_line:
                    app_info["virtual_desktop"] = "1280x720"
            else:
                if app_info["exe"]:
                    app_info["prefix"] = ProtonUtils.get_prefix_dir(app_info["exe"])
                
            if app_info["name"] and app_info["exe"]:
                apps.append(app_info)
        except Exception as e:
            print(f"Lỗi khi đọc {filename}: {e}")
            
    return apps


class AppRow(ctk.CTkFrame):
    def __init__(self, master, app_info, click_callback, double_click_callback, **kwargs):
        super().__init__(master, cursor="hand2", **kwargs)
        self.app_info = app_info
        self.click_callback = click_callback
        
        # Emoji icon based on app type
        self.lbl_icon = ctk.CTkLabel(self, text="🎮", font=("Helvetica", 22))
        self.lbl_icon.pack(side=tk.LEFT, padx=12, pady=8)
        
        # Text details frame
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.lbl_name = ctk.CTkLabel(text_frame, text=app_info["name"], font=("Helvetica", 13, "bold"), anchor="w")
        self.lbl_name.pack(fill=tk.X)
        
        # Shorten exe path for display
        exe_basename = os.path.basename(app_info["exe"])
        self.lbl_exe = ctk.CTkLabel(text_frame, text=exe_basename, font=("Helvetica", 11), text_color="gray", anchor="w")
        self.lbl_exe.pack(fill=tk.X)
        
        # Bind events for selection highlight
        self.bind("<Button-1>", self.on_click)
        self.lbl_icon.bind("<Button-1>", self.on_click)
        text_frame.bind("<Button-1>", self.on_click)
        self.lbl_name.bind("<Button-1>", self.on_click)
        self.lbl_exe.bind("<Button-1>", self.on_click)
        
        # Double click to launch
        self.bind("<Double-Button-1>", double_click_callback)
        self.lbl_icon.bind("<Double-Button-1>", double_click_callback)
        text_frame.bind("<Double-Button-1>", double_click_callback)
        self.lbl_name.bind("<Double-Button-1>", double_click_callback)
        self.lbl_exe.bind("<Double-Button-1>", double_click_callback)
        
    def on_click(self, event):
        self.click_callback(self)


class AppManagerWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("MicroProton App Manager")
        self.root.geometry("1280x830")
        self.root.minsize(1140, 680)
        
        self.selected_row = None
        self.apps = []
        self.row_widgets = []
        
        self.root.grid_columnconfigure(0, weight=3, minsize=360, uniform="group1")
        self.root.grid_columnconfigure(1, weight=7, uniform="group1")
        self.root.grid_rowconfigure(0, weight=1)
        
        self.build_left_panel()
        self.build_right_panel()
        
        self.refresh_list()
        self.update_resource_monitor()
        
        # Start the desktop tray indicator in the background if it exists
        local_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        search_paths = [
            os.path.join(local_dir, "micro-proton-indicator"),
            "/usr/bin/micro-proton-indicator"
        ]
        indicator_script = None
        for p in search_paths:
            if os.path.exists(p):
                indicator_script = p
                break
        if indicator_script:
            subprocess.Popen([sys.executable, indicator_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        # Check first run optimization
        self.root.after(1000, self.check_first_run_optimization)
        
    def deiconify_and_raise(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def check_first_run_optimization(self):
        global_prefix_wine = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default", "pfx")
        if os.path.exists(global_prefix_wine):
            return
            
        confirm = messagebox.askyesno(
            "Tối ưu hóa Hệ thống",
            "Chào mừng bạn đến với MicroProton!\n\n"
            "Hệ thống phát hiện đây là lần chạy đầu tiên. Bạn có muốn tự động cấu hình và tối ưu hóa môi trường Windows mặc định (WINEPREFIX) không?\n\n"
            "Quá trình này sẽ:\n"
            "1. Thiết lập Font Smoothing (ClearType) giúp hiển thị chữ sắc nét.\n"
            "2. Tắt hộp thoại báo lỗi crash phiền phức của Wine.\n"
            "3. Tải và cài đặt tự động các gói quan trọng (Microsoft Fonts, Msxml6, Riched20, Visual C++ 2015).\n\n"
            "Việc này giúp phần mềm văn phòng (Office 365, WPS Office) và game hoạt động mượt mà nhất. Bạn có muốn tiến hành không?",
            parent=self.root
        )
        if not confirm:
            return
            
        # Create and show progress window
        progress_win = ctk.CTkToplevel(self.root)
        progress_win.title("Đang tối ưu hóa môi trường")
        progress_win.geometry("500x220")
        progress_win.resizable(False, False)
        progress_win.transient(self.root)
        progress_win.grab_set()
        
        lbl_title = ctk.CTkLabel(progress_win, text="🔧 Đang thiết lập cấu hình tối ưu", font=("Helvetica", 14, "bold"))
        lbl_title.pack(pady=(15, 10))
        
        lbl_status = ctk.CTkLabel(progress_win, text="Đang chuẩn bị...", font=("Helvetica", 12))
        lbl_status.pack(pady=5)
        
        progress_bar = ctk.CTkProgressBar(progress_win, width=400)
        progress_bar.pack(pady=10)
        progress_bar.set(0)
        
        def run_optimization():
            steps = [
                ("Khởi tạo WINEPREFIX mặc định...", 0.1),
                ("Thiết lập Font Smoothing và tối ưu Registry...", 0.3),
                ("Đồng bộ bộ cài Winetricks...", 0.5),
                ("Cài đặt Microsoft Core Fonts...", 0.7),
                ("Cài đặt các component bổ trợ (Msxml6, Riched20)...", 0.85),
                ("Cài đặt Visual C++ Runtime (vcrun2015)...", 0.95)
            ]
            
            try:
                # Find default proton
                proton_versions = ProtonUtils.find_proton_versions()
                if proton_versions:
                    proton_name, proton_path = proton_versions[0]
                else:
                    proton_path = "wine"
                
                env = os.environ.copy()
                global_prefix = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default")
                global_pfx = os.path.join(global_prefix, "pfx")
                env["WINEPREFIX"] = global_pfx
                
                is_proton = "wine" not in os.path.basename(proton_path).lower()
                
                # Step 1: Init prefix
                progress_win.after(0, lambda: (lbl_status.configure(text=steps[0][0]), progress_bar.set(steps[0][1])))
                os.makedirs(global_prefix, exist_ok=True)
                if is_proton:
                    cmd = [proton_path, "run", "wineboot", "-u"]
                else:
                    cmd = [proton_path, "wineboot", "-u"]
                subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Step 2: Apply registry
                progress_win.after(0, lambda: (lbl_status.configure(text=steps[1][0]), progress_bar.set(steps[1][1])))
                reg_file = os.path.join(global_prefix, "optimize.reg")
                with open(reg_file, "w") as f:
                    f.write("Windows Registry Editor Version 5.00\n\n")
                    f.write("[HKEY_CURRENT_USER\\Control Panel\\Desktop]\n")
                    f.write('"FontSmoothing"="2"\n')
                    f.write('"FontSmoothingType"=dword:00000002\n')
                    f.write('"FontSmoothingWidth"=dword:00000000\n')
                    f.write('"FontSmoothingOrientation"=dword:00000001\n\n')
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\WineDbg]\n")
                    f.write('"ShowCrashDialog"=dword:00000000\n')
                if is_proton:
                    cmd = [proton_path, "run", "regedit", reg_file]
                else:
                    cmd = [proton_path, "regedit", reg_file]
                subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    os.remove(reg_file)
                except Exception:
                    pass
                    
                # Step 3: Check/download Winetricks
                progress_win.after(0, lambda: (lbl_status.configure(text=steps[2][0]), progress_bar.set(steps[2][1])))
                winetricks_path = shutil.which("winetricks")
                if not winetricks_path:
                    local_winetricks = os.path.expanduser("~/.local/bin/winetricks")
                    if not os.path.exists(local_winetricks):
                        url = "https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"
                        os.makedirs(os.path.expanduser("~/.local/bin"), exist_ok=True)
                        subprocess.run(["curl", "-sL", url, "-o", local_winetricks], check=True)
                        os.chmod(local_winetricks, 0o755)
                    winetricks_path = local_winetricks
                    
                # Winetricks env setup
                w_env = env.copy()
                w_env["NO_AT_BRIDGE"] = "1"
                w_env["GTK_A11Y"] = "none"
                if is_proton:
                    proton_dir = os.path.dirname(proton_path)
                    wine_path = os.path.join(proton_dir, "files/bin/wine")
                    if os.path.exists(wine_path):
                        w_env["WINE"] = wine_path
                        w_env["WINEARCH"] = "win64"
                else:
                    w_env["WINE"] = proton_path
                    
                # Step 4: Install corefonts
                progress_win.after(0, lambda: (lbl_status.configure(text=steps[3][0]), progress_bar.set(steps[3][1])))
                subprocess.run([winetricks_path, "-q", "corefonts"], env=w_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Step 5: Install msxml6 riched20
                progress_win.after(0, lambda: (lbl_status.configure(text=steps[4][0]), progress_bar.set(steps[4][1])))
                subprocess.run([winetricks_path, "-q", "msxml6", "riched20", "riched30"], env=w_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Step 6: Install vcrun2015
                progress_win.after(0, lambda: (lbl_status.configure(text=steps[5][0]), progress_bar.set(steps[5][1])))
                subprocess.run([winetricks_path, "-q", "vcrun2015"], env=w_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                progress_win.after(0, lambda: (progress_bar.set(1.0), progress_win.destroy(), messagebox.showinfo("Thành công", "Tối ưu hóa môi trường mặc định hoàn tất!", parent=self.root)))
            except Exception as e:
                progress_win.after(0, lambda: (progress_win.destroy(), messagebox.showerror("Lỗi", f"Lỗi tối ưu hóa hệ thống: {e}", parent=self.root)))
                
        threading.Thread(target=run_optimization, daemon=True).start()

    def build_left_panel(self):
        left_frame = ctk.CTkFrame(self.root, corner_radius=0)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(2, weight=1)
        
        header_container = ctk.CTkFrame(left_frame, fg_color="transparent")
        header_container.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 5))
        header_container.grid_columnconfigure(0, weight=1)
        header_container.grid_columnconfigure(1, weight=0)
        
        lbl_header = ctk.CTkLabel(header_container, text="MicroProton", font=("Helvetica", 22, "bold"), anchor="w")
        lbl_header.grid(row=0, column=0, sticky="w")
        
        header_buttons = ctk.CTkFrame(header_container, fg_color="transparent")
        header_buttons.grid(row=0, column=1, sticky="e", pady=(2, 0))
        
        btn_help = ctk.CTkButton(
            header_buttons,
            text="❓ Hướng dẫn",
            font=("Helvetica", 11, "bold"),
            fg_color="#1f538d",
            hover_color="#14375e",
            width=85,
            height=26,
            command=self.open_help_dialog
        )
        btn_help.pack(side=tk.LEFT, padx=(0, 5))
        
        btn_donate = ctk.CTkButton(
            header_buttons, 
            text="☕ Tài trợ", 
            font=("Helvetica", 11, "bold"), 
            fg_color="#2eb85c", 
            hover_color="#229949",
            width=70,
            height=26,
            command=self.open_donate_dialog
        )
        btn_donate.pack(side=tk.LEFT)
        
        lbl_subheader = ctk.CTkLabel(header_container, text="Quản lý & Tối ưu môi trường Windows", font=("Helvetica", 11), text_color="gray", anchor="w")
        lbl_subheader.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        
        btn_add = ctk.CTkButton(
            left_frame, 
            text="+ Đăng ký ứng dụng", 
            font=("Helvetica", 13, "bold"), 
            fg_color="#1f538d", 
            hover_color="#14375e",
            command=self.add_app_dialog
        )
        btn_add.grid(row=1, column=0, sticky="ew", padx=15, pady=10)
        
        self.scroll_list = ctk.CTkScrollableFrame(left_frame, label_text="Danh sách Ứng dụng")
        self.scroll_list.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        btn_kill_all_sandboxes = ctk.CTkButton(
            left_frame, 
            text="⏹️ Terminate All Sandboxes", 
            font=("Helvetica", 12, "bold"), 
            fg_color="#e55353", 
            hover_color="#d93737",
            height=32,
            command=self.kill_all_sandboxes
        )
        btn_kill_all_sandboxes.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 5))
        
        bottom_btn_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        bottom_btn_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(5, 10))
        bottom_btn_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        btn_open_c_drive = ctk.CTkButton(
            bottom_btn_frame, 
            text="📁 File Explorer", 
            font=("Helvetica", 11, "bold"), 
            fg_color="#2b2b2b", 
            hover_color="#3a3a3a",
            height=32,
            command=self.open_global_c_drive
        )
        btn_open_c_drive.grid(row=0, column=0, sticky="ew", padx=2)
        
        btn_open_taskbar = ctk.CTkButton(
            bottom_btn_frame, 
            text="🖥️ Virtual Desktop", 
            font=("Helvetica", 11, "bold"), 
            fg_color="#2b2b2b", 
            hover_color="#3a3a3a",
            height=32,
            command=self.launch_global_taskbar
        )
        btn_open_taskbar.grid(row=0, column=1, sticky="ew", padx=2)
        
        btn_settings = ctk.CTkButton(
            bottom_btn_frame, 
            text="⚙️ Cấu hình", 
            font=("Helvetica", 11, "bold"), 
            fg_color="#2b2b2b", 
            hover_color="#3a3a3a",
            height=32,
            command=self.open_settings_dialog
        )
        btn_settings.grid(row=0, column=2, sticky="ew", padx=2)
        
    def build_right_panel(self):
        self.right_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(0, weight=1)
        
        self.welcome_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.welcome_frame.grid(row=0, column=0, sticky="nsew")
        self.build_welcome_frame()
        
        self.details_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.build_details_frame()
        
    def build_welcome_frame(self):
        self.welcome_frame.grid_columnconfigure(0, weight=1)
        self.welcome_frame.grid_rowconfigure((0, 1, 2), weight=1)
        
        lbl_welcome_icon = ctk.CTkLabel(self.welcome_frame, text="🛡️", font=("Helvetica", 80))
        lbl_welcome_icon.grid(row=1, column=0, pady=(0, 15))
        
        lbl_welcome_text = ctk.CTkLabel(
            self.welcome_frame, 
            text="Vui lòng lựa chọn ứng dụng từ danh sách bên trái\nhoặc nhấp chọn '+ Đăng ký ứng dụng' để cấu hình & thực thi.",
            font=("Helvetica", 14), 
            text_color="gray",
            justify="center"
        )
        lbl_welcome_text.grid(row=1, column=0, pady=(140, 0))

    def build_details_frame(self):
        self.details_frame.grid_columnconfigure(0, weight=1)
        self.details_frame.grid_rowconfigure(1, weight=1)
        
        self.header_frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        
        self.lbl_app_title = ctk.CTkLabel(self.header_frame, text="Tên định danh (App Name)", font=("Helvetica", 22, "bold"), anchor="w")
        self.lbl_app_title.pack(fill=tk.X)
        
        self.lbl_app_status = ctk.CTkLabel(self.header_frame, text="Trạng thái: Idle", font=("Helvetica", 12), text_color="gray", anchor="w")
        self.lbl_app_status.pack(fill=tk.X, pady=(2, 0))
        
        self.tabview = ctk.CTkTabview(self.details_frame)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        
        self.tabview.add("Khởi chạy & Tiện ích")
        self.tabview.add("Thiết lập Hệ thống")
        self.tabview.add("Hiệu chỉnh Thông tin")
        
        self.build_tools_tab()
        self.build_config_tab()
        self.build_edit_tab()
        
    def bind_hover_description(self, widget, description_text):
        widget.bind("<Enter>", lambda event, text=description_text: self.lbl_tool_desc.configure(text=text))
        widget.bind("<Leave>", lambda event: self.lbl_tool_desc.configure(text="Di con trỏ chuột vào các chức năng để xem thông tin chi tiết..."))

    def bind_scroll_to_widget(self, scrollable_frame, widget):
        def on_scroll(event):
            if hasattr(scrollable_frame, "_parent_canvas") and scrollable_frame._parent_canvas.winfo_exists():
                if event.num == 4:
                    scrollable_frame._parent_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    scrollable_frame._parent_canvas.yview_scroll(1, "units")
                elif event.delta:
                    scrollable_frame._parent_canvas.yview_scroll(-int(event.delta/120), "units")

        widget.bind("<Button-4>", on_scroll, add="+")
        widget.bind("<Button-5>", on_scroll, add="+")
        widget.bind("<MouseWheel>", on_scroll, add="+")
        
        for child in widget.winfo_children():
            self.bind_scroll_to_widget(scrollable_frame, child)

    def build_tools_tab(self):
        tab = self.tabview.tab("Khởi chạy & Tiện ích")
        tab.grid_columnconfigure((0, 1), weight=1)
        tab.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1)
        
        self.btn_launch = ctk.CTkButton(
            tab, 
            text="KHỞI CHẠY (LAUNCH)", 
            font=("Helvetica", 16, "bold"), 
            fg_color="#2eb85c", 
            hover_color="#229949",
            height=52,
            command=self.launch_app
        )
        self.btn_launch.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(15, 10))
        
        self.btn_winecfg = ctk.CTkButton(tab, text="Cấu hình Wine (winecfg)", height=38, command=self.run_winecfg)
        self.btn_winecfg.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        
        self.btn_winetricks = ctk.CTkButton(tab, text="Quản lý Component (Winetricks)", height=38, command=self.run_winetricks)
        self.btn_winetricks.grid(row=1, column=1, sticky="ew", padx=20, pady=6)
        
        self.btn_browse = ctk.CTkButton(tab, text="Mở thư mục Drive C", height=38, command=self.browse_c_drive)
        self.btn_browse.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        
        self.btn_change_exe = ctk.CTkButton(tab, text="Thay đổi Executable Path (.exe)", height=38, command=self.change_exe_target)
        self.btn_change_exe.grid(row=2, column=1, sticky="ew", padx=20, pady=6)
        
        self.btn_backup = ctk.CTkButton(tab, text="Backup WINEPREFIX", height=38, command=self.backup_prefix)
        self.btn_backup.grid(row=3, column=0, sticky="ew", padx=20, pady=6)
        
        self.btn_restore = ctk.CTkButton(tab, text="Restore WINEPREFIX", height=38, command=self.restore_prefix)
        self.btn_restore.grid(row=3, column=1, sticky="ew", padx=20, pady=6)
        
        self.btn_kill = ctk.CTkButton(tab, text="Terminate All Processes", height=38, fg_color="#e55353", hover_color="#d93737", command=self.kill_app)
        self.btn_kill.grid(row=4, column=0, sticky="ew", padx=20, pady=6)
        
        self.btn_delete = ctk.CTkButton(tab, text="Gỡ bỏ Ứng dụng (Delete)", height=38, fg_color="#f9b115", hover_color="#e69d0d", command=self.delete_app)
        self.btn_delete.grid(row=4, column=1, sticky="ew", padx=20, pady=6)
        
        self.lbl_tool_desc = ctk.CTkLabel(
            tab, 
            text="Di con trỏ chuột vào các chức năng để xem thông tin chi tiết...", 
            font=("Helvetica", 12, "italic"), 
            text_color="gray", 
            justify="center",
            wraplength=600,
            height=45
        )
        self.lbl_tool_desc.grid(row=5, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 15))
        
        self.bind_hover_description(self.btn_launch, "Khởi chạy ứng dụng Windows bằng môi trường Proton/Wine đã định cấu hình.")
        self.bind_hover_description(self.btn_winecfg, "Mở giao diện cấu hình Wine (winecfg) để thiết lập Windows Version, DLL Overrides, Graphics và Audio.")
        self.bind_hover_description(self.btn_winetricks, "Cài đặt các gói thư viện bổ sung (Microsoft Core Fonts, DirectX, .NET Framework, Visual C++ Redistributable...) vào WINEPREFIX.")
        self.bind_hover_description(self.btn_browse, "Mở thư mục Drive C (drive_c) trong WINEPREFIX để quản lý dữ liệu, cài đặt MOD hoặc cấu hình tệp tin ứng dụng.")
        self.bind_hover_description(self.btn_change_exe, "Thay đổi đường dẫn tệp thực thi chính (thường sử dụng sau khi hoàn tất chạy Installer để trỏ Shortcut đến file thực thi .exe của phần mềm).")
        self.bind_hover_description(self.btn_backup, "Nén toàn bộ cấu trúc WINEPREFIX của ứng dụng thành file lưu trữ (.zip) phục vụ backup hoặc di chuyển dữ liệu.")
        self.bind_hover_description(self.btn_restore, "Giải nén file sao lưu (.zip) để khôi phục trạng thái WINEPREFIX và toàn bộ dữ liệu ứng dụng về thời điểm backup.")
        self.bind_hover_description(self.btn_kill, "Buộc chấm dứt (Terminate) toàn bộ tiến trình Windows đang thực thi ngầm trong WINEPREFIX hiện hành để khắc phục lỗi đóng băng (freeze).")
        self.bind_hover_description(self.btn_delete, "Gỡ bỏ Shortcut File (.desktop) khỏi Desktop Environment và cung cấp tuỳ chọn xoá WINEPREFIX để giải phóng bộ nhớ lưu trữ.")

    def create_setting_card(self, parent, title, description):
        card = ctk.CTkFrame(parent, corner_radius=8, border_width=1, border_color=("#e0e0e0", "#2d2d2d"), fg_color=("#f8f8f8", "#1c1c1e"))
        card.pack(fill=tk.X, padx=10, pady=5)
        
        text_frame = ctk.CTkFrame(card, fg_color="transparent")
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        lbl_title = ctk.CTkLabel(text_frame, text=title, font=("Helvetica", 13, "bold"), anchor="w", justify="left", wraplength=280)
        lbl_title.pack(fill=tk.X)
        
        lbl_desc = ctk.CTkLabel(text_frame, text=description, font=("Helvetica", 11), text_color="gray", anchor="w", justify="left", wraplength=280)
        lbl_desc.pack(fill=tk.X)
        
        control_frame = ctk.CTkFrame(card, fg_color="transparent")
        control_frame.pack(side=tk.RIGHT, padx=15, pady=10)
        
        return card, control_frame

    def build_config_tab(self):
        tab = self.tabview.tab("Thiết lập Hệ thống")
        
        container = ctk.CTkScrollableFrame(tab, fg_color="transparent", label_text="Cấu hình Hệ thống & Tối ưu hoá")
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        card_proton, ctrl_proton = self.create_setting_card(
            container, 
            "Phiên bản Proton/Wine Runtime", 
            "Định cấu hình phiên bản Proton (Steam) hoặc Proton-GE (Custom) để thực thi ứng dụng."
        )
        self.opt_proton = ctk.CTkOptionMenu(ctrl_proton, values=["Mặc định (Mới nhất)"], width=200)
        self.opt_proton.pack(padx=5, pady=5)
        
        card_mango, ctrl_mango = self.create_setting_card(
            container, 
            "Kích hoạt MangoHud Performance Overlay", 
            "Hiển thị FPS, thông số phần cứng (CPU/GPU/RAM) và nhiệt độ hệ thống realtime."
        )
        self.var_mangohud = tk.BooleanVar()
        self.chk_mangohud = ctk.CTkSwitch(ctrl_mango, text="", variable=self.var_mangohud)
        self.chk_mangohud.pack(padx=5, pady=5)
        
        card_gamemode, ctrl_gamemode = self.create_setting_card(
            container, 
            "Kích hoạt Feral GameMode", 
            "Tối ưu hóa lập lịch CPU/GPU (Governor & Scheduler) để gia tăng hiệu năng thực thi."
        )
        self.var_gamemode = tk.BooleanVar()
        self.chk_gamemode = ctk.CTkSwitch(ctrl_gamemode, text="", variable=self.var_gamemode)
        self.chk_gamemode.pack(padx=5, pady=5)
        
        card_wined3d, ctrl_wined3d = self.create_setting_card(
            container, 
            "Bắt buộc OpenGL Renderer (WineD3D)", 
            "Vô hiệu hóa Vulkan/DXVK và chuyển hướng đồ hoạ qua OpenGL API (khắc phục lỗi đồ hoạ game cũ)."
        )
        self.var_wined3d = tk.BooleanVar()
        self.chk_wined3d = ctk.CTkSwitch(ctrl_wined3d, text="", variable=self.var_wined3d)
        self.chk_wined3d.pack(padx=5, pady=5)
        
        card_vd, ctrl_vd = self.create_setting_card(
            container, 
            "Kích hoạt Virtual Desktop (Khung giả lập)", 
            "Thực thi ứng dụng trong một Virtual Window cố định để ngăn ngừa xung đột độ phân giải Display."
        )
        self.var_vd = tk.BooleanVar()
        self.chk_vd = ctk.CTkSwitch(ctrl_vd, text="", variable=self.var_vd, command=self.toggle_vd_dropdown)
        self.chk_vd.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.opt_resolution = ctk.CTkOptionMenu(ctrl_vd, values=["800x600", "1024x768", "1280x720", "1600x900", "1920x1080"], width=110)
        self.opt_resolution.pack(side=tk.LEFT, padx=5, pady=5)
        
        card_unikey, ctrl_unikey = self.create_setting_card(
            container,
            "Tích hợp Bộ gõ Tiếng Việt UniKey (Wine)",
            "Thực thi tiến trình UniKeyNT.exe trong WINEPREFIX để hỗ trợ nhập liệu tiếng Việt Telex/VNI."
        )
        self.var_unikey = tk.BooleanVar()
        self.chk_unikey = ctk.CTkSwitch(ctrl_unikey, text="", variable=self.var_unikey, command=self.handle_unikey_toggle)
        self.chk_unikey.pack(padx=5, pady=5)
        
        card_taskbar, ctrl_taskbar = self.create_setting_card(
            container,
            "Kích hoạt Windows Explorer Shell",
            "Tự động khởi chạy tiến trình explorer.exe để hiển thị Desktop GUI và thanh Taskbar trong môi trường ảo."
        )
        self.var_taskbar = tk.BooleanVar()
        self.chk_taskbar = ctk.CTkSwitch(ctrl_taskbar, text="", variable=self.var_taskbar)
        self.chk_taskbar.pack(padx=5, pady=5)
        
        self.btn_save_config = ctk.CTkButton(
            container, 
            text="Áp dụng Cấu hình", 
            font=("Helvetica", 14, "bold"), 
            fg_color="#3a82f6", 
            hover_color="#2563eb",
            height=40,
            command=self.save_game_config
        )
        self.btn_save_config.pack(fill=tk.X, padx=15, pady=15)
        
        self.bind_scroll_to_widget(container, tab)

    def build_edit_tab(self):
        tab = self.tabview.tab("Hiệu chỉnh Thông tin")
        tab.grid_columnconfigure((0, 1), weight=1)
        
        lbl_name = ctk.CTkLabel(tab, text="Tên hiển thị (Display Name):", font=("Helvetica", 12, "bold"), anchor="w")
        lbl_name.grid(row=0, column=0, sticky="w", padx=20, pady=(15, 2))
        
        self.ent_name = ctk.CTkEntry(tab, placeholder_text="Nhập tên ứng dụng...")
        self.ent_name.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 10))
        
        lbl_icon = ctk.CTkLabel(tab, text="Đường dẫn Biểu tượng (Icon):", font=("Helvetica", 12, "bold"), anchor="w")
        lbl_icon.grid(row=2, column=0, sticky="w", padx=20, pady=(10, 2))
        
        self.ent_icon = ctk.CTkEntry(tab, placeholder_text="Đường dẫn hình ảnh PNG/SVG hoặc Tên Icon hệ thống")
        self.ent_icon.grid(row=3, column=0, sticky="ew", padx=(20, 5), pady=(0, 10))
        
        btn_browse_icon = ctk.CTkButton(tab, text="Chọn...", width=80, command=self.select_icon_edit)
        btn_browse_icon.grid(row=3, column=1, sticky="w", padx=(5, 20), pady=(0, 10))
        
        lbl_exe_label = ctk.CTkLabel(tab, text="Đường dẫn tệp gốc Executable (.exe):", font=("Helvetica", 11, "bold"), text_color="gray", anchor="w")
        lbl_exe_label.grid(row=4, column=0, sticky="w", padx=20, pady=(10, 2))
        
        self.lbl_exe_val = ctk.CTkLabel(tab, text="", font=("Helvetica", 11), text_color="gray", anchor="w", justify="left")
        self.lbl_exe_val.grid(row=5, column=0, columnspan=2, sticky="w", padx=25, pady=(0, 10))
        
        lbl_prefix_label = ctk.CTkLabel(tab, text="Đường dẫn WINEPREFIX:", font=("Helvetica", 11, "bold"), text_color="gray", anchor="w")
        lbl_prefix_label.grid(row=6, column=0, sticky="w", padx=20, pady=(5, 2))
        
        self.lbl_prefix_val = ctk.CTkLabel(tab, text="", font=("Helvetica", 11), text_color="gray", anchor="w", justify="left")
        self.lbl_prefix_val.grid(row=7, column=0, columnspan=2, sticky="w", padx=25, pady=(0, 15))
        
        self.btn_save_info = ctk.CTkButton(
            tab, 
            text="Cập nhật Thông tin", 
            font=("Helvetica", 14, "bold"),
            fg_color="#3a82f6",
            hover_color="#2563eb",
            height=40,
            command=self.save_app_info
        )
        self.btn_save_info.grid(row=8, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 15))

    def show_welcome_screen(self):
        self.details_frame.grid_forget()
        self.welcome_frame.grid(row=0, column=0, sticky="nsew")
        
    def show_details_screen(self):
        self.welcome_frame.grid_forget()
        self.details_frame.grid(row=0, column=0, sticky="nsew")

    def toggle_vd_dropdown(self):
        if self.var_vd.get():
            self.opt_resolution.configure(state="normal")
        else:
            self.opt_resolution.configure(state="disabled")

    def refresh_list(self):
        for widget in self.row_widgets:
            widget.destroy()
        self.row_widgets.clear()
        
        self.selected_row = None
        self.show_welcome_screen()
        
        self.apps = scan_apps()
        
        if not self.apps:
            lbl_empty = ctk.CTkLabel(self.scroll_list, text="Không có ứng dụng nào.\nHãy nhấn nút '+ Thêm ứng dụng'!", text_color="gray", font=("Helvetica", 13))
            lbl_empty.pack(pady=30)
            self.row_widgets.append(lbl_empty)
            return
            
        for app in self.apps:
            row = AppRow(
                self.scroll_list, 
                app, 
                click_callback=self.select_row, 
                double_click_callback=lambda e: self.launch_app()
            )
            row.pack(fill=tk.X, padx=5, pady=4)
            self.row_widgets.append(row)
            
        self.bind_scroll_to_widget(self.scroll_list, self.scroll_list)

    def select_row(self, row_widget):
        if self.selected_row:
            self.selected_row.configure(fg_color="transparent")
            
        self.selected_row = row_widget
        self.selected_row.configure(fg_color=("#e2e2e2", "#2c2c2c"))
        
        app = row_widget.app_info
        self.show_details_screen()
        
        self.lbl_app_title.configure(text=app["name"])
        
        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, app["name"])
        self.ent_icon.delete(0, tk.END)
        self.ent_icon.insert(0, app["icon"])
        self.lbl_exe_val.configure(text=app["exe"])
        self.lbl_prefix_val.configure(text=app["prefix"])
        
        self.var_mangohud.set(app["mangohud"])
        self.var_gamemode.set(app["gamemode"])
        self.var_wined3d.set(app["wined3d"])
        self.var_unikey.set(app.get("unikey", False))
        self.var_taskbar.set(app.get("taskbar", False))
        
        if app["virtual_desktop"]:
            self.var_vd.set(True)
            self.opt_resolution.configure(state="normal")
            if app["virtual_desktop"] in self.opt_resolution.cget("values"):
                self.opt_resolution.set(app["virtual_desktop"])
        else:
            self.var_vd.set(False)
            self.opt_resolution.configure(state="disabled")
            self.opt_resolution.set("1280x720")
            
        proton_versions = ProtonUtils.find_proton_versions()
        proton_names = ["Mặc định (Mới nhất)"] + [p[0] for p in proton_versions]
        self.opt_proton.configure(values=proton_names)
        
        if app["proton"]:
            matching_name = None
            for p_name in proton_names:
                if app["proton"] in p_name:
                    matching_name = p_name
                    break
            if matching_name:
                self.opt_proton.set(matching_name)
            else:
                self.opt_proton.set("Mặc định (Mới nhất)")
        else:
            self.opt_proton.set("Mặc định (Mới nhất)")

    def get_selected_app(self):
        if not self.selected_row:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một ứng dụng trong danh sách!")
            return None
        return self.selected_row.app_info

    def launch_app(self):
        app = self.get_selected_app()
        if not app:
            return
        
        from src.runner import ProtonRunner
        cmd = [MICRO_PROTON_BIN, "--prefix", app["prefix"]]
        if app["proton"]:
            cmd.extend(["--proton", app["proton"]])
        if app["mangohud"]:
            cmd.append("--mangohud")
        if app["gamemode"]:
            cmd.append("--gamemode")
        if app["wined3d"]:
            cmd.append("--wined3d")
        if app.get("unikey", False):
            cmd.append("--unikey")
        if app.get("taskbar", False):
            cmd.append("--taskbar")
        if app["virtual_desktop"]:
            cmd.extend(["--virtual-desktop", app["virtual_desktop"]])
            
        cmd.append(app["exe"])
        subprocess.Popen(cmd)

    def run_winecfg(self):
        app = self.get_selected_app()
        if not app:
            return
        
        cmd = [MICRO_PROTON_BIN, "--prefix", app["prefix"]]
        if app["proton"]:
            cmd.extend(["--proton", app["proton"]])
            
        cmd.extend(["--winecfg", app["exe"]])
        subprocess.Popen(cmd)

    def run_winetricks(self):
        app = self.get_selected_app()
        if not app:
            return
            
        winetricks_path = shutil.which("winetricks")
        if not winetricks_path:
            local_winetricks = os.path.expanduser("~/.local/bin/winetricks")
            if not os.path.exists(local_winetricks):
                confirm = messagebox.askyesno(
                    "Tải Winetricks",
                    "Không tìm thấy Winetricks trên hệ thống. Bạn có muốn tự động tải về thư mục cá nhân (~/.local/bin/winetricks) không?"
                )
                if not confirm:
                    return
                
                def do_download():
                    try:
                        url = "https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"
                        local_bin = os.path.expanduser("~/.local/bin")
                        os.makedirs(local_bin, exist_ok=True)
                        subprocess.run(["curl", "-sL", url, "-o", local_winetricks], check=True)
                        os.chmod(local_winetricks, 0o755)
                        messagebox.showinfo("Thành công", "Đã tải xong Winetricks. Hãy nhấn nút Winetricks lần nữa để khởi chạy.")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Lỗi tải Winetricks: {e}")
                
                threading.Thread(target=do_download, daemon=True).start()
                messagebox.showinfo("Đang tải", "Đang tải Winetricks về máy tính. Vui lòng đợi thông báo hoàn thành.")
                return
            else:
                winetricks_path = local_winetricks
                
        env = os.environ.copy()
        env["WINEPREFIX"] = os.path.join(app["prefix"], "pfx")
        env["NO_AT_BRIDGE"] = "1"
        env["GTK_A11Y"] = "none"
        
        proton_versions = ProtonUtils.find_proton_versions()
        proton_path = None
        if app["proton"]:
            for name, path in proton_versions:
                if name == app["proton"] or app["proton"] in name:
                    proton_path = path
                    break
        if not proton_path and proton_versions:
            proton_path = proton_versions[0][1]
            
        if proton_path:
            is_system_wine = "wine" in os.path.basename(proton_path).lower()
            if is_system_wine:
                env["WINE"] = proton_path
            else:
                proton_dir = os.path.dirname(proton_path)
                wine_path = os.path.join(proton_dir, "files/bin/wine")
                if os.path.exists(wine_path):
                    env["WINE"] = wine_path
                    env["WINEARCH"] = "win64"
                
        try:
            subprocess.Popen([winetricks_path], env=env)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể khởi chạy Winetricks: {e}")

    def browse_c_drive(self):
        app = self.get_selected_app()
        if not app:
            return
            
        prefix_dir = app["prefix"]
        c_drive = os.path.join(prefix_dir, "pfx", "drive_c")
        if os.path.exists(c_drive):
            subprocess.Popen(["xdg-open", c_drive])
        else:
            messagebox.showerror("Lỗi", "Thư mục ổ C: ảo chưa được tạo (hãy chạy ứng dụng hoặc cài đặt ít nhất một lần để khởi tạo).")

    def change_exe_target(self):
        app = self.get_selected_app()
        if not app:
            return
            
        prefix_dir = app["prefix"]
        c_drive = os.path.join(prefix_dir, "pfx", "drive_c")
        if not os.path.exists(c_drive):
            messagebox.showerror("Lỗi", "Thư mục ổ C: ảo chưa được tạo. Vui lòng khởi chạy một lần trước.")
            return
            
        new_exe = ProtonUtils.select_file_via_zenity("Chọn file chạy (.exe) đã cài đặt", c_drive, parent=self.root)
        
        if new_exe:
            desktop_path = app["desktop_file"]
            try:
                with open(desktop_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                content = re.sub(r"^X-MicroProton-Exe=.*$", f"X-MicroProton-Exe={new_exe}", content, flags=re.MULTILINE)
                
                exec_match = re.search(r"^Exec=(.*)$", content, re.MULTILINE)
                if exec_match:
                    exec_line = exec_match.group(1).strip()
                    old_exe = app["exe"]
                    new_exec_line = exec_line.replace(f'"{old_exe}"', f'"{new_exe}"').replace(old_exe, f'"{new_exe}"')
                    content = re.sub(r"^Exec=.*$", f"Exec={new_exec_line}", content, flags=re.MULTILINE)
                
                new_icon = app["icon"]
                try:
                    exe_hash = ProtonUtils.get_exe_hash(new_exe)
                    extracted_icon = ProtonUtils.extract_app_icon(new_exe, exe_hash)
                    if extracted_icon and extracted_icon != "com.valvesoftware.Steam":
                        new_icon = extracted_icon
                except Exception:
                    pass
                
                content = re.sub(r"^Icon=.*$", f"Icon={new_icon}", content, flags=re.MULTILINE)
                
                with open(desktop_path, "w", encoding="utf-8") as f:
                    f.write(content)
                    
                app["exe"] = new_exe
                app["icon"] = new_icon
                self.lbl_exe_val.configure(text=new_exe)
                self.ent_icon.delete(0, tk.END)
                self.ent_icon.insert(0, new_icon)
                self.selected_row.lbl_exe.configure(text=os.path.basename(new_exe))
                
                subprocess.run(["update-desktop-database", ProtonUtils.APPLICATIONS_DIR])
                messagebox.showinfo("Thành công", f"Đã chuyển đổi đường dẫn chạy sang:\n{os.path.basename(new_exe)}\nvà tự động trích xuất logo ứng dụng mới.")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể cập nhật đường dẫn: {e}")

    def kill_app(self):
        app = self.get_selected_app()
        if not app:
            return
            
        cmd = [MICRO_PROTON_BIN, "--prefix", app["prefix"]]
        if app["proton"]:
            cmd.extend(["--proton", app["proton"]])
            
        cmd.extend(["--kill", app["exe"]])
        subprocess.Popen(cmd)

    def delete_app(self):
        app = self.get_selected_app()
        if not app:
            return
            
        confirm = messagebox.askyesno(
            "Xác nhận xóa", 
            f"Bạn có chắc muốn gỡ bỏ ứng dụng '{app['name']}' khỏi danh sách ứng dụng Linux không?"
        )
        if not confirm:
            return
            
        delete_prefix = False
        global_prefix = ProtonUtils.get_prefix_dir(None)
        if os.path.abspath(app["prefix"]) != os.path.abspath(global_prefix):
            delete_prefix = messagebox.askyesno(
                "Xác nhận xóa thư mục Prefix",
                f"Ứng dụng này đang chạy trong ổ ảo Sandbox riêng biệt:\n{app['prefix']}\n\nBạn có muốn XÓA HOÀN TOÀN thư mục này để giải phóng dung lượng không?\n(Lưu ý: Mọi dữ liệu lưu game/cấu hình sẽ bị xóa)."
            )
            
        try:
            if os.path.exists(app["desktop_file"]):
                os.remove(app["desktop_file"])
                
            if delete_prefix and os.path.exists(app["prefix"]):
                shutil.rmtree(app["prefix"])
                messagebox.showinfo("Thành công", "Đã gỡ ứng dụng và xóa sạch thư mục ổ C: ảo thành công.")
            else:
                messagebox.showinfo("Thành công", "Đã gỡ ứng dụng thành công (đã giữ lại ổ C: ảo).")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xóa ứng dụng: {e}")
            return
            
        subprocess.run(["update-desktop-database", ProtonUtils.APPLICATIONS_DIR])
        self.refresh_list()

    def backup_prefix(self):
        app = self.get_selected_app()
        if not app:
            return
            
        prefix_dir = app["prefix"]
        app_name = app["name"]
        
        file_path = ProtonUtils.select_save_file_via_zenity(f"Sao lưu Prefix cho {app_name}", f"micro_proton_{app_name.lower().replace(' ', '_')}_backup.zip", parent=self.root)
        if not file_path:
            return
            
        if file_path.endswith(".zip"):
            base_name = file_path[:-4]
        else:
            base_name = file_path
            
        def run_zip():
            try:
                shutil.make_archive(base_name, 'zip', prefix_dir)
                messagebox.showinfo("Thành công", f"Đã sao lưu cấu hình (Prefix) thành công tại:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi khi nén thư mục Prefix: {e}")
                
        threading.Thread(target=run_zip, daemon=True).start()
        messagebox.showinfo("Đang sao lưu", "Đang tiến hành nén thư mục Prefix trong nền. Vui lòng đợi đến khi có thông báo hoàn thành.")

    def restore_prefix(self):
        app = self.get_selected_app()
        if not app:
            return
            
        prefix_dir = app["prefix"]
        app_name = app["name"]
        
        confirm = messagebox.askyesno(
            "Xác nhận khôi phục",
            f"Cảnh báo: Hành động này sẽ GHI ĐÈ toàn bộ dữ liệu ổ C: ảo (Prefix) hiện tại của '{app_name}'.\nBạn có chắc chắn muốn tiếp tục?"
        )
        if not confirm:
            return
            
        file_path = ProtonUtils.select_zip_file_via_zenity(f"Chọn tệp sao lưu .zip cho {app_name}", parent=self.root)
        if not file_path:
            return
            
        def run_unzip():
            try:
                if os.path.exists(prefix_dir):
                    shutil.rmtree(prefix_dir)
                os.makedirs(prefix_dir, exist_ok=True)
                
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(prefix_dir)
                    
                messagebox.showinfo("Thành công", f"Đã khôi phục cấu hình (Prefix) thành công từ:\n{os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi khi giải nén thư mục Prefix: {e}")
                
        threading.Thread(target=run_unzip, daemon=True).start()
        messagebox.showinfo("Đang khôi phục", "Đang tiến hành giải nén thư mục Prefix trong nền. Vui lòng đợi đến khi có thông báo hoàn thành.")

    def save_game_config(self):
        app = self.get_selected_app()
        if not app:
            return
        
        proton_sel = self.opt_proton.get()
        proton_val = ""
        if proton_sel != "Mặc định (Mới nhất)":
            proton_val = proton_sel
            
        mangohud_val = self.var_mangohud.get()
        gamemode_val = self.var_gamemode.get()
        wined3d_val = self.var_wined3d.get()
        
        vd_val = ""
        if self.var_vd.get():
            vd_val = self.opt_resolution.get()
            
        unikey_val = self.var_unikey.get()
        taskbar_val = self.var_taskbar.get()
        
        from src.runner import ProtonRunner
        exec_line = ProtonRunner.make_exec_line(
            prefix_dir=app["prefix"],
            exe_path=app["exe"],
            proton=proton_val,
            mangohud=mangohud_val,
            gamemode=gamemode_val,
            wined3d=wined3d_val,
            virtual_desktop=vd_val,
            unikey=unikey_val,
            taskbar=taskbar_val
        )
        
        desktop_path = app["desktop_file"]
        try:
            with open(desktop_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            content = re.sub(r"^Exec=.*$", f"Exec={exec_line}", content, flags=re.MULTILINE)
            
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            app["proton"] = proton_val
            app["mangohud"] = mangohud_val
            app["gamemode"] = gamemode_val
            app["wined3d"] = wined3d_val
            app["virtual_desktop"] = vd_val
            app["unikey"] = unikey_val
            app["taskbar"] = taskbar_val
            
            subprocess.run(["update-desktop-database", ProtonUtils.APPLICATIONS_DIR])
            messagebox.showinfo("Thành công", "Đã lưu cấu hình trò chơi thành công!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi file cấu hình: {e}")

    def save_app_info(self):
        app = self.get_selected_app()
        if not app:
            return
            
        new_name = self.ent_name.get().strip()
        new_icon = self.ent_icon.get().strip()
        
        if not new_name:
            messagebox.showerror("Lỗi", "Tên hiển thị không được để trống!")
            return
            
        desktop_path = app["desktop_file"]
        try:
            with open(desktop_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            content = re.sub(r"^Name=.*$", f"Name={new_name}", content, flags=re.MULTILINE)
            content = re.sub(r"^Icon=.*$", f"Icon={new_icon}", content, flags=re.MULTILINE)
            
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            app["name"] = new_name
            app["icon"] = new_icon
            self.lbl_app_title.configure(text=new_name)
            self.selected_row.lbl_name.configure(text=new_name)
            
            subprocess.run(["update-desktop-database", ProtonUtils.APPLICATIONS_DIR])
            messagebox.showinfo("Thành công", "Đã cập nhật thông tin hiển thị ứng dụng!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu thông tin: {e}")

    def select_icon_edit(self):
        file_path = ProtonUtils.select_image_via_zenity("Chọn hình ảnh làm Icon", parent=self.root)
        if file_path:
            self.ent_icon.delete(0, tk.END)
            self.ent_icon.insert(0, file_path)

    def open_proton_downloader(self):
        ProtonDownloaderDialog(self, self.refresh_proton_dropdown)

    def open_donate_dialog(self):
        DonateDialog(self)

    def open_help_dialog(self):
        HelpDialog(self)

    def open_settings_dialog(self):
        SettingsDialog(self)

    def open_global_c_drive(self):
        c_drive = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default", "pfx", "drive_c")
        os.makedirs(c_drive, exist_ok=True)
        subprocess.Popen(["xdg-open", c_drive])

    def kill_all_sandboxes(self):
        confirm = messagebox.askyesno(
            "Xác nhận tắt toàn bộ",
            "Bạn có chắc chắn muốn tắt toàn bộ các ứng dụng Windows và ổ ảo (Sandbox) đang chạy không?"
        )
        if not confirm:
            return
            
        import glob
        my_uid = os.getuid()
        prefixes_dir_abs = os.path.abspath(ProtonUtils.PREFIXES_DIR)
        
        pids_to_kill = []
        
        for pid_dir in glob.glob("/proc/[0-9]*"):
            pid_str = os.path.basename(pid_dir)
            try:
                stat_info = os.stat(pid_dir)
                if stat_info.st_uid != my_uid:
                    continue
                
                environ_path = os.path.join(pid_dir, "environ")
                if not os.path.exists(environ_path):
                    continue
                
                with open(environ_path, "rb") as f:
                    env_data = f.read()
                env_list = env_data.decode("utf-8", errors="ignore").split("\x00")
                
                belongs_to_microproton = False
                for item in env_list:
                    if item.startswith("WINEPREFIX="):
                        wp = os.path.abspath(item.split("=", 1)[1])
                        if wp.startswith(prefixes_dir_abs):
                            belongs_to_microproton = True
                            break
                
                if belongs_to_microproton:
                    pids_to_kill.append(int(pid_str))
            except Exception:
                continue
                
        for pid in pids_to_kill:
            try:
                os.kill(pid, 9)
            except Exception:
                pass
                
        messagebox.showinfo("Thành công", f"Đã tắt hoàn tất toàn bộ các ứng dụng ngầm và ổ ảo Sandbox ({len(pids_to_kill)} tiến trình).")

    def launch_global_taskbar(self):
        proton_versions = ProtonUtils.find_proton_versions()
        if not proton_versions:
            messagebox.showerror("Lỗi", "Không tìm thấy phiên bản Proton nào trên hệ thống.")
            return
            
        proton_name, proton_path = proton_versions[0]
        prefix_dir = ProtonUtils.get_prefix_dir("")
        
        # Kill any existing explorer.exe processes first to ensure clean startup and avoid duplicate taskbars
        import glob
        my_uid = os.getuid()
        for pid_dir in glob.glob("/proc/[0-9]*"):
            pid = os.path.basename(pid_dir)
            try:
                stat_info = os.stat(pid_dir)
                if stat_info.st_uid != my_uid:
                    continue
                cmdline_path = os.path.join(pid_dir, "cmdline")
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, "rb") as f:
                        cmd_data = f.read()
                    cmd_str = cmd_data.decode("utf-8", errors="ignore").replace("\x00", " ")
                    if "explorer.exe" in cmd_str:
                        os.kill(int(pid), 9)
            except Exception:
                pass

        resolution = "1280x720"
        try:
            if hasattr(self, "opt_resolution") and self.opt_resolution:
                resolution = self.opt_resolution.get()
        except Exception:
            pass
            
        if not resolution or resolution == "Tự động":
            resolution = ProtonUtils.get_screen_resolution()
            
        is_system_wine = "wine" in os.path.basename(proton_path).lower()
        env = os.environ.copy()
        env["WINEPREFIX"] = prefix_dir
        if not is_system_wine:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = ProtonUtils.STEAM_PATH
            env["STEAM_COMPAT_DATA_PATH"] = prefix_dir
            env["PROTON_NO_PATH_TRANSLATION"] = "1"
            
        # Write Explorer Virtual Desktop Registry keys to prefix to ensure stability
        reg_vd_path = os.path.join(prefix_dir, "virtual_desktop_global.reg")
        try:
            with open(reg_vd_path, "w") as f:
                f.write("Windows Registry Editor Version 5.00\n\n")
                f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer]\n")
                f.write('"Desktop"="Default"\n\n')
                f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer\\Desktops]\n")
                f.write(f'"Default"="{resolution}"\n')
            
            # Execute regedit to register it
            reg_env = env.copy()
            if is_system_wine:
                subprocess.run([proton_path, "regedit", reg_vd_path], env=reg_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run([proton_path, "run", "regedit", reg_vd_path], env=reg_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error applying virtual desktop registry: {e}")
        
        try:
            if is_system_wine:
                subprocess.Popen([proton_path, "explorer.exe", f"/desktop=Default,{resolution}", "explorer.exe"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([proton_path, "run", "explorer.exe", f"/desktop=Default,{resolution}", "explorer.exe"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            messagebox.showinfo("Thành công", f"Đang khởi chạy màn hình ảo Windows ({resolution}) trong nền...")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở màn hình Windows ảo: {e}")

    def refresh_proton_dropdown(self):
        if self.selected_row:
            app = self.selected_row.app_info
            proton_versions = ProtonUtils.find_proton_versions()
            proton_names = ["Mặc định (Mới nhất)"] + [p[0] for p in proton_versions]
            self.opt_proton.configure(values=proton_names)
            if app["proton"]:
                matching_name = None
                for p_name in proton_names:
                    if app["proton"] in p_name:
                        matching_name = p_name
                        break
                if matching_name:
                    self.opt_proton.set(matching_name)
                else:
                    self.opt_proton.set("Mặc định (Mới nhất)")
            else:
                self.opt_proton.set("Mặc định (Mới nhất)")

    def update_resource_monitor(self):
        if self.selected_row:
            app = self.selected_row.app_info
            threading.Thread(target=self.scan_resources_async, args=(app["exe"],), daemon=True).start()
        else:
            if hasattr(self, "lbl_app_status"):
                self.lbl_app_status.configure(text="Trạng thái: Đang dừng", text_color="gray")
                
        self.root.after(2000, self.update_resource_monitor)

    def scan_resources_async(self, app_exe_path):
        import glob
        my_uid = os.getuid()
        app_exe_path = os.path.abspath(app_exe_path)
        game_dir = os.path.dirname(app_exe_path)
        
        # Get selected app info to check sandbox status
        app = self.get_selected_app()
        if not app:
            return
            
        prefix_dir = app["prefix"]
        global_prefix = ProtonUtils.get_prefix_dir(None)
        is_sandbox = (os.path.abspath(prefix_dir) != os.path.abspath(global_prefix))
        
        target_pfx = os.path.abspath(prefix_dir)
        target_pfx_pfx = os.path.abspath(os.path.join(prefix_dir, "pfx"))
        
        matched_pids = set()
        parent_map = {}
        
        wine_keywords = {"wine", "proton", "wineserver", "explorer.exe", "unikey", "conhost", "winedevice", "plugplay", "rpcss", "services.exe", "svchost.exe", "wineboot.exe"}
        
        for pid_dir in glob.glob("/proc/[0-9]*"):
            pid = os.path.basename(pid_dir)
            try:
                stat_info = os.stat(pid_dir)
                if stat_info.st_uid != my_uid:
                    continue
                    
                # 1. Cheap check on command name to reduce CPU overhead
                comm_path = os.path.join(pid_dir, "comm")
                comm_name = ""
                if os.path.exists(comm_path):
                    with open(comm_path, "r") as f:
                        comm_name = f.read().strip().lower()
                
                is_candidate = False
                for kw in wine_keywords:
                    if kw in comm_name:
                        is_candidate = True
                        break
                        
                if not is_candidate:
                    # Also check cmdline for python launcher, gamemode, or windows .exe binary
                    cmdline_path = os.path.join(pid_dir, "cmdline")
                    if os.path.exists(cmdline_path):
                        with open(cmdline_path, "rb") as f:
                            cmd_data = f.read()
                        cmd_str = cmd_data.decode("utf-8", errors="ignore").lower()
                        if "wine" in cmd_str or "proton" in cmd_str or "micro-proton" in cmd_str or ".exe" in cmd_str or ".exe" in comm_name:
                            is_candidate = True
                                
                if not is_candidate:
                    continue
                    
                stat_path = os.path.join(pid_dir, "stat")
                ppid = "0"
                if os.path.exists(stat_path):
                    with open(stat_path, "r") as f:
                        stat_content = f.read()
                    r_paren = stat_content.rfind(')')
                    if r_paren != -1:
                        parts = stat_content[r_paren+2:].split()
                        if len(parts) >= 2:
                            ppid = parts[1]
                parent_map[pid] = ppid
                
                # Check WINEPREFIX from /proc/<pid>/environ
                environ_path = os.path.join(pid_dir, "environ")
                if not os.path.exists(environ_path):
                    continue
                    
                with open(environ_path, "rb") as f:
                    env_data = f.read()
                env_list = env_data.decode("utf-8", errors="ignore").split("\x00")
                belongs_to_pfx = False
                for item in env_list:
                    if item.startswith("WINEPREFIX="):
                        wp = os.path.abspath(item.split("=", 1)[1])
                        if wp == target_pfx or wp == target_pfx_pfx:
                            belongs_to_pfx = True
                            break
                            
                if belongs_to_pfx:
                    if is_sandbox:
                        # Sandbox prefix: any process in this prefix belongs to the app
                        matched_pids.add(pid)
                    else:
                        # Shared prefix: check cmdline to match the specific app
                        cmdline_path = os.path.join(pid_dir, "cmdline")
                        if os.path.exists(cmdline_path):
                            with open(cmdline_path, "rb") as f:
                                cmd_data = f.read()
                            cmd_str = cmd_data.decode("utf-8", errors="ignore").replace("\x00", " ")
                            
                            if app_exe_path in cmd_str or game_dir in cmd_str:
                                matched_pids.add(pid)
                            else:
                                exe_basename = os.path.basename(app_exe_path)
                                if exe_basename in cmd_str and ("proton" in cmd_str or "wine" in cmd_str):
                                    matched_pids.add(pid)
            except Exception:
                continue
                
        added_new = True
        while added_new:
            added_new = False
            for pid, ppid in parent_map.items():
                if pid not in matched_pids and ppid in matched_pids:
                    matched_pids.add(pid)
                    added_new = True
                    
        pids = list(matched_pids)
        if not pids:
            self.root.after(0, lambda: self.update_status_ui(False, 0.0, 0, 0))
            return
            
        total_cpu = 0.0
        total_mem_kb = 0
        
        try:
            res = subprocess.run(
                ["ps", "-p", ",".join(pids), "-o", "pid,%cpu,rss"],
                capture_output=True, text=True, check=True
            )
            lines = res.stdout.strip().split("\n")[1:]
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    total_cpu += float(parts[1])
                    total_mem_kb += int(parts[2])
        except Exception:
            pass
            
        self.root.after(0, lambda: self.update_status_ui(True, total_cpu, total_mem_kb * 1024, len(pids)))

    def update_status_ui(self, is_running, cpu, mem_bytes, proc_count):
        if not self.selected_row or not hasattr(self, "lbl_app_status"):
            return
            
        if is_running:
            mem_mb = mem_bytes / (1024 * 1024)
            status_text = f"Trạng thái: Đang chạy  •  CPU: {cpu:.1f}%  •  RAM: {mem_mb:.1f} MB  •  Tiến trình: {proc_count}"
            self.lbl_app_status.configure(text=status_text, text_color="#2eb85c")
        else:
            self.lbl_app_status.configure(text="Trạng thái: Đang dừng", text_color="gray")

    def handle_unikey_toggle(self):
        if self.var_unikey.get():
            app = self.get_selected_app()
            if not app:
                self.var_unikey.set(False)
                return
                
            unikey_dir = os.path.join(app["prefix"], "pfx/drive_c/UniKey")
            unikey_exe = os.path.join(unikey_dir, "UniKeyNT.exe")
            
            if not os.path.exists(unikey_exe):
                confirm = messagebox.askyesno(
                    "Tải bộ gõ UniKey",
                    "Bộ gõ tiếng Việt UniKey chưa được tải về ổ ảo này.\nBạn có muốn tự động tải bản UniKey chính thức (4.6 RC2 64-bit) từ unikey.org về không?",
                    parent=self.root
                )
                if confirm:
                    threading.Thread(target=self.download_unikey_async, args=(unikey_dir,), daemon=True).start()
                else:
                    self.var_unikey.set(False)

    def download_unikey_async(self, unikey_dir):
        import urllib.request
        try:
            os.makedirs(unikey_dir, exist_ok=True)
            zip_path = os.path.join(unikey_dir, "unikey.zip")
            
            url = "https://www.unikey.org/assets/release/unikey46RC2-230919-win64.zip"
            
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
                
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(unikey_dir)
                
            if os.path.exists(zip_path):
                os.remove(zip_path)
                
            self.root.after(0, lambda: messagebox.showinfo("Thành công", "Đã tải và cài đặt UniKey thành công vào ổ ảo! Hãy nhấn nút 'Lưu cấu hình hệ thống'.", parent=self.root))
        except Exception as e:
            self.root.after(0, lambda: [
                self.var_unikey.set(False),
                messagebox.showerror("Lỗi", f"Không thể tải UniKey: {e}", parent=self.root)
            ])

    def add_app_dialog(self):
        AddAppDialog(self, self.refresh_list)

    def run_cli_installer(self):
        try:
            subprocess.run([MICRO_PROTON_BIN])
            self.root.after(500, self.refresh_list)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể khởi chạy bộ cài đặt: {e}"))


def main():
    # Single instance lock for manager GUI
    _instance_socket = None
    
    def listen_for_raise(s, root_win, app_inst):
        while True:
            try:
                conn, addr = s.accept()
                data = conn.recv(1024)
                if data == b"raise":
                    root_win.after(0, app_inst.deiconify_and_raise)
                conn.close()
            except Exception:
                break
                
    def check_single_instance(root_win, app_inst, port=18245):
        nonlocal _instance_socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', port))
            s.listen(1)
            _instance_socket = s
            threading.Thread(target=listen_for_raise, args=(s, root_win, app_inst), daemon=True).start()
            return True
        except socket.error:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(('127.0.0.1', port))
                s.sendall(b"raise")
                s.close()
            except Exception:
                pass
            return False

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk(className="micro-proton-manager")
    app = AppManagerWindow(root)
    
    if not check_single_instance(root, app):
        sys.exit(0)
        
    root.mainloop()
