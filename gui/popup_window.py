import os
import time
import subprocess
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QProgressBar, QMessageBox, QSizePolicy
)

from gui.styles import MODERN_QSS
from core.task_runner import run_async_task


def elide_text(text, max_len=36):
    s = str(text or "")
    if len(s) <= max_len:
        return s
    keep = (max_len - 3) // 2
    return f"{s[:keep]}...{s[-keep:]}"


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

        # Action buttons row (uniform equal widths & responsive)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.open_btn = QPushButton("📂 Dolphin")
        self.open_btn.setObjectName("secondaryBtn")
        self.open_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.open_btn.setToolTip("Abrir carpeta sincronizada en el explorador Dolphin")
        self.open_btn.clicked.connect(lambda: self.open_folder_clicked.emit(self.account_id))
        btn_row.addWidget(self.open_btn, stretch=1)

        self.inspect_btn = QPushButton("🔍 Nube vs Local")
        self.inspect_btn.setObjectName("secondaryBtn")
        self.inspect_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.inspect_btn.setToolTip("Ver qué archivos están descargados y cuáles en la nube")
        self.inspect_btn.clicked.connect(lambda: self.inspect_clicked.emit(self.account_id))
        btn_row.addWidget(self.inspect_btn, stretch=1)

        self.refresh_btn = QPushButton("🔄 Sincronizar")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh_btn.setToolTip("Refrescar cambios desde la nube")
        self.refresh_btn.clicked.connect(lambda: self.refresh_clicked.emit(self.account_id))
        btn_row.addWidget(self.refresh_btn, stretch=1)

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
    open_transfer_requested = Signal(str)

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
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # Native Wayland/X11 compositor dragging from header area (top 65px)
            if event.position().y() <= 65:
                wh = self.windowHandle()
                if wh and hasattr(wh, "startSystemMove") and wh.startSystemMove():
                    event.accept()
                    return
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

        # Close Panel Button
        close_btn = QPushButton("✕")
        close_btn.setObjectName("iconBtn")
        close_btn.setToolTip("Cerrar panel (Esc)")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

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
        cache_btn_row.setSpacing(8)
        self.free_all_btn = QPushButton("🗑️ Liberar caché")
        self.free_all_btn.setObjectName("secondaryBtn")
        self.free_all_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.free_all_btn.clicked.connect(self.free_all_cache)
        cache_btn_row.addWidget(self.free_all_btn, stretch=1)

        inspect_all_btn = QPushButton("🔍 Nube vs Local")
        inspect_all_btn.setObjectName("secondaryBtn")
        inspect_all_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        inspect_all_btn.clicked.connect(lambda: self.open_inspector_requested.emit(""))
        cache_btn_row.addWidget(inspect_all_btn, stretch=1)

        cache_layout.addLayout(cache_btn_row)

        self.body_layout.addWidget(cache_frame)
        self.body_layout.addStretch()

        scroll.setWidget(scroll_widget)
        root_layout.addWidget(scroll)

        # 3. Footer Bar (Uniform equal-width responsive buttons)
        footer = QFrame()
        footer.setStyleSheet("background-color: #0b1120; border-top: 1px solid #1e293b;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)
        footer_layout.setSpacing(8)

        add_acc_btn = QPushButton("+ Cuenta")
        add_acc_btn.setObjectName("primaryBtn")
        add_acc_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        add_acc_btn.setToolTip("Vincular una nueva cuenta de Google Drive o OneDrive")
        add_acc_btn.clicked.connect(self.add_account_requested.emit)
        footer_layout.addWidget(add_acc_btn, stretch=1)

        transfer_btn = QPushButton("🔄 Entre Nubes")
        transfer_btn.setObjectName("secondaryBtn")
        transfer_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        transfer_btn.setToolTip("Copiar o mover archivos/carpetas de una nube a otra sin usar el disco duro")
        transfer_btn.clicked.connect(lambda: self.open_transfer_requested.emit(""))
        footer_layout.addWidget(transfer_btn, stretch=1)

        open_root_btn = QPushButton("📂 Carpeta raíz")
        open_root_btn.setObjectName("secondaryBtn")
        open_root_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        open_root_btn.setToolTip("Abrir la carpeta principal de CloudSync en Dolphin")
        open_root_btn.clicked.connect(self.open_root_folder)
        footer_layout.addWidget(open_root_btn, stretch=1)

        root_layout.addWidget(footer)

        # Initial async cache calculation (subsequent updates come from rclone in-memory stats)
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
        down_speed = stats.get("download_speed", 0)
        up_speed = stats.get("upload_speed", 0)
        is_paused = stats.get("is_paused", False)
        active_transfers = stats.get("active_transfers", [])
        accounts_data = stats.get("accounts", {})

        # If manual pin is actively hydrating, include its speed
        if self.active_hydration:
            hydration_speed = self.active_hydration.get("speed", 0)
            down_speed = max(down_speed, hydration_speed)

        self.pause_btn.setText("Reanudar" if is_paused else "Pausar")

        if is_paused:
            self.down_speed_label.setText("↓ Pausado")
            self.up_speed_label.setText("↑ Pausado")
            self.status_msg_label.setText("Pausado")
            self.status_msg_label.setStyleSheet("color: #f59e0b; font-weight: 600; font-size: 13px;")
            self.subtitle_lbl.setText("Sincronización en pausa")
        elif down_speed > 0 or up_speed > 0 or active_transfers or self.active_hydration:
            self.down_speed_label.setText(f"↓ Descarga: {format_bytes(down_speed)}/s")
            self.up_speed_label.setText(f"↑ Subida: {format_bytes(up_speed)}/s")
            if up_speed > down_speed and up_speed > 0:
                self.status_msg_label.setText("Subiendo a la nube...")
                self.status_msg_label.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 13px;")
                self.subtitle_lbl.setText("Subiendo archivos a la nube")
            else:
                self.status_msg_label.setText("Descargando...")
                self.status_msg_label.setStyleSheet("color: #34d399; font-weight: 600; font-size: 13px;")
                self.subtitle_lbl.setText("Descargando archivos a este equipo")
        else:
            self.down_speed_label.setText("↓ Descarga: 0 B/s")
            self.up_speed_label.setText("↑ Subida: 0 B/s")
            self.status_msg_label.setText("Todo al día")
            self.status_msg_label.setStyleSheet("color: #10b981; font-weight: 600; font-size: 13px;")
            self.subtitle_lbl.setText("Archivos a petición activos")

        for acc_id, card in self.account_cards.items():
            acc_info = accounts_data.get(acc_id, {})
            is_alive = acc_info.get("alive", False)
            card.set_status(is_alive, is_paused)

        up_in_prog = stats.get("uploads_in_progress", 0)
        up_queued = stats.get("uploads_queued", 0)

        # Active transfers widgets
        while self.transfers_layout.count():
            item = self.transfers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if up_in_prog > 0 or up_queued > 0:
            q_lbl = QLabel(
                f"⏳ Cola de subida activa: {up_in_prog} subiendo, {up_queued} en espera (protegidos en caché)"
            )
            q_lbl.setStyleSheet(
                "color: #fbbf24; font-size: 11px; font-weight: bold; background: #451a03; "
                "padding: 4px 8px; border-radius: 6px; border: 1px solid #d97706;"
            )
            self.transfers_layout.addWidget(q_lbl)

        if active_transfers:
            for t in active_transfers[:4]:
                t_box = QVBoxLayout()
                t_box.setSpacing(4)
                t_dir = t.get("direction", "down")
                dir_icon = "📤 Subiendo:" if t_dir == "up" else "📥 Descargando:"
                short_name = elide_text(Path(t.get("name", "")).name, 34)
                t_lbl = QLabel(f"{dir_icon} {short_name} ({format_bytes(t['bytes'])} / {format_bytes(t['size'])})")
                t_lbl.setToolTip(t.get("name", ""))
                t_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
                pbar = QProgressBar()
                pbar.setValue(int(t.get("percentage", 0)))
                t_box.addWidget(t_lbl)
                t_box.addWidget(pbar)
                w = QWidget()
                w.setLayout(t_box)
                self.transfers_layout.addWidget(w)
        elif self.active_hydration:
            t_box = QVBoxLayout()
            t_box.setSpacing(4)
            raw_name = self.active_hydration.get("file_name", "Descargando...")
            f_name = elide_text(raw_name, 34)
            f_bytes = self.active_hydration.get("file_bytes", 0)
            f_total = self.active_hydration.get("file_total", 0)
            f_idx = self.active_hydration.get("file_index")
            f_count = self.active_hydration.get("total_files")
            idx_str = f" ({f_idx}/{f_count})" if f_idx and f_count and f_count > 1 else ""
            pct = int((f_bytes / f_total) * 100) if f_total > 0 else 0
            t_lbl = QLabel(f"📥 Descargando: {f_name}{idx_str} ({format_bytes(f_bytes)} / {format_bytes(f_total)})")
            t_lbl.setToolTip(raw_name)
            t_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
            pbar = QProgressBar()
            pbar.setValue(pct)
            t_box.addWidget(t_lbl)
            t_box.addWidget(pbar)
            w = QWidget()
            w.setLayout(t_box)
            self.transfers_layout.addWidget(w)
        elif up_in_prog == 0 and up_queued == 0:
            idle_lbl = QLabel("✓ Todos los archivos sincronizados")
            idle_lbl.setStyleSheet("color: #10b981; font-size: 12px; padding: 4px 0;")
            self.transfers_layout.addWidget(idle_lbl)

        # Update cache gauge from rclone in-memory stats (zero disk I/O)
        if "cache_bytes_used" in stats and stats["cache_bytes_used"] > 0:
            self._render_cache_gauge(stats["cache_bytes_used"])

    def set_active_hydration(self, hydration_data):
        """Called when a file is actively being downloaded via 'Mantener en este equipo'"""
        if not hydration_data:
            self.active_hydration = None
            return

        if hydration_data.get("event") == "file_completed":
            self.add_session_completed(
                hydration_data["name"],
                hydration_data.get("size", 0),
                hydration_data.get("speed", 0),
                file_path=hydration_data.get("path"),
                direction="down"
            )
            return

        self.active_hydration = hydration_data
        speed = hydration_data.get("speed", 0)
        self.down_speed_label.setText(f"↓ Descarga: {format_bytes(speed)}/s")
        self.status_msg_label.setText("Descargando...")
        self.status_msg_label.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 13px;")

    def add_session_completed(self, file_name, file_size, speed, file_path=None, direction="down"):
        """Adds a completed download or upload to the in-memory session history (Quick Access)"""
        now = time.time()
        for prev in self.session_downloads[:3]:
            if prev.get("name") == file_name and (now - prev.get("timestamp", 0)) < 2.0:
                return

        self.active_hydration = None
        self.session_downloads.insert(0, {
            "name": file_name,
            "size": file_size,
            "speed": speed,
            "path": file_path,
            "direction": direction,
            "time": time.strftime("%H:%M:%S"),
            "timestamp": now
        })
        self.session_downloads = self.session_downloads[:20]
        self.update_session_history_ui()

    def open_downloaded_item(self, target_path):
        if target_path and os.path.exists(target_path):
            if os.path.isdir(target_path):
                subprocess.Popen(["dolphin", target_path])
            else:
                subprocess.Popen(["xdg-open", target_path])
        else:
            self.open_root_folder()

    def update_session_history_ui(self):
        while self.session_layout.count():
            item = self.session_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Show completed session downloads (Quick Access list)
        if self.session_downloads:
            for item in self.session_downloads[:8]:
                row = QHBoxLayout()
                row.setSpacing(8)

                direction = item.get("direction", "down")
                icon_str = "📥" if direction == "down" else "📤"
                color_str = "#34d399" if direction == "down" else "#38bdf8"
                short_name = elide_text(item["name"], 28)
                lbl = QLabel(f"{icon_str} <b>{short_name}</b> ({format_bytes(item['size'])})")
                lbl.setToolTip(item["name"])
                lbl.setStyleSheet(f"color: {color_str}; font-size: 12px;")
                row.addWidget(lbl)

                row.addStretch()
                time_lbl = QLabel(f"{item['time']} ({format_bytes(item['speed'])}/s)")
                time_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
                row.addWidget(time_lbl)

                open_btn = QPushButton("Abrir")
                open_btn.setObjectName("tableBtn")
                target_p = item.get("path")
                open_btn.clicked.connect(lambda _, p=target_p: self.open_downloaded_item(p))
                row.addWidget(open_btn)

                w = QWidget()
                w.setLayout(row)
                self.session_layout.addWidget(w)
        else:
            empty_lbl = QLabel(
                "No hay descargas en esta sesión (se reinicia al abrir la app).\n"
                "• Para descargar sin conexión: Clic derecho en Dolphin → 'Mantener siempre en este equipo'\n"
                "• O pulsa '🔍 Nube vs Local' para ver el estado de cada archivo y descargarlo con un clic."
            )
            empty_lbl.setStyleSheet("color: #64748b; font-size: 11px; padding: 4px; line-height: 140%;")
            empty_lbl.setWordWrap(True)
            self.session_layout.addWidget(empty_lbl)

    def _render_cache_gauge(self, used_bytes):
        try:
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

    def update_cache_gauge(self):
        run_async_task(
            self.vfs_controller.get_cache_disk_usage,
            on_finished=lambda res: self._render_cache_gauge(res.get("result", 0))
        )

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
        pending = self.vfs_controller.count_pending_uploads()
        extra_note = (
            f"\n\nNota de seguridad: Se detectaron {pending} archivo(s) aún pendientes de subir a la nube; "
            "estos archivos se protegerán automáticamente y NO serán eliminados."
            if pending > 0 else ""
        )
        reply = QMessageBox.question(
            self,
            "Liberar caché segura",
            "¿Deseas liberar el espacio de todos los archivos ya sincronizados en la nube?"
            f"{extra_note}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            res = self.vfs_controller.free_all_cache_safe()
            self.update_cache_gauge()
            freed_str = format_bytes(res.get("freed_bytes", 0))
            skipped = res.get("skipped_dirty", 0)
            if skipped > 0:
                QMessageBox.information(
                    self,
                    "Caché liberada de forma segura",
                    f"Se liberaron {freed_str} de archivos ya sincronizados.\n"
                    f"Se protegieron {skipped} archivo(s) que aún se están subiendo a la nube."
                )
            else:
                QMessageBox.information(
                    self,
                    "Éxito",
                    f"Se ha liberado la caché local de forma segura ({freed_str})."
                )
