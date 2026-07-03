import os
import sys
import shutil
import zipfile
import threading
import subprocess
import re
import urllib.request
import json
import tempfile
import webbrowser
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

from src.utils import ProtonUtils
from src.config import SettingsManager
from src.runner import MICRO_PROTON_BIN

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app_window):
        super().__init__(app_window.root)
        self.app_window = app_window
        self.title("Thiết lập chung")
        self.geometry("450x290")
        self.resizable(False, False)
        
        # Focus/Grab
        self.transient(app_window.root)
        self.after(250, lambda: self.grab_set())
        
        lbl_title = ctk.CTkLabel(self, text="⚙️ Thiết lập cấu hình chung", font=("Helvetica", 16, "bold"))
        lbl_title.pack(pady=(15, 10))
        
        # Main settings frame
        settings_frame = ctk.CTkFrame(self)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        settings_frame.grid_columnconfigure(1, weight=1)
        
        # Default Proton Selection
        lbl_proton = ctk.CTkLabel(settings_frame, text="Proton mặc định:", font=("Helvetica", 12, "bold"))
        lbl_proton.grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))
        
        self.proton_versions = ProtonUtils.find_proton_versions()
        proton_names = [v[0] for v in self.proton_versions]
        
        self.opt_default_proton = ctk.CTkOptionMenu(settings_frame, values=proton_names, width=220)
        self.opt_default_proton.grid(row=0, column=1, sticky="e", padx=15, pady=(15, 5))
        
        # Load settings
        settings = SettingsManager.get_settings()
        current_default = settings.get("default_proton", "")
        if current_default in proton_names:
            self.opt_default_proton.set(current_default)
        elif proton_names:
            self.opt_default_proton.set(proton_names[0])
            
        # Link C drive to Home option
        self.var_symlink = tk.BooleanVar()
        self.var_symlink.set(settings.get("map_home_symlink", False))
        self.chk_symlink = ctk.CTkCheckBox(
            settings_frame, 
            text="Tạo liên kết ổ C: ra thư mục cá nhân (~/micro-proton-c)", 
            variable=self.var_symlink,
            font=("Helvetica", 12)
        )
        self.chk_symlink.grid(row=1, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 5))
            
        # Download Proton button inside the settings frame
        btn_download = ctk.CTkButton(
            settings_frame, 
            text="📥 Tải thêm phiên bản Proton-GE", 
            font=("Helvetica", 12),
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
            height=32,
            command=self.trigger_download
        )
        btn_download.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=(15, 10))
        
        # Action buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=(0, 15), padx=20)
        
        btn_save = ctk.CTkButton(
            btn_frame, 
            text="Lưu thiết lập", 
            fg_color="#2eb85c", 
            hover_color="#229949",
            width=150, 
            command=self.save_settings
        )
        btn_save.pack(side=tk.LEFT, expand=True, padx=5)
        
        btn_close = ctk.CTkButton(
            btn_frame, 
            text="Hủy", 
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            width=150, 
            command=self.destroy
        )
        btn_close.pack(side=tk.RIGHT, expand=True, padx=5)
        
    def trigger_download(self):
        self.destroy()
        self.app_window.open_proton_downloader()
        
    def save_settings(self):
        selected_proton = self.opt_default_proton.get()
        enable_symlink = self.var_symlink.get()
        
        # Save settings
        SettingsManager.save_settings({
            "default_proton": selected_proton,
            "map_home_symlink": enable_symlink
        })
        
        # Handle symlink creation/removal
        target_dir = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default", "pfx", "drive_c")
        link_path = os.path.expanduser("~/micro-proton-c")
        
        if enable_symlink:
            if not os.path.exists(link_path) and not os.path.islink(link_path):
                try:
                    os.symlink(target_dir, link_path)
                except Exception as e:
                    messagebox.showerror("Lỗi", f"Không thể tạo liên kết ổ C: {e}", parent=self)
        else:
            if os.path.islink(link_path):
                try:
                    os.remove(link_path)
                except Exception as e:
                    messagebox.showerror("Lỗi", f"Không thể xóa liên kết ổ C: {e}", parent=self)
                    
        messagebox.showinfo("Thành công", "Đã lưu thiết lập thành công.", parent=self)
        self.destroy()

