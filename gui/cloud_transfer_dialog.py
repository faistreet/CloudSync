from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QProgressBar, QFrame, QFileDialog,
    QMessageBox, QWidget, QScrollArea, QSizePolicy
)

from gui.styles import MODERN_QSS
from gui.popup_window import format_bytes, elide_text


class CloudTransferDialog(QDialog):
    def __init__(self, config_manager, transfer_manager, initial_src_path=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.transfer_manager = transfer_manager
        self.initial_src_path = initial_src_path

        self.setWindowTitle("Transferir entre Nubes - CloudSync")
        self.setStyleSheet(MODERN_QSS)
        self.resize(660, 620)
        self.setMinimumSize(440, 460)

        icon_path = Path(__file__).parent.parent / "assets" / "icons" / "app_icon.svg"
        self.setWindowIcon(QIcon(str(icon_path)))

        self.init_ui()
        self.populate_accounts()

        self.transfer_manager.progress_updated.connect(self.on_progress_updated)
        self.transfer_manager.transfer_finished.connect(self.on_transfer_finished)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 14)
        root_layout.setSpacing(10)

        # Header
        title = QLabel("🔄 Transferir archivos o carpetas entre nubes")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        title.setWordWrap(True)
        root_layout.addWidget(title)

        subtitle = QLabel(
            "Pasa información entre cuentas diferentes o dentro de la misma nube en streaming directo "
            "(sin ocupar espacio en tu disco duro ni usar la caché local)."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        root_layout.addWidget(subtitle)

        # Scrollable content area so window remains responsive at any size
        scroll = QScrollArea()
        scroll.setObjectName("mainScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("scrollContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 2, 6, 2)
        layout.setSpacing(12)

        # 1. Source Card
        src_card = QFrame()
        src_card.setObjectName("cardFrame")
        src_layout = QVBoxLayout(src_card)
        src_layout.setContentsMargins(14, 12, 14, 12)
        src_layout.setSpacing(8)

        src_hdr = QLabel("1. ORIGEN (¿Desde dónde quieres pasar?)")
        src_hdr.setStyleSheet("font-size: 11px; font-weight: bold; color: #38bdf8; letter-spacing: 1px;")
        src_layout.addWidget(src_hdr)

        src_acc_row = QHBoxLayout()
        src_acc_row.addWidget(QLabel("Cuenta origen:"))
        self.src_acc_combo = QComboBox()
        self.src_acc_combo.currentIndexChanged.connect(self.on_src_account_changed)
        src_acc_row.addWidget(self.src_acc_combo, stretch=1)
        src_layout.addLayout(src_acc_row)

        src_path_row = QHBoxLayout()
        src_path_row.setSpacing(6)
        self.src_path_input = QLineEdit()
        self.src_path_input.setPlaceholderText("Selecciona una carpeta o archivo de origen...")
        self.src_path_input.textChanged.connect(self.update_destination_preview)
        src_path_row.addWidget(self.src_path_input, stretch=1)

        src_folder_btn = QPushButton("📁 Carpeta...")
        src_folder_btn.setObjectName("secondaryBtn")
        src_folder_btn.clicked.connect(self.browse_src_folder)
        src_path_row.addWidget(src_folder_btn)

        src_file_btn = QPushButton("📄 Archivo...")
        src_file_btn.setObjectName("secondaryBtn")
        src_file_btn.clicked.connect(self.browse_src_file)
        src_path_row.addWidget(src_file_btn)

        src_layout.addLayout(src_path_row)
        layout.addWidget(src_card)

        # 2. Destination Card
        dst_card = QFrame()
        dst_card.setObjectName("cardFrame")
        dst_layout = QVBoxLayout(dst_card)
        dst_layout.setContentsMargins(14, 12, 14, 12)
        dst_layout.setSpacing(8)

        dst_hdr = QLabel("2. DESTINO (¿Hacia qué nube y carpeta va?)")
        dst_hdr.setStyleSheet("font-size: 11px; font-weight: bold; color: #34d399; letter-spacing: 1px;")
        dst_layout.addWidget(dst_hdr)

        dst_acc_row = QHBoxLayout()
        dst_acc_row.addWidget(QLabel("Cuenta destino:"))
        self.dst_acc_combo = QComboBox()
        self.dst_acc_combo.currentIndexChanged.connect(self.update_destination_preview)
        dst_acc_row.addWidget(self.dst_acc_combo, stretch=1)
        dst_layout.addLayout(dst_acc_row)

        dst_path_row = QHBoxLayout()
        dst_path_row.setSpacing(6)
        self.dst_path_input = QLineEdit()
        self.dst_path_input.setPlaceholderText("Raíz de la nube destino (o elige una subcarpeta)...")
        self.dst_path_input.textChanged.connect(self.update_destination_preview)
        dst_path_row.addWidget(self.dst_path_input, stretch=1)

        dst_folder_btn = QPushButton("📁 Elegir carpeta...")
        dst_folder_btn.setObjectName("secondaryBtn")
        dst_folder_btn.clicked.connect(self.browse_dst_folder)
        dst_path_row.addWidget(dst_folder_btn)

        dst_layout.addLayout(dst_path_row)

        self.preview_label = QLabel("Destino final: -")
        self.preview_label.setStyleSheet(
            "color: #38bdf8; font-size: 11px; font-family: monospace; "
            "background: #0f172a; padding: 6px 10px; border-radius: 6px;"
        )
        self.preview_label.setWordWrap(True)
        dst_layout.addWidget(self.preview_label)

        layout.addWidget(dst_card)

        # 3. Mode Selection
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>Modo de operación:</b>"))
        self.mode_combo = QComboBox()
        self.mode_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mode_combo.addItem(
            "📋 Copiar (Mantener originales en la nube de origen)",
            userData="copy"
        )
        self.mode_combo.addItem(
            "✂️ Mover seguro (Solo borra del origen tras verificar en destino)",
            userData="move"
        )
        mode_row.addWidget(self.mode_combo, stretch=1)
        layout.addLayout(mode_row)

        # 4. Progress & Live Status Card
        prog_card = QFrame()
        prog_card.setObjectName("cardFrame")
        prog_layout = QVBoxLayout(prog_card)
        prog_layout.setContentsMargins(14, 12, 14, 12)
        prog_layout.setSpacing(8)

        stat_top = QHBoxLayout()
        self.status_lbl = QLabel("Listo para iniciar")
        self.status_lbl.setStyleSheet("color: #cbd5e1; font-weight: bold; font-size: 13px;")
        self.status_lbl.setWordWrap(True)
        stat_top.addWidget(self.status_lbl, stretch=1)

        self.speed_lbl = QLabel("⚡ 0 B/s")
        self.speed_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        stat_top.addWidget(self.speed_lbl)
        prog_layout.addLayout(stat_top)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)

        self.counts_lbl = QLabel("Archivos transferidos: 0 / 0 | Omitidos (ya existentes): 0")
        self.counts_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.counts_lbl.setWordWrap(True)
        prog_layout.addWidget(self.counts_lbl)

        self.active_files_layout = QVBoxLayout()
        self.active_files_layout.setSpacing(4)
        prog_layout.addLayout(self.active_files_layout)

        layout.addWidget(prog_card)
        layout.addStretch()

        scroll.setWidget(content)
        root_layout.addWidget(scroll, stretch=1)

        # 5. Action Buttons (Uniform Sizing)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.start_btn = QPushButton("🚀 Iniciar transferencia")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.start_btn.clicked.connect(self.on_start_clicked)
        btn_row.addWidget(self.start_btn, stretch=2)

        self.cancel_btn = QPushButton("⏹ Detener seguro")
        self.cancel_btn.setObjectName("dangerBtn")
        self.cancel_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        btn_row.addWidget(self.cancel_btn, stretch=2)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.close_btn.clicked.connect(self.close)
        btn_row.addWidget(self.close_btn, stretch=1)

        root_layout.addLayout(btn_row)

    def populate_accounts(self):
        accounts = self.config_manager.get_accounts()
        self.src_acc_combo.clear()
        self.dst_acc_combo.clear()

        for acc_id, info in accounts.items():
            name = info.get("display_name", acc_id)
            email = info.get("email")
            label = f"{name} ({email})" if email else name
            self.src_acc_combo.addItem(label, userData=acc_id)
            self.dst_acc_combo.addItem(label, userData=acc_id)

        # Default destination to second account if available
        if self.dst_acc_combo.count() > 1:
            self.dst_acc_combo.setCurrentIndex(1)

        if self.initial_src_path:
            p = Path(self.initial_src_path).resolve()
            for i in range(self.src_acc_combo.count()):
                acc_id = self.src_acc_combo.itemData(i)
                m_path = Path(self.config_manager.get_mount_path_for_account(acc_id)).resolve()
                try:
                    p.relative_to(m_path)
                    self.src_acc_combo.setCurrentIndex(i)
                    # Set destination to a different account by default if possible
                    if self.dst_acc_combo.count() > 1:
                        other_idx = (i + 1) % self.dst_acc_combo.count()
                        self.dst_acc_combo.setCurrentIndex(other_idx)
                    break
                except ValueError:
                    pass
            self.src_path_input.setText(str(p))

        self.update_destination_preview()

    def on_src_account_changed(self, _):
        self.update_destination_preview()

    def browse_src_folder(self):
        acc_id = self.src_acc_combo.currentData()
        if not acc_id:
            return
        mount_path = self.config_manager.get_mount_path_for_account(acc_id)
        chosen = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de origen", mount_path)
        if chosen:
            self.src_path_input.setText(chosen)

    def browse_src_file(self):
        acc_id = self.src_acc_combo.currentData()
        if not acc_id:
            return
        mount_path = self.config_manager.get_mount_path_for_account(acc_id)
        chosen, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo de origen", mount_path)
        if chosen:
            self.src_path_input.setText(chosen)

    def browse_dst_folder(self):
        acc_id = self.dst_acc_combo.currentData()
        if not acc_id:
            return
        mount_path = self.config_manager.get_mount_path_for_account(acc_id)
        chosen = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de destino", mount_path)
        if chosen:
            self.dst_path_input.setText(chosen)

    def update_destination_preview(self):
        src_acc = self.src_acc_combo.currentData()
        dst_acc = self.dst_acc_combo.currentData()
        src_path = self.src_path_input.text().strip()
        dst_path = self.dst_path_input.text().strip()

        if not src_acc or not dst_acc or not src_path:
            self.preview_label.setText("Destino final: Selecciona el origen y destino para ver la ruta final.")
            return

        _, _, src_rel, dst_rel, _ = self.transfer_manager.compute_final_destination(
            src_acc, src_path, dst_acc, dst_path
        )
        same_cloud_tag = (
            " ⚡ [Misma cuenta: Copia/Movimiento instantáneo en los servidores de la nube]"
            if src_acc == dst_acc else " ☁️ [Streaming directo en RAM: 0 B en disco local]"
        )
        self.preview_label.setText(
            f"Ruta origen:  {src_acc}:/{src_rel}\n"
            f"Ruta destino: {dst_acc}:/{dst_rel}{same_cloud_tag}"
        )

    def on_start_clicked(self):
        src_acc = self.src_acc_combo.currentData()
        dst_acc = self.dst_acc_combo.currentData()
        src_path = self.src_path_input.text().strip()
        dst_path = self.dst_path_input.text().strip()
        mode = self.mode_combo.currentData()

        if not src_path:
            QMessageBox.warning(self, "Falta origen", "Por favor selecciona un archivo o carpeta de origen.")
            return

        _, _, src_rel, dst_rel, _ = self.transfer_manager.compute_final_destination(
            src_acc, src_path, dst_acc, dst_path
        )

        if mode == "move":
            reply = QMessageBox.question(
                self,
                "Confirmar movimiento seguro",
                f"Se moverá:\n  {src_acc}:/{src_rel}\nhacia:\n  {dst_acc}:/{dst_rel}\n\n"
                "Nota de seguridad: Cada archivo solo se eliminará de la nube origen DESPUÉS "
                "de que la nube destino confirme que se guardó completo.\n\n"
                "¿Deseas comenzar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return

        ok, err = self.transfer_manager.start_transfer(src_acc, src_path, dst_acc, dst_path, mode=mode)
        if not ok:
            QMessageBox.warning(self, "Aviso", err)
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_lbl.setText("Iniciando conexión entre nubes...")
        self.status_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        self.progress_bar.setRange(0, 0)

    def on_cancel_clicked(self):
        self.transfer_manager.cancel_transfer()
        self.status_lbl.setText("Deteniendo de forma segura...")

    def on_progress_updated(self, data):
        b_done = data.get("bytes", 0)
        b_total = data.get("total_bytes", 0)
        speed = data.get("speed", 0)
        t_done = data.get("transfers", 0)
        t_total = data.get("total_transfers", 0)
        checks = data.get("checks", 0)
        ss_count = data.get("server_side_count", 0)
        eta = data.get("eta")

        if b_total > 0:
            self.progress_bar.setRange(0, 100)
            pct = int((b_done / b_total) * 100)
            self.progress_bar.setValue(min(pct, 100))
        else:
            self.progress_bar.setRange(0, 0)

        eta_str = f" | ETA: {eta}s" if eta is not None else ""
        self.status_lbl.setText(
            f"Transfiriendo: {format_bytes(b_done)} / {format_bytes(b_total)}{eta_str}"
        )

        if ss_count > 0 and speed == 0:
            self.speed_lbl.setText(f"☁️ Server-Side ({ss_count} archivos)")
        else:
            self.speed_lbl.setText(f"⚡ {format_bytes(speed)}/s")

        self.counts_lbl.setText(
            f"Archivos completados: {t_done} / {t_total} | Omitidos (ya existentes en destino): {checks}"
        )

        while self.active_files_layout.count():
            item = self.active_files_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for af in data.get("active_files", []):
            full_name = af.get("name", "")
            short_name = elide_text(full_name, 46)
            lbl = QLabel(
                f"📤 {short_name} — {af.get('percentage', 0)}% ({format_bytes(af.get('speed', 0))}/s)"
            )
            lbl.setToolTip(full_name)
            lbl.setStyleSheet("color: #cbd5e1; font-size: 11px;")
            self.active_files_layout.addWidget(lbl)

    def on_transfer_finished(self, res):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)

        while self.active_files_layout.count():
            item = self.active_files_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if res.get("cancelled"):
            self.progress_bar.setValue(0)
            self.status_lbl.setText("⏹ Transferencia detenida de forma segura (sin pérdida de datos)")
            self.status_lbl.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 13px;")
            self.speed_lbl.setText("⚡ 0 B/s")
            return

        if res.get("success"):
            self.progress_bar.setValue(100)
            t_done = res.get("transfers", 0)
            checks = res.get("checks", 0)
            b_done = format_bytes(res.get("bytes", 0))
            ss_count = res.get("server_side_count", 0)
            ss_note = f" ({ss_count} directo en servidor)" if ss_count > 0 else ""

            self.status_lbl.setText(f"✓ Transferencia completada ({b_done}){ss_note}")
            self.status_lbl.setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px;")
            self.speed_lbl.setText("✓ Completado")
            QMessageBox.information(
                self,
                "Transferencia exitosa",
                f"La operación entre nubes ha finalizado con éxito.\n\n"
                f"• Archivos transferidos: {t_done}{ss_note}\n"
                f"• Archivos omitidos (ya existían en destino): {checks}\n"
                f"• Datos transferidos: {b_done}"
            )
        else:
            self.status_lbl.setText("⚠ La transferencia finalizó con errores")
            self.status_lbl.setStyleSheet("color: #f87171; font-weight: bold; font-size: 13px;")
            err = res.get("error", "Error desconocido")
            QMessageBox.warning(
                self,
                "Error en transferencia",
                f"Ocurrió un problema durante la transferencia:\n{err}"
            )
