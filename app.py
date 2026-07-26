import os
import sys
import time
import torch
import logging
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QCheckBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QProgressBar, QFileDialog,
    QHeaderView, QGroupBox, QSplitter, QTextEdit, QStatusBar, QMessageBox, QMenu
)
import json
from upscaler_engine import probe_video, probe_system_encoders, run_upscale_pipeline

# ============================================================================
# LOGGING SYSTEM & CRASH HANDLER
# ============================================================================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename=f"logs/session_{time.strftime('%Y%m%d_%H%M%S')}.log",
    filemode='a',
    format='%(asctime)s - %(levelname)s - [%(threadName)s] %(module)s.%(funcName)s - %(message)s',
    level=logging.INFO
)

def global_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.critical("Uncaught UI exception", exc_info=(exc_type, exc_value, exc_tb))

sys.excepthook = global_exception_handler

# ============================================================================
# MODERN DARK STYLESHEET
# ============================================================================
DARK_STYLE = """
QMainWindow {
    background-color: #121418;
    color: #E1E6ED;
}
QWidget {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #E1E6ED;
}
QGroupBox {
    background-color: #1A1D24;
    border: 1px solid #2E3440;
    border-radius: 8px;
    margin-top: 12px;
    font-weight: bold;
    padding-top: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 6px;
    color: #61AFEF;
}
QPushButton {
    background-color: #2C323D;
    color: #FFFFFF;
    border: 1px solid #3E4452;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #3E4452;
    border-color: #61AFEF;
}
QPushButton:pressed {
    background-color: #1E222A;
}
QPushButton#primaryBtn {
    background-color: #61AFEF;
    color: #121418;
    border: none;
}
QPushButton#primaryBtn:hover {
    background-color: #79BAF2;
}
QPushButton#stopBtn {
    background-color: #E06C75;
    color: #FFFFFF;
    border: none;
}
QPushButton#stopBtn:hover {
    background-color: #E8838B;
}
QComboBox, QSpinBox {
    background-color: #21252B;
    border: 1px solid #3E4452;
    border-radius: 6px;
    padding: 6px;
    color: #ABB2BF;
}
QComboBox:hover, QSpinBox:hover {
    border-color: #61AFEF;
}
QComboBox QAbstractItemView {
    background-color: #21252B;
    border: 1px solid #3E4452;
    selection-background-color: #3E4452;
    selection-color: #61AFEF;
    color: #E1E6ED;
    padding: 4px;
    outline: none;
}
QLineEdit, QTextEdit {
    background-color: #21252B;
    border: 1px solid #3E4452;
    border-radius: 6px;
    padding: 6px;
    color: #ABB2BF;
}
QLineEdit:hover, QTextEdit:hover {
    border-color: #61AFEF;
}
QCheckBox {
    color: #E1E6ED;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #3E4452;
    background-color: #21252B;
}
QCheckBox::indicator:checked {
    background-color: #61AFEF;
    border-color: #61AFEF;
}
QTableWidget {
    background-color: #1A1D24;
    border: 1px solid #2E3440;
    border-radius: 8px;
    gridline-color: #21252B;
    color: #E1E6ED;
}
QTableWidget::item {
    color: #E1E6ED;
}
QHeaderView::section {
    background-color: #21252B;
    color: #ABB2BF;
    padding: 8px;
    font-weight: bold;
    border: none;
}
QProgressBar {
    background-color: #21252B;
    border-radius: 4px;
    text-align: center;
    color: #FFFFFF;
}
QProgressBar::chunk {
    background-color: #98C379;
    border-radius: 4px;
}
QStatusBar {
    background-color: #1A1D24;
    color: #5C6370;
}
"""

