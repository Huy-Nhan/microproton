import os
import sys
import subprocess
import glob
import re
import socket
import threading
import time
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GObject, GLib

from src.utils import ProtonUtils
from src.config import SettingsManager

class ProtonIndicator:
    def __init__(self):
        # Determine the logo icon path
        base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        logo_path = os.path.join(base_dir, "images", "logo.png")
        if not os.path.exists(logo_path):
            logo_path = "/usr/share/micro-proton/images/logo.png"
        if not os.path.exists(logo_path):
            logo_path = "/usr/share/pixmaps/micro-proton.png"
        if not os.path.exists(logo_path):
            logo_path = "preferences-desktop-keyboard"

        self.indicator = AppIndicator3.Indicator.new(
            "micro-proton-indicator",
            logo_path,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        
        self.menu = Gtk.Menu()
        
        self.menu_status = Gtk.MenuItem(label="MicroProton: Idle")
        self.menu_status.set_sensitive(False)
        self.menu.append(self.menu_status)
        
        self.menu.append(Gtk.SeparatorMenuItem())
        
        menu_manager = Gtk.MenuItem(label="Khởi chạy Manager")
        menu_manager.connect("activate", self.open_manager)
        self.menu.append(menu_manager)
        
        self.menu_taskbar = Gtk.MenuItem(label="Mở Virtual Desktop")
        self.menu_taskbar.connect("activate", self.toggle_taskbar)
        self.menu.append(self.menu_taskbar)
        
        menu_unikey = Gtk.MenuItem(label="Chạy UniKey (WINE)")
        menu_unikey.connect("activate", self.launch_unikey)
        self.menu.append(menu_unikey)
        
        self.menu.append(Gtk.SeparatorMenuItem())
        
        menu_kill = Gtk.MenuItem(label="Kill All Processes")
        menu_kill.connect("activate", self.kill_all)
        self.menu.append(menu_kill)
        
        menu_exit = Gtk.MenuItem(label="Thoát")
        menu_exit.connect("activate", self.quit)
        self.menu.append(menu_exit)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        self.is_running = False
        self.is_taskbar_active = False
        
        threading.Thread(target=self.monitor_loop, daemon=True).start()

    def open_manager(self, widget):
        local_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        search_paths = [
            os.path.join(local_dir, "micro-proton-manager"),
            "/usr/bin/micro-proton-manager"
        ]
        manager_path = None
        for p in search_paths:
            if os.path.exists(p):
                manager_path = p
                break
        if manager_path:
            subprocess.Popen([sys.executable, manager_path])
        else:
            subprocess.Popen(["micro-proton-manager"])

    def toggle_taskbar(self, widget):
        proton_versions = ProtonUtils.find_proton_versions()
        if not proton_versions:
            return
        proton_name, proton_path = proton_versions[0]
        
        global_prefix = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default")
        is_system_wine = "wine" in os.path.basename(proton_path).lower()
        env = os.environ.copy()
        env["WINEPREFIX"] = global_prefix
        if not is_system_wine:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = ProtonUtils.STEAM_PATH
            env["STEAM_COMPAT_DATA_PATH"] = global_prefix
        
        if self.is_taskbar_active:
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
                            subprocess.run(["kill", "-9", pid])
                except Exception:
                    pass
        else:
            # Detect screen resolution or fall back
            resolution = "1280x720"
            try:
                settings = SettingsManager.get_settings()
                resolution = settings.get("global_resolution", "")
            except Exception:
                pass
            
            if not resolution or resolution == "Tự động":
                resolution = ProtonUtils.get_screen_resolution()
                
            # Apply virtual desktop registry before launching
            reg_vd_path = os.path.join(global_prefix, "virtual_desktop_global.reg")
            try:
                os.makedirs(global_prefix, exist_ok=True)
                with open(reg_vd_path, "w") as f:
                    f.write("Windows Registry Editor Version 5.00\n\n")
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer]\n")
                    f.write('"Desktop"="Default"\n\n')
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer\\Desktops]\n")
                    f.write(f'"Default"="{resolution}"\n')
                
                reg_env = env.copy()
                if is_system_wine:
                    subprocess.run([proton_path, "regedit", reg_vd_path], env=reg_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.run([proton_path, "run", "regedit", reg_vd_path], env=reg_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Error applying virtual desktop registry in indicator: {e}")
                
            taskbar_env = env.copy()
            if not is_system_wine:
                taskbar_env["PROTON_NO_PATH_TRANSLATION"] = "1"
                subprocess.Popen([proton_path, "run", "explorer.exe", f"/desktop=Default,{resolution}", "explorer.exe"], env=taskbar_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([proton_path, "explorer.exe", f"/desktop=Default,{resolution}", "explorer.exe"], env=taskbar_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def launch_unikey(self, widget):
        proton_versions = ProtonUtils.find_proton_versions()
        if not proton_versions:
            return
        proton_name, proton_path = proton_versions[0]
        
        global_prefix = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default")
        is_system_wine = "wine" in os.path.basename(proton_path).lower()
        env = os.environ.copy()
        env["WINEPREFIX"] = global_prefix
        if not is_system_wine:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = ProtonUtils.STEAM_PATH
            env["STEAM_COMPAT_DATA_PATH"] = global_prefix
        
        unikey_exe = os.path.join(global_prefix, "pfx/drive_c/UniKey/UniKeyNT.exe")
        if os.path.exists(unikey_exe):
            if is_system_wine:
                subprocess.Popen([proton_path, unikey_exe], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([proton_path, "run", unikey_exe], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            import shutil
            if shutil.which("zenity"):
                subprocess.Popen(["zenity", "--info", "--text=Vui lòng truy cập Manager -> System Configuration để kích hoạt và tự động tải UniKey.", "--title=UniKey NOT FOUND"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    messagebox.showinfo("UniKey NOT FOUND", "Vui lòng truy cập Manager -> System Configuration để kích hoạt và tự động tải UniKey.", parent=root)
                    root.destroy()
                except Exception:
                    print("[UniKey NOT FOUND] Vui lòng truy cập Manager -> System Configuration để kích hoạt và tự động tải UniKey.")

    def kill_all(self, widget):
        proton_versions = ProtonUtils.find_proton_versions()
        if not proton_versions:
            return
        proton_name, proton_path = proton_versions[0]
        
        global_prefix = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default")
        is_system_wine = "wine" in os.path.basename(proton_path).lower()
        env = os.environ.copy()
        env["WINEPREFIX"] = global_prefix
        if not is_system_wine:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = ProtonUtils.STEAM_PATH
            env["STEAM_COMPAT_DATA_PATH"] = global_prefix
            
            proton_dir = os.path.dirname(proton_path)
            wineserver_path = os.path.join(proton_dir, "files/bin/wineserver")
            if os.path.exists(wineserver_path):
                subprocess.Popen([wineserver_path, "-k"], env=env)
            else:
                subprocess.Popen([proton_path, "run", "wineserver", "-k"], env=env)
        else:
            import shutil
            wineserver_bin = shutil.which("wineserver") or "wineserver"
            subprocess.Popen([wineserver_bin, "-k"], env=env)

        my_uid = os.getuid()
        for pid_dir in glob.glob("/proc/[0-9]*"):
            try:
                stat_info = os.stat(pid_dir)
                if stat_info.st_uid != my_uid:
                    continue
                cmdline_path = os.path.join(pid_dir, "cmdline")
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, "rb") as f:
                        cmd_data = f.read()
                    cmd_str = cmd_data.decode("utf-8", errors="ignore").replace("\x00", " ")
                    if any(x in cmd_str for x in ["wineserver", "explorer.exe", "winedevice.exe", "wineboot.exe"]):
                        pid = int(os.path.basename(pid_dir))
                        try:
                            os.kill(pid, 9)
                        except Exception:
                            pass
            except Exception:
                pass

    def quit(self, widget):
        Gtk.main_quit()
        sys.exit(0)

    def monitor_loop(self):
        while True:
            try:
                is_running, status_text, running_games, is_taskbar_running = self.get_proton_running_status()
                self.is_running = is_running
                self.is_taskbar_active = is_taskbar_running
                GLib.idle_add(self.update_ui, status_text, is_taskbar_running)
            except Exception:
                pass
            time.sleep(2)

    def get_proton_running_status(self):
        apps_info = []
        global_prefix = os.path.join(ProtonUtils.PREFIXES_DIR, "global_default")
        global_prefix_abs = os.path.abspath(global_prefix)
        
        if os.path.exists(ProtonUtils.APPLICATIONS_DIR):
            for f in os.listdir(ProtonUtils.APPLICATIONS_DIR):
                if f.startswith("micro-proton-app-") and f.endswith(".desktop"):
                    path = os.path.join(ProtonUtils.APPLICATIONS_DIR, f)
                    try:
                        with open(path, "r", encoding="utf-8") as file:
                            content = file.read()
                        name_match = re.search(r"^Name=(.*)$", content, re.MULTILINE)
                        exe_match = re.search(r"^X-MicroProton-Exe=(.*)$", content, re.MULTILINE)
                        exec_match = re.search(r"^Exec=(.*)$", content, re.MULTILINE)
                        if name_match and exe_match:
                            name = name_match.group(1).strip()
                            exe = os.path.abspath(exe_match.group(1).strip())
                            
                            prefix = global_prefix
                            if exec_match:
                                exec_line = exec_match.group(1).strip()
                                prefix_match = re.search(r'--prefix\s+"([^"]+)"', exec_line)
                                if prefix_match:
                                    prefix = prefix_match.group(1).strip()
                            prefix_abs = os.path.abspath(prefix)
                            is_sandbox = (prefix_abs != global_prefix_abs)
                            
                            apps_info.append({
                                "name": name,
                                "exe": exe,
                                "prefix": prefix_abs,
                                "is_sandbox": is_sandbox
                            })
                    except Exception:
                        pass

        my_uid = os.getuid()
        matched_pids = {}
        parent_map = {}
        is_taskbar_running = False
        
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
                
                cmdline_path = os.path.join(pid_dir, "cmdline")
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, "rb") as f:
                        cmd_data = f.read()
                    cmd_str = cmd_data.decode("utf-8", errors="ignore").replace("\x00", " ")
                    
                    # Resolve WINEPREFIX
                    environ_path = os.path.join(pid_dir, "environ")
                    belongs_to_prefix = None
                    if os.path.exists(environ_path):
                        with open(environ_path, "rb") as f:
                            env_data = f.read()
                        env_list = env_data.decode("utf-8", errors="ignore").split("\x00")
                        for item in env_list:
                            if item.startswith("WINEPREFIX="):
                                belongs_to_prefix = os.path.abspath(item.split("=", 1)[1])
                                break
                    
                    if "explorer.exe" in cmd_str:
                        if belongs_to_prefix and belongs_to_prefix in [global_prefix_abs, os.path.join(global_prefix_abs, "pfx")]:
                            is_taskbar_running = True
                    
                    if belongs_to_prefix:
                        # Match this process against our applications
                        for app in apps_info:
                            app_pfx = app["prefix"]
                            app_pfx_pfx = os.path.join(app_pfx, "pfx")
                            if belongs_to_prefix in [app_pfx, app_pfx_pfx]:
                                if app["is_sandbox"]:
                                    matched_pids[pid] = app["name"]
                                    break
                                else:
                                    # Shared prefix: check cmdline to match the specific app
                                    exe_path = app["exe"]
                                    game_dir = os.path.dirname(exe_path)
                                    if exe_path in cmd_str or game_dir in cmd_str:
                                        matched_pids[pid] = app["name"]
                                        break
                                    else:
                                        exe_basename = os.path.basename(exe_path)
                                        if exe_basename in cmd_str and ("proton" in cmd_str or "wine" in cmd_str):
                                            matched_pids[pid] = app["name"]
                                            break
            except Exception:
                continue

        added_new = True
        while added_new:
            added_new = False
            for pid, ppid in parent_map.items():
                if pid not in matched_pids and ppid in matched_pids:
                    matched_pids[pid] = matched_pids[ppid]
                    added_new = True

        if not matched_pids:
            return False, "MicroProton: Idle", [], is_taskbar_running

        pids = list(matched_pids.keys())
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

        mem_mb = total_mem_kb / 1024.0
        running_games = sorted(list(set(matched_pids.values())))
        games_str = ", ".join(running_games)
        
        status_text = f"Active: {games_str} (CPU: {total_cpu:.1f}%, RAM: {mem_mb:.1f} MB)"
        return True, status_text, running_games, is_taskbar_running

    def update_ui(self, status_text, is_taskbar_running):
        self.menu_status.set_label(status_text)
        if is_taskbar_running:
            self.menu_taskbar.set_label("🖥️ Tắt Virtual Desktop")
        else:
            self.menu_taskbar.set_label("🖥️ Mở Virtual Desktop")


def main():
    # Single instance lock for indicator
    _indicator_socket = None
    
    def check_indicator_single_instance(port=18246):
        nonlocal _indicator_socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', port))
            s.listen(1)
            _indicator_socket = s
            return True
        except socket.error:
            return False

    if not check_indicator_single_instance():
        sys.exit(0)
        
    GObject.threads_init()
    indicator = ProtonIndicator()
    Gtk.main()
