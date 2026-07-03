#!/usr/bin/env bash
set -e

echo "=== Building Fedora RPM package (.rpm) ==="

# Check if rpmbuild is installed
if ! command -v rpmbuild &> /dev/null; then
    echo "❌ 'rpmbuild' command not found."
    echo "Please install the packaging tools first by running:"
    echo "  sudo dnf install rpm-build rpmdevtools"
    exit 1
fi

# Define directories
RPMBUILD_DIR="${HOME}/rpmbuild"
mkdir -p "${RPMBUILD_DIR}/SOURCES"
mkdir -p "${RPMBUILD_DIR}/SPECS"

# Copy source scripts to the SOURCES directory
cp micro-proton "${RPMBUILD_DIR}/SOURCES/"
cp micro-proton-indicator "${RPMBUILD_DIR}/SOURCES/"
cp micro-proton-manager "${RPMBUILD_DIR}/SOURCES/"
cp -r src "${RPMBUILD_DIR}/SOURCES/"
cp -r images "${RPMBUILD_DIR}/SOURCES/"

# Copy spec file to the SPECS directory
cp micro-proton.spec "${RPMBUILD_DIR}/SPECS/"

# Run rpmbuild to build binary packages (-bb)
echo "Building RPM package..."
rpmbuild -bb "${RPMBUILD_DIR}/SPECS/micro-proton.spec"

# Create local build directory
mkdir -p build

# Copy generated RPM to local build folder
cp "${RPMBUILD_DIR}/RPMS/noarch"/micro-proton-*.rpm build/ 2>/dev/null || true

echo "✅ RPM Package built successfully!"
echo "You can find the RPM installer package in:"
ls -lh build/micro-proton-*.rpm