class AddAppDialog(ctk.CTkToplevel):
    def __init__(self, app_window, callback):
        super().__init__(app_window.root)
        self.app_window = app_window
        self.callback = callback
        self.title("Thêm ứng dụng mới")
        self.geometry("520x460")
        
        self.after(250, lambda: self.grab_set())
        
        self.exe_path = ""
        self.icon_path = "com.valvesoftware.Steam"
        self.proton_versions = ProtonUtils.find_proton_versions()
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(8, weight=1)
        
        lbl_title = ctk.CTkLabel(self, text="Thêm ứng dụng Windows mới", font=("Helvetica", 16, "bold"))
        lbl_title.grid(row=0, column=0, columnspan=3, pady=(20, 15), padx=20, sticky="w")
        
        # EXE Type Option (Install new vs Import existing)
        lbl_type = ctk.CTkLabel(self, text="Mục đích:", font=("Helvetica", 12, "bold"))
        lbl_type.grid(row=1, column=0, sticky="w", padx=20, pady=5)
        
        self.var_exe_type = tk.StringVar(value="install") # "install" or "import"
        
        rdo_install = ctk.CTkRadioButton(self, text="Cài đặt mới (tệp từ Fedora)", variable=self.var_exe_type, value="install", font=("Helvetica", 12), command=self.toggle_sandbox_switch)
        rdo_install.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        rdo_import = ctk.CTkRadioButton(self, text="Đã cài (nhập từ ổ C: ảo)", variable=self.var_exe_type, value="import", font=("Helvetica", 12), command=self.toggle_sandbox_switch)
        rdo_import.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        
        # EXE Selection
        lbl_exe = ctk.CTkLabel(self, text="Tệp tin (.exe):", font=("Helvetica", 12, "bold"))
        lbl_exe.grid(row=2, column=0, sticky="w", padx=20, pady=5)
        
        self.ent_exe = ctk.CTkEntry(self, placeholder_text="Đường dẫn đến file .exe")
        self.ent_exe.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
        btn_browse_exe = ctk.CTkButton(self, text="Chọn...", width=80, command=self.select_exe)
        btn_browse_exe.grid(row=2, column=2, padx=(5, 20), pady=5)
        
        # Display Name
        lbl_name = ctk.CTkLabel(self, text="Tên ứng dụng:", font=("Helvetica", 12, "bold"))
        lbl_name.grid(row=3, column=0, sticky="w", padx=20, pady=5)
        
        self.ent_name = ctk.CTkEntry(self, placeholder_text="Tên hiển thị trong Menu")
        self.ent_name.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(5, 20), pady=5)
        
        # Icon Selection
        lbl_icon = ctk.CTkLabel(self, text="Biểu tượng (Icon):", font=("Helvetica", 12, "bold"))
        lbl_icon.grid(row=4, column=0, sticky="w", padx=20, pady=5)
        
        self.ent_icon = ctk.CTkEntry(self, placeholder_text="Đường dẫn file ảnh hoặc tên icon")
        self.ent_icon.insert(0, self.icon_path)
        self.ent_icon.grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        
        btn_browse_icon = ctk.CTkButton(self, text="Chọn...", width=80, command=self.select_icon)
        btn_browse_icon.grid(row=4, column=2, padx=(5, 20), pady=5)
        
        # Proton Selection
        lbl_proto = ctk.CTkLabel(self, text="Phiên bản Proton:", font=("Helvetica", 12, "bold"))
        lbl_proto.grid(row=5, column=0, sticky="w", padx=20, pady=5)
        
        proto_names = ["Mặc định (Mới nhất)"] + [p[0] for p in self.proton_versions]
        self.opt_proto = ctk.CTkOptionMenu(self, values=proto_names)
        self.opt_proto.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(5, 20), pady=5)
        
        default_proton = SettingsManager.get_default_proton()
        if default_proton:
            matching_name = None
            for p_name in proto_names:
                if default_proton in p_name:
                    matching_name = p_name
                    break
            if matching_name:
                self.opt_proto.set(matching_name)
            else:
                self.opt_proto.set("Mặc định (Mới nhất)")
        else:
            self.opt_proto.set("Mặc định (Mới nhất)")

        # Sandbox Option
        lbl_sandbox = ctk.CTkLabel(self, text="Hộp cát (Sandbox):", font=("Helvetica", 12, "bold"))
        lbl_sandbox.grid(row=6, column=0, sticky="w", padx=20, pady=5)
        
        self.var_sandbox = tk.BooleanVar(value=False)
        self.chk_sandbox = ctk.CTkSwitch(
            self, 
            text="Ổ C: ảo riêng biệt cho ứng dụng này", 
            variable=self.var_sandbox,
            font=("Helvetica", 12)
        )
        self.chk_sandbox.grid(row=6, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=8, column=0, columnspan=3, pady=(20, 15), padx=20, sticky="ew")
        
        btn_cancel = ctk.CTkButton(btn_frame, text="Hủy bỏ", fg_color="gray", hover_color="#555", command=self.destroy)
        btn_cancel.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
        
        btn_add = ctk.CTkButton(btn_frame, text="Thêm ứng dụng", fg_color="#2eb85c", hover_color="#229949", command=self.save_app)
        btn_add.pack(side=tk.RIGHT, padx=10, expand=True, fill=tk.X)

    def toggle_sandbox_switch(self):
        if self.var_exe_type.get() == "install":
            self.chk_sandbox.configure(state="normal")
        else:
            self.chk_sandbox.configure(state="disabled")
            self.var_sandbox.set(False)

    def select_exe(self):
        init_dir = os.path.expanduser("~")
        if self.var_exe_type.get() == "import":
            c_drive = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default", "pfx", "drive_c")
            if os.path.exists(c_drive):
                init_dir = c_drive
                
        file_path = ProtonUtils.select_file_via_zenity("Chọn file Windows Executable (.exe)", init_dir, parent=self)
        if file_path:
            self.exe_path = file_path
            self.ent_exe.delete(0, tk.END)
            self.ent_exe.insert(0, file_path)
            
            suggested_name = os.path.splitext(os.path.basename(file_path))[0]
            suggested_name = suggested_name.replace("_", " ").replace("-", " ").title()
            self.ent_name.delete(0, tk.END)
            self.ent_name.insert(0, suggested_name)
            
    def select_icon(self):
        file_path = ProtonUtils.select_image_via_zenity("Chọn hình ảnh làm Icon", parent=self)
        if file_path:
            self.icon_path = file_path
            self.ent_icon.delete(0, tk.END)
            self.ent_icon.insert(0, file_path)

    def save_app(self):
        name = self.ent_name.get().strip()
        exe = self.ent_exe.get().strip()
        icon = self.ent_icon.get().strip()
        proton_sel = self.opt_proto.get()
        
        proton_val = ""
        if proton_sel != "Mặc định (Mới nhất)":
            proton_val = proton_sel
            
        if not name or not exe:
            messagebox.showerror("Lỗi", "Tên ứng dụng và đường dẫn .exe không được để trống!", parent=self)
            return
            
        if not os.path.exists(exe):
            messagebox.showerror("Lỗi", "Tệp tin .exe không tồn tại tại đường dẫn đã chọn!", parent=self)
            return
            
        exe_hash = ProtonUtils.get_exe_hash(exe)
        
        if self.var_exe_type.get() == "install":
            sandbox_val = self.var_sandbox.get()
            prefix_dir = ProtonUtils.get_prefix_dir(exe) if sandbox_val else ProtonUtils.get_prefix_dir(None)
            
            run_cmd = [MICRO_PROTON_BIN]
            if prefix_dir:
                run_cmd.extend(["--prefix", prefix_dir])
            if proton_val:
                run_cmd.extend(["--proton", proton_val])
            if name:
                run_cmd.extend(["--name", name])
            run_cmd.append(exe)
            
            # Save reference to root window before destroying this dialog
            root_win = self.master
            
            # Define worker to wait for installer process to finish
            def run_installer_worker():
                try:
                    subprocess.run(run_cmd)
                    root_win.after(500, self.callback)
                except Exception as e:
                    root_win.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể chạy trình cài đặt: {e}", parent=root_win))
                    
            # Launch thread
            threading.Thread(target=run_installer_worker, daemon=True).start()
            
            messagebox.showinfo(
                "Đang chạy bộ cài đặt",
                "Trình cài đặt phần mềm đang được khởi chạy.\n\n"
                "Hãy thực hiện quá trình cài đặt phần mềm của bạn. "
                "Sau khi cài đặt xong, bạn đóng trình cài đặt lại, hệ thống sẽ tự động quét, cấu hình và thêm phím tắt vào danh sách cho bạn.",
                parent=self
            )
            self.destroy()
            return
            
        else:
            # For import type: we write the .desktop file immediately
            prefix_dir = ProtonUtils.get_prefix_dir(None)
            desktop_filename = f"micro-proton-app-{exe_hash}.desktop"
            desktop_path = os.path.join(ProtonUtils.APPLICATIONS_DIR, desktop_filename)
            
            # Try to auto-extract icon from exe if it's default
            if icon == "com.valvesoftware.Steam":
                try:
                    extracted_icon = ProtonUtils.extract_app_icon(exe, exe_hash)
                    if extracted_icon:
                        icon = extracted_icon
                except Exception:
                    pass
                    
            from src.runner import ProtonRunner
            exec_line = ProtonRunner.make_exec_line(
                prefix_dir=prefix_dir,
                exe_path=exe,
                proton=proton_val
            )
            
            # Determine the WM_CLASS for proper window grouping
            exe_basename = os.path.basename(exe).lower()
            wm_class = exe_basename
            
            is_proton = True
            if proton_val and "wine" in proton_val.lower():
                is_proton = False
            elif not proton_val and self.proton_versions:
                if "wine" in self.proton_versions[0][0].lower():
                    is_proton = False
                    
            if is_proton:
                wm_class = f"steam_app_{int(exe_hash, 16) % 1000000}"
                
            content = f"""[Desktop Entry]
Name={name}
Exec={exec_line}
Icon={icon}
Terminal=false
Type=Application
Categories=Game;Emulator;Utility;
MimeType=application/x-ms-dos-executable;
Comment=Chạy bằng MicroProton
StartupWMClass={wm_class}
X-MicroProton-Exe={exe}
"""
            try:
                with open(desktop_path, "w", encoding="utf-8") as f:
                    f.write(content)
                
                subprocess.run(["update-desktop-database", ProtonUtils.APPLICATIONS_DIR])
                self.callback()
                self.destroy()
                messagebox.showinfo("Thành công", f"Đã nhập ứng dụng '{name}' thành công!", parent=self.app_window.root)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể lưu ứng dụng: {e}", parent=self)

