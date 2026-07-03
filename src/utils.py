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
        """Finds all installed Proton versions in Steam directories and fallback to system wine."""
        versions = []
        
        # 1. Scan steamapps/common
        if os.path.exists(cls.STEAM_COMMON):
            for item in os.listdir(cls.STEAM_COMMON):
                if item.startswith("Proton") and os.path.isdir(os.path.join(cls.STEAM_COMMON, item)):
                    proton_script = os.path.join(cls.STEAM_COMMON, item, "proton")
                    if os.path.exists(proton_script):
                        versions.append((item, proton_script))
                        
        # 2. Scan compatibilitytools.d (custom Protons like Proton-GE)
        compat_dir = os.path.join(cls.STEAM_PATH, "compatibilitytools.d")
        if os.path.exists(compat_dir):
            for item in os.listdir(compat_dir):
                item_path = os.path.join(compat_dir, item)
                if os.path.isdir(item_path):
                    proton_script = os.path.join(item_path, "proton")
                    if os.path.exists(proton_script):
                        versions.append((item, proton_script))
                        
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
    def select_file_via_zenity(title="Chọn file Windows (.exe)", initialdir=None):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", f"--title={title}", "--file-filter=Executable files (*.exe) | *.exe"]
                if initialdir and os.path.exists(initialdir):
                    cmd.append(f"--filename={initialdir}/")
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return res.stdout.strip()
            except subprocess.CalledProcessError:
                return None
        return filedialog.askopenfilename(
            title=title,
            initialdir=initialdir,
            filetypes=[("Windows Executable", "*.exe"), ("All files", "*.*")]
        )

    @staticmethod
    def select_image_via_zenity(title="Chọn hình ảnh làm Icon", initialdir=None):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", f"--title={title}", "--file-filter=Image files (*.png *.jpg *.jpeg *.svg) | *.png *.jpg *.jpeg *.svg"]
                if initialdir and os.path.exists(initialdir):
                    cmd.append(f"--filename={initialdir}/")
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return res.stdout.strip()
            except subprocess.CalledProcessError:
                return None
        return filedialog.askopenfilename(
            title=title,
            initialdir=initialdir,
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.svg"), ("All files", "*.*")]
        )

    @staticmethod
    def select_save_file_via_zenity(title="Lưu tệp", initialfile=None):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", "--save", f"--title={title}", "--confirm-overwrite"]
                if initialfile:
                    cmd.append(f"--filename={initialfile}")
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return res.stdout.strip()
            except subprocess.CalledProcessError:
                return None
        return filedialog.asksaveasfilename(
            title=title,
            initialfile=initialfile,
            filetypes=[("Zip Archive", "*.zip"), ("All files", "*.*")]
        )

    @staticmethod
    def select_zip_file_via_zenity(title="Chọn tệp .zip"):
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", f"--title={title}", "--file-filter=Zip archives (*.zip) | *.zip"]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return res.stdout.strip()
            except subprocess.CalledProcessError:
                return None
        return filedialog.askopenfilename(
            title=title,
            filetypes=[("Zip Archive", "*.zip"), ("All files", "*.*")]
        )