# ============================================================================
# BACKGROUND BATCH WORKER THREAD
# ============================================================================
class BatchWorker(QThread):
    progress_signal = Signal(int, dict)  # (row_index, info_dict)
    finished_signal = Signal(int, str)    # (row_index, status_msg)
    log_signal = Signal(str)

    def __init__(self, items, settings):
        super().__init__()
        self.items = items
        self.settings = settings
        self.cancel_flag = threading.Event()
        self.pause_after_current = False

    def stop(self):
        self.cancel_flag.set()

    def pause_after_item(self):
        self.pause_after_current = True

    def run(self):
        for idx, item in enumerate(self.items):
            if self.cancel_flag.is_set():
                self.finished_signal.emit(idx, "Cancelled")
                break
                
            if "Completed" in item.get('status', ''):
                self.finished_signal.emit(idx, "Completed")
                continue

            input_path = item['input_path']
            output_path = item['output_path']
            
            logging.info(f"Starting worker for: {input_path}")
            self.log_signal.emit(f"🚀 Starting upscaling: {os.path.basename(input_path)}")
            
            def progress_cb(info):
                self.progress_signal.emit(idx, info)

            try:
                res = run_upscale_pipeline(
                    input_path=input_path,
                    output_path=output_path,
                    model_path=self.settings['model_path'],
                    custom_scale=self.settings['scale'],
                    target_fps=self.settings['fps'],
                    encoder=self.settings['encoder'],
                    crf=self.settings['crf'],
                    tile_size=self.settings['tile_size'],
                    half=self.settings['half'],
                    sample_test=self.settings.get('sample_test', False),
                    target_res=self.settings.get('target_res'),
                    res_method=self.settings.get('res_method', 'lanczos'),
                    progress_cb=progress_cb,
                    cancel_event=self.cancel_flag
                )
                if self.cancel_flag.is_set():
                    logging.info(f"Worker cancelled for: {input_path}")
                    self.finished_signal.emit(idx, "Cancelled")
                else:
                    logging.info(f"Worker completed: {output_path} in {res['elapsed_time']:.1f}s")
                    self.log_signal.emit(f"✅ Completed: {os.path.basename(output_path)} in {res['elapsed_time']:.1f}s")
                    self.finished_signal.emit(idx, "Completed")
                    if self.pause_after_current:
                        self.log_signal.emit("⏸️ Queue paused after item completion as requested.")
                        break
            except Exception as e:
                logging.error(f"Worker Error on {input_path}: {e}", exc_info=True)
                self.log_signal.emit(f"❌ Error on {os.path.basename(input_path)}: {e}")
                self.finished_signal.emit(idx, f"Error: {e}")
                break

import threading

