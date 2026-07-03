# 🛡️ MicroProton - Chạy ứng dụng Windows trên Linux dễ dàng nhất

**MicroProton** là công cụ gọn nhẹ giúp bạn chạy các phần mềm (`.exe`) và game Windows trên Linux thông qua **Steam Proton** hoặc **Wine**. Công cụ được tối ưu hóa đặc biệt cho người dùng Việt Nam với khả năng gõ tiếng Việt mượt mà (hỗ trợ UniKey) và cơ chế đóng gói hộp cát (Sandbox) tự động.

---

## ✨ Tính năng nổi bật

*   **Tự động quét Proton/Wine:** Phát hiện toàn bộ các phiên bản Steam Proton, Proton-GE và Wine trên hệ thống.
*   **Đăng ký Shortcut tiện lợi:** Tạo lối tắt phần mềm Windows hiển thị trực tiếp trên App Menu của Linux.
*   **Sandbox độc lập:** Mỗi ứng dụng có thể chạy trong một phân vùng ảo (WINEPREFIX) riêng biệt để tránh lỗi xung đột.
*   **Hỗ trợ gõ Tiếng Việt Telex/VNI:** Tích hợp sẵn bộ gõ UniKey trong môi trường ảo, tự động sửa lỗi mất chữ, mất ký tự khi gõ trên Linux.
*   **Trích xuất Icon thông minh:** Tự động lấy icon từ file `.exe` để làm ảnh đại diện cho Shortcut trên Linux.
*   **Giám sát Hệ thống:** Khay hệ thống hiển thị thời gian thực mức sử dụng CPU/RAM và hỗ trợ tắt nhanh (Kill) ứng dụng bị treo.

---

## 📦 Hướng dẫn Cài đặt nhanh

### 1. Cài đặt các gói phụ thuộc (Dependencies)

Mở Terminal và chạy lệnh tương ứng với hệ điều hành của bạn:

**Trên Fedora:**
```bash
sudo dnf install python3 python3-tkinter python3-gobject gtk3 zenity icoutils python3-pillow
```

**Trên Debian / Ubuntu / Linux Mint:**
```bash
sudo apt install python3 python3-tk python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 zenity icoutils python3-pil
```

### 2. Đóng gói & Cài đặt phần mềm

Di chuyển vào thư mục dự án và chạy kịch bản tự động đóng gói:

```bash
# Build gói cài đặt (.deb hoặc .rpm)
./build_packages.sh

# Cài đặt (Ví dụ trên Debian/Ubuntu)
sudo apt install ./build/micro-proton_1.0.0_all.deb
```

---

## 📖 Hướng dẫn Sử dụng

### 1. Quản lý qua giao diện (MicroProton Manager)
Mở ứng dụng **MicroProton Manager** từ App Menu của bạn hoặc gõ lệnh:
```bash
micro-proton-manager
```
*   Nhấp **`+ Đăng ký ứng dụng`** ở góc trái để thêm phần mềm mới.
*   Chọn ứng dụng trong danh sách để bật/tắt: *MangoHud (Hiển thị FPS), Feral GameMode (Tối ưu hiệu năng), Virtual Desktop (Khung giả lập), UniKey (Bộ gõ tiếng Việt)*.
*   Sử dụng nút **`Winecfg`** hoặc **`Winetricks`** ở phần **Cấu hình** (Settings) để tùy chỉnh các thư viện hệ thống cần thiết.

> [!TIP]
> Bạn có thể bật tùy chọn **"Sao chép Winecfg/Winetricks mặc định cho Sandbox mới"** trong phần Cấu hình. Khi bạn tạo Sandbox mới cho ứng dụng, nó sẽ tự động kế thừa toàn bộ thư viện và phông chữ đã cài đặt ở môi trường mặc định (`global_default`).

### 2. Sử dụng qua dòng lệnh (CLI)
Để khởi chạy nhanh một tệp `.exe` bằng lệnh:
```bash
micro-proton "/đường-dẫn/đến/phần-mềm.exe"
```
*   **Các tham số tùy chọn:**
    *   `--prefix "đường-dẫn"`: Chỉ định thư mục Sandbox chứa môi trường ảo.
    *   `--proton "tên-proton"`: Chọn phiên bản Proton để chạy.
    *   `--unikey`: Khởi động kèm bộ gõ UniKey.
    *   `--virtual-desktop "1280x720"`: Thực thi trong màn hình ảo riêng.

### 3. Khay hệ thống (Indicator)
Khởi chạy khay hệ thống để theo dõi và quản lý các tiến trình Windows đang chạy:
```bash
micro-proton-indicator
```
Bạn có thể mở nhanh **Virtual Desktop**, chạy **UniKey** hoặc **Kill All Processes** (Tắt toàn bộ tiến trình) ngay trên khay hệ thống khi ứng dụng bị đóng băng (treo).

---

## 📄 Giấy phép (License)
Dự án được phân phối dưới giấy phép mã nguồn mở **MIT**. Xem chi tiết tại tệp [LICENSE](LICENSE).
