import os
import shutil
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QCheckBox, QComboBox, QMessageBox
)

from gui.styles import MODERN_QSS


class SettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Configuración - CloudSync")
        self.setStyleSheet(MODERN_QSS)
        self.setFixedSize(540, 560)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Configuración general de sincronización")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        # 1. Base Directory
        layout.addWidget(QLabel("Carpeta raíz de sincronización (Almacenamiento en disco):"))
        dir_box = QHBoxLayout()
        dir_box.setSpacing(10)
        self.base_dir_input = QLineEdit(self.config_manager.base_dir)
        dir_box.addWidget(self.base_dir_input)

        browse_btn = QPushButton("Examinar...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self.browse_base_dir)
        dir_box.addWidget(browse_btn)
        layout.addLayout(dir_box)

        # 2. Cache Max Size
        layout.addWidget(QLabel("Límite máximo de tamaño de caché local (para no llenar el disco):"))
        self.cache_size_combo = QComboBox()
        self.cache_size_combo.addItems(["10G", "20G", "50G", "100G", "200G", "Sin límite (off)"])
        current_size = self.config_manager.cache_max_size
        idx = self.cache_size_combo.findText(current_size)
        if idx >= 0:
            self.cache_size_combo.setCurrentIndex(idx)
        else:
            self.cache_size_combo.setCurrentText(current_size)
        layout.addWidget(self.cache_size_combo)

        # 3. Cache Retention (Max age)
        layout.addWidget(QLabel("Tiempo de permanencia en caché antes de liberar espacio inactivo:"))
        self.cache_age_combo = QComboBox()
        self.cache_age_combo.addItems(["24h (1 día)", "72h (3 días)", "168h (1 semana)", "720h (1 mes)"])
        current_age = self.config_manager.cache_max_age
        for i in range(self.cache_age_combo.count()):
            if current_age in self.cache_age_combo.itemText(i):
                self.cache_age_combo.setCurrentIndex(i)
                break
        layout.addWidget(self.cache_age_combo)

        # 4. Polling interval
        layout.addWidget(QLabel("Intervalo de comprobación de cambios en la nube:"))
        self.poll_combo = QComboBox()
        self.poll_combo.addItems(["30s", "1m", "2m", "5m"])
        current_poll = self.config_manager.get("poll_interval", "1m")
        idx_poll = self.poll_combo.findText(current_poll)
        if idx_poll >= 0:
            self.poll_combo.setCurrentIndex(idx_poll)
        layout.addWidget(self.poll_combo)

        # 5. Checkboxes
        self.autostart_cb = QCheckBox("Iniciar automáticamente al iniciar sesión en Fedora")
        self.autostart_cb.setChecked(self.config_manager.autostart)
        layout.addWidget(self.autostart_cb)

        self.notif_cb = QCheckBox("Mostrar notificaciones de escritorio al sincronizar archivos")
        self.notif_cb.setChecked(self.config_manager.notifications_enabled)
        layout.addWidget(self.notif_cb)

        # Dolphin Service Menu re-installer
        reinstall_btn = QPushButton("Reinstalar menús de Dolphin (Clic derecho)")
        reinstall_btn.setObjectName("secondaryBtn")
        reinstall_btn.clicked.connect(self.install_dolphin_menus)
        layout.addWidget(reinstall_btn)

        layout.addStretch()

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Guardar cambios")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_settings)
        btn_box.addWidget(save_btn)

        layout.addLayout(btn_box)

    def browse_base_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta raíz de sincronización", self.base_dir_input.text())
        if d:
            self.base_dir_input.setText(d)

    def save_settings(self):
        new_base = self.base_dir_input.text().strip()
        if not new_base:
            QMessageBox.warning(self, "Error", "La ruta raíz no puede estar vacía.")
            return

        size_text = self.cache_size_combo.currentText()
        if "Sin límite" in size_text:
            new_size = "off"
        else:
            new_size = size_text.split()[0]

        age_text = self.cache_age_combo.currentText().split()[0]
        poll_text = self.poll_combo.currentText()
        autostart_val = self.autostart_cb.isChecked()
        notif_val = self.notif_cb.isChecked()

        self.config_manager.set("base_dir", new_base)
        self.config_manager.set("cache_dir", os.path.join(new_base, ".cache"))
        self.config_manager.set("cache_max_size", new_size)
        self.config_manager.set("cache_max_age", age_text)
        self.config_manager.set("poll_interval", poll_text)
        self.config_manager.set("autostart", autostart_val)
        self.config_manager.set("notifications", notif_val)

        # Update autostart desktop entry
        self.update_autostart_entry(autostart_val)

        QMessageBox.information(
            self,
            "Configuración guardada",
            "Los ajustes se han guardado. Si cambiaste la carpeta raíz, reinicia la sincronización."
        )
        self.settings_saved.emit()
        self.accept()

    def update_autostart_entry(self, enabled):
        autostart_path = Path.home() / ".config" / "autostart" / "cloudsync.desktop"
        if enabled:
            autostart_path.parent.mkdir(parents=True, exist_ok=True)
            script_path = (Path(__file__).parent.parent / "main.py").resolve()
            content = f"""[Desktop Entry]
Type=Application
Name=CloudSync
Comment=Sincronización de Google Drive y OneDrive con archivos a petición
Exec=python3 "{script_path}" --tray
Icon=cloudsync
Terminal=false
Categories=Utility;Network;
X-GNOME-Autostart-enabled=true
"""
            with open(autostart_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(autostart_path, 0o755)
        else:
            if autostart_path.exists():
                autostart_path.unlink()

    def install_dolphin_menus(self):
        try:
            from integration.install_desktop import install_all
            install_all()
            QMessageBox.information(self, "Menús instalados", "Los menús contextuales para Dolphin han sido actualizados e integrados.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al instalar menús de Dolphin: {e}")
