import sys
import os
import shutil
import datetime
import multiprocessing
import concurrent.futures
from functools import partial
from pathlib import Path

import pandas as pd

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QInputDialog, QMessageBox,
    QTableView, QProgressBar, QTextEdit, QHeaderView, QSplitter
)
from PySide6.QtCore import Qt, QAbstractTableModel, QThread, Signal

# Import from existing modules
from helper import Args
from pipeline import process_csv_row, setup_loguru
from loguru import logger


class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.isValid() and role == Qt.EditRole:
            self._data.iloc[index.row(), index.column()] = value
            self.dataChanged.emit(index, index, [Qt.EditRole])
            return True
        return False

    def flags(self, index):
        return super().flags(index) | Qt.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])
        return None


class PipelineWorker(QThread):
    progress_updated = Signal(str, float, str)
    overall_progress = Signal(int, int)
    finished_processing = Signal(bool)

    def __init__(self, args_obj, styles, log_path, tasks):
        super().__init__()
        self.args_obj = args_obj
        self.styles = styles
        self.log_path = log_path
        self.tasks = tasks

    def run(self):
        total_tasks = len(self.tasks)
        if total_tasks == 0:
            self.finished_processing.emit(True)
            return

        with multiprocessing.Manager() as manager:
            progress_queue = manager.Queue()
            
            worker_func = partial(
                process_csv_row,
                original_args=self.args_obj,
                styles_dict=self.styles,
                log_path_str=str(self.log_path),
                progress_queue=progress_queue
            )

            tasks_submitted = 0
            tasks_completed = 0
            num_workers = min(os.cpu_count() or 4, 4)

            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                for i in range(min(num_workers, total_tasks)):
                    executor.submit(worker_func, self.tasks[i])
                    tasks_submitted += 1
                
                while tasks_completed < total_tasks:
                    try:
                        msg = progress_queue.get()
                        process_name, progress_pct, description = msg
                        self.progress_updated.emit(process_name, progress_pct, description)
                        
                        if progress_pct == 1.0 or progress_pct == -1.0:
                            tasks_completed += 1
                            self.overall_progress.emit(tasks_completed, total_tasks)
                            if tasks_submitted < total_tasks:
                                executor.submit(worker_func, self.tasks[tasks_submitted])
                                tasks_submitted += 1
                    except Exception as e:
                        logger.error(f"Worker Error: {e}")
                        break
        
        logger.complete()
        self.finished_processing.emit(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arrowscape - Generation Pipeline UI")
        self.resize(1000, 700)

        self.level_set_base_dir = Path(__file__).parent / "level_set"
        self.current_dataframe = None
        self.csv_path = None
        
        self.init_ui()
        self.refresh_folder_list()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Top Controls (Folder selection + Copy template)
        top_layout = QHBoxLayout()
        
        self.folder_combo = QComboBox()
        self.folder_combo.currentIndexChanged.connect(self.on_folder_selected)
        top_layout.addWidget(QLabel("Select Level Set:"))
        top_layout.addWidget(self.folder_combo, stretch=1)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_folder_list)
        top_layout.addWidget(self.btn_refresh)

        self.btn_template = QPushButton("Create from template")
        self.btn_template.clicked.connect(self.create_from_template)
        top_layout.addWidget(self.btn_template)

        main_layout.addLayout(top_layout)

        # 2. DataFrame Viewer
        self.table_view = QTableView()
        main_layout.addWidget(self.table_view, stretch=1)
        
        btn_layout = QHBoxLayout()
        self.btn_save_csv = QPushButton("Save CSV")
        self.btn_save_csv.clicked.connect(self.save_csv)
        btn_layout.addWidget(self.btn_save_csv)
        
        self.btn_run = QPushButton("Run Pipeline")
        self.btn_run.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 5px;")
        self.btn_run.clicked.connect(self.run_pipeline)
        btn_layout.addWidget(self.btn_run)
        
        main_layout.addLayout(btn_layout)

        # 3. Progress Section
        progress_layout = QVBoxLayout()
        
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setValue(0)
        progress_layout.addWidget(QLabel("Overall Progress:"))
        progress_layout.addWidget(self.overall_progress_bar)

        self.log_window = QTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setMaximumHeight(150)
        progress_layout.addWidget(self.log_window)

        main_layout.addLayout(progress_layout)
        
        self.worker = None

    def refresh_folder_list(self):
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        
        if self.level_set_base_dir.exists():
            folders = [f.name for f in self.level_set_base_dir.iterdir() if f.is_dir() and f.name != ".DS_Store"]
            folders.sort()
            self.folder_combo.addItems(folders)
        
        self.folder_combo.blockSignals(False)
        self.on_folder_selected()

    def create_from_template(self):
        template_dir = self.level_set_base_dir / "level_set_0_template"
        if not template_dir.exists():
            QMessageBox.warning(self, "Error", "Template folder 'level_set_0_template' not found!")
            return

        text, ok = QInputDialog.getText(self, "Create Folder", "Enter new level set Name (e.g. level_set_15_test):")
        if ok and text:
            new_dir = self.level_set_base_dir / text
            if new_dir.exists():
                QMessageBox.warning(self, "Error", f"Folder '{text}' already exists!")
                return
            
            try:
                shutil.copytree(template_dir, new_dir)
                QMessageBox.information(self, "Success", f"Created '{text}' successfully!")
                self.refresh_folder_list()
                
                # set combobox to new folder
                index = self.folder_combo.findText(text)
                if index >= 0:
                    self.folder_combo.setCurrentIndex(index)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clone template:\n{e}")

    def on_folder_selected(self):
        folder_name = self.folder_combo.currentText()
        if not folder_name:
            return

        selected_dir = self.level_set_base_dir / folder_name
        self.csv_path = selected_dir / "[Data] levels - test dataframe.csv"
        
        if self.csv_path.exists():
            try:
                # Load CSV
                self.current_dataframe = pd.read_csv(self.csv_path)
                self.current_dataframe.fillna("", inplace=True)
                
                model = PandasModel(self.current_dataframe)
                self.table_view.setModel(model)
                self.table_view.resizeColumnsToContents()
            except Exception as e:
                QMessageBox.warning(self, "Error loading CSV", str(e))
                self.table_view.setModel(None)
                self.current_dataframe = None
        else:
            self.table_view.setModel(None)
            self.current_dataframe = None

    def save_csv(self):
        if self.current_dataframe is not None and self.csv_path:
            try:
                self.current_dataframe.to_csv(self.csv_path, index=False)
                QMessageBox.information(self, "Success", "CSV saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save CSV: {e}")

    def run_pipeline(self):
        if self.current_dataframe is None:
            QMessageBox.warning(self, "No Data", "No CSV data loaded to run.")
            return

        # Prepare arguments
        args = Args()
        args.level_set_path = str(self.level_set_base_dir / self.folder_combo.currentText())
        args.length_step = 5
        args.min_length = 5
        args.size = (50, 50)
        args.start_length = 54
        args.turn_probability = 0.5
        args.left_weight = 1.3
        args.right_weight = 1.0
        args.straight_weight = 1.0
        args.max_turns = 18

        styles = {
            "Aztec": {"left_weight": 0, "right_weight": 2.5, "straight_weight": 5, "turn_probability": 0.5, "max_turns": 12},
            "Basic": {"left_weight": 1.0, "right_weight": 1.0, "straight_weight": 1.0, "turn_probability": 0.3, "max_turns": 18},
            "Spaghetti": {"left_weight": 1.0, "right_weight": 1.0, "straight_weight": 1.5, "turn_probability": 0.4, "max_turns": 29},
            "Country": {"left_weight": 1.3, "right_weight": 1.1, "straight_weight": 1.0, "turn_probability": 0.25, "max_turns": 13},
            "Loopy": {"left_weight": 2.7, "right_weight": 1.15, "straight_weight": 1.0, "turn_probability": 0.27, "max_turns": 14},
            "Snake": {"left_weight": 1.6, "right_weight": 1.25, "straight_weight": 1.0, "turn_probability": 0.5, "max_turns": 42},
        }

        # Save CSV first just in case
        self.save_csv()

        # We need a tasks list dict from the dataframe
        # Convert each row to dict (tương thích với process_csv_row)
        tasks = self.current_dataframe.to_dict('records')

        # Start Log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path(__file__).parent / "logs" / f"debug_{timestamp}.log"
        setup_loguru(str(log_path), enable_stderr=False)
        self.log_window.append(f"Starting pipeline. Log path: {log_path.name}")

        # Disable buttons
        self.btn_run.setEnabled(False)
        self.btn_save_csv.setEnabled(False)
        self.btn_template.setEnabled(False)
        self.folder_combo.setEnabled(False)
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setMaximum(len(tasks))

        self.worker = PipelineWorker(args, styles, log_path, tasks)
        self.worker.progress_updated.connect(self.on_worker_progress)
        self.worker.overall_progress.connect(self.on_worker_overall)
        self.worker.finished_processing.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_progress(self, process_name, progress_pct, description):
        # We will log the progress message
        self.log_window.append(f"[{process_name}] {description}")
        self.log_window.verticalScrollBar().setValue(
            self.log_window.verticalScrollBar().maximum()
        )

    def on_worker_overall(self, completed, total):
        self.overall_progress_bar.setValue(completed)
        self.overall_progress_bar.setMaximum(total)

    def on_worker_finished(self, success):
        self.log_window.append("Pipeline finished!")
        self.btn_run.setEnabled(True)
        self.btn_save_csv.setEnabled(True)
        self.btn_template.setEnabled(True)
        self.folder_combo.setEnabled(True)
        QMessageBox.information(self, "Done", "Pipeline execution finished successfully.")


if __name__ == "__main__":
    multiprocessing.freeze_support() # Optional: For PyInstaller if you ever compile this
    app = QApplication(sys.argv)
    
    # Modernize UI style slightly
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
