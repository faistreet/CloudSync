Name:           cloudsync
Version:        %{?version}%{!?version:1.0.0}
Release:        1%{?dist}
Summary:        Cliente de sincronización en la nube con soporte de Archivos a petición para Fedora KDE
Summary(es):    Cliente de sincronización en la nube con soporte de Archivos a petición para Fedora KDE

License:        MIT
URL:            https://github.com/faistreet/CloudSync
BuildArch:      noarch

Requires:       python3 >= 3.9
Requires:       python3-pyside6
Requires:       rclone >= 1.58

%description
CloudSync es una aplicación gráfica moderna inspirada en MEGASync y OneDrive
para Windows, optimizada para Linux Fedora con KDE Plasma. Permite sincronizar
y acceder a tus cuentas de Google Drive y Microsoft OneDrive con soporte
completo para Archivos a petición (Files On-Demand) y transferencia directa
entre nubes.

%prep
# No prep stage needed for source directory packaging

%build
# Pure Python application

%install
rm -rf %{buildroot}

# Directorios de destino
mkdir -p %{buildroot}%{_datadir}/%{name}
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
mkdir -p %{buildroot}%{_datadir}/kio/servicemenus

# Copiar archivos de la aplicación
cp -a main.py cloudsync_cli.py core gui assets integration %{buildroot}%{_datadir}/%{name}/

# Wrapper ejecutable principal /usr/bin/cloudsync
cat << 'EOF' > %{buildroot}%{_bindir}/cloudsync
#!/bin/bash
exec /usr/bin/python3 /usr/share/cloudsync/main.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/cloudsync

# Wrapper CLI /usr/bin/cloudsync-cli
cat << 'EOF' > %{buildroot}%{_bindir}/cloudsync-cli
#!/bin/bash
exec /usr/bin/python3 /usr/share/cloudsync/cloudsync_cli.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/cloudsync-cli

# Instalar icono vectorial SVG
install -m 644 assets/icons/app_icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/cloudsync.svg

# Instalar lanzador de escritorio .desktop
cat << 'EOF' > %{buildroot}%{_datadir}/applications/cloudsync.desktop
[Desktop Entry]
Type=Application
Name=CloudSync
GenericName=Sincronizador en la nube
Comment=Sincroniza Google Drive y OneDrive con archivos a petición
Exec=/usr/bin/cloudsync
Icon=cloudsync
Terminal=false
Categories=Network;FileTransfer;Utility;Qt;
Keywords=cloud;drive;onedrive;sync;google;files-on-demand;
EOF
chmod 644 %{buildroot}%{_datadir}/applications/cloudsync.desktop

# Instalar menú de servicio para Dolphin (KDE Plasma 6 / KIO)
cat << 'EOF' > %{buildroot}%{_datadir}/kio/servicemenus/cloudsync_dolphin.desktop
[Desktop Entry]
Type=Service
MimeType=all/allfiles;inode/directory;
Actions=PinOffline;FreeSpace;InspectStatus;TransferCloud;
X-KDE-Submenu=CloudSync
X-KDE-Submenu[es]=CloudSync
X-KDE-Priority=TopLevel

[Desktop Action PinOffline]
Name=Mantener siempre en este equipo (Descargar)
Name[es]=Mantener siempre en este equipo (Descargar)
Icon=download
Exec=/usr/bin/cloudsync-cli pin %F

[Desktop Action FreeSpace]
Name=Liberar espacio local
Name[es]=Liberar espacio local
Icon=edit-clear
Exec=/usr/bin/cloudsync-cli free %F

[Desktop Action InspectStatus]
Name=Ver estado de archivos (Nube vs Local)
Name[es]=Ver estado de archivos (Nube vs Local)
Icon=view-list-details
Exec=/usr/bin/cloudsync-cli inspect %F

[Desktop Action TransferCloud]
Name=Pasar a otra nube (Copiar / Mover sin usar disco)
Name[es]=Pasar a otra nube (Copiar / Mover sin usar disco)
Icon=network-workgroup
Exec=/usr/bin/cloudsync-cli transfer %F
EOF
chmod 644 %{buildroot}%{_datadir}/kio/servicemenus/cloudsync_dolphin.desktop

%post
touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
update-desktop-database &> /dev/null || :

%postun
if [ $1 -eq 0 ] ; then
    touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
    update-desktop-database &> /dev/null || :
    gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
fi

%files
%{_bindir}/cloudsync
%{_bindir}/cloudsync-cli
%{_datadir}/%{name}
%{_datadir}/applications/cloudsync.desktop
%{_datadir}/icons/hicolor/scalable/apps/cloudsync.svg
%{_datadir}/kio/servicemenus/cloudsync_dolphin.desktop

%changelog
* Sun Oct 25 2026 CloudSync Team <support@github.com> - 1.0.0-1
- Release inicial de CloudSync para Fedora con soporte Files On-Demand y transferencia entre nubes.
