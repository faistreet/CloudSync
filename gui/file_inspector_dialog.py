import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QFrame, QProgressBar
)

from gui.styles import MODERN_QSS
from gui.popup_window import format_bytes
from core.task_runner import run_async_task


class FileInspectorDialog(QDialog):
    action_requested = Signal(str, str) # action, path
    file_action_triggered = Signal(str, str) # backwards compatibility

    def __init__(self, config_manager, vfs_controller, initial_folder=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.vfs_controller = vfs_controller
        self.current_folder = Path(initial_folder) if initial_folder else None
        self.worker = None

        self.setWindowTitle("Explorador de Estado - Archivos en la Nube vs Local")
        self.setStyleSheet(MODERN_QSS)
        self.resize(780, 600)
        self.setMinimumSize(600, 450)

        icon_path = Path(__file__).parent.parent / "assets" / "icons" / "app_icon.svg"
        self.setWindowIcon(QIcon(str(icon_path)))

        self.init_ui()
        self.init_account_selection()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Top bar: Account Selector and Up Folder Button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        top_bar.addWidget(QLabel("<b>Cuenta:</b>"))
        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(self.on_account_changed)
        top_bar.addWidget(self.account_combo, stretch=1)

        self.up_btn = QPushButton("⬆ Subir carpeta")
        self.up_btn.setObjectName("secondaryBtn")
        self.up_btn.clicked.connect(self.navigate_up)
        top_bar.addWidget(self.up_btn)

        self.refresh_btn = QPushButton("🔄 Actualizar")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.clicked.connect(self.refresh_current_folder)
        top_bar.addWidget(self.refresh_btn)

        layout.addLayout(top_bar)

        # 2. Path Breadcrumb display
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #38bdf8; font-size: 12px; font-family: monospace; background: #1e293b; padding: 6px 10px; border-radius: 6px; border: 1px solid #334155;")
        layout.addWidget(self.path_label)

        # 3. Filter Bar: Search and Status Filter
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Buscar archivo por nombre...")
        self.search_input.textChanged.connect(self.apply_filters)
        filter_bar.addWidget(self.search_input, stretch=2)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "Todos los archivos",
            "Solo en la nube ☁️",
            "Descargados en PC 💾",
            "Pendientes de subir ⏳"
        ])
        self.filter_combo.currentIndexChanged.connect(self.apply_filters)
        filter_bar.addWidget(self.filter_combo, stretch=1)

        layout.addLayout(filter_bar)

        # 4. Progress bar for active downloads/frees
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 5. File Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Nombre", "Tamaño", "Estado de sincronización", "Acción"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e293b;
                alternate-background-color: #172033;
                border: 1px solid #334155;
                border-radius: 8px;
                gridline-color: #334155;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #334155;
            }
        """)
        layout.addWidget(self.table)

        # 6. Bottom info / close
        bottom_bar = QHBoxLayout()
        self.summary_label = QLabel("Cargando archivos...")
        self.summary_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        bottom_bar.addWidget(self.summary_label)

        bottom_bar.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)

        layout.addLayout(bottom_bar)

    def init_account_selection(self):
        accounts = self.config_manager.get_accounts()
        self.account_combo.clear()
        for acc_id, info in accounts.items():
            name = info.get("display_name", acc_id)
            email = info.get("email")
            label = f"{name} ({email})" if email else name
            mount_path = self.config_manager.get_mount_path_for_account(acc_id)
            self.account_combo.addItem(label, userData=mount_path)

        if self.account_combo.count() > 0:
            if self.current_folder:
                # Try to select the account that matches current_folder
                for i in range(self.account_combo.count()):
                    m_path = Path(self.account_combo.itemData(i))
                    try:
                        self.current_folder.relative_to(m_path)
                        self.account_combo.setCurrentIndex(i)
                        break
                    except ValueError:
                        pass
            else:
                self.current_folder = Path(self.account_combo.itemData(0))
            self.load_folder(self.current_folder)

    def on_account_changed(self, idx):
        if idx >= 0:
            m_path = self.account_combo.itemData(idx)
            if m_path:
                self.current_folder = Path(m_path)
                self.load_folder(self.current_folder)

    def load_folder(self, folder_path):
        self.current_folder = Path(folder_path).resolve()
        self.path_label.setText(str(self.current_folder))
        
        # Check if root of account to enable/disable Up button
        acc_root = Path(self.account_combo.currentData()).resolve() if self.account_combo.currentData() else None
        self.up_btn.setEnabled(acc_root is not None and self.current_folder != acc_root)

        self.all_items = self.vfs_controller.inspect_folder(self.current_folder)
        self.apply_filters()

    def apply_filters(self):
        search_query = self.search_input.text().strip().lower()
        filter_mode = self.filter_combo.currentIndex() # 0: All, 1: Cloud, 2: Local, 3: Uploading

        filtered = []
        local_count = 0
        uploading_count = 0
        cloud_count = 0

        for item in self.all_items:
            if not item["is_dir"]:
                if item["status"] == "local":
                    local_count += 1
                elif item["status"] == "uploading":
                    uploading_count += 1
                else:
                    cloud_count += 1

            # Search text match
            if search_query and search_query not in item["name"].lower():
                continue

            # Status match
            if filter_mode == 1 and item["status"] != "cloud" and not item["is_dir"]:
                continue
            if filter_mode == 2 and item["status"] != "local" and not item["is_dir"]:
                continue
            if filter_mode == 3 and item["status"] != "uploading" and not item["is_dir"]:
                continue

            filtered.append(item)

        self.populate_table(filtered)
        up_str = f" | ⏳ {uploading_count} subiendo a la nube" if uploading_count > 0 else ""
        self.summary_label.setText(
            f"Mostrando {len(filtered)} elementos | 💾 {local_count} en este equipo{up_str} | ☁️ {cloud_count} solo en la nube"
        )

    def populate_table(self, items):
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            # Column 0: Icon + Name
            name_text = f"📁  {item['name']}" if item["is_dir"] else f"📄  {item['name']}"
            name_cell = QTableWidgetItem(name_text)
            name_cell.setData(Qt.UserRole, item)
            self.table.setItem(row, 0, name_cell)

            # Column 1: Size
            size_text = "-" if item["is_dir"] else format_bytes(item["size"])
            size_cell = QTableWidgetItem(size_text)
            size_cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, size_cell)

            # Column 2: Status Badge
            if item["is_dir"]:
                if item["status"] == "uploading":
                    status_widget = QLabel("⏳ Carpeta subiendo")
                    status_widget.setObjectName("statusPillPaused")
                elif item["status"] == "local":
                    status_widget = QLabel("💾 Con datos locales")
                    status_widget.setObjectName("statusPillSuccess")
                else:
                    status_widget = QLabel("Carpeta")
                    status_widget.setStyleSheet("color: #94a3b8; font-weight: bold; padding: 2px 8px;")
            elif item["status"] == "uploading":
                status_widget = QLabel("⏳ Subiendo a la nube")
                status_widget.setObjectName("statusPillPaused")
            elif item["status"] == "local":
                status_widget = QLabel("💾 En este equipo")
                status_widget.setObjectName("statusPillSuccess")
            else:
                status_widget = QLabel("☁️ Solo en la nube")
                status_widget.setObjectName("statusPillSyncing")
            status_widget.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row, 2, status_widget)

            # Column 3: Action Button
            if item["is_dir"]:
                btn = QPushButton("📥 Descargar todo")
                btn.setObjectName("secondaryBtn")
                btn.clicked.connect(lambda _, p=item["path"]: self.trigger_action("pin", p))
                btn.setStyleSheet("padding: 2px 10px; font-size: 11px;")
                self.table.setCellWidget(row, 3, btn)
            elif item["status"] == "uploading":
                btn = QPushButton("⏳ Sincronizando...")
                btn.setObjectName("secondaryBtn")
                btn.setEnabled(False)
                btn.setToolTip("Este archivo aún se está subiendo a la nube. Se podrá liberar espacio cuando termine.")
                btn.setStyleSheet("padding: 2px 10px; font-size: 11px; color: #fbbf24;")
                self.table.setCellWidget(row, 3, btn)
            elif item["status"] == "local":
                btn = QPushButton("🗑️ Liberar espacio")
                btn.setObjectName("secondaryBtn")
                btn.clicked.connect(lambda _, p=item["path"]: self.trigger_action("free", p))
                btn.setStyleSheet("padding: 2px 10px; font-size: 11px;")
                self.table.setCellWidget(row, 3, btn)
            else:
                btn = QPushButton("📥 Descargar")
                btn.setObjectName("secondaryBtn")
                btn.clicked.connect(lambda _, p=item["path"]: self.trigger_action("pin", p))
                btn.setStyleSheet("padding: 2px 10px; font-size: 11px;")
                self.table.setCellWidget(row, 3, btn)

    def on_cell_double_clicked(self, row, col):
        item_cell = self.table.item(row, 0)
        if not item_cell:
            return
        item_data = item_cell.data(Qt.UserRole)
        if item_data and item_data.get("is_dir"):
            self.load_folder(item_data["path"])
        elif item_data and not item_data.get("is_dir"):
            import subprocess
            subprocess.Popen(["xdg-open", item_data["path"]])

    def navigate_up(self):
        if self.current_folder and self.current_folder.parent:
            self.load_folder(self.current_folder.parent)

    def refresh_current_folder(self):
        if self.current_folder:
            self.load_folder(self.current_folder)

    def trigger_action(self, action, target_path):
        fname = os.path.basename(target_path)
        if action == "pin":
            self.summary_label.setText(f"Descargando {fname}...")
        else:
            self.summary_label.setText(f"Liberando espacio de {fname}...")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Indeterminate spinner
        self.action_requested.emit(action, target_path)
        self.file_action_triggered.emit(action, target_path)

    def on_action_progress(self, data):
        if not data:
            return
        if data.get("event") == "file_completed":
            return
        self.progress_bar.setVisible(True)
        f_bytes = data.get("file_bytes", 0)
        f_total = data.get("file_total", 0)
        speed = data.get("speed", 0)
        f_name = data.get("file_name", "")
        f_idx = data.get("file_index")
        f_count = data.get("total_files")
        idx_str = f" ({f_idx}/{f_count})" if f_idx and f_count and f_count > 1 else ""

        if f_total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int((f_bytes / f_total) * 100))
        else:
            self.progress_bar.setRange(0, 0)

        self.summary_label.setText(
            f"Descargando {f_name}{idx_str} ({format_bytes(f_bytes)} / {format_bytes(f_total)}) a {format_bytes(speed)}/s"
        )

    def on_action_finished(self, res):
        self.progress_bar.setVisible(False)
        self.refresh_current_folder()
        fname = res.get("name", "Archivo")
        if res.get("success"):
            if res.get("empty_folder"):
                self.summary_label.setText(f"ℹ '{fname}' es una carpeta vacía.")
            elif "total_bytes" in res:
                b = format_bytes(res.get("total_bytes", 0))
                self.summary_label.setText(f"✓ '{fname}' ({b}) disponible sin conexión.")
            else:
                b = format_bytes(res.get("freed_bytes", 0))
                skipped = res.get("skipped_dirty", 0)
                if skipped > 0:
                    self.summary_label.setText(
                        f"✓ Liberado '{fname}' ({b}). Se protegieron {skipped} archivo(s) aún subiendo a la nube."
                    )
                else:
                    self.summary_label.setText(f"✓ Espacio liberado para '{fname}' ({b}).")
        else:
            err = res.get("error", "Error desconocido")
            QMessageBox.warning(self, "Atención", f"No se pudo completar la operación:\n{err}")

    def on_worker_finished(self, res):
        self.on_action_finished(res)
