import os
import sys
import subprocess
import hashlib
import re
import shutil
import glob
import threading
import resource
from src.config import SettingsManager
from src.utils import ProtonUtils

# Path definitions
STEAM_PATH = os.path.expanduser("~/.local/share/Steam")
BASE_PREFIX_DIR = os.path.expanduser("~/.local/share/micro-proton/prefixes")
APPLICATIONS_DIR = os.path.expanduser("~/.local/share/applications")

# Fallback to local script if not installed in bin
local_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "micro-proton")
if os.path.exists(local_script):
    MICRO_PROTON_BIN = local_script
else:
    MICRO_PROTON_BIN = os.path.expanduser("~/.local/bin/micro-proton")

class ProtonRunner:
    @staticmethod
    def show_message(text, title="Thông báo", timeout=3):
        """Displays a desktop notification using notify-send or Zenity."""
        try:
            def run_msg():
                try:
                    if shutil.which("notify-send"):
                        subprocess.run(["notify-send", title, text, "-t", str(timeout * 1000)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif shutil.which("zenity"):
                        subprocess.run(["zenity", "--info", f"--text={text}", f"--title={title}", f"--timeout={timeout}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            threading.Thread(target=run_msg, daemon=True).start()
        except Exception:
            print(f"[{title}] {text}")

    @staticmethod
    def get_target_wineserver_path(proton_path):
        if not proton_path:
            return None
        is_system_wine = "wine" in os.path.basename(proton_path).lower()
        if is_system_wine:
            return shutil.which("wineserver") or "wineserver"
        else:
            proton_dir = os.path.dirname(proton_path)
            return os.path.abspath(os.path.join(proton_dir, "files/bin/wineserver"))

    @classmethod
    def kill_processes_by_prefix(cls, prefix_dir, wineserver_only_mismatch=None):
        """Kills processes belonging to the WINEPREFIX, optionally checking for wineserver path mismatch."""
        import glob
        my_uid = os.getuid()
        target_pfx = os.path.abspath(prefix_dir)
        target_pfx_pfx = os.path.abspath(os.path.join(prefix_dir, "pfx"))
        
        prefix_processes = []
        running_wineserver_exe = None
        
        for pid_dir in glob.glob("/proc/[0-9]*"):
            pid_str = os.path.basename(pid_dir)
            try:
                stat_info = os.stat(pid_dir)
                if stat_info.st_uid != my_uid:
                    continue
                
                # Check WINEPREFIX
                environ_path = os.path.join(pid_dir, "environ")
                if not os.path.exists(environ_path):
                    continue
                
                with open(environ_path, "rb") as f:
                    env_data = f.read()
                env_list = env_data.decode("utf-8", errors="ignore").split("\x00")
                belongs = False
                for item in env_list:
                    if item.startswith("WINEPREFIX="):
                        wp = os.path.abspath(item.split("=", 1)[1])
                        if wp == target_pfx or wp == target_pfx_pfx:
                            belongs = True
                            break
                
                if belongs:
                    pid = int(pid_str)
                    prefix_processes.append(pid)
                    
                    # Detect wineserver exe path
                    exe_link = os.path.join(pid_dir, "exe")
                    if os.path.exists(exe_link):
                        exe_path = os.readlink(exe_link)
                        if os.path.basename(exe_path) == "wineserver":
                            running_wineserver_exe = os.path.abspath(exe_path)
            except Exception:
                continue

        if wineserver_only_mismatch:
            # If we only want to kill on mismatch
            wineserver_mismatch = (running_wineserver_exe and wineserver_only_mismatch != running_wineserver_exe)
            if not wineserver_mismatch:
                return False # No mismatch, no need to kill
                
            print(f"Phát hiện lệch phiên bản wineserver: đang chạy {running_wineserver_exe}, yêu cầu {wineserver_only_mismatch}. Tiến hành dọn dẹp prefix...")
            cls.show_message("Phát hiện lệch phiên bản Wine/Proton đang chạy trên Prefix này.\nHệ thống đang dọn dẹp các tiến trình cũ để tránh lỗi...", timeout=4)
        
        # Kill the processes gracefully first with SIGTERM (15), then SIGKILL (9)
        for pid in prefix_processes:
            try:
                os.kill(pid, 15)
            except Exception:
                pass
                
        if prefix_processes:
            import time
            time.sleep(0.5)
            # Recheck and force kill if still alive
            for pid in prefix_processes:
                try:
                    os.kill(pid, 0) # Checks if process is alive
                    os.kill(pid, 9)
                except OSError:
                    pass
                except Exception:
                    pass
            time.sleep(0.5)
            return True
        return False

    @staticmethod
    def resolve_case_insensitive_path(path):
        """Resolves a case-insensitive path on a case-sensitive filesystem."""
        path = os.path.abspath(path)
        if os.path.exists(path):
            return path
            
        parts = path.split(os.sep)
        current = "/"
        if os.name == 'nt':
            current = parts[0] + os.sep
            parts = parts[1:]
        else:
            parts = parts[1:]
            
        for part in parts:
            if not part:
                continue
            found = False
            if os.path.isdir(current):
                for entry in os.listdir(current):
                    if entry.lower() == part.lower():
                        current = os.path.join(current, entry)
                        found = True
                        break
            if not found:
                current = os.path.join(current, part)
        return current

    @staticmethod
    def parse_lnk_file(lnk_path):
        """Parses a Windows .lnk file to extract the target path."""
        try:
            with open(lnk_path, "rb") as f:
                data = f.read()
                
            # ASCII search
            match_ascii = re.findall(rb'[A-Za-z]:\\[^\x00-\x1f"<>|]*\.exe', data, re.IGNORECASE)
            if match_ascii:
                return match_ascii[-1].decode('ascii', errors='ignore')
                
            # UTF-16 search
            data_utf16 = data.decode('utf-16-le', errors='ignore')
            match_utf16 = re.findall(r'[A-Za-z]:\\[^"<>\x00-\x1f]*\.exe', data_utf16, re.IGNORECASE)
            if match_utf16:
                return match_utf16[-1]
        except Exception as e:
            print(f"Error parsing .lnk: {e}")
        return None

    @staticmethod
    def find_lnk_files(prefix_dir):
        """Finds all .lnk files in the prefix desktop and start menu directories."""
        pfx = os.path.join(prefix_dir, "pfx")
        if not os.path.exists(pfx):
            return set()
            
        lnk_files = set()
        search_dirs = [
            os.path.join(pfx, "drive_c/users/Public/Desktop"),
            os.path.join(pfx, "drive_c/users/steamuser/Desktop"),
            os.path.join(pfx, "drive_c/users/Public/Start Menu"),
            os.path.join(pfx, "drive_c/users/steamuser/Start Menu"),
        ]
        
        for d in search_dirs:
            resolved_d = ProtonRunner.resolve_case_insensitive_path(d)
            if os.path.exists(resolved_d):
                for root, dirs, files in os.walk(resolved_d):
                    for f in files:
                        if f.lower().endswith(".lnk"):
                            lnk_files.add(os.path.join(root, f))
        return lnk_files

    @staticmethod
    def find_exe_files(prefix_dir):
        """Finds all .exe files in drive_c of the prefix (excluding windows system directory)."""
        drive_c = os.path.join(prefix_dir, "pfx", "drive_c")
        if not os.path.exists(drive_c):
            return set()
            
        exe_files = set()
        for root, dirs, files in os.walk(drive_c):
            # Case-insensitive removal of "windows" directory
            for d in list(dirs):
                if d.lower() == "windows":
                    dirs.remove(d)
            for f in files:
                if f.lower().endswith(".exe"):
                    exe_files.add(os.path.join(root, f))
        return exe_files

    @staticmethod
    def make_exec_line(prefix_dir, exe_path, proton="", mangohud=False, gamemode=False, wined3d=False, virtual_desktop="", unikey=False, taskbar=False):
        cmd = [f'"{MICRO_PROTON_BIN}"']
        if prefix_dir:
            cmd.extend(["--prefix", f'"{prefix_dir}"'])
        if proton:
            cmd.extend(["--proton", f'"{proton}"'])
        if mangohud:
            cmd.append("--mangohud")
        if gamemode:
            cmd.append("--gamemode")
        if wined3d:
            cmd.append("--wined3d")
        if virtual_desktop:
            cmd.extend(["--virtual-desktop", f'"{virtual_desktop}"'])
        if unikey:
            cmd.append("--unikey")
        if taskbar:
            cmd.append("--taskbar")
        cmd.append(f'"{exe_path}"')
        return " ".join(cmd)

    @classmethod
    def run_command(cls, proton_path, prefix_dir, exe_path, action="run", mangohud=False, gamemode=False, wined3d=False, virtual_desktop=None, unikey=False, taskbar=False):
        """Runs Proton or Wine with the specified action and environment."""
        os.makedirs(prefix_dir, exist_ok=True)
        
        # Try to raise file descriptor limit for Esync
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            if soft < 524288:
                target_soft = min(524288, hard)
                resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))
        except Exception as e:
            print(f"Không thể nâng giới hạn file descriptor cho Esync: {e}")
            
        # Prevent wineserver version mismatch error by automatically clean up if necessary
        target_wineserver = cls.get_target_wineserver_path(proton_path)
        cls.kill_processes_by_prefix(prefix_dir, wineserver_only_mismatch=target_wineserver)
        
        env = os.environ.copy()
        env["WINEPREFIX"] = prefix_dir
        env["NO_AT_BRIDGE"] = "1"
        env["GTK_A11Y"] = "none"
        
        # Enable Esync, Fsync, and graphics thread optimizations
        env["WINEESYNC"] = "1"
        env["WINEFSYNC"] = "1"
        env["__GL_THREADED_OPTIMIZATIONS"] = "1"
        env["mesa_glthread"] = "true"
        
        is_system_wine = False
        if proton_path:
            is_system_wine = "wine" in os.path.basename(proton_path).lower()

        if proton_path and not is_system_wine:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = STEAM_PATH
            env["STEAM_COMPAT_DATA_PATH"] = prefix_dir
            exe_hash = ProtonUtils.get_exe_hash(exe_path) if exe_path else ""
            if exe_hash:
                env["STEAM_COMPAT_APP_ID"] = str(int(exe_hash, 16) % 1000000)
            else:
                env["STEAM_COMPAT_APP_ID"] = "0"
            # Disable Xalia
            env["PROTON_USE_XALIA"] = "0"
        
        # Apply MangoHud
        if mangohud:
            env["MANGOHUD"] = "1"
            
        # Apply Wine3D
        if wined3d:
            env["PROTON_USE_WINED3D"] = "1"
        
        # Auto detect Vietnamese IME
        is_fcitx = False
        is_ibus = False
        xmods = os.environ.get("XMODIFIERS", "")
        if "fcitx" in xmods:
            is_fcitx = True
        elif "ibus" in xmods:
            is_ibus = True
        else:
            try:
                if subprocess.run(["pgrep", "-x", "fcitx5"], stdout=subprocess.DEVNULL).returncode == 0:
                    is_fcitx = True
                elif subprocess.run(["pgrep", "-x", "fcitx"], stdout=subprocess.DEVNULL).returncode == 0:
                    is_fcitx = True
                elif subprocess.run(["pgrep", "-x", "ibus-daemon"], stdout=subprocess.DEVNULL).returncode == 0:
                    is_ibus = True
            except Exception:
                pass
                
        if not is_fcitx and not is_ibus:
            is_fcitx = True
            
        if is_fcitx:
            env["XMODIFIERS"] = "@im=fcitx"
            env["GTK_IM_MODULE"] = "xim"
            env["QT_IM_MODULE"] = "xim"
            env["SDL_IM_MODULE"] = "fcitx"
        elif is_ibus:
            env["XMODIFIERS"] = "@im=ibus"
            env["GTK_IM_MODULE"] = "xim"
            env["QT_IM_MODULE"] = "xim"
            env["SDL_IM_MODULE"] = "ibus"
        
        p_wine = os.path.join(prefix_dir, "pfx")
        is_first_run = not os.path.exists(p_wine)
        
        if is_first_run:
            use_template = SettingsManager.get_settings().get("use_global_as_template", True)
            global_pfx = os.path.join(BASE_PREFIX_DIR, "global_default")
            global_pfx_wine = os.path.join(global_pfx, "pfx")
            if use_template and prefix_dir != global_pfx and os.path.exists(global_pfx_wine):
                cls.show_message("Đang đồng bộ cấu hình mặc định (winecfg/winetricks) từ global_default...\nVui lòng đợi giây lát!", timeout=5)
                try:
                    if os.path.exists(prefix_dir):
                        shutil.rmtree(prefix_dir)
                    shutil.copytree(global_pfx, prefix_dir, symlinks=True)
                    print(f"Copied global_default template to new sandbox prefix: {prefix_dir}")
                    is_first_run = False
                except Exception as e:
                    print(f"Lỗi khi sao chép cấu hình template global_default: {e}")
                    if os.path.exists(prefix_dir):
                        try:
                            shutil.rmtree(prefix_dir)
                        except Exception:
                            pass
            
            if is_first_run:
                cls.show_message("Đang tạo môi trường chạy (Prefix) lần đầu cho ứng dụng này.\nVui lòng đợi vài giây...", timeout=4)
            
        def run_wine_sub(args, background=False, custom_env=None):
            sub_env = custom_env if custom_env else env
            exec_bin = proton_path or "wine"
            is_sys_wine = is_system_wine or (not proton_path)
            if is_sys_wine:
                full_cmd = [exec_bin] + args
            else:
                full_cmd = [exec_bin, "run"] + args
                
            if gamemode and shutil.which("gamemoderun"):
                full_cmd = ["gamemoderun"] + full_cmd
                
            if background:
                return subprocess.Popen(full_cmd, env=sub_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                return subprocess.run(full_cmd, env=sub_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        reg_file_path = os.path.join(prefix_dir, "input_style.reg")
        if action == "run":
            try:
                with open(reg_file_path, "w") as f:
                    f.write("Windows Registry Editor Version 5.00\n\n")
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\X11 Driver]\n")
                    if unikey:
                        f.write('"InputStyle"="none"\n')
                    else:
                        f.write('"InputStyle"="overthespot"\n')
                run_wine_sub(["regedit", reg_file_path])
            except Exception as e:
                print(f"Lỗi thiết lập bộ gõ: {e}")
                
            if unikey:
                unikey_dir = os.path.join(prefix_dir, "pfx/drive_c/UniKey")
                unikey_exe = os.path.join(unikey_dir, "UniKeyNT.exe")
                if not os.path.exists(unikey_exe):
                    global_unikey = os.path.join(BASE_PREFIX_DIR, "global_default/pfx/drive_c/UniKey")
                    if os.path.exists(os.path.join(global_unikey, "UniKeyNT.exe")):
                        try:
                            shutil.copytree(global_unikey, unikey_dir, dirs_exist_ok=True)
                        except Exception as e:
                            print(f"Không thể sao chép UniKey từ global_default: {e}")
                
                if os.path.exists(unikey_exe):
                    run_wine_sub([unikey_exe], background=True)
                    
            if taskbar:
                taskbar_env = env.copy()
                if proton_path and not is_system_wine:
                    taskbar_env["PROTON_NO_PATH_TRANSLATION"] = "1"
                run_wine_sub(["explorer.exe", "/desktop=Default,1280x720", "explorer.exe"], background=True, custom_env=taskbar_env)
                
        reg_vd_path = os.path.join(prefix_dir, "virtual_desktop.reg")
        if virtual_desktop:
            try:
                with open(reg_vd_path, "w") as f:
                    f.write("Windows Registry Editor Version 5.00\n\n")
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer]\n")
                    f.write('"Desktop"="Default"\n\n')
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer\\Desktops]\n")
                    f.write(f'"Default"="{virtual_desktop}"\n')
                run_wine_sub(["regedit", reg_vd_path])
            except Exception as e:
                print(f"Lỗi cấu hình Virtual Desktop: {e}")
        else:
            if os.path.exists(p_wine):
                try:
                    with open(reg_vd_path, "w") as f:
                        f.write("Windows Registry Editor Version 5.00\n\n")
                        f.write("[HKEY_CURRENT_USER\\Software\\Wine\\Explorer]\n")
                        f.write('"Desktop"=-\n')
                    run_wine_sub(["regedit", reg_vd_path])
                except Exception as e:
                    print(f"Lỗi gỡ cấu hình Virtual Desktop: {e}")
                
        exec_bin = proton_path or "wine"
        is_sys_wine = is_system_wine or (not proton_path)
        
        if is_sys_wine:
            if action == "run":
                cmd = [exec_bin]
                if exe_path:
                    cmd.append(exe_path)
            elif action == "winecfg":
                winecfg_bin = shutil.which("winecfg") or "winecfg"
                cmd = [winecfg_bin]
            else:
                cmd = [exec_bin, action]
                if exe_path:
                    cmd.append(exe_path)
        else:
            if action in ["winecfg", "regedit"]:
                cmd = [exec_bin, "run", action]
            else:
                cmd = [exec_bin, action]
                if action == "run" and exe_path:
                    cmd.append(exe_path)
            
        if gamemode and shutil.which("gamemoderun"):
            cmd = ["gamemoderun"] + cmd
            
        try:
            subprocess.run(cmd, env=env)
        except Exception as e:
            if shutil.which("zenity"):
                subprocess.run(["zenity", "--error", f"--text=Lỗi khi chạy ứng dụng:\n{str(e)}", "--title=MicroProton Error"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    messagebox.showerror("MicroProton Error", f"Lỗi khi chạy ứng dụng:\n{str(e)}", parent=root)
                    root.destroy()
                except Exception:
                    print(f"[MicroProton Error] Lỗi khi chạy ứng dụng: {e}")

    @classmethod
    def main(cls):
        proton_list = ProtonUtils.find_proton_versions()
        if not proton_list:
            if shutil.which("zenity"):
                subprocess.run(["zenity", "--error", "--text=Không tìm thấy Proton hoặc Wine trên hệ thống.\nVui lòng cài đặt Steam Proton hoặc Wine.", "--title=Lỗi hệ thống"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    messagebox.showerror("Lỗi hệ thống", "Không tìm thấy Proton hoặc Wine trên hệ thống.\nVui lòng cài đặt Steam Proton hoặc Wine.", parent=root)
                    root.destroy()
                except Exception:
                    print("[Lỗi hệ thống] Không tìm thấy Proton hoặc Wine trên hệ thống. Vui lòng cài đặt Steam Proton hoặc Wine.")
            sys.exit(1)
            
        args = sys.argv[1:]
        
        custom_prefix = None
        if "--prefix" in args:
            try:
                idx = args.index("--prefix")
                if idx + 1 < len(args):
                    custom_prefix = args[idx + 1]
                    args.pop(idx + 1)
                    args.pop(idx)
            except ValueError:
                pass

        selected_proton_name = None
        if "--proton" in args:
            try:
                idx = args.index("--proton")
                if idx + 1 < len(args):
                    selected_proton_name = args[idx + 1]
                    args.pop(idx + 1)
                    args.pop(idx)
            except ValueError:
                pass

        global_default = SettingsManager.get_default_proton()
        
        proton_name = ""
        proton_path = ""
        search_default = selected_proton_name or global_default
        if search_default:
            for name, path in proton_list:
                if name == search_default or search_default in name:
                    proton_name = name
                    proton_path = path
                    break
                    
        if not proton_path:
            proton_name, proton_path = proton_list[0]
            if selected_proton_name:
                print(f"Không tìm thấy Proton phiên bản: {selected_proton_name}. Dùng mặc định: {proton_name}")

        mangohud = False
        if "--mangohud" in args:
            mangohud = True
            args.remove("--mangohud")

        gamemode = False
        if "--gamemode" in args:
            gamemode = True
            args.remove("--gamemode")

        wined3d = False
        if "--wined3d" in args:
            wined3d = True
            args.remove("--wined3d")

        unikey = False
        if "--unikey" in args:
            unikey = True
            args.remove("--unikey")

        taskbar = False
        if "--taskbar" in args:
            taskbar = True
            args.remove("--taskbar")

        app_display_name = None
        if "--name" in args:
            try:
                idx = args.index("--name")
                if idx + 1 < len(args):
                    app_display_name = args[idx + 1]
                    args.pop(idx + 1)
                    args.pop(idx)
            except ValueError:
                pass

        virtual_desktop = None
        if "--virtual-desktop" in args:
            try:
                idx = args.index("--virtual-desktop")
                if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    virtual_desktop = args[idx + 1]
                    args.pop(idx + 1)
                else:
                    virtual_desktop = "1280x720"
                args.pop(idx)
            except ValueError:
                pass

        action = "run"
        exe_path = None
        
        if not args:
            if unikey or taskbar:
                exe_path = None
            else:
                exe_path = ProtonUtils.select_file_via_zenity()
                if not exe_path:
                    sys.exit(0)
        else:
            if args[0] in ["--winecfg", "-c"]:
                action = "winecfg"
                if len(args) > 1:
                    exe_path = args[1]
            elif args[0] in ["--regedit", "-r"]:
                action = "regedit"
                if len(args) > 1:
                    exe_path = args[1]
            elif args[0] in ["--kill", "-k"]:
                action = "kill"
                if len(args) > 1:
                    exe_path = args[1]
            else:
                exe_path = args[0]
                
        if not exe_path or not os.path.exists(exe_path):
            if (action != "run" or unikey or taskbar) and not exe_path:
                prefix_dir = custom_prefix or os.path.join(BASE_PREFIX_DIR, "global_default")
                cls.run_command(proton_path, prefix_dir, None, action, mangohud, gamemode, wined3d, virtual_desktop, unikey, taskbar)
                sys.exit(0)
            subprocess.run(["zenity", "--error", f"--text=Đường dẫn tệp tin không hợp lệ hoặc không tồn tại:\n{exe_path}", "--title=Lỗi đường dẫn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            sys.exit(1)
            
        prefix_dir = custom_prefix or ProtonUtils.get_prefix_dir(exe_path)
        
        if action == "kill":
            cls.show_message("Đang tắt mọi tiến trình trong môi trường chạy này...", timeout=2)
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix_dir
            if proton_path:
                is_system_wine = "wine" in os.path.basename(proton_path).lower()
                if not is_system_wine:
                    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = STEAM_PATH
                    env["STEAM_COMPAT_DATA_PATH"] = prefix_dir
                    proton_dir = os.path.dirname(proton_path)
                    wineserver_path = os.path.join(proton_dir, "files/bin/wineserver")
                    try:
                        if os.path.exists(wineserver_path):
                            subprocess.run([wineserver_path, "-k"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            subprocess.run([proton_path, "run", "wineserver", "-k"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass

            cls.kill_processes_by_prefix(prefix_dir)
        else:
            old_links = set()
            old_exes = set()
            
            # Check if this executable is already registered (has a .desktop file)
            is_registered = False
            if exe_path:
                orig_exe_hash = hashlib.md5(os.path.abspath(exe_path).encode('utf-8')).hexdigest()[:8]
                desktop_filename = f"micro-proton-app-{orig_exe_hash}.desktop"
                desktop_path = os.path.join(APPLICATIONS_DIR, desktop_filename)
                if os.path.exists(desktop_path):
                    is_registered = True

            should_detect_install = (action == "run" and exe_path and exe_path.lower().endswith(".exe") and not is_registered)
            
            if should_detect_install:
                old_links = cls.find_lnk_files(prefix_dir)
                old_exes = cls.find_exe_files(prefix_dir)
                
            cls.run_command(proton_path, prefix_dir, exe_path, action, mangohud, gamemode, wined3d, virtual_desktop, unikey, taskbar)
            
            if should_detect_install:
                import time
                # Smart wait for installer/processes to finish
                # We wait as long as there are active processes in the prefix that are NOT standard system services
                standard_services = {"wineserver", "explorer.exe", "winedevice.exe", "plugplay.exe", "rpcss.exe", "services.exe", "svchost.exe", "wineboot.exe", "unikeynt.exe", "conhost.exe"}
                
                timeout_seconds = 600  # 10 minutes max timeout
                start_time = time.time()
                
                while time.time() - start_time < timeout_seconds:
                    # Scan active processes in this prefix
                    my_uid = os.getuid()
                    active_installer_procs = []
                    
                    target_pfx = os.path.abspath(prefix_dir)
                    target_pfx_pfx = os.path.abspath(os.path.join(prefix_dir, "pfx"))
                    
                    for pid_dir in glob.glob("/proc/[0-9]*"):
                        pid = os.path.basename(pid_dir)
                        try:
                            stat_info = os.stat(pid_dir)
                            if stat_info.st_uid != my_uid:
                                continue
                            
                            # Check WINEPREFIX
                            environ_path = os.path.join(pid_dir, "environ")
                            if not os.path.exists(environ_path):
                                continue
                            
                            with open(environ_path, "rb") as f:
                                env_data = f.read()
                            env_list = env_data.decode("utf-8", errors="ignore").split("\x00")
                            belongs = False
                            for item in env_list:
                                if item.startswith("WINEPREFIX="):
                                    wp = os.path.abspath(item.split("=", 1)[1])
                                    if wp == target_pfx or wp == target_pfx_pfx:
                                        belongs = True
                                        break
                            
                            if belongs:
                                # Get process name from cmdline
                                cmdline_path = os.path.join(pid_dir, "cmdline")
                                if os.path.exists(cmdline_path):
                                    with open(cmdline_path, "rb") as f:
                                        cmd_data = f.read()
                                    cmd_str = cmd_data.decode("utf-8", errors="ignore").replace("\x00", " ")
                                    proc_args = cmd_str.split()
                                    proc_name = os.path.basename(proc_args[0]).lower() if proc_args else ""
                                    if proc_name and proc_name not in standard_services:
                                        active_installer_procs.append(proc_name)
                        except Exception:
                            continue
                    
                    if not active_installer_procs:
                        break
                    
                    print(f"Đang đợi bộ cài đặt hoàn tất. Tiến trình còn chạy: {active_installer_procs}")
                    time.sleep(3)
                    
                time.sleep(2.0)
                
                new_links = cls.find_lnk_files(prefix_dir)
                new_links_added = new_links - old_links
                
                target_installed_exe = None
                app_name = None
                
                if new_links_added:
                    valid_links = [l for l in new_links_added if "uninst" not in l.lower() and "uninstall" not in l.lower()]
                    if valid_links:
                        lnk_to_use = valid_links[0]
                        win_target = cls.parse_lnk_file(lnk_to_use)
                        if win_target:
                            rel_target = win_target.replace("\\", "/")
                            if rel_target.upper().startswith("C:"):
                                rel_target = "pfx/drive_c" + rel_target[2:]
                            linux_target = os.path.join(prefix_dir, rel_target)
                            linux_target = cls.resolve_case_insensitive_path(linux_target)
                            if os.path.exists(linux_target):
                                target_installed_exe = linux_target
                                app_name = os.path.splitext(os.path.basename(lnk_to_use))[0]
                
                if not target_installed_exe:
                    new_exes = cls.find_exe_files(prefix_dir)
                    new_exes_added = new_exes - old_exes
                    if new_exes_added:
                        valid_exes = [e for e in new_exes_added if "uninst" not in e.lower() and "uninstall" not in e.lower()]
                        if valid_exes:
                            valid_exes.sort(key=lambda x: os.path.getsize(x), reverse=True)
                            target_installed_exe = valid_exes[0]
                            app_name = os.path.splitext(os.path.basename(target_installed_exe))[0]
                            app_name = app_name.replace("_", " ").replace("-", " ").title()
                            
                if target_installed_exe and app_name and os.path.abspath(target_installed_exe) != os.path.abspath(exe_path):
                    print(f"Phát hiện ứng dụng đã cài đặt: {app_name} -> {target_installed_exe}")
                    
                    final_app_name = app_display_name or app_name
                    orig_exe_hash = hashlib.md5(os.path.abspath(exe_path).encode('utf-8')).hexdigest()[:8]
                    icon_path = ProtonUtils.extract_app_icon(target_installed_exe, orig_exe_hash)
                    
                    desktop_filename = f"micro-proton-app-{orig_exe_hash}.desktop"
                    desktop_path = os.path.join(APPLICATIONS_DIR, desktop_filename)
                    
                    exec_line = cls.make_exec_line(
                        prefix_dir=prefix_dir, 
                        exe_path=target_installed_exe,
                        proton=selected_proton_name or "",
                        mangohud=mangohud,
                        gamemode=gamemode,
                        wined3d=wined3d,
                        virtual_desktop=virtual_desktop or "",
                        unikey=unikey,
                        taskbar=taskbar
                    )
                    
                    content = f"""[Desktop Entry]
Name={final_app_name}
Exec={exec_line}
Icon={icon_path}
Terminal=false
Type=Application
Categories=Game;Emulator;Utility;
MimeType=application/x-ms-dos-executable;
Comment=Chạy bằng MicroProton
X-MicroProton-Exe={target_installed_exe}
"""
                    try:
                        with open(desktop_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        subprocess.run(["update-desktop-database", APPLICATIONS_DIR])
                        cls.show_message(f"Đã phát hiện và cấu hình tự động cho ứng dụng:\nTên: {final_app_name}\nFile chạy: {os.path.basename(target_installed_exe)}", timeout=5)
                    except Exception as e:
                        print(f"Lỗi ghi file .desktop: {e}")
                else:
                    subprocess.run([
                        "zenity", "--info", 
                        "--title=Không tìm thấy ứng dụng mới", 
                        "--text=Không tìm thấy tệp tin khởi chạy mới nào được tạo ra sau khi cài đặt.\n\nNếu phần mềm đã cài đặt thành công, bạn hãy dùng tính năng 'Đã cài (nhập từ ổ C: ảo)' để chọn file chạy thủ công."
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