class ProtonDownloaderDialog(ctk.CTkToplevel):
    def __init__(self, parent_win, callback):
        super().__init__(parent_win.root)
        self.app_window = parent_win
        self.callback = callback
        self.title("Tải & Quản lý Proton-GE")
        self.geometry("600x520")
        self.resizable(False, False)
        
        self.after(250, lambda: self.grab_set())
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        lbl_title = ctk.CTkLabel(self, text="Bộ quản lý & Tải Proton-GE", font=("Helvetica", 18, "bold"))
        lbl_title.grid(row=0, column=0, sticky="w", padx=20, pady=(15, 2))
        
        self.scroll_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_container.grid(row=2, column=0, sticky="nsew", padx=15, pady=(0, 15))
        
        self.lbl_status = None
        self.progress_frame = None
        self.progress_label = None
        self.progress_bar = None
        self.releases_frame = None
        
        self.refresh_ui()

    def refresh_ui(self):
        for w in self.scroll_container.winfo_children():
            w.destroy()
            
        lbl_inst = ctk.CTkLabel(self.scroll_container, text="Các phiên bản đang cài trên máy:", font=("Helvetica", 13, "bold"), anchor="w")
        lbl_inst.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        installed_versions = ProtonUtils.find_proton_versions()
        if not installed_versions:
            lbl_no_inst = ctk.CTkLabel(self.scroll_container, text="Chưa phát hiện phiên bản Proton nào.", text_color="gray", anchor="w")
            lbl_no_inst.pack(fill=tk.X, padx=20, pady=5)
        else:
            for name, path in installed_versions:
                row = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
                row.pack(fill=tk.X, padx=15, pady=2)
                
                is_custom = "compatibilitytools.d" in path
                location_str = "Custom" if is_custom else "Steam"
                
                lbl_name = ctk.CTkLabel(row, text=f"• {name} ({location_str})", font=("Helvetica", 12), anchor="w")
                lbl_name.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
                if is_custom:
                    btn_del = ctk.CTkButton(
                        row, 
                        text="Xóa", 
                        width=50, 
                        height=22, 
                        fg_color="#e55353", 
                        hover_color="#d93737",
                        command=lambda n=name, p=path: self.delete_proton_version(n, p)
                    )
                    btn_del.pack(side=tk.RIGHT, padx=5)
                    
        divider = ctk.CTkFrame(self.scroll_container, height=2, fg_color=("#e0e0e0", "#2d2d2d"))
        divider.pack(fill=tk.X, padx=10, pady=15)
        
        lbl_online = ctk.CTkLabel(self.scroll_container, text="Tải phiên bản Proton-GE từ GitHub:", font=("Helvetica", 13, "bold"), anchor="w")
        lbl_online.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.lbl_status = ctk.CTkLabel(self.scroll_container, text="Đang tải danh sách từ GitHub...", font=("Helvetica", 11), text_color="gray", anchor="w")
        self.lbl_status.pack(fill=tk.X, padx=15, pady=5)
        
        self.progress_frame = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Đang tải...", font=("Helvetica", 11))
        self.progress_label.pack(fill=tk.X, padx=10, pady=(5, 2))
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=5)
        self.progress_bar.set(0)
        
        self.releases_frame = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        self.releases_frame.pack(fill=tk.X, padx=5, pady=5)
        
        threading.Thread(target=self.fetch_releases, daemon=True).start()

    def delete_proton_version(self, name, path):
        confirm = messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn có chắc chắn muốn xóa phiên bản Proton tùy chỉnh '{name}' để giải phóng dung lượng không?",
            parent=self
        )
        if not confirm:
            return
            
        try:
            version_dir = os.path.dirname(path)
            if os.path.exists(version_dir):
                shutil.rmtree(version_dir)
                messagebox.showinfo("Thành công", f"Đã gỡ bỏ phiên bản Proton '{name}' thành công.", parent=self)
                self.callback()
                self.refresh_ui()
            else:
                messagebox.showerror("Lỗi", "Thư mục không tồn tại.", parent=self)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xóa thư mục: {e}", parent=self)

    def fetch_releases(self):
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req) as res:
                releases = json.loads(res.read().decode())
                
            valid_releases = []
            for r in releases[:6]:
                tag = r.get("tag_name", "")
                assets = r.get("assets", [])
                download_url = None
                tarball_name = None
                size_bytes = 0
                for a in assets:
                    name = a.get("name", "")
                    if name.endswith(".tar.gz") and not name.endswith(".sha512sum"):
                        download_url = a.get("browser_download_url", "")
                        tarball_name = name
                        size_bytes = a.get("size", 0)
                        break
                if download_url and tarball_name:
                    valid_releases.append({
                        "tag": tag,
                        "url": download_url,
                        "filename": tarball_name,
                        "size": size_bytes
                    })
            
            self.after(0, lambda: self.display_releases(valid_releases))
        except Exception as e:
            self.after(0, lambda: self.show_error(f"Lỗi tải danh sách: {e}"))

    def display_releases(self, releases):
        if self.lbl_status and self.lbl_status.winfo_exists():
            self.lbl_status.pack_forget()
        
        for widget in self.releases_frame.winfo_children():
            widget.destroy()
            
        if not releases:
            lbl_empty = ctk.CTkLabel(self.releases_frame, text="Không tìm thấy phiên bản khả dụng.", text_color="gray")
            lbl_empty.pack(pady=10)
            return
            
        compat_dir = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
        
        for r in releases:
            row = ctk.CTkFrame(self.releases_frame, fg_color="transparent")
            row.pack(fill=tk.X, padx=10, pady=3)
            
            size_mb = r["size"] / (1024 * 1024)
            lbl_version = ctk.CTkLabel(
                row, 
                text=f"{r['tag']}  ({size_mb:.1f} MB)", 
                font=("Helvetica", 12, "bold"), 
                anchor="w"
            )
            lbl_version.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            installed_path = os.path.join(compat_dir, r["tag"])
            if os.path.exists(installed_path):
                lbl_installed = ctk.CTkLabel(row, text="Đã cài đặt", text_color="#2eb85c", font=("Helvetica", 11, "bold"))
                lbl_installed.pack(side=tk.RIGHT, padx=15)
            else:
                btn_dl = ctk.CTkButton(
                    row, 
                    text="Tải về", 
                    width=75, 
                    height=24,
                    fg_color="#1f538d", 
                    hover_color="#14375e",
                    command=lambda release=r: self.start_download(release)
                )
                btn_dl.pack(side=tk.RIGHT, padx=5)

    def start_download(self, release):
        self.releases_frame.pack_forget()
        self.progress_frame.pack(fill=tk.X, padx=10, pady=10)
        self.progress_bar.set(0)
        self.progress_label.configure(text=f"Đang tải {release['tag']}...")
        
        threading.Thread(target=self.download_and_extract_thread, args=(release,), daemon=True).start()

    def download_and_extract_thread(self, release):
        import tarfile
        compat_dir = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
        os.makedirs(compat_dir, exist_ok=True)
        dest_archive = os.path.join(compat_dir, release["filename"])
        
        try:
            url = release["url"]
            total_size = release["size"]
            downloaded = 0
            
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response:
                with open(dest_archive, "wb") as out_file:
                    block_size = 1024 * 64
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        out_file.write(buffer)
                        
                        percent = downloaded / total_size
                        mb_downloaded = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        
                        self.after(0, lambda p=percent, m_dl=mb_downloaded, m_tot=total_mb: self.update_progress(p, f"Đang tải: {m_dl:.1f} MB / {m_tot:.1f} MB ({int(p*100)}%)"))
            
            self.after(0, lambda: self.update_progress(1.0, "Đang giải nén tệp tin (TarGz)... Vui lòng đợi!"))
            
            with tarfile.open(dest_archive, "r:gz") as tar:
                tar.extractall(path=compat_dir)
                
            if os.path.exists(dest_archive):
                os.remove(dest_archive)
                
            self.after(0, self.download_complete_success)
        except Exception as e:
            if os.path.exists(dest_archive):
                try:
                    os.remove(dest_archive)
                except Exception:
                    pass
            self.after(0, lambda err=e: self.show_error(f"Lỗi cài đặt: {err}"))

    def update_progress(self, percent, text):
        self.progress_bar.set(percent)
        self.progress_label.configure(text=text)
        
    def download_complete_success(self):
        messagebox.showinfo("Thành công", "Đã tải và cài đặt Proton-GE thành công!", parent=self)
        self.callback()
        self.refresh_ui()
        
    def show_error(self, err_msg):
        messagebox.showerror("Lỗi", err_msg, parent=self)
        self.progress_frame.pack_forget()
        self.refresh_ui()

