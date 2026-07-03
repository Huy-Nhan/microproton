Name:           micro-proton
Version:        1.0.0
Release:        1%{?dist}
Summary:        Lightweight Proton Prefix Manager for Steam Play games
License:        MIT
URL:            https://github.com/ryando/microproton
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
Requires:       python3
Requires:       python3-gobject
Requires:       python3-tkinter
Requires:       gtk3
Requires:       zenity

%description
Micro Proton allows running Windows executables (.exe) under Steam's Proton
compatibility layer, managing prefixes, and running them with options like
MangoHud, GameMode, and taskbar integration.

%prep
# No source tarball extraction for local directory build
%setup -q -c -T

%install
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/applications

# Copy the executables from the source directory
cp %{_sourcedir}/micro-proton %{buildroot}%{_bindir}/micro-proton
cp %{_sourcedir}/micro-proton-indicator %{buildroot}%{_bindir}/micro-proton-indicator
cp %{_sourcedir}/micro-proton-manager %{buildroot}%{_bindir}/micro-proton-manager

chmod 755 %{buildroot}%{_bindir}/micro-proton
chmod 755 %{buildroot}%{_bindir}/micro-proton-indicator
chmod 755 %{buildroot}%{_bindir}/micro-proton-manager

# Create desktop entry files
cat << 'EOF' > %{buildroot}%{_datadir}/applications/micro-proton-manager.desktop
[Desktop Entry]
Name=Micro Proton Manager
Comment=Manage Windows applications running under Proton
Exec=micro-proton-manager
Icon=steam
Terminal=false
Type=Application
Categories=Game;Utility;
EOF

cat << 'EOF' > %{buildroot}%{_datadir}/applications/micro-proton-indicator.desktop
[Desktop Entry]
Name=Micro Proton Indicator
Comment=System Tray Indicator for Micro Proton
Exec=micro-proton-indicator
Icon=steam
Terminal=false
Type=Application
Categories=Game;Utility;
EOF

%files
%{_bindir}/micro-proton
%{_bindir}/micro-proton-indicator
%{_bindir}/micro-proton-manager
%{_datadir}/applications/micro-proton-manager.desktop
%{_datadir}/applications/micro-proton-indicator.desktop

%changelog
* Fri Jul 03 2026 Ryando <ryando@example.com> - 1.0.0-1
- Initial release.
