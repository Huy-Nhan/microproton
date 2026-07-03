# MicroProton - Trình quản lý chạy ứng dụng Windows trên Linux tối ưu

**MicroProton** là một bộ công cụ gọn nhẹ viết bằng Python giúp người dùng Linux (đặc biệt là người dùng chuyển giao từ Windows) dễ dàng khởi chạy, cấu hình và quản lý các phần mềm/game Windows `.exe` thông qua lớp tương thích **Steam Play Proton** hoặc **Wine hệ thống**.

Dự án được tối ưu hóa đặc biệt cho người dùng Việt Nam với tính năng tích hợp bộ gõ tiếng Việt UniKey và cơ chế đóng gói hộp cát (Sandbox) tự động.

---

## 🚀 Các tính năng nổi bật

1. **Tự động quét phiên bản Proton & Wine:**
   - Quét tìm tất cả các bản Proton được cài đặt bởi Steam (bao gồm Proton GE, Experimental, stable).
   - Tự động phát hiện và thêm bản **System Wine** làm phương án dự phòng khi hệ thống chưa cài đặt Steam.
2. **Giao diện Quản lý Trực quan (`micro-proton-manager`):**
   - Thêm, sửa, xóa phím tắt ứng dụng Windows vào Menu hệ thống Linux cực kỳ nhanh chóng.
   - Cho phép tinh chỉnh nhanh các tính năng tối ưu: bật/tắt MangoHud (hiển thị FPS), Feral GameMode (tối ưu CPU), Wine3D (sử dụng OpenGL thay cho Vulkan cho GPU cũ).
3. **Môi trường ảo Sandbox riêng biệt:**
   - Tự động cô lập mỗi ứng dụng Windows vào một thư mục Prefix riêng (`prefix_<hash>`) để tránh lỗi xung đột thư viện giữa các phần mềm.
   - Có tùy chọn dùng chung môi trường ảo mặc định (`global_default`) khi thêm ứng dụng.
4. **Hỗ trợ gõ tiếng Việt hoàn hảo:**
   - Tự động thay đổi giá trị Registry (`InputStyle = none`) để bộ gõ Linux (Fcitx, IBus với Bamboo/UniKey) gửi phím trực tiếp vào Wine mà không bị mất chữ hay crash.
   - Tùy chọn `--unikey` tự động tải và chạy ngầm bản Windows `UniKeyNT.exe` bên trong môi trường ảo của ứng dụng.
5. **Tránh lỗi phân giải màn hình với Màn hình ảo (Virtual Desktop):**
   - Chạy các trò chơi hoặc ứng dụng Windows cũ trong chế độ màn hình ảo của Wine Explorer để tránh làm đảo lộn độ phân giải của màn hình chính Linux.
6. **Trích xuất Biểu tượng (Icon) thông minh:**
   - Tự động bóc tách icon gốc của file `.exe` bằng thư viện `icoextract` hoặc công cụ `wrestool` (icoutils).
   - Chuyển đổi file `.ico` sang `.png` bằng ImageMagick hoặc Python Pillow (PIL) để hiển thị mượt mà trên Dock/Menu của Linux.
7. **Khay hệ thống Tiện ích (`micro-proton-indicator`):**
   - Hiển thị tài nguyên RAM, CPU thời gian thực của các phần mềm Windows đang chạy.
   - Hỗ trợ phím nóng đóng nhanh ứng dụng bị treo (`wineserver -k`), mở nhanh giao diện cấu hình `winecfg` hay `regedit`.

---

## 📦 Yêu cầu hệ thống & Cài đặt

### Các gói phụ thuộc cơ bản (Dependencies)

Để chạy đầy đủ giao diện và tính năng bóc tách icon, hệ thống của bạn cần cài đặt các gói sau:

**Trên Debian / Ubuntu / Linux Mint:**
```bash
sudo apt install python3 python3-tk python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 zenity icoutils python3-pil
```

**Trên Fedora:**
```bash
sudo dnf install python3 python3-tkinter python3-gobject gtk3 zenity icoutils python3-pillow
```

---

## 🛠️ Hướng dẫn cài đặt gói đóng sẵn

Bộ dự án đi kèm công cụ tự động đóng gói sang dạng cài đặt `.deb` (cho Ubuntu/Debian) hoặc `.rpm` (cho Fedora).

### Bước 1: Build gói cài đặt
Di chuyển vào thư mục dự án và chạy:
```bash
./build_packages.sh
```
Sau khi hoàn thành, tệp cài đặt `.deb` sẽ được tạo trong thư mục `build/`.

### Bước 2: Cài đặt vào hệ thống
**Với Debian/Ubuntu:**
```bash
sudo apt install ./build/micro-proton_1.0.0_all.deb
```

---

## 📖 Hướng dẫn sử dụng

### 1. Sử dụng Giao diện Manager (`micro-proton-manager`)
Mở Menu ứng dụng Linux của bạn và tìm **Micro Proton Manager**, hoặc chạy lệnh sau từ Terminal:
```bash
micro-proton-manager
```
Từ đây, bạn có thể:
* Nhấn **Thêm ứng dụng mới** -> Chọn file `.exe` -> Đặt tên ứng dụng -> Nhấn Lưu để tạo shortcut trên Linux.
* Chọn ứng dụng trong danh sách để tùy chỉnh: bật/tắt bộ gõ tiếng Việt, màn hình ảo, hoặc mở trình quản lý thư viện **Winetricks** riêng cho ứng dụng đó.

### 2. Sử dụng Khay hệ thống (`micro-proton-indicator`)
Khởi động khay hệ thống để theo dõi các ứng dụng đang chạy:
```bash
micro-proton-indicator
```
Biểu tượng của MicroProton sẽ xuất hiện trên khay hệ thống, cung cấp các thao tác tắt khẩn cấp ứng dụng Windows khi bị treo.

### 3. Sử dụng qua dòng lệnh (CLI - `micro-proton`)
Bạn cũng có thể chạy trực tiếp một file `.exe` bằng lệnh:
```bash
micro-proton "/đường-dẫn/đến/file-của-bạn.exe"
```
**Các cờ tham số bổ sung:**
* `--prefix "đường-dẫn"`: Chỉ định thư mục chứa môi trường ảo Wine.
* `--proton "tên-proton"`: Chọn phiên bản Proton cụ thể.
* `--unikey`: Khởi động UniKey cùng ứng dụng.
* `--virtual-desktop "1280x720"`: Khởi động trong màn hình ảo.
* `--wined3d`: Sử dụng chế độ dựng hình OpenGL.

---

## 📄 Giấy phép (License)

Dự án được phân phối dưới giấy phép **MIT**. Xem chi tiết tại tệp [LICENSE](LICENSE).