# ============================================================================
# MAIN APPLICATION WINDOW
# ============================================================================
class VideoUpscalerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("S.Q.U.I.N.T. (Super-resolution Quality Upgrades In Neural Tasks)")
        self.setGeometry(100, 100, 1300, 850)
        self.setStyleSheet(DARK_STYLE)
        self.setAcceptDrops(True)

        self.queue_items = []
        self.worker = None

        self.init_ui()
        self.probe_system_hardware()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        splitter = QSplitter(Qt.Horizontal)

        # --------------------------------------------------------------------
        # LEFT PANEL: BATCH QUEUE & CONTROL BUTTONS
        # --------------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Batch Action Bar
        btn_bar = QHBoxLayout()
        self.add_files_btn = QPushButton("📁 Add Videos")
        self.add_files_btn.clicked.connect(self.add_files_dialog)
        self.add_folder_btn = QPushButton("📂 Add Folder")
        self.add_folder_btn.clicked.connect(self.add_folder_dialog)
        self.clear_queue_btn = QPushButton("🗑️ Clear Queue")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        
        self.clear_finished_btn = QPushButton("🧹 Clear Finished")
        self.clear_finished_btn.clicked.connect(self.clear_finished)
        
        self.save_btn = QPushButton("💾 Save Job")
        self.save_btn.clicked.connect(self.save_job)
        
        self.load_btn = QPushButton("📂 Load Job")
        self.load_btn.clicked.connect(self.load_job)

        btn_bar.addWidget(self.add_files_btn)
        btn_bar.addWidget(self.add_folder_btn)
        btn_bar.addWidget(self.clear_queue_btn)
        btn_bar.addWidget(self.clear_finished_btn)
        btn_bar.addWidget(self.save_btn)
        btn_bar.addWidget(self.load_btn)
        btn_bar.addStretch()
        left_layout.addLayout(btn_bar)

        # Table View
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Input File", "Resolution", "FPS", "Progress", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 180)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.table)

        # Start / Stop Control Bar
        control_bar = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start Batch")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self.start_batch)

        self.stop_btn = QPushButton("⏹ Pause / Stop Batch")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_batch)

        self.pause_after_btn = QPushButton("⏸️ Pause After Current Item")
        self.pause_after_btn.setEnabled(False)
        self.pause_after_btn.clicked.connect(self.trigger_pause_after_item)

        control_bar.addWidget(self.start_btn)
        control_bar.addWidget(self.stop_btn)
        control_bar.addWidget(self.pause_after_btn)
        control_bar.addStretch()
        left_layout.addLayout(control_bar)

        # Log Console
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(120)
        left_layout.addWidget(self.log_console)

        splitter.addWidget(left_widget)

        # --------------------------------------------------------------------
        # RIGHT PANEL: SETTINGS CONTROLS
        # --------------------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Model Settings Group
        model_group = QGroupBox("AI Model Settings")
        model_layout = QVBoxLayout(model_group)

        model_layout.addWidget(QLabel("Select Model (.pth):"))
        self.model_combo = QComboBox()
        self.refresh_models()
        model_layout.addWidget(self.model_combo)

        model_btn_bar = QHBoxLayout()
        self.browse_model_btn = QPushButton("Browse Model...")
        self.browse_model_btn.clicked.connect(self.browse_model_file)
        model_btn_bar.addWidget(self.browse_model_btn)
        self.refresh_models_btn = QPushButton("🔄 Refresh")
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        model_btn_bar.addWidget(self.refresh_models_btn)
        model_layout.addLayout(model_btn_bar)

        right_layout.addWidget(model_group)

        # Video Output Settings Group
        out_group = QGroupBox("Video Output Settings")
        out_layout = QVBoxLayout(out_group)

        # Scale Factor
        out_layout.addWidget(QLabel("Output Resolution Scale:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["Auto (Model Native)", "1.5x", "2.0x", "3.0x", "4.0x"])
        out_layout.addWidget(self.scale_combo)

        # Target Resolution
        out_layout.addWidget(QLabel("Target Resolution:"))
        res_layout = QHBoxLayout()
        self.res_combo = QComboBox()
        self.res_combo.addItems(["Auto (Model Scale)", "Custom Resolution"])
        self.res_combo.setToolTip("Applies traditional resampling on the GPU AFTER AI model inference is complete.")
        self.res_w = QSpinBox()
        self.res_w.setRange(16, 8192)
        self.res_w.setValue(1920)
        self.res_h = QSpinBox()
        self.res_h.setRange(16, 8192)
        self.res_h.setValue(1080)
        
        self.lock_ar_cb = QCheckBox("Lock AR")
        self.lock_ar_cb.setChecked(True)
        self.lock_ar_cb.toggled.connect(lambda v: self.res_h.setEnabled(not v))
        self.res_h.setEnabled(False)

        self.res_method = QComboBox()
        self.res_method.addItems(["lanczos", "bicubic", "bilinear", "neighbor"])
        self.res_method.setToolTip("Traditional resampling method applied AFTER AI inference.")
        
        res_layout.addWidget(self.res_combo)
        res_layout.addWidget(self.res_w)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.res_h)
        res_layout.addWidget(self.lock_ar_cb)
        res_layout.addWidget(self.res_method)
        out_layout.addLayout(res_layout)
        
        self.res_w.setVisible(False)
        self.res_h.setVisible(False)
        self.lock_ar_cb.setVisible(False)
        self.res_method.setVisible(False)
        
        def toggle_custom_res(index):
            show = (index == 1)
            self.res_w.setVisible(show)
            self.res_h.setVisible(show)
            self.lock_ar_cb.setVisible(show)
            self.res_method.setVisible(show)
            
        self.res_combo.currentIndexChanged.connect(toggle_custom_res)

        # Frame Rate
        out_layout.addWidget(QLabel("Frame Rate (FPS):"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["Same as Source", "23.976 FPS", "24.0 FPS", "29.97 FPS", "30.0 FPS", "60.0 FPS"])
        out_layout.addWidget(self.fps_combo)

        # Video Encoder
        out_layout.addWidget(QLabel("Video Encoder:"))
        self.encoder_combo = QComboBox()
        self.encoder_combo.currentIndexChanged.connect(self.on_encoder_changed)
        out_layout.addWidget(self.encoder_combo)

        # Container
        out_layout.addWidget(QLabel("Output Container:"))
        self.container_combo = QComboBox()
        self.container_combo.addItems([".mkv (Recommended)", ".mp4", ".mov", ".avi"])
        out_layout.addWidget(self.container_combo)

        # Quality (CRF/CQ)
        crf_layout = QHBoxLayout()
        crf_layout.addWidget(QLabel("Quality (CQ/CRF):"))
        self.crf_label = QLabel("20")
        crf_layout.addWidget(self.crf_label)
        out_layout.addLayout(crf_layout)

        self.crf_slider = QSlider(Qt.Horizontal)
        self.crf_slider.setRange(15, 30)
        self.crf_slider.setValue(20)
        self.crf_slider.valueChanged.connect(lambda v: self.crf_label.setText(str(v)))
        out_layout.addWidget(self.crf_slider)

        right_layout.addWidget(out_group)

        # Output Folder & Naming Options Group
        path_group = QGroupBox("Output Folder & Naming")
        path_layout = QVBoxLayout(path_group)

        self.use_custom_out_cb = QCheckBox("Use Custom Output Directory")
        path_layout.addWidget(self.use_custom_out_cb)

        out_dir_bar = QHBoxLayout()
        self.out_dir_edit = QLineEdit()
        self.out_dir_edit.setPlaceholderText("Select output folder...")
        self.browse_out_btn = QPushButton("Browse...")
        self.browse_out_btn.clicked.connect(self.browse_output_dir)
        out_dir_bar.addWidget(self.out_dir_edit)
        out_dir_bar.addWidget(self.browse_out_btn)
        path_layout.addLayout(out_dir_bar)

        self.preserve_struct_cb = QCheckBox("Retain Input Subfolder Structure")
        self.preserve_struct_cb.setChecked(True)
        path_layout.addWidget(self.preserve_struct_cb)

        path_layout.addWidget(QLabel("Filename Suffix / Append:"))
        self.suffix_edit = QLineEdit("_upscaled")
        path_layout.addWidget(self.suffix_edit)

        self.append_model_cb = QCheckBox("Append Model Name to Filename")
        path_layout.addWidget(self.append_model_cb)
        
        self.overwrite_cb = QCheckBox("Overwrite existing files")
        self.overwrite_cb.setChecked(False)
        path_layout.addWidget(self.overwrite_cb)

        right_layout.addWidget(path_group)

        # Performance & Hardware Safety Group
        hw_group = QGroupBox("Performance & Memory")
        hw_layout = QVBoxLayout(hw_group)

        hw_layout.addWidget(QLabel("CUDA Tile Size (OOM Prevention):"))
        self.tile_combo = QComboBox()
        self.tile_combo.addItems(["Off (Full Frame)", "512 (Safe)", "256 (Low VRAM)", "1024 (High VRAM)"])
        hw_layout.addWidget(self.tile_combo)

        self.fp16_cb = QCheckBox("Enable FP16 Half Precision (2x Speed)")
        self.fp16_cb.setChecked(True)
        hw_layout.addWidget(self.fp16_cb)

        self.sample_cb = QCheckBox("5s Sample Test (Fast Preview)")
        hw_layout.addWidget(self.sample_cb)

        self.debug_cb = QCheckBox("Enable Session Debug Logging")
        self.debug_cb.toggled.connect(self.toggle_debug)
        hw_layout.addWidget(self.debug_cb)

        right_layout.addWidget(hw_group)
        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setSizes([750, 400])

        main_layout.addWidget(splitter)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.statusBar.showMessage("Ready")
        
        self.master_progress = QProgressBar()
        self.master_progress.setFixedWidth(300)
        self.master_progress.setValue(0)
        self.master_progress.setFormat("Job Progress: %p%")
        self.master_progress.hide()
        self.statusBar.addPermanentWidget(self.master_progress)

    # ------------------------------------------------------------------------
    # SYSTEM PROBING & MODEL SCANNING
    # ------------------------------------------------------------------------
    def toggle_debug(self, checked):
        logging.getLogger().setLevel(logging.DEBUG if checked else logging.INFO)
        logging.info(f"Debug logging {'enabled' if checked else 'disabled'} from UI.")
        self.log_console.append(f"🔧 Debug logging {'enabled' if checked else 'disabled'}.")

    def probe_system_hardware(self):
        encoders = probe_system_encoders()
        self.encoder_combo.clear()
        for enc_id, label in encoders:
            self.encoder_combo.addItem(label, userData=enc_id)

        gpu_info = "CPU Mode"
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            gpu_info = f"GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)"

        self.status_bar.showMessage(f"Hardware Detected: {gpu_info}")

    def refresh_models(self):
        self.model_combo.clear()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        found_models = []
        
        # Recursively search base_dir for any .pth files
        for root, _, files in os.walk(base_dir):
            if '.venv' in root:
                continue
            for f in sorted(files):
                if f.endswith('.pth'):
                    full_path = os.path.join(root, f)
                    rel_parent = os.path.basename(root)
                    display_name = f"{rel_parent}/{f}" if rel_parent != os.path.basename(base_dir) else f
                    found_models.append((display_name, full_path))

        for display_name, full_path in found_models:
            self.model_combo.addItem(display_name, userData=full_path)
            
        if not found_models:
            self.model_combo.addItem("No .pth models found in project folder", userData="")
            self.show_no_models_popup()

    def show_no_models_popup(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("No AI Models Found")
        msg_box.setText("<h3>No PyTorch (.pth) models found!</h3>")
        msg_box.setInformativeText(
            "To upscale videos, you need at least one PyTorch model file.<br><br>"
            "You can find and download compatible models from <b>OpenModelDB</b>:<br>"
            "<a href='https://openmodeldb.info'>https://openmodeldb.info</a><br><br>"
            "Place downloaded <code>.pth</code> files inside the <code>models/</code> folder, then click <b>🔄 Refresh</b>."
        )
        msg_box.setTextFormat(Qt.RichText)
        
        open_db_btn = msg_box.addButton("🌐 Open OpenModelDB", QMessageBox.ActionRole)
        msg_box.addButton(QMessageBox.Close)
        
        msg_box.exec()
        if msg_box.clickedButton() == open_db_btn:
            QDesktopServices.openUrl(QUrl("https://openmodeldb.info"))

    def browse_model_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PyTorch Model (.pth)", "", "PyTorch Model (*.pth)")
        if file_path:
            filename = os.path.basename(file_path)
            self.model_combo.addItem(f"Custom: {filename}", userData=file_path)
            self.model_combo.setCurrentIndex(self.model_combo.count() - 1)

    def browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.out_dir_edit.setText(folder)
            self.use_custom_out_cb.setChecked(True)

    def compute_output_path(self, path, base_folder=None):
        custom_dir = self.out_dir_edit.text().strip()
        use_custom = self.use_custom_out_cb.isChecked() and custom_dir != ""

        if use_custom:
            if base_folder and self.preserve_struct_cb.isChecked():
                rel_dir = os.path.relpath(os.path.dirname(path), base_folder)
                target_dir = os.path.normpath(os.path.join(custom_dir, rel_dir))
            else:
                target_dir = custom_dir
        else:
            target_dir = os.path.dirname(path)

        base_name, _ = os.path.splitext(os.path.basename(path))
        suffix = self.suffix_edit.text().strip()

        if self.append_model_cb.isChecked():
            model_text = self.model_combo.currentText()
            if model_text and "No .pth models" not in model_text:
                model_name = os.path.splitext(os.path.basename(model_text))[0]
                suffix += f"_{model_name}"

        container = self.container_combo.currentText().split()[0]
        out_file = f"{base_name}{suffix}{container}"
        final_path = os.path.join(target_dir, out_file)
        
        if not self.overwrite_cb.isChecked():
            counter = 1
            while os.path.exists(final_path):
                out_file = f"{base_name}{suffix}({counter}){container}"
                final_path = os.path.join(target_dir, out_file)
                counter += 1
                
        return final_path

    # ------------------------------------------------------------------------
    # DRAG & DROP & QUEUE MANAGEMENT
    # ------------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self.add_video_to_queue(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for f in files:
                        if f.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm')):
                            self.add_video_to_queue(os.path.join(root, f), base_folder=path)

    def add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Input Videos", "", "Video Files (*.mp4 *.mkv *.mov *.avi *.webm)")
        for f in files:
            self.add_video_to_queue(f)

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Videos")
        if folder:
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm')):
                        self.add_video_to_queue(os.path.join(root, f), base_folder=folder)

    def add_video_to_queue(self, path, base_folder=None):
        if base_folder is None:
            base_folder = os.path.dirname(path)
            
        try:
            info = probe_video(path)
        except Exception:
            return

        out_path = self.compute_output_path(path, base_folder=base_folder)

        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(path)))
        self.table.setItem(row, 1, QTableWidgetItem(f"{info['width']}x{info['height']}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{info['fps']:.2f}"))

        pbar = QProgressBar()
        pbar.setValue(0)
        self.table.setCellWidget(row, 3, pbar)

        self.table.setItem(row, 4, QTableWidgetItem("Queued"))

        self.queue_items.append({
            'input_path': path,
            'output_path': out_path,
            'base_folder': base_folder,
            'info': info
        })

    def clear_queue(self):
        self.table.setRowCount(0)
        self.queue_items.clear()

    def on_encoder_changed(self):
        enc = self.encoder_combo.currentData()
        if not enc: return
        
        defaults = {
            'libx264': 21,
            'libx265': 24,
            'hevc_nvenc': 24,
            'h264_nvenc': 21,
            'libaom-av1': 26,
            'av1_nvenc': 26
        }
        
        if enc in defaults:
            self.crf_slider.setValue(defaults[enc])

    # ------------------------------------------------------------------------
    # BATCH PROCESSING CONTROLS
    # ------------------------------------------------------------------------
    def get_current_settings(self):
        model_path = self.model_combo.currentData()
        if not model_path or not os.path.exists(model_path):
            raise ValueError("Please select a valid .pth model file!")

        # Scale
        scale_str = self.scale_combo.currentText()
        scale = None
        if "1.5x" in scale_str: scale = 1.5
        elif "2.0x" in scale_str: scale = 2.0
        elif "3.0x" in scale_str: scale = 3.0
        elif "4.0x" in scale_str: scale = 4.0

        # FPS
        fps_str = self.fps_combo.currentText()
        fps = None
        if "23.976" in fps_str: fps = 23.976
        elif "24.0" in fps_str: fps = 24.0
        elif "29.97" in fps_str: fps = 29.97
        elif "30.0" in fps_str: fps = 30.0
        elif "60.0" in fps_str: fps = 60.0

        # Encoder
        encoder = self.encoder_combo.currentData()

        # Tile Size
        tile_str = self.tile_combo.currentText()
        tile_size = 512
        if "256" in tile_str: tile_size = 256
        elif "1024" in tile_str: tile_size = 1024
        elif "Off" in tile_str: tile_size = 0
        
        target_res = None
        res_method = None
        if self.res_combo.currentIndex() == 1:
            w = self.res_w.value()
            h = -2 if self.lock_ar_cb.isChecked() else self.res_h.value()
            target_res = (w, h)
            res_method = self.res_method.currentText()

        return {
            'model_path': model_path,
            'scale': scale,
            'fps': fps,
            'encoder': encoder,
            'crf': self.crf_slider.value(),
            'tile_size': tile_size,
            'half': self.fp16_cb.isChecked(),
            'target_res': target_res,
            'res_method': res_method,
            'sample_test': getattr(self, 'sample_cb', QCheckBox()).isChecked()
        }

    def start_batch(self):
        if not self.queue_items:
            QMessageBox.warning(self, "Empty Queue", "Please add at least one video to the queue.")
            return

        # Recompute output paths dynamically in case settings were changed after adding to queue
        for row, item in enumerate(self.queue_items):
            status_item = self.table.item(row, 4)
            status = status_item.text() if status_item else "Queued"
            
            if "Completed" in status:
                item['status'] = status
                continue
                
            out_p = item.get('output_path', '')
            if out_p:
                part_p = out_p + '.partial'
                if os.path.exists(part_p):
                    try: os.remove(part_p)
                    except: pass

            if "Cancelled" in status and os.path.exists(out_p):
                try: os.remove(out_p)
                except: pass
                
            item['output_path'] = self.compute_output_path(item['input_path'], base_folder=item.get('base_folder'))
            item['status'] = status

        try:
            settings = self.get_current_settings()
        except Exception as e:
            QMessageBox.critical(self, "Settings Error", str(e))
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_after_btn.setEnabled(True)
        self.pause_after_btn.setText("⏸️ Pause After Current Item")
        
        # Lock UI controls
        self.add_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.load_job_btn.setEnabled(False)
        
        self.master_progress.setValue(0)
        self.master_progress.show()

        self.worker = BatchWorker(self.queue_items, settings)
        self.worker.progress_signal.connect(self.on_worker_progress)
        self.worker.finished_signal.connect(self.on_worker_finished_item)
        self.worker.log_signal.connect(self.log_console.append)
        self.worker.start()

    def stop_batch(self):
        if self.worker:
            self.worker.stop()
            self.log_console.append("⚠️ Stop signal sent. Completing current frame...")
            self.stop_btn.setEnabled(False)

    def trigger_pause_after_item(self):
        if self.worker:
            self.worker.pause_after_item()
            self.pause_after_btn.setText("⏳ Pausing After Item...")
            self.pause_after_btn.setEnabled(False)
            self.log_console.append("⏸️ Queue will pause automatically after current item finishes.")

    def on_worker_progress(self, row, info):
        if 'status_override' in info:
            self.table.setItem(row, 4, QTableWidgetItem(info['status_override']))
            return
            
        pbar = self.table.cellWidget(row, 3)
        if pbar:
            pbar.setValue(int(info['percent']))
        status_str = f"{info['fps']:.1f} FPS | ETA: {info['eta']:.0f}s"
        self.table.setItem(row, 4, QTableWidgetItem(status_str))
        
        total_items = len(self.queue_items)
        if total_items > 0:
            total_frames_in_batch = sum(item.get('info', {}).get('total_frames', 0) for item in self.queue_items)
            completed_frames = sum(item.get('info', {}).get('total_frames', 0) for i, item in enumerate(self.queue_items) if i < row or "Completed" in item.get('status', ''))
            
            # Frame-accurate progress
            if total_frames_in_batch > 0:
                current_item_total = self.queue_items[row].get('info', {}).get('total_frames', 0)
                current_item_frames = (info['percent'] / 100.0) * current_item_total
                overall_percent = ((completed_frames + current_item_frames) / total_frames_in_batch) * 100.0
                self.master_progress.setValue(int(overall_percent))
            else:
                # Fallback to naive math if frame counts are missing
                overall_percent = ((row * 100.0) + info['percent']) / total_items
                self.master_progress.setValue(int(overall_percent))

    def on_worker_finished_item(self, row, status_msg):
        self.queue_items[row]['status'] = status_msg
        self.table.setItem(row, 4, QTableWidgetItem(status_msg))
        pbar = self.table.cellWidget(row, 3)
        if pbar:
            pbar.setStyleSheet("")  # Reset styling
            if "Completed" in status_msg:
                pbar.setValue(100)
            elif "Error" in status_msg:
                pbar.setStyleSheet("QProgressBar::chunk { background-color: #E06C75; }")
            
        is_last = (row == len(self.queue_items) - 1)
        was_paused = self.worker and getattr(self.worker, 'pause_after_current', False)
        
        if is_last or "Cancelled" in status_msg or was_paused or "Error" in status_msg:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.pause_after_btn.setEnabled(False)
            self.pause_after_btn.setText("⏸️ Pause After Current Item")
            
            # Unlock UI controls
            self.add_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
            self.load_job_btn.setEnabled(True)
            if "Cancelled" in status_msg:
                self.log_console.append("🛑 Upscaling process fully stopped.")
            elif was_paused:
                self.log_console.append("⏸️ Batch paused after completed item.")
            elif "Error" in status_msg:
                self.log_console.append(f"🛑 Batch stopped due to error on item {row + 1}.")
            else:
                self.master_progress.setValue(100)
                self.statusBar.showMessage("Batch Complete!", 5000)

    def clear_finished(self):
        new_queue = []
        rows_to_remove = []
        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, 4)
            if status_item and "Completed" in status_item.text():
                rows_to_remove.append(row)
            else:
                new_queue.append(self.queue_items[row])
        
        for row in reversed(rows_to_remove):
            self.table.removeRow(row)
            
        self.queue_items = new_queue
        self.master_progress.setValue(0)
        self.log_console.append("🧹 Cleared completed items from queue.")

    def show_context_menu(self, pos):
        menu = QMenu()
        remove_action = menu.addAction("❌ Remove Selected")
        restart_action = menu.addAction("🔄 Restart Selected")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        
        if action == remove_action:
            for item in sorted(self.table.selectionModel().selectedRows(), reverse=True):
                self.table.removeRow(item.row())
                del self.queue_items[item.row()]
        elif action == restart_action:
            for item in self.table.selectionModel().selectedRows():
                row = item.row()
                self.queue_items[row]['status'] = "Queued"
                self.table.setItem(row, 4, QTableWidgetItem("Queued"))
                pbar = self.table.cellWidget(row, 3)
                if pbar: pbar.setValue(0)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        for p in sorted(paths):
            if os.path.isdir(p):
                paths_in_dir = []
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm')):
                            paths_in_dir.append(os.path.join(root, f))
                for file_p in sorted(paths_in_dir):
                    self.add_video_to_queue(file_p, base_folder=p)
            elif os.path.isfile(p) and p.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm')):
                self.add_video_to_queue(p)

    def save_job(self, auto_path=None):
        if not auto_path:
            path, _ = QFileDialog.getSaveFileName(self, "Save Job", "", "Upscaler Job (*.vuj);;JSON Files (*.json);;All Files (*)")
            if not path: return
            if not path.endswith('.vuj') and not path.endswith('.json'):
                path += '.vuj'
        else:
            path = auto_path
            
        try:
            for row in range(len(self.queue_items)):
                status_item = self.table.item(row, 4)
                if status_item:
                    self.queue_items[row]['status'] = status_item.text()
            
            job_data = {
                'queue': self.queue_items,
                'out_dir': self.out_dir_edit.text(),
                'use_custom_out': self.use_custom_out_cb.isChecked(),
                'preserve_struct': self.preserve_struct_cb.isChecked()
            }
            with open(path, 'w') as f:
                json.dump(job_data, f, indent=4)
            if not auto_path:
                self.current_job_file = path
                self.log_console.append(f"💾 Job saved to {os.path.basename(path)}")
        except Exception as e:
            if not auto_path:
                QMessageBox.critical(self, "Error", f"Failed to save job: {e}")

    def load_job(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Job", "", "Upscaler Job (*.vuj);;JSON Files (*.json);;All Files (*)")
        if not path: return
        try:
            with open(path, 'r') as f:
                job_data = json.load(f)
            
            self.clear_queue()
            self.out_dir_edit.setText(job_data.get('out_dir', ''))
            self.use_custom_out_cb.setChecked(job_data.get('use_custom_out', False))
            self.preserve_struct_cb.setChecked(job_data.get('preserve_struct', True))
            
            completed_count = 0
            for item in job_data.get('queue', []):
                in_path = item['input_path']
                if not os.path.exists(in_path):
                    continue
                # Reuse add_video_to_queue but inject saved status
                self.add_video_to_queue(in_path, base_folder=item.get('base_folder'))
                row = self.table.rowCount() - 1
                status = item.get('status', 'Queued')
                self.queue_items[row]['status'] = status
                self.table.setItem(row, 4, QTableWidgetItem(status))
                
                if "Completed" in status:
                    completed_count += 1
                    pbar = self.table.cellWidget(row, 3)
                    if pbar: pbar.setValue(100)
                
                # Delete half-done files
                if status == "Cancelled" and os.path.exists(item['output_path']):
                    try: os.remove(item['output_path'])
                    except: pass
            
            queue_len = len(job_data.get('queue', []))
            if queue_len > 0:
                self.master_progress.setValue(int((completed_count / queue_len) * 100))
            
            self.current_job_file = path
            self.log_console.append(f"📂 Job loaded from {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load job: {e}")

    def closeEvent(self, event):
        if hasattr(self, 'current_job_file') and self.current_job_file:
            self.save_job(auto_path=self.current_job_file)
        event.accept()


def main():
    logging.info("Application starting...")
    app = QApplication(sys.argv)
    window = VideoUpscalerApp()
    window.show()
    exit_code = app.exec()
    logging.info(f"Application exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
