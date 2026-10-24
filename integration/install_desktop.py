#!/usr/bin/env python3
import os
import shutil
from pathlib import Path


def install_all():
    project_root = Path(__file__).parent.parent.resolve()
    cli_path = (project_root / "cloudsync_cli.py").resolve()
    main_path = (project_root / "main.py").resolve()
    icon_src = (project_root / "assets" / "icons" / "app_icon.svg").resolve()

    home = Path.home()
    python_bin = shutil.which("python3") or "/usr/bin/python3"

    # 1. Install app icon
    icon_dest_dir = home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    icon_dest_dir.mkdir(parents=True, exist_ok=True)
    icon_dest = icon_dest_dir / "cloudsync.svg"
    shutil.copyfile(icon_src, icon_dest)
    print(f"✓ Icono instalado en: {icon_dest}")

    # 2. Install application menu launcher (.desktop)
    apps_dir = home / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    app_desktop = apps_dir / "cloudsync.desktop"
    app_desktop_content = f"""[Desktop Entry]
Type=Application
Name=CloudSync
GenericName=Sincronizador en la nube
Comment=Sincroniza Google Drive y OneDrive con archivos a petición
Exec={python_bin} "{main_path}"
Icon=cloudsync
Terminal=false
Categories=Network;FileTransfer;Utility;Qt;
Keywords=cloud;drive;onedrive;sync;google;files-on-demand;
"""
    with open(app_desktop, "w", encoding="utf-8") as f:
        f.write(app_desktop_content)
    os.chmod(app_desktop, 0o755)
    print(f"✓ Lanzador de aplicaciones instalado en: {app_desktop}")

    # 3. Install Dolphin Service Menu (KIO Service Menus for KDE Plasma 6)
    servicemenus_dir = home / ".local" / "share" / "kio" / "servicemenus"
    servicemenus_dir.mkdir(parents=True, exist_ok=True)
    dolphin_desktop = servicemenus_dir / "cloudsync_dolphin.desktop"
    dolphin_desktop_content = f"""[Desktop Entry]
Type=Service
MimeType=all/allfiles;inode/directory;
Actions=PinOffline;FreeSpace;InspectStatus;
X-KDE-Submenu=CloudSync
X-KDE-Submenu[es]=CloudSync
X-KDE-Priority=TopLevel

[Desktop Action PinOffline]
Name=Mantener siempre en este equipo (Descargar)
Name[es]=Mantener siempre en este equipo (Descargar)
Icon=download
Exec={python_bin} "{cli_path}" pin %F

[Desktop Action FreeSpace]
Name=Liberar espacio local
Name[es]=Liberar espacio local
Icon=user-trash
Exec={python_bin} "{cli_path}" free %F

[Desktop Action InspectStatus]
Name=Ver estado de archivos (Nube vs Local)
Name[es]=Ver estado de archivos (Nube vs Local)
Icon=cloud
Exec={python_bin} "{cli_path}" inspect %F
"""
    with open(dolphin_desktop, "w", encoding="utf-8") as f:
        f.write(dolphin_desktop_content)
    os.chmod(dolphin_desktop, 0o755)
    print(f"✓ Menú contextual de Dolphin instalado y autorizado (chmod +x) en: {dolphin_desktop}")

    # 4. Install Autostart desktop entry
    autostart_dir = home / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    autostart_desktop = autostart_dir / "cloudsync.desktop"
    autostart_content = f"""[Desktop Entry]
Type=Application
Name=CloudSync
Comment=Sincronización de Google Drive y OneDrive con archivos a petición
Exec={python_bin} "{main_path}" --tray
Icon=cloudsync
Terminal=false
Categories=Utility;Network;
X-GNOME-Autostart-enabled=true
"""
    with open(autostart_desktop, "w", encoding="utf-8") as f:
        f.write(autostart_content)
    os.chmod(autostart_desktop, 0o755)
    print(f"✓ Inicio automático (Autostart) configurado en: {autostart_desktop}")

    os.chmod(cli_path, 0o755)
    os.chmod(main_path, 0o755)

    print("\n¡Instalación completada exitosamente!")


if __name__ == "__main__":
    install_all()