class DonateDialog(ctk.CTkToplevel):
    def __init__(self, parent_win):
        super().__init__(parent_win.root)
        self.title("Ủng hộ tác giả (Donate)")
        self.geometry("680x340")
        self.resizable(False, False)
        
        self.transient(parent_win.root)
        self.after(250, lambda: self.grab_set())
        
        lbl_title = ctk.CTkLabel(self, text="☕ Ủng hộ phát triển MicroProton", font=("Helvetica", 16, "bold"))
        lbl_title.pack(pady=(15, 10))
        
        main_layout = ctk.CTkFrame(self, fg_color="transparent")
        main_layout.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        qr_frame = ctk.CTkFrame(main_layout, width=200, height=200)
        qr_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        qr_frame.pack_propagate(False)
        
        # Get the actual directory of manager stub
        real_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        search_paths = [
            os.path.join(real_dir, "images", "donate_qr.jpg"),
            os.path.join(real_dir, "images", "donate_qr.png"),
            os.path.join(real_dir, "donate_qr.png"),
            os.path.join(real_dir, "donate_qr.jpg"),
            "/usr/share/micro-proton/images/donate_qr.jpg",
            "/usr/share/micro-proton/images/donate_qr.png"
        ]
        
        qr_path = None
        for path in search_paths:
            if os.path.exists(path):
                qr_path = path
                break
        
        qr_loaded = False
        if qr_path:
            try:
                from PIL import Image
                img = Image.open(qr_path)
                img_resized = img.resize((180, 180), Image.Resampling.LANCZOS)
                
                temp_png = os.path.join(tempfile.gettempdir(), f"micro_proton_donate_qr_{os.getuid()}.png")
                img_resized.save(temp_png, "PNG")
                
                tk_image = tk.PhotoImage(file=temp_png)
                
                bg_color = qr_frame.cget("fg_color")
                if isinstance(bg_color, (list, tuple)):
                    bg_color = bg_color[1] if ctk.get_appearance_mode() == "Dark" else bg_color[0]
                elif not bg_color:
                    bg_color = "transparent"
                    
                if bg_color == "transparent":
                    bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#dbdbdb"
                
                lbl_qr = tk.Label(qr_frame, image=tk_image, bg=bg_color, bd=0)
                lbl_qr.image = tk_image
                lbl_qr.pack(expand=True)
                qr_loaded = True
            except Exception as e:
                print(f"Error loading QR code: {e}")
                
        if not qr_loaded:
            lbl_qr_placeholder = ctk.CTkLabel(
                qr_frame, 
                text="[ Chưa có mã QR ]\n\nHãy chép ảnh mã QR của bạn\nvào thư mục ứng dụng với tên\n'images/donate_qr.jpg' để hiển thị.",
                font=("Helvetica", 10, "italic"),
                text_color="gray",
                justify="center"
            )
            lbl_qr_placeholder.pack(expand=True, padx=10, pady=10)
            
        details_frame = ctk.CTkFrame(main_layout)
        details_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        details_frame.grid_columnconfigure(1, weight=1)
        
        lbl_bank_title = ctk.CTkLabel(details_frame, text="🏦 Ngân hàng:", font=("Helvetica", 11, "bold"))
        lbl_bank_title.grid(row=0, column=0, sticky="w", padx=15, pady=(20, 8))
        
        self.bank_info = "MB Bank: 0833313668 - Đỗ Huy Nhân"
        lbl_bank_val = ctk.CTkLabel(details_frame, text=self.bank_info, font=("Helvetica", 11))
        lbl_bank_val.grid(row=0, column=1, sticky="w", padx=5, pady=(20, 8))
        
        btn_copy_bank = ctk.CTkButton(
            details_frame, 
            text="Sao chép", 
            width=70, 
            height=22, 
            font=("Helvetica", 10),
            command=lambda: self.copy_to_clipboard(self.bank_info, btn_copy_bank)
        )
        btn_copy_bank.grid(row=0, column=2, padx=(5, 15), pady=(20, 8))
        
        lbl_momo_title = ctk.CTkLabel(details_frame, text="📱 Ví Momo:", font=("Helvetica", 11, "bold"))
        lbl_momo_title.grid(row=1, column=0, sticky="w", padx=15, pady=8)
        
        self.momo_info = "0833313668 - Đỗ Huy Nhân"
        lbl_momo_val = ctk.CTkLabel(details_frame, text=self.momo_info, font=("Helvetica", 11))
        lbl_momo_val.grid(row=1, column=1, sticky="w", padx=5, pady=8)
        
        btn_copy_momo = ctk.CTkButton(
            details_frame, 
            text="Sao chép", 
            width=70, 
            height=22, 
            font=("Helvetica", 10),
            command=lambda: self.copy_to_clipboard(self.momo_info, btn_copy_momo)
        )
        btn_copy_momo.grid(row=1, column=2, padx=(5, 15), pady=8)
        
        lbl_web_title = ctk.CTkLabel(details_frame, text="🌐 Dự án:", font=("Helvetica", 11, "bold"))
        lbl_web_title.grid(row=2, column=0, sticky="w", padx=15, pady=8)
        
        lbl_web_val = ctk.CTkLabel(details_frame, text="github.com/Huy-Nhan/microproton", font=("Helvetica", 11))
        lbl_web_val.grid(row=2, column=1, sticky="w", padx=5, pady=8)
        
        btn_open_web = ctk.CTkButton(
            details_frame, 
            text="Mở link", 
            width=70, 
            height=22, 
            font=("Helvetica", 10),
            command=self.open_github
        )
        btn_open_web.grid(row=2, column=2, padx=(5, 15), pady=8)
        
        btn_close = ctk.CTkButton(
            self, 
            text="Đóng", 
            fg_color="#3a3a3a", 
            hover_color="#4a4a4a", 
            width=100, 
            command=self.destroy
        )
        btn_close.pack(pady=(0, 15))
        
    def copy_to_clipboard(self, text_to_copy, button_widget):
        self.clipboard_clear()
        parts = text_to_copy.split(":")
        val = parts[-1].split("-")[0].strip() if "-" in parts[-1] else parts[-1].strip()
        self.clipboard_append(val)
        
        button_widget.configure(text="Đã chép!", fg_color="#2eb85c", hover_color="#229949")
        self.after(1500, lambda: button_widget.configure(text="Sao chép", fg_color="#1f538d", hover_color="#14375e"))
        
    def open_github(self):
        webbrowser.open("https://github.com/Huy-Nhan/microproton")

