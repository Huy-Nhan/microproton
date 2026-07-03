import os
import re
import shutil
import hashlib
import subprocess
from tkinter import filedialog

class ProtonUtils:
    APPLICATIONS_DIR = os.path.expanduser("~/.local/share/applications")
    PREFIXES_DIR = os.path.expanduser("~/.local/share/micro-proton/prefixes")
    STEAM_PATH = os.path.expanduser("~/.local/share/Steam")
    STEAM_COMMON = os.path.join(STEAM_PATH, "steamapps/common")

    @staticmethod
    def get_exe_hash(exe_path):
        abs_path = os.path.abspath(exe_path)
        return hashlib.md5(abs_path.encode('utf-8')).hexdigest()[:8]

    @classmethod
    def get_prefix_dir(cls, exe_path):
        """Returns the shared global Proton Prefix directory or a per-app directory."""
        if exe_path:
            return os.path.join(cls.PREFIXES_DIR, f"prefix_{cls.get_exe_hash(exe_path)}")
        return os.path.join(cls.PREFIXES_DIR, "global_default")

    @classmethod
    def find_proton_versions(cls):
        """Finds all installed Proton versions in Steam directories (including Flatpak) and fallback to system wine."""
        versions = []
        
        # Define search directories for system and Flatpak Steam
        search_sources = [
            (cls.STEAM_COMMON, os.path.join(cls.STEAM_PATH, "compatibilitytools.d"))
        ]
        flatpak_steam_path = os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam")
        if os.path.exists(flatpak_steam_path):
            search_sources.append((
                os.path.join(flatpak_steam_path, "steamapps/common"),
                os.path.join(flatpak_steam_path, "compatibilitytools.d")
            ))
        
        for common_dir, compat_dir in search_sources:
            # 1. Scan steamapps/common
            if os.path.exists(common_dir):
                for item in os.listdir(common_dir):
                    if item.startswith("Proton") and os.path.isdir(os.path.join(common_dir, item)):
                        proton_script = os.path.join(common_dir, item, "proton")
                        if os.path.exists(proton_script):
                            versions.append((f"{item} (Flatpak)" if "com.valvesoftware.Steam" in common_dir else item, proton_script))
                            
            # 2. Scan compatibilitytools.d (custom Protons like Proton-GE)
            if os.path.exists(compat_dir):
                for item in os.listdir(compat_dir):
                    item_path = os.path.join(compat_dir, item)
                    if os.path.isdir(item_path):
                        proton_script = os.path.join(item_path, "proton")
                        if os.path.exists(proton_script):
                            versions.append((f"{item} (Flatpak)" if "com.valvesoftware.Steam" in compat_dir else item, proton_script))
                            
        # 3. Fallback to system wine
        wine_path = shutil.which("wine")
        if wine_path:
            versions.append(("System Wine (Fallback)", wine_path))
            
        # Deduplicate by script path
        seen_paths = set()
        unique_versions = []
        for name, path in versions:
            if path not in seen_paths:
                seen_paths.add(path)
                unique_versions.append((name, path))
                
        # Sort: Proton/GE-Proton 10.x first, then 9.x, then Experimental, then System Wine
        def sort_key(v):
            name = v[0]
            if "System Wine" in name:
                return -1.0
            if "Experimental" in name:
                return 999.0
            numbers = re.findall(r"\d+", name)
            if numbers:
                if len(numbers) >= 2:
                    return float(f"{numbers[0]}.{numbers[1].zfill(3)}")
                return float(numbers[0])
            return 0.0
            
        unique_versions.sort(key=sort_key, reverse=True)
        return unique_versions

    @staticmethod
    def extract_app_icon(exe_path, app_hash):
        """Extracts icon from exe using icoextract (or wrestool) and converts to PNG if possible."""
        icon_dir = os.path.expanduser("~/.local/share/icons")
        os.makedirs(icon_dir, exist_ok=True)
        
        ico_output = os.path.join(icon_dir, f"micro-proton-app-{app_hash}.ico")
        png_output = os.path.join(icon_dir, f"micro-proton-app-{app_hash}.png")
        
        try:
            from icoextract import IconExtractor
            extractor = IconExtractor(exe_path)
            extractor.export_icon(ico_output)
            
            # Use Pillow to convert to PNG
            try:
                from PIL import Image
                with Image.open(ico_output) as img:
                    best_size = (0, 0)
                    best_frame = 0
                    try:
                        n_frames = getattr(img, "n_frames", 1)
                        for i in range(n_frames):
                            img.seek(i)
                            if img.size[0] > best_size[0]:
                                best_size = img.size
                                best_frame = i
                    except Exception:
                        pass
                    img.seek(best_frame)
                    png_img = img.convert("RGBA")
                    png_img.save(png_output, "PNG")
                if os.path.exists(png_output):
                    try:
                        os.remove(ico_output)
                    except Exception:
                        pass
                    return png_output
            except Exception:
                if shutil.which("convert"):
                    subprocess.run(["convert", ico_output, png_output], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(png_output):
                        try:
                            os.remove(ico_output)
                        except Exception:
                            pass
                        return png_output
            return ico_output
        except Exception:
            # Fallback to wrestool (from icoutils) if icoextract is not available
            if shutil.which("wrestool") and shutil.which("icotool"):
                try:
                    subprocess.run(
                        ["wrestool", "-x", "-t", "14", exe_path, "-o", ico_output],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    if os.path.exists(ico_output) and os.path.getsize(ico_output) > 0:
                        # Try PIL conversion first on the extracted .ico
                        try:
                            from PIL import Image
                            with Image.open(ico_output) as img:
                                best_size = (0, 0)
                                best_frame = 0
                                try:
                                    n_frames = getattr(img, "n_frames", 1)
                                    for i in range(n_frames):
                                        img.seek(i)
                                        if img.size[0] > best_size[0]:
                                            best_size = img.size
                                            best_frame = i
                                except Exception:
                                    pass
                                img.seek(best_frame)
                                png_img = img.convert("RGBA")
                                png_img.save(png_output, "PNG")
                            if os.path.exists(png_output):
                                try:
                                    os.remove(ico_output)
                                except Exception:
                                    pass
                                return png_output
                        except Exception:
                            pass
                            
                        # Fallback to icotool command
                        subprocess.run(["icotool", "-x", "-o", icon_dir, ico_output], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        # Find the largest extracted icon file (wrestool names them with suffixes)
                        basename = f"micro-proton-app-{app_hash}"
                        extracted_files = [f for f in os.listdir(icon_dir) if f.startswith(basename) and f.endswith(".png")]
                        if extracted_files:
                            extracted_files.sort(key=lambda x: os.path.getsize(os.path.join(icon_dir, x)), reverse=True)
                            largest_png = os.path.join(icon_dir, extracted_files[0])
                            
                            # Clean up other sizes
                            for f in extracted_files[1:]:
                                try:
                                    os.remove(os.path.join(icon_dir, f))
                                except Exception:
                                    pass
                            try:
                                os.remove(ico_output)
                            except Exception:
                                pass
                            return largest_png
                except Exception:
                    pass
        return "com.valvesoftware.Steam"

    @staticmethod
    def select_file_via_zenity(title="Chọn file Windows (.exe)", initialdir=None, parent=None):
        import shutil
        if shutil.which("zenity"):
            cmd = ["zenity", "--file-selection", f"--title={title}"]
            if initialdir:
                if not initialdir.endswith(os.sep):
                    initialdir += os.sep
                cmd.append(f"--filename={initialdir}")
            cmd.append('--file-filter=Windows Executable (*.exe) | *.exe')
            cmd.append('--file-filter=All files | *')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    path = res.stdout.strip()
                    return path if path else None
                return None
            except Exception:
                pass

        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=parent,
            title=title,
            initialdir=initialdir,
            filetypes=[("Windows Executable", "*.exe"), ("All files", "*.*")]
        )
        return path if path else None

    @staticmethod
    def select_image_via_zenity(title="Chọn hình ảnh làm Icon", initialdir=None, parent=None):
        import shutil
        if shutil.which("zenity"):
            cmd = ["zenity", "--file-selection", f"--title={title}"]
            if initialdir:
                if not initialdir.endswith(os.sep):
                    initialdir += os.sep
                cmd.append(f"--filename={initialdir}")
            cmd.append('--file-filter=Image files | *.png *.jpg *.jpeg *.svg')
            cmd.append('--file-filter=All files | *')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    path = res.stdout.strip()
                    return path if path else None
                return None
            except Exception:
                pass

        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=parent,
            title=title,
            initialdir=initialdir,
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.svg"), ("All files", "*.*")]
        )
        return path if path else None

    @staticmethod
    def select_save_file_via_zenity(title="Lưu tệp", initialfile=None, parent=None):
        import shutil
        if shutil.which("zenity"):
            cmd = ["zenity", "--file-selection", "--save", f"--title={title}"]
            if initialfile:
                cmd.append(f"--filename={initialfile}")
            cmd.append('--file-filter=Zip Archive (*.zip) | *.zip')
            cmd.append('--file-filter=All files | *')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    path = res.stdout.strip()
                    return path if path else None
                return None
            except Exception:
                pass

        from tkinter import filedialog
        initialdir = os.path.dirname(initialfile) if initialfile else None
        filename = os.path.basename(initialfile) if initialfile else None
        path = filedialog.asksaveasfilename(
            parent=parent,
            title=title,
            initialdir=initialdir,
            initialfile=filename,
            filetypes=[("Zip Archive", "*.zip"), ("All files", "*.*")]
        )
        return path if path else None

    @staticmethod
    def select_zip_file_via_zenity(title="Chọn tệp .zip", parent=None):
        import shutil
        if shutil.which("zenity"):
            cmd = ["zenity", "--file-selection", f"--title={title}"]
            cmd.append('--file-filter=Zip Archive (*.zip) | *.zip')
            cmd.append('--file-filter=All files | *')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    path = res.stdout.strip()
                    return path if path else None
                return None
            except Exception:
                pass

        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=parent,
            title=title,
            filetypes=[("Zip Archive", "*.zip"), ("All files", "*.*")]
        )
        return path if path else None

    @staticmethod
    def get_screen_resolution():
        """Detects the screen resolution and returns a suited size (85% of display)."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            root.destroy()
            if sw > 200 and sh > 200:
                w = int(sw * 0.85) // 2 * 2
                h = int(sh * 0.85) // 2 * 2
                return f"{w}x{h}"
        except Exception:
            pass
        return "1280x720"
