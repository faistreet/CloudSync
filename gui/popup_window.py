import os
import time
import subprocess
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QProgressBar, QMessageBox
)

from gui.styles import MODERN_QSS


def format_bytes(num_bytes):
    if not num_bytes or num_bytes <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


class AccountCard(QFrame):
    open_folder_clicked = Signal(str)
    inspect_clicked = Signal(str)
    refresh_clicked = Signal(str)

    def __init__(self, account_id, info, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.info = info
        self.setObjectName("cardFrame")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Top row: Brand Icon, Name & Email, Status Pill
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        icon_label = QLabel()
        icon_path = Path(__file__).parent.parent / "assets" / "icons"
        brand_type = self.info.get("type", "drive")
        if brand_type == "drive":
            brand_icon = icon_path / "gdrive.svg"
        else:
            brand_icon = icon_path / "onedrive.svg"
        
        pixmap = QPixmap(str(brand_icon)).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        top_row.addWidget(icon_label)

        # Name, Email & Path
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        display_name = self.info.get("display_name", self.account_id)
        name_label = QLabel(f"<b>{display_name}</b>")
        name_label.setStyleSheet("font-size: 14px; color: #ffffff;")
        info_col.addWidget(name_label)

        email = self.info.get("email")
        if email:
            email_lbl = QLabel(f"✉ {email}")
            email_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 500;")
            info_col.addWidget(email_lbl)

        folder_name = self.info.get("mount_folder", self.account_id)
        path_label = QLabel(f"Carpeta: {folder_name}")
        path_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        info_col.addWidget(path_label)

        top_row.addLayout(info_col)
        top_row.addStretch()

        # Status Pill
        self.status_pill = QLabel("Montado")
        self.status_pill.setObjectName("statusPillSuccess")
        top_row.addWidget(self.status_pill)
        layout.addLayout(top_row)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.open_btn = QPushButton("Abrir en Dolphin")
        self.open_btn.setObjectName("secondaryBtn")
        self.open_btn.clicked.connect(lambda: self.open_folder_clicked.emit(self.account_id))
        btn_row.addWidget(self.open_btn)

        self.inspect_btn = QPushButton("🔍 Nube vs Local")
        self.inspect_btn.setObjectName("secondaryBtn")
        self.inspect_btn.setToolTip("Ver qué archivos están descargados y cuáles en la nube")
        self.inspect_btn.clicked.connect(lambda: self.inspect_clicked.emit(self.account_id))
        btn_row.addWidget(self.inspect_btn)

        self.refresh_btn = QPushButton("Sincronizar")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.clicked.connect(lambda: self.refresh_clicked.emit(self.account_id))
        btn_row.addWidget(self.refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def set_status(self, is_alive, is_paused):
        if is_paused:
            self.status_pill.setText("Pausado")
            self.status_pill.setObjectName("statusPillPaused")
        elif is_alive:
            self.status_pill.setText("Archivos a petición")
            self.status_pill.setObjectName("statusPillSuccess")
        else:
            self.status_pill.setText("Desconectado")
            self.status_pill.setObjectName("statusPillError")
        self.status_pill.setStyle(self.status_pill.style())


class PopupWindow(QWidget):
    open_settings_requested = Signal()
    add_account_requested = Signal()
    open_inspector_requested = Signal(str)

    def __init__(self, config_manager, sync_engine, vfs_controller, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.sync_engine = sync_engine
        self.vfs_controller = vfs_controller
        self.account_cards = {}
        self._drag_pos = None

        # Session-based download history (cleared on app restart)
        self.session_downloads = []
        self.active_hydration = None

        self.setWindowTitle("CloudSync - Sincronización en la nube")
        self.setObjectName("popupWindowRoot")
        self.setWindowFlags(Qt.Window)
        self.setStyleSheet(MODERN_QSS)
        self.resize(480, 680)
        self.setMinimumSize(420, 520)

        icon_path = Path(__file__).parent.parent / "assets" / "icons" / "app_icon.svg"
        self.setWindowIcon(QIcon(str(icon_path)))

        self.init_ui()
        self.sync_engine.stats_updated.connect(self.on_stats_updated)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        event.accept()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Header Frame
        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)

        # Title & Subtitle
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title_lbl = QLabel("CloudSync")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #38bdf8;")
        self.subtitle_lbl = QLabel("Archivos a petición activos")
        self.subtitle_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        title_col.addWidget(title_lbl)
        title_col.addWidget(self.subtitle_lbl)
        header_layout.addLayout(title_col)

        header_layout.addStretch()

        # Pause / Resume Button
        self.pause_btn = QPushButton("Pausar")
        self.pause_btn.setObjectName("secondaryBtn")
        self.pause_btn.clicked.connect(self.toggle_pause)
        header_layout.addWidget(self.pause_btn)

        # Settings Button
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("iconBtn")
        settings_btn.setToolTip("Configuración")
        settings_btn.clicked.connect(self.open_settings_requested.emit)
        header_layout.addWidget(settings_btn)

        root_layout.addWidget(header)

        # 2. Scrollable Body
        scroll = QScrollArea()
        scroll.setObjectName("mainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        scroll_widget.setObjectName("scrollContent")
        self.body_layout = QVBoxLayout(scroll_widget)
        self.body_layout.setContentsMargins(20, 16, 20, 16)
        self.body_layout.setSpacing(16)

        # Accounts Section Header
        acc_header = QLabel("CUENTAS CONECTADAS")
        acc_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; letter-spacing: 1px;")
        self.body_layout.addWidget(acc_header)

        # Accounts Cards Container
        self.accounts_container = QVBoxLayout()
        self.accounts_container.setSpacing(10)
        self.body_layout.addLayout(self.accounts_container)

        self.update_accounts_view()

        # Live Activity Section (Speeds & Transfers)
        activity_header = QLabel("VELOCIDAD Y ACTIVIDAD")
        activity_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; letter-spacing: 1px;")
        self.body_layout.addWidget(activity_header)

        self.activity_frame = QFrame()
        self.activity_frame.setObjectName("cardFrame")
        self.activity_layout = QVBoxLayout(self.activity_frame)
        self.activity_layout.setContentsMargins(16, 14, 16, 14)
        self.activity_layout.setSpacing(10)

        # Speed stats row (Download and Upload gauges)
        speed_row = QHBoxLayout()
        self.down_speed_label = QLabel("↓ Descarga: 0 B/s")
        self.down_speed_label.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        speed_row.addWidget(self.down_speed_label)

        self.up_speed_label = QLabel("↑ Subida: 0 B/s")
        self.up_speed_label.setStyleSheet("color: #34d399; font-weight: bold; font-size: 13px;")
        speed_row.addWidget(self.up_speed_label)

        speed_row.addStretch()
        self.status_msg_label = QLabel("Al día")
        self.status_msg_label.setStyleSheet("color: #10b981; font-weight: 600; font-size: 13px;")
        speed_row.addWidget(self.status_msg_label)
        self.activity_layout.addLayout(speed_row)

        # Active transfers list layout
        self.transfers_layout = QVBoxLayout()
        self.transfers_layout.setSpacing(8)
        self.activity_layout.addLayout(self.transfers_layout)

        self.body_layout.addWidget(self.activity_frame)

        # Session Downloads Section (Resets on restart)
        session_header = QLabel("DESCARGAS BAJO DEMANDA (ESTA SESIÓN)")
        session_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; letter-spacing: 1px;")
        self.body_layout.addWidget(session_header)

        self.session_frame = QFrame()
        self.session_frame.setObjectName("cardFrame")
        self.session_layout = QVBoxLayout(self.session_frame)
        self.session_layout.setContentsMargins(16, 14, 16, 14)
        self.session_layout.setSpacing(8)

        self.update_session_history_ui()
        self.body_layout.addWidget(self.session_frame)

        # Local Cache Status Section
        cache_header = QLabel("ALMACENAMIENTO EN CACHÉ LOCAL")
        cache_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; letter-spacing: 1px;")
        self.body_layout.addWidget(cache_header)

        cache_frame = QFrame()
        cache_frame.setObjectName("cardFrame")
        cache_layout = QVBoxLayout(cache_frame)
        cache_layout.setContentsMargins(16, 14, 16, 14)
        cache_layout.setSpacing(10)

        self.cache_usage_label = QLabel("Caché utilizada: Calculando...")
        self.cache_usage_label.setStyleSheet("color: #cbd5e1; font-size: 13px;")
        cache_layout.addWidget(self.cache_usage_label)

        self.cache_progress = QProgressBar()
        self.cache_progress.setValue(0)
        cache_layout.addWidget(self.cache_progress)

        cache_btn_row = QHBoxLayout()
        self.free_all_btn = QPushButton("Liberar toda la caché")
        self.free_all_btn.setObjectName("secondaryBtn")
        self.free_all_btn.clicked.connect(self.free_all_cache)
        cache_btn_row.addWidget(self.free_all_btn)

        inspect_all_btn = QPushButton("🔍 Explorador Nube vs Local")
        inspect_all_btn.setObjectName("secondaryBtn")
        inspect_all_btn.clicked.connect(lambda: self.open_inspector_requested.emit(""))
        cache_btn_row.addWidget(inspect_all_btn)

        cache_btn_row.addStretch()
        cache_layout.addLayout(cache_btn_row)

        self.body_layout.addWidget(cache_frame)
        self.body_layout.addStretch()

        scroll.setWidget(scroll_widget)
        root_layout.addWidget(scroll)

        # 3. Footer Bar
        footer = QFrame()
        footer.setStyleSheet("background-color: #0b1120; border-top: 1px solid #1e293b;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 14, 20, 14)
        footer_layout.setSpacing(12)

        add_acc_btn = QPushButton("+ Añadir cuenta")
        add_acc_btn.setObjectName("primaryBtn")
        add_acc_btn.clicked.connect(self.add_account_requested.emit)
        footer_layout.addWidget(add_acc_btn)

        open_root_btn = QPushButton("Abrir carpeta raíz")
        open_root_btn.clicked.connect(self.open_root_folder)
        footer_layout.addWidget(open_root_btn)

        root_layout.addWidget(footer)

        # Timer to update cache size occasionally
        self.cache_timer = QTimer(self)
        self.cache_timer.timeout.connect(self.update_cache_gauge)
        self.cache_timer.start(8000)
        self.update_cache_gauge()

    def update_accounts_view(self):
        while self.accounts_container.count():
            item = self.accounts_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.account_cards.clear()

        accounts = self.config_manager.get_accounts()
        if not accounts:
            empty_lbl = QLabel("No hay cuentas sincronizadas aún.\nHaz clic en '+ Añadir cuenta' abajo.")
            empty_lbl.setStyleSheet("color: #64748b; font-style: italic; padding: 12px; font-size: 13px;")
            empty_lbl.setAlignment(Qt.AlignCenter)
            self.accounts_container.addWidget(empty_lbl)
            return

        for acc_id, info in accounts.items():
            card = AccountCard(acc_id, info)
            card.open_folder_clicked.connect(self.open_account_folder)
            card.inspect_clicked.connect(lambda a=acc_id: self.open_inspector_requested.emit(a))
            card.refresh_clicked.connect(self.refresh_account)
            self.account_cards[acc_id] = card
            self.accounts_container.addWidget(card)

    def on_stats_updated(self, stats):
        total_speed = stats.get("total_speed", 0)
        is_paused = stats.get("is_paused", False)
        active_transfers = stats.get("active_transfers", [])
        accounts_data = stats.get("accounts", {})

        # If we have active hydration from pin, include its speed
        hydration_speed = self.active_hydration.get("speed", 0) if self.active_hydration else 0
        display_down_speed = total_speed + hydration_speed

        self.pause_btn.setText("Reanudar" if is_paused else "Pausar")

        if is_paused:
            self.down_speed_label.setText("↓ Pausado")
            self.up_speed_label.setText("↑ Pausado")
            self.status_msg_label.setText("Pausado")
            self.subtitle_lbl.setText("Sincronización en pausa")
        elif active_transfers or self.active_hydration:
            self.down_speed_label.setText(f"↓ Descarga: {format_bytes(display_down_speed)}/s")
            self.up_speed_label.setText(f"↑ Subida: {format_bytes(total_speed * 0.2)}/s") # estimated upload
            self.status_msg_label.setText("Sincronizando...")
            self.subtitle_lbl.setText("Descargando / subiendo archivos")
        else:
            self.down_speed_label.setText("↓ Descarga: 0 B/s")
            self.up_speed_label.setText("↑ Subida: 0 B/s")
            self.status_msg_label.setText("Todo al día")
            self.subtitle_lbl.setText("Archivos a petición activos")

        for acc_id, card in self.account_cards.items():
            acc_info = accounts_data.get(acc_id, {})
            is_alive = acc_info.get("alive", False)
            card.set_status(is_alive, is_paused)

        # Active transfers widgets
        while self.transfers_layout.count():
            item = self.transfers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if active_transfers:
            for t in active_transfers[:4]:
                t_box = QVBoxLayout()
                t_box.setSpacing(4)
                t_lbl = QLabel(f"{t['name']} ({format_bytes(t['bytes'])} / {format_bytes(t['size'])})")
                t_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
                pbar = QProgressBar()
                pbar.setValue(int(t.get("percentage", 0)))
                t_box.addWidget(t_lbl)
                t_box.addWidget(pbar)
                w = QWidget()
                w.setLayout(t_box)
                self.transfers_layout.addWidget(w)
        elif not self.active_hydration:
            idle_lbl = QLabel("✓ Todos los archivos sincronizados")
            idle_lbl.setStyleSheet("color: #10b981; font-size: 12px; padding: 4px 0;")
            self.transfers_layout.addWidget(idle_lbl)

    def set_active_hydration(self, hydration_data):
        """Called when a file is actively being downloaded via 'Mantener en este equipo'"""
        self.active_hydration = hydration_data
        self.update_session_history_ui()

    def add_session_completed(self, file_name, file_size, speed):
        """Adds a completed download to the in-memory session history"""
        self.active_hydration = None
        self.session_downloads.insert(0, {
            "name": file_name,
            "size": file_size,
            "speed": speed,
            "time": time.strftime("%H:%M:%S")
        })
        self.update_session_history_ui()

    def update_session_history_ui(self):
        while self.session_layout.count():
            item = self.session_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # If currently downloading a file via pin
        if self.active_hydration:
            f_name = self.active_hydration.get("file_name", "Descargando...")
            f_bytes = self.active_hydration.get("file_bytes", 0)
            f_total = self.active_hydration.get("file_total", 0)
            speed = self.active_hydration.get("speed", 0)
            pct = int((f_bytes / f_total) * 100) if f_total > 0 else 0

            active_box = QVBoxLayout()
            active_box.setSpacing(4)
            lbl = QLabel(f"📥 <b>{f_name}</b> ({format_bytes(f_bytes)} / {format_bytes(f_total)}) - {format_bytes(speed)}/s")
            lbl.setStyleSheet("color: #38bdf8; font-size: 12px;")
            pbar = QProgressBar()
            pbar.setValue(pct)
            active_box.addWidget(lbl)
            active_box.addWidget(pbar)
            w = QWidget()
            w.setLayout(active_box)
            self.session_layout.addWidget(w)

        # Show completed session downloads (top 5)
        if self.session_downloads:
            for item in self.session_downloads[:5]:
                row = QHBoxLayout()
                row.setSpacing(8)
                lbl = QLabel(f"✓ <b>{item['name']}</b> ({format_bytes(item['size'])})")
                lbl.setStyleSheet("color: #34d399; font-size: 12px;")
                row.addWidget(lbl)

                row.addStretch()
                time_lbl = QLabel(f"{item['time']} ({format_bytes(item['speed'])}/s)")
                time_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
                row.addWidget(time_lbl)

                w = QWidget()
                w.setLayout(row)
                self.session_layout.addWidget(w)
        elif not self.active_hydration:
            empty_lbl = QLabel("No hay descargas recientes en esta sesión.")
            empty_lbl.setStyleSheet("color: #64748b; font-style: italic; font-size: 12px;")
            self.session_layout.addWidget(empty_lbl)

    def update_cache_gauge(self):
        try:
            used_bytes = self.vfs_controller.get_cache_disk_usage()
            max_size_str = self.config_manager.cache_max_size
            max_bytes = 50 * 1024 * 1024 * 1024
            if max_size_str.endswith("G"):
                max_bytes = float(max_size_str[:-1]) * 1024 * 1024 * 1024
            elif max_size_str.endswith("M"):
                max_bytes = float(max_size_str[:-1]) * 1024 * 1024

            pct = int((used_bytes / max_bytes) * 100) if max_bytes > 0 else 0
            self.cache_progress.setValue(min(pct, 100))
            self.cache_usage_label.setText(
                f"Caché utilizada: <b>{format_bytes(used_bytes)}</b> de {max_size_str}"
            )
        except Exception:
            pass

    def toggle_pause(self):
        if self.pause_btn.text() == "Pausar":
            self.sync_engine.pause_all()
            self.pause_btn.setText("Reanudar")
        else:
            self.sync_engine.resume_all()
            self.pause_btn.setText("Pausar")

    def open_account_folder(self, acc_id):
        mount_path = self.config_manager.get_mount_path_for_account(acc_id)
        if os.path.exists(mount_path):
            subprocess.Popen(["dolphin", mount_path])
        else:
            QMessageBox.warning(self, "Aviso", f"La carpeta {mount_path} aún no está montada.")

    def refresh_account(self, acc_id):
        self.sync_engine.refresh_account(acc_id)
        QMessageBox.information(self, "CloudSync", f"Se ha solicitado una actualización para {acc_id}.")

    def open_root_folder(self):
        root_dir = self.config_manager.base_dir
        os.makedirs(root_dir, exist_ok=True)
        subprocess.Popen(["dolphin", root_dir])

    def free_all_cache(self):
        reply = QMessageBox.question(
            self,
            "Liberar toda la caché",
            "¿Deseas liberar todos los archivos descargados localmente?\n"
            "Tus archivos seguirán estando seguros en la nube y seguirás viéndolos en tu PC.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            cache_dir = Path(self.config_manager.cache_dir)
            if cache_dir.exists():
                import shutil
                shutil.rmtree(cache_dir, ignore_errors=True)
                cache_dir.mkdir(parents=True, exist_ok=True)
            for acc_id in self.config_manager.get_accounts():
                self.sync_engine.refresh_account(acc_id)
            self.update_cache_gauge()
            QMessageBox.information(self, "Éxito", "Se ha liberado la caché local por completo.")
