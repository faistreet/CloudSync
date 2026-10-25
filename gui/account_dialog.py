import sys
import subprocess
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QWidget, QMessageBox, QComboBox,
    QProgressBar, QTextEdit
)

from gui.styles import MODERN_QSS
from core.task_runner import run_async_task


def do_oauth(remote_name, remote_type):
    try:
        if remote_type == "drive":
            cmd = ["rclone", "config", "create", remote_name, "drive", "scope", "drive", "config_is_local", "true"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode == 0:
                return {"success": True, "message": "Autenticación de Google Drive completada con éxito."}
            return {"success": False, "message": proc.stderr or proc.stdout}
        elif remote_type == "onedrive":
            cmd = ["rclone", "config", "create", remote_name, "onedrive", "config_is_local", "true"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
            if proc.returncode == 0:
                return {"success": True, "message": "Autenticación de OneDrive completada con éxito."}
            return {"success": False, "message": proc.stderr or proc.stdout}
    except Exception as e:
        return {"success": False, "message": str(e)}


class AccountWizardDialog(QDialog):
    account_added = Signal(str)

    def __init__(self, config_manager, account_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.account_manager = account_manager
        self.oauth_worker = None

        self.setWindowTitle("Añadir cuenta - CloudSync")
        self.setStyleSheet(MODERN_QSS)
        self.resize(540, 580)
        self.setMinimumSize(480, 520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("Vincular almacenamiento en la nube")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        subtitle = QLabel("Selecciona el proveedor que deseas vincular con sincronización bajo demanda:")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px;")
        layout.addWidget(subtitle)

        # Tab widget for providers
        self.tabs = QTabWidget()

        # Tab 1: Google Drive
        self.tabs.addTab(self.create_gdrive_tab(), "Google Drive")

        # Tab 2: OneDrive
        self.tabs.addTab(self.create_onedrive_tab(), "Microsoft OneDrive")

        # Tab 3: Existing Rclone Remotes
        self.tabs.addTab(self.create_existing_tab(), "Remotos Existentes")

        layout.addWidget(self.tabs)

        # Status output
        self.status_box = QLabel("")
        self.status_box.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 500;")
        self.status_box.setWordWrap(True)
        layout.addWidget(self.status_box)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setVisible(False)
        layout.addWidget(self.loading_bar)

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        btn_box.addWidget(close_btn)

        layout.addLayout(btn_box)

    def create_gdrive_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl = QLabel("Vincular Google Drive mediante navegador web.")
        lbl.setStyleSheet("color: #f1f5f9; font-weight: 500;")
        layout.addWidget(lbl)

        layout.addWidget(QLabel("Nombre descriptivo:"))
        self.gdrive_name = QLineEdit("Google Drive Personal")
        layout.addWidget(self.gdrive_name)

        layout.addWidget(QLabel("Nombre de la carpeta local en DATOS/CloudSync:"))
        self.gdrive_folder = QLineEdit("GoogleDrive")
        layout.addWidget(self.gdrive_folder)

        info = QLabel("• Al pulsar el botón, se abrirá tu navegador predeterminado.\n• Inicia sesión con tu cuenta de Google y otorga los permisos necesarios.")
        info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(info)

        layout.addSpacing(10)

        self.gdrive_btn = QPushButton("Iniciar sesión con Google")
        self.gdrive_btn.setObjectName("primaryBtn")
        self.gdrive_btn.clicked.connect(self.start_gdrive_auth)
        layout.addWidget(self.gdrive_btn)

        layout.addStretch()
        return w

    def create_onedrive_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl = QLabel("Vincular Microsoft OneDrive:")
        lbl.setStyleSheet("color: #f1f5f9; font-weight: 500;")
        layout.addWidget(lbl)

        layout.addWidget(QLabel("Nombre descriptivo:"))
        self.onedrive_name = QLineEdit("OneDrive Personal")
        layout.addWidget(self.onedrive_name)

        layout.addWidget(QLabel("Nombre de la carpeta local en DATOS/CloudSync:"))
        self.onedrive_folder = QLineEdit("OneDrive")
        layout.addWidget(self.onedrive_folder)

        info = QLabel("• Puedes usar la configuración guiada en terminal para seleccionar Personal o Empresa.\n• Se abrirá una ventana de Konsole para completar el inicio de sesión en Microsoft de forma segura.")
        info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(info)

        layout.addSpacing(10)

        self.onedrive_btn = QPushButton("Abrir Asistente OneDrive (Konsole)")
        self.onedrive_btn.setObjectName("primaryBtn")
        self.onedrive_btn.clicked.connect(self.start_onedrive_auth)
        layout.addWidget(self.onedrive_btn)

        layout.addStretch()
        return w

    def create_existing_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        lbl = QLabel("Si ya tienes remotos de rclone configurados en tu sistema, selecciónalos:")
        lbl.setStyleSheet("color: #f1f5f9; font-weight: 500;")
        layout.addWidget(lbl)

        self.remote_combo = QComboBox()
        self.refresh_remotes_combo()
        layout.addWidget(self.remote_combo)

        layout.addWidget(QLabel("Nombre de la carpeta local:"))
        self.existing_folder = QLineEdit("MiNube")
        layout.addWidget(self.existing_folder)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        refresh_btn = QPushButton("Actualizar lista")
        refresh_btn.clicked.connect(self.refresh_remotes_combo)
        btn_row.addWidget(refresh_btn)

        import_btn = QPushButton("Vincular este remoto")
        import_btn.setObjectName("primaryBtn")
        import_btn.clicked.connect(self.import_existing_remote)
        btn_row.addWidget(import_btn)

        layout.addLayout(btn_row)
        return w

    def refresh_remotes_combo(self):
        self.remote_combo.clear()
        remotes = self.account_manager.get_all_rclone_remotes()
        for name, data in remotes.items():
            rtype = data.get("type", "desconocido")
            self.remote_combo.addItem(f"{name} ({rtype})", userData=(name, rtype))

    def _get_unique_account_ids(self, base_acc_id, base_remote_name, desired_folder):
        accounts = self.config_manager.get_accounts()
        if base_acc_id not in accounts:
            return base_acc_id, base_remote_name, desired_folder
        idx = 2
        while f"{base_acc_id}_{idx}" in accounts:
            idx += 1
        folder = desired_folder if desired_folder != base_acc_id else f"{desired_folder}_{idx}"
        return f"{base_acc_id}_{idx}", f"{base_remote_name}_{idx}", folder

    def start_gdrive_auth(self):
        desired_folder = self.gdrive_folder.text().strip() or "GoogleDrive"
        acc_id, remote_name, folder = self._get_unique_account_ids("GoogleDrive", "cloudsync_gdrive", desired_folder)
        self._pending_gdrive = (acc_id, remote_name, folder)
        self.status_box.setText("Abriendo navegador web para autorizar Google Drive... Esperando confirmación.")
        self.loading_bar.setVisible(True)
        self.gdrive_btn.setEnabled(False)

        def on_done(res):
            self.on_gdrive_finished(res.get("success", False), res.get("message", ""))

        run_async_task(do_oauth, args=(remote_name, "drive"), on_finished=on_done)

    def on_gdrive_finished(self, success, message):
        self.loading_bar.setVisible(False)
        self.gdrive_btn.setEnabled(True)
        if success:
            acc_id, remote_name, folder = getattr(
                self, "_pending_gdrive", ("GoogleDrive", "cloudsync_gdrive", "GoogleDrive")
            )
            self.config_manager.add_or_update_account(acc_id, {
                "remote_name": remote_name,
                "type": "drive",
                "display_name": self.gdrive_name.text().strip() or acc_id,
                "mount_folder": folder,
                "enabled": True
            })
            QMessageBox.information(self, "Cuenta vinculada", "Google Drive ha sido vinculado y configurado correctamente.")
            self.account_added.emit(acc_id)
            self.accept()
        else:
            QMessageBox.critical(self, "Error de autenticación", f"No se pudo completar la vinculación:\n{message}")
            self.status_box.setText("Error en la autenticación.")

    def start_onedrive_auth(self):
        desired_folder = self.onedrive_folder.text().strip() or "OneDrive"
        acc_id, remote_name, folder = self._get_unique_account_ids("OneDrive", "cloudsync_onedrive", desired_folder)

        # Check if already authenticated and valid
        ok, _ = self.account_manager.test_remote_connection(remote_name)
        if ok:
            self.config_manager.add_or_update_account(acc_id, {
                "remote_name": remote_name,
                "type": "onedrive",
                "display_name": self.onedrive_name.text().strip() or acc_id,
                "mount_folder": folder,
                "enabled": True
            })
            QMessageBox.information(
                self,
                "Cuenta vinculada",
                "OneDrive ya está correctamente autenticado y ha sido vinculado con éxito a CloudSync."
            )
            self.account_added.emit(acc_id)
            self.accept()
            return

        self.status_box.setText("Iniciando Konsole para configurar OneDrive...")
        cmd = ["rclone", "config"]
        launched = self.account_manager.launch_assisted_terminal(cmd)
        if launched:
            reply = QMessageBox.information(
                self,
                "Configuración de OneDrive en Konsole",
                "Se ha abierto una terminal (Konsole).\n"
                f"Crea el remoto con el nombre '{remote_name}' e inicia sesión en tu cuenta de Microsoft.\n\n"
                "Una vez terminada la configuración en la terminal, pulsa 'Aceptar' aquí.",
                QMessageBox.Ok | QMessageBox.Cancel
            )
            if reply == QMessageBox.Ok:
                ok, err = self.account_manager.test_remote_connection(remote_name)
                if ok:
                    self.config_manager.add_or_update_account(acc_id, {
                        "remote_name": remote_name,
                        "type": "onedrive",
                        "display_name": self.onedrive_name.text().strip() or acc_id,
                        "mount_folder": folder,
                        "enabled": True
                    })
                    QMessageBox.information(self, "Cuenta vinculada", "OneDrive ha sido configurado y vinculado exitosamente.")
                    self.account_added.emit(acc_id)
                    self.accept()
                else:
                    QMessageBox.warning(self, "Comprobación fallida", f"No se pudo validar el acceso a OneDrive:\n{err}")
        else:
            QMessageBox.critical(self, "Error", "No se encontró ningún emulador de terminal compatible instalado.")

    def import_existing_remote(self):
        idx = self.remote_combo.currentIndex()
        if idx < 0:
            return
        remote_name, rtype = self.remote_combo.itemData(idx)
        acc_id = remote_name.replace(":", "")
        folder_name = self.existing_folder.text().strip() or acc_id

        self.config_manager.add_or_update_account(acc_id, {
            "remote_name": remote_name,
            "type": rtype,
            "display_name": f"{remote_name} ({rtype})",
            "mount_folder": folder_name,
            "enabled": True
        })
        QMessageBox.information(self, "Cuenta vinculada", f"El remoto '{remote_name}' ha sido vinculado correctamente.")
        self.account_added.emit(acc_id)
        self.accept()
