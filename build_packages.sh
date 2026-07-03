#!/usr/bin/env bash
set -e

# Define version
VERSION="1.0.0"
PACKAGE_NAME="micro-proton"
BUILD_DIR="build_pkg"

echo "=== Building Debian/Ubuntu package (.deb) for ${PACKAGE_NAME} v${VERSION} ==="

# Clean previous build directories
rm -rf "${BUILD_DIR}"
mkdir -p build
rm -f "build/${PACKAGE_NAME}_${VERSION}_all.deb"

# Create directories
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/micro-proton/src"
mkdir -p "${BUILD_DIR}/usr/share/micro-proton/images"
mkdir -p "${BUILD_DIR}/usr/share/pixmaps"

# Copy executables and libraries
cp micro-proton "${BUILD_DIR}/usr/bin/micro-proton"
cp micro-proton-indicator "${BUILD_DIR}/usr/bin/micro-proton-indicator"
cp micro-proton-manager "${BUILD_DIR}/usr/bin/micro-proton-manager"
cp -r src/* "${BUILD_DIR}/usr/share/micro-proton/src/"
cp -r images/* "${BUILD_DIR}/usr/share/micro-proton/images/"
cp images/logo.png "${BUILD_DIR}/usr/share/pixmaps/micro-proton.png"

# Make sure they are executable
chmod 755 "${BUILD_DIR}/usr/bin/micro-proton"
chmod 755 "${BUILD_DIR}/usr/bin/micro-proton-indicator"
chmod 755 "${BUILD_DIR}/usr/bin/micro-proton-manager"

# Create .desktop files
cat << 'EOF' > "${BUILD_DIR}/usr/share/applications/micro-proton-manager.desktop"
[Desktop Entry]
Name=Micro Proton Manager
Comment=Manage Windows applications running under Proton
Exec=micro-proton-manager
Icon=micro-proton
Terminal=false
Type=Application
Categories=Game;Utility;
EOF

cat << 'EOF' > "${BUILD_DIR}/usr/share/applications/micro-proton-indicator.desktop"
[Desktop Entry]
Name=Micro Proton Indicator
Comment=System Tray Indicator for Micro Proton
Exec=micro-proton-indicator
Icon=micro-proton
Terminal=false
Type=Application
Categories=Game;Utility;
EOF

# Create DEBIAN/control file
cat << EOF > "${BUILD_DIR}/DEBIAN/control"
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, python3-tk, gir1.2-gtk-3.0, gir1.2-appindicator3-0.1 | gir1.2-ayatanaappindicator3-0.1, zenity
Maintainer: Ryando <ryando@example.com>
Description: Lightweight Proton Prefix Manager for Steam Play games.
 Micro Proton allows running Windows executables (.exe) under Steam's Proton
 compatibility layer, managing prefixes, and running them with options like
 MangoHud, GameMode, and taskbar integration.
EOF

# Build Debian package
dpkg-deb --build "${BUILD_DIR}" "build/${PACKAGE_NAME}_${VERSION}_all.deb"
echo "✅ Debian/Ubuntu package created: build/${PACKAGE_NAME}_${VERSION}_all.deb"

# Clean up build directory
rm -rf "${BUILD_DIR}"

# Build RPM using alien if installed
echo ""
echo "=== Building Fedora package (.rpm) ==="
if command -v alien &> /dev/null; then
    echo "Converting .deb to .rpm using 'alien'..."
    sudo alien --to-rpm "build/${PACKAGE_NAME}_${VERSION}_all.deb"
    mv "${PACKAGE_NAME}-"*.rpm build/ 2>/dev/null || true
    echo "✅ Fedora package created in build/ directory"
else
    echo "⚠️ 'alien' command is not installed. Cannot automatically convert .deb to .rpm."
    echo "To build the RPM package on Ubuntu/Debian, install 'alien':"
    echo "  sudo apt install alien"
    echo "Then convert the package manually using:"
    echo "  sudo alien --to-rpm build/${PACKAGE_NAME}_${VERSION}_all.deb"
fi