class HelpDialog(ctk.CTkToplevel):
    def __init__(self, parent_win):
        super().__init__(parent_win.root)
        self.title("Hướng dẫn sử dụng MicroProton")
        self.geometry("640x500")
        self.minsize(580, 400)
        
        self.transient(parent_win.root)
        self.after(250, lambda: self.grab_set())
        
        lbl_title = ctk.CTkLabel(self, text="📖 Hướng dẫn sử dụng MicroProton", font=("Helvetica", 16, "bold"))
        lbl_title.pack(pady=(15, 10))
        
        scroll_help = ctk.CTkScrollableFrame(self)
        scroll_help.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        self.add_section(
            scroll_help, 
            "1. Cách thêm và chạy ứng dụng",
            "• Nhấn nút '+ Thêm ứng dụng' ở bảng bên trái.\n"
            "• Chọn tệp tin .exe của ứng dụng Windows cần chạy.\n"
            "• Nhập tên hiển thị và nhấn 'Thêm ứng dụng' để hoàn tất tạo shortcut.\n"
            "• Chọn ứng dụng trong danh sách và nhấn 'Khởi chạy'."
        )
        
        self.add_section(
            scroll_help,
            "2. Gõ Tiếng Việt Telex/VNI (UniKey)",
            "• Bật tùy chọn 'Bộ gõ tiếng Việt UniKey (Proton)' trong phần cấu hình của app.\n"
            "• Khi chạy ứng dụng, UniKeyNT.exe sẽ tự động khởi chạy cùng.\n"
            "• Mẹo sửa lỗi gõ trong WPS Office hoặc một số Game/Phần mềm:\n"
            "  Nhấp đúp vào biểu tượng UniKey ở khay hệ thống (hoặc mở bảng điều khiển), chọn 'Mở rộng', tích vào ô 'Luôn sử dụng clipboard cho Unicode' rồi đóng lại."
        )
        
        self.add_section(
            scroll_help,
            "3. Cài đặt thư viện bổ trợ (Winetricks)",
            "• Nếu ứng dụng (ví dụ MS Office, Photoshop, v.v.) báo thiếu DLL hoặc không hoạt động:\n"
            "  Hãy nhấp vào nút 'Thư viện Winetricks' ở bảng cấu hình bên phải của app đó.\n"
            "• Cài đặt các thư viện phổ biến như: corefonts (Font chữ), dotnet48 (.NET Framework), msxml6, riched20."
        )
        
        self.add_section(
            scroll_help,
            "4. MangoHud & GameMode & Màn hình ảo",
            "• MangoHud: Hiển thị thông số FPS, CPU, RAM, nhiệt độ khi chơi game.\n"
            "• GameMode: Tối ưu hiệu năng CPU/GPU cho trò chơi.\n"
            "• Màn hình ảo: Khởi chạy ứng dụng trong một cửa sổ ảo độ phân giải cố định (ví dụ 1280x720) để tránh lỗi đổi độ phân giải màn hình hệ thống."
        )
        
        btn_close = ctk.CTkButton(
            self, 
            text="Đóng", 
            fg_color="#3a3a3a", 
            hover_color="#4a4a4a", 
            width=100, 
            command=self.destroy
        )
        btn_close.pack(pady=(0, 15))
        
    def add_section(self, parent, title, content):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill=tk.X, pady=10, padx=5)
        
        lbl_title = ctk.CTkLabel(frame, text=title, font=("Helvetica", 13, "bold"), text_color="#1f538d", anchor="w")
        lbl_title.pack(fill=tk.X, pady=(0, 3))
        
        lbl_content = ctk.CTkLabel(frame, text=content, font=("Helvetica", 11), justify="left", anchor="w", wraplength=540)
        lbl_content.pack(fill=tk.X, padx=10)
