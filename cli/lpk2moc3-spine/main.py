import json
import os
import sys
import manager
from Core.lpk_loader import LpkLoader
from Core.utils import normalize, safe_mkdir
from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, Qt, QThread,
    pyqtSignal, pyqtSlot, QObject, QAbstractAnimation,
    pyqtProperty
)
from PyQt6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QFont,
    QPainter, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar, QSpacerItem, QStackedWidget, QGraphicsOpacityEffect
)
DARK = {
    "bg":           "#0d0d0f",
    "surface":      "#141416",
    "surface2":     "#1c1c21",
    "border":       "#2a2a32",
    "border_focus": "#5a5aff",
    "accent":       "#5a5aff",
    "accent_hover": "#7272ff",
    "accent_dim":   "#1e1e44",
    "text":         "#e8e8f0",
    "text_muted":   "#60607a",
    "text_label":   "#8888a4",
    "success":      "#3dd68c",
    "error":        "#ff5566",
    "warn":         "#ffaa44",
    "log_bg":       "#09090b",
    "log_text":     "#9090b0",
}
LIGHT = {
    "bg":           "#eeeef5",
    "surface":      "#ffffff",
    "surface2":     "#f5f5fa",
    "border":       "#d8d8e8",
    "border_focus": "#5a5aff",
    "accent":       "#5a5aff",
    "accent_hover": "#4040dd",
    "accent_dim":   "#e6e6ff",
    "text":         "#111118",
    "text_muted":   "#9090a8",
    "text_label":   "#55556a",
    "success":      "#1fa060",
    "error":        "#cc2233",
    "warn":         "#cc7700",
    "log_bg":       "#f8f8fc",
    "log_text":     "#44445a",
}
class WorkerSignals(QObject):
    log     = pyqtSignal(str)
    success = pyqtSignal(str)
    error   = pyqtSignal(str)
    done    = pyqtSignal()
class LogAreaAdapter:
    """Catches Tkinter .insert() calls from manager.py and routes them to PyQt signals."""
    def __init__(self, log_signal):
        self.log_signal = log_signal
    def configure(self, *args, **kwargs):
        pass
    def delete(self, *args, **kwargs):
        pass
    def insert(self, index, text, *args):
        text = text.strip()
        if text:
            self.log_signal.emit(text)
class ExtractionWorker(QThread):
    def __init__(self, lpk_path, config_path, output_path, model_name, mode):
        super().__init__()
        self.lpk_path    = lpk_path
        self.config_path = config_path
        self.output_path = output_path
        self.model_name  = model_name
        self.mode        = mode
        self.signals     = WorkerSignals()
    def run(self):
        try:
            manager.LogArea = LogAreaAdapter(self.signals.log)
            manager.Log = lambda msg: self.signals.log.emit(str(msg))
            self.signals.log.emit(f"📂  LPK   →  {self.lpk_path}")
            self.signals.log.emit(f"📁  Out   →  {self.output_path}")
            self.signals.log.emit(f"🏷️   Name  →  {self.model_name}  [{self.mode}]")
            loader = LpkLoader(self.lpk_path, self.config_path)
            loader.extract(self.output_path, self.model_name)
            extracted_folder = None
            if self.config_path and os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                extracted_folder = normalize(config_data.get("title", "character"))
            else:
                extracted_folder = normalize(self.model_name)
            model_dir = os.path.join(self.output_path, normalize(self.model_name))
            if self.mode == "Live2D":
                manager.SetupModel(model_dir, self.model_name)
            elif self.mode == "Spine":
                manager.SetupSpineModel(model_dir)
            self.signals.success.emit("Extraction complete!")
        except Exception as exc:
            self.signals.error.emit(str(exc))
            manager.Log(f"Error occurred: {exc}\nExtraction stopped.")
        finally:
            self.signals.done.emit()
def apply_shadow(widget, color="#000000", blur=32, offset=(0, 6)):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setColor(QColor(color))
    eff.setOffset(*offset)
    widget.setGraphicsEffect(eff)
class AnimatedButton(QPushButton):
    def __init__(self, text, theme, parent=None):
        super().__init__(text, parent)
        self._theme = theme
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self._refresh()
    def _refresh(self):
        t = self._theme
        self.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-size: 14px;
                font-weight: 600;
                letter-spacing: 0.4px;
                padding: 0 32px;
            }}
            QPushButton:hover {{ background: {t['accent_hover']}; }}
            QPushButton:pressed {{ background: {t['accent_dim']}; color: {t['accent']}; }}
            QPushButton:disabled {{ background: {t['border']}; color: {t['text_muted']}; }}
        """)
    def update_theme(self, theme):
        self._theme = theme
        self._refresh()
class GhostButton(QPushButton):
    def __init__(self, text, theme, parent=None):
        super().__init__(text, parent)
        self._theme = theme
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(80, 36)
        self._refresh()
    def _refresh(self):
        t = self._theme
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t['text_label']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                border-color: {t['accent']};
                color: {t['accent']};
                background: {t['accent_dim']};
            }}
            QPushButton:pressed {{ background: {t['accent']}; color: #fff; border-color: {t['accent']}; }}
        """)
    def update_theme(self, theme):
        self._theme = theme
        self._refresh()
class DropLineEdit(QLineEdit):
    file_dropped = pyqtSignal(str)
    def __init__(self, placeholder, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)
        self.setFixedHeight(36)
        self._refresh()
    def _refresh(self, focused=False):
        t = self._theme
        b = t['border_focus'] if focused else t['border']
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {t['surface2']};
                color: {t['text']};
                border: 1px solid {b};
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
            }}
            QLineEdit::placeholder {{ color: {t['text_muted']}; }}
        """)
    def update_theme(self, theme):
        self._theme = theme
        self._refresh()
    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._refresh(True)
    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._refresh(False)
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._refresh(True)
    def dragLeaveEvent(self, e):
        self._refresh(False)
    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.setText(path)
            self.file_dropped.emit(path)
        self._refresh(False)
class FieldRow(QWidget):
    def __init__(self, label, placeholder, btn_text, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.lbl = QLabel(label)
        self.lbl.setFixedWidth(96)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.entry = DropLineEdit(placeholder, theme)
        lay.addWidget(self.lbl)
        lay.addWidget(self.entry)
        if btn_text:
            self.btn = GhostButton(btn_text, theme)
            lay.addWidget(self.btn)
        else:
            self.btn = None
        self._refresh()
    def _refresh(self):
        t = self._theme
        self.lbl.setStyleSheet(
            f"color: {t['text_label']}; font-size: 12px; font-weight: 500; background: transparent;")
    def update_theme(self, theme):
        self._theme = theme
        self.entry.update_theme(theme)
        if self.btn:
            self.btn.update_theme(theme)
        self._refresh()
class ThemeToggle(QWidget):
    toggled = pyqtSignal(bool)   
    def __init__(self, is_dark=True, parent=None):
        super().__init__(parent)
        self._dark = is_dark
        self.setFixedSize(40, 24) 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._knob_x = 20.0 if is_dark else 0.0 
        self._anim = QPropertyAnimation(self, b"knob_x")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    @pyqtProperty(float)
    def knob_x(self):
        return self._knob_x
    @knob_x.setter
    def knob_x(self, v):
        self._knob_x = v
        self.update()
    def mousePressEvent(self, e):
        self._dark = not self._dark
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(20.0 if self._dark else 0.0) 
        self._anim.start()
        self.toggled.emit(self._dark)
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5a5aff") if self._dark else QColor("#c0c0d0"))
        p.drawRoundedRect(0, 4, 40, 16, 8, 8) 
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(self._knob_x), 2, 20, 20) 
        p.end()
class LargeDropZone(QLabel):
    file_dropped = pyqtSignal(str)
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setText("Drop .lpk file here")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()
    def _refresh(self, drag_active=False):
        t = self._theme
        b = t['accent'] if drag_active else t['border']
        bg = t['accent_dim'] if drag_active else t['surface2']
        text_color = t['accent'] if drag_active else t['text_muted']
        self.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                color: {text_color};
                border: 2px dashed {b};
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
            }}
        """)
    def update_theme(self, theme):
        self._theme = theme
        self._refresh()
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            urls = e.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.lpk'):
                e.acceptProposedAction()
                self._refresh(True)
    def dragLeaveEvent(self, e):
        self._refresh(False)
    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith('.lpk'):
                self.file_dropped.emit(path)
        self._refresh(False)
class SegmentedControl(QWidget):
    mode_changed = pyqtSignal(str)
    def __init__(self, options, theme, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._theme = theme
        self._options = options
        self._active = options[0]
        self.setFixedHeight(36)
        self._slider = QWidget(self)
        self._slider.setObjectName("slider")
        self._anim = QPropertyAnimation(self._slider, b"geometry")
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(2, 2, 2, 2) 
        self._lay.setSpacing(0)
        self._btns = {}
        for opt in options:
            btn = QPushButton(opt)
            btn.setFixedHeight(32)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, o=opt: self._select(o))
            self._btns[opt] = btn
            self._lay.addWidget(btn)
        self._refresh()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._active in self._btns:
            self._slider.setGeometry(self._btns[self._active].geometry())
    def _select(self, opt):
        if self._active == opt:
            return
        self._active = opt
        self._refresh()
        self.mode_changed.emit(opt)
        target_geo = self._btns[opt].geometry()
        self._anim.stop()
        self._anim.setStartValue(self._slider.geometry())
        self._anim.setEndValue(target_geo)
        self._anim.start()
    def get_mode(self):
        return self._active
    def _refresh(self):
        t = self._theme
        self.setStyleSheet(f"""
            SegmentedControl {{
                background: {t['surface2']};
                border: 1px solid {t['border']};
                border-radius: 8px;
            }}
            QWidget#slider {{
                background: {t['accent']};
                border-radius: 6px;
            }}
        """)
        for opt, btn in self._btns.items():
            active = (opt == self._active)
            color = "#ffffff" if active else t['text_muted']
            weight = "600" if active else "500"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {color};
                    border: none;
                    font-size: 13px; 
                    font-weight: {weight};
                    padding: 0 24px; /* <--- This padding fixes the clumped look */
                }}
                QPushButton:hover {{
                    color: {"#ffffff" if active else t['text']};
                }}
            """)
    def update_theme(self, theme):
        self._theme = theme
        self._refresh()
class LogConsole(QTextEdit):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setReadOnly(True)
        self.setFixedHeight(128)
        self._refresh()
    def _refresh(self):
        t = self._theme
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {t['log_bg']};
                color: {t['log_text']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 10px 12px;
                font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
                font-size: 12px;
            }}
        """)
    def append_log(self, msg, color=None):
        if color:
            self.append(f'<span style="color:{color}; font-family: monospace;">{msg}</span>')
        else:
            self.append(msg)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
    def update_theme(self, theme):
        self._theme = theme
        self._refresh()
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._dark   = True
        self._express_mode = False
        self._theme  = DARK.copy()
        self._worker = None
        self._drag_pos = None
        self.setWindowTitle("LPK Extractor")
        self.setFixedSize(580, 540)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()
        self._wire()
        self._fade_in()
        self._log.append_log("  LPK Model Extractor  —  ready")
        self._log.append_log("  Drop files onto the fields or use Browse buttons.")
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
    def mouseReleaseEvent(self, e):
        self._drag_pos = None
    def _build_ui(self):
        t = self._theme
        self._card = QWidget(self)
        self._card.setObjectName("card")
        self._card.setGeometry(10, 10, 580, 540)
        root_lay = QVBoxLayout(self._card)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        self._tbar = QWidget()
        self._tbar.setObjectName("tbar")
        self._tbar.setFixedHeight(50)
        tbar_lay = QHBoxLayout(self._tbar)
        tbar_lay.setContentsMargins(20, 0, 14, 0)
        tbar_lay.setSpacing(8)
        dot = QLabel("⬡")
        dot.setObjectName("dot")
        self._title = QLabel("LPK Extractor")
        self._title.setObjectName("title")
        sp = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._btn_settings = QPushButton("⚙")
        self._btn_min   = QPushButton("–")
        self._btn_close = QPushButton("×")
        for b in (self._btn_settings, self._btn_min, self._btn_close):
            b.setFixedSize(28, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setObjectName("wmbtn")
        tbar_lay.addWidget(dot)
        tbar_lay.addWidget(self._title)
        tbar_lay.addItem(sp)
        tbar_lay.addWidget(self._btn_settings)
        tbar_lay.addWidget(self._btn_min)
        tbar_lay.addWidget(self._btn_close)
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setObjectName("div")
        div.setFixedHeight(1)
        self._stack = QStackedWidget()
        self._main_body = QWidget()
        self._main_body.setObjectName("body")
        body_lay = QVBoxLayout(self._main_body)
        body_lay.setContentsMargins(24, 20, 24, 22)
        body_lay.setSpacing(13)
        self._lpk_row    = FieldRow("LPK File",    "Drop .lpk here or Browse…", "Browse", t)
        self._cfg_row    = FieldRow("config.json", "Drop JSON here or Browse…", "Browse", t)
        self._out_row    = FieldRow("Output",      "Drop folder here or Browse…","Browse", t)
        self._name_row   = FieldRow("Model Name",  "e.g. Mona",             None,     t)
        self._name_row.entry.setText("Character")
        mode_row_w = QWidget()
        mode_row_w.setObjectName("transparent_wrap")
        self._mode_row_lay = QHBoxLayout(mode_row_w)
        self._mode_row_lay.setContentsMargins(0, 0, 0, 0)
        self._mode_row_lay.setSpacing(10)
        self._mode_lbl = QLabel("Mode")
        self._mode_lbl.setFixedWidth(96)
        self._mode_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._mode_ctrl = SegmentedControl(["Live2D", "Spine"], t)
        self._mode_row_lay.addWidget(self._mode_lbl)
        self._mode_row_lay.addWidget(self._mode_ctrl)
        self._mode_row_lay.addStretch()
        self._log = LogConsole(t)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.hide()
        self._extract_btn = AnimatedButton("Extract Model", t)
        self._extract_btn.setFixedWidth(190)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._extract_btn)
        btn_row.addStretch()
        self._large_drop_zone = LargeDropZone(t)
        self._large_drop_zone.hide() 
        body_lay.addWidget(self._lpk_row)
        body_lay.addWidget(self._cfg_row)
        body_lay.addWidget(self._out_row)
        body_lay.addWidget(self._name_row)
        body_lay.addWidget(self._large_drop_zone)
        body_lay.addWidget(mode_row_w)
        body_lay.addWidget(self._log)
        body_lay.addWidget(self._progress)
        body_lay.addLayout(btn_row)
        self._stack.addWidget(self._main_body)
        self._settings_body = QWidget()
        self._settings_body.setObjectName("body")
        set_lay = QVBoxLayout(self._settings_body)
        set_lay.setContentsMargins(30, 30, 30, 30)
        self._lbl_appearance = QLabel("Appearance")
        theme_row = QHBoxLayout()
        self._lbl_theme_desc = QLabel("Dark Mode")
        self._toggle = ThemeToggle(is_dark=self._dark)
        theme_row.addWidget(self._lbl_theme_desc)
        theme_row.addStretch()
        theme_row.addWidget(self._toggle)
        express_row = QHBoxLayout()
        self._lbl_express_desc = QLabel("Express Mode")
        self._toggle_express = ThemeToggle(is_dark=self._express_mode)
        express_row.addWidget(self._lbl_express_desc)
        express_row.addStretch()
        express_row.addWidget(self._toggle_express)
        self._btn_back = GhostButton("Return", t)
        self._btn_back.setFixedWidth(70)
        set_lay.addWidget(self._lbl_appearance)
        set_lay.addLayout(theme_row)
        set_lay.addLayout(express_row)
        set_lay.addStretch()
        set_lay.addWidget(self._btn_back, alignment=Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._settings_body)
        root_lay.addWidget(self._tbar)
        root_lay.addWidget(div)
        root_lay.addWidget(self._stack)
        self._dot = dot
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self._card)
        self._apply_theme()
    def _wire(self):
        self._btn_close.clicked.connect(self._fade_out_and_close)
        self._btn_min.clicked.connect(self.showMinimized)
        self._btn_settings.clicked.connect(self._open_settings)
        self._btn_back.clicked.connect(self._close_settings)
        self._toggle.toggled.connect(self._on_toggle)
        self._toggle_express.toggled.connect(self._on_express_toggle)
        self._lpk_row.btn.clicked.connect(self._browse_lpk)
        self._cfg_row.btn.clicked.connect(self._browse_cfg)
        self._out_row.btn.clicked.connect(self._browse_out)
        self._lpk_row.entry.file_dropped.connect(self._on_drop_lpk)
        self._cfg_row.entry.file_dropped.connect(self._on_drop_cfg)
        self._out_row.entry.file_dropped.connect(self._on_drop_out)
        self._extract_btn.clicked.connect(self._extract)
        self._large_drop_zone.file_dropped.connect(self._on_express_drop)
    def _fade_to_page(self, widget, title, show_btn):
        self._stack.setCurrentWidget(widget)
        self._title.setText(title)
        self._btn_settings.setVisible(show_btn)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        self._page_anim = QPropertyAnimation(effect, b"opacity")
        self._page_anim.setDuration(200)
        self._page_anim.setStartValue(0.0)
        self._page_anim.setEndValue(1.0)
        self._page_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._page_anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._page_anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    def _open_settings(self):
        self._fade_to_page(self._settings_body, "Settings", False)
    def _close_settings(self):
        self._fade_to_page(self._main_body, "LPK Extractor", True)
    def _on_toggle(self, dark):
        self._start_theme_transition()
        self._dark = dark
        self._theme = DARK.copy() if dark else LIGHT.copy()
        self._lbl_theme_desc.setText("Dark Mode" if dark else "Light Mode")
        self._apply_theme()
    def _on_express_toggle(self, express):
        self._express_mode = express
        self._lpk_row.setVisible(not express)
        self._cfg_row.setVisible(not express)
        self._out_row.setVisible(not express)
        self._name_row.setVisible(not express)
        self._extract_btn.setVisible(not express)
        self._large_drop_zone.setVisible(express)
        self._mode_lbl.setVisible(not express)
        if express:
            self._log.setMinimumHeight(128)
            self._log.setMaximumHeight(16777215)
            self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._large_drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self._log.setFixedHeight(128)
            self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._large_drop_zone.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        if express:
            self._mode_row_lay.insertStretch(0)
        else:
            item = self._mode_row_lay.itemAt(0)
            if item and item.spacerItem():
                self._mode_row_lay.takeAt(0)
    def _on_express_drop(self, path):
        self._lpk_row.entry.setText(path)
        folder = os.path.dirname(path)
        cfg = os.path.join(folder, "config.json")
        self._cfg_row.entry.setText(cfg if os.path.exists(cfg) else "")
        self._out_row.entry.setText(os.path.join(folder, "output"))
        if os.path.exists(cfg):
            self._read_name(cfg)
        else:
            self._name_row.entry.setText("character")
        self._extract()
    def _start_theme_transition(self):
        pixmap = self.grab()
        self._overlay = QLabel(self)
        self._overlay.setPixmap(pixmap)
        self._overlay.resize(self.size())
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._overlay.show()
        self._overlay_effect = QGraphicsOpacityEffect(self._overlay)
        self._overlay.setGraphicsEffect(self._overlay_effect)
        self._theme_anim = QPropertyAnimation(self._overlay_effect, b"opacity")
        self._theme_anim.setDuration(350) 
        self._theme_anim.setStartValue(1.0)
        self._theme_anim.setEndValue(0.0)
        self._theme_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._theme_anim.finished.connect(self._overlay.deleteLater)
        self._theme_anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    def _apply_theme(self):
        t = self._theme
        self._card.setStyleSheet(f"#card {{ background: {t['bg']}; border-radius: 16px; border: 1px solid {t['border']}; }}")
        self._tbar.setStyleSheet(f"""
            #tbar {{
                background: {t['surface']};
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }}
        """)
        for f in self._card.findChildren(QFrame):
            if f.objectName() == "div":
                f.setStyleSheet(f"background: {t['border']}; border: none;")
        for w in self._card.findChildren(QWidget):
            if w.objectName() == "body":
                w.setStyleSheet(f"""
                    #body {{ 
                        background: {t['bg']}; 
                        border-bottom-left-radius: 15px; 
                        border-bottom-right-radius: 15px; 
                    }}
                """)
        self._dot.setStyleSheet(f"color: {t['accent']}; font-size: 17px; background: transparent;")
        self._title.setStyleSheet(
            f"color: {t['text']}; font-size: 15px; font-weight: 700; letter-spacing: 0.3px; background: transparent;")
        for b, txt_col in [(self._btn_settings, t['text_muted']), (self._btn_min, t['text_muted']), (self._btn_close, t['text_muted'])]:
            b.setStyleSheet(f"""
                QPushButton#wmbtn {{
                    background: transparent; color: {txt_col};
                    border: none; font-size: 18px; border-radius: 6px;
                }}
                QPushButton#wmbtn:hover {{ background: {t['border']}; color: {t['text']}; }}
            """)
        for row in (self._lpk_row, self._cfg_row, self._out_row, self._name_row):
            row.update_theme(t)
        self._large_drop_zone.update_theme(t)
        self._mode_lbl.setStyleSheet(
            f"color: {t['text_label']}; font-size: 12px; font-weight: 500; background: transparent;")
        self._lbl_appearance.setStyleSheet(f"color: {t['text']}; font-size: 16px; font-weight: 700; background: transparent;")
        self._lbl_theme_desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 13px; font-weight: 450; background: transparent;")
        self._lbl_express_desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 13px; font-weight: 450; background: transparent;")
        self._btn_back.update_theme(t)
        self._mode_ctrl.update_theme(t)
        self._log.update_theme(t)
        self._extract_btn.update_theme(t)
        self._progress.setStyleSheet(f"""
            QProgressBar {{ background: {t['border']}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {t['accent']}; border-radius: 2px; }}
        """)
    def _fade_in(self):
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    def _fade_out_and_close(self):
        self._btn_close.setEnabled(False) 
        self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_out_anim.setDuration(250)
        self._fade_out_anim.setStartValue(1.0)
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_out_anim.finished.connect(self.close)
        self._fade_out_anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    def _browse_lpk(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select LPK file", "", "LPK (*.lpk)")
        if p:
            self._lpk_row.entry.setText(p)
            self._on_drop_lpk(p)
    def _browse_cfg(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select config.json", "", "JSON (*.json)")
        if p:
            self._cfg_row.entry.setText(p)
            self._on_drop_cfg(p)
    def _browse_out(self):
        p = QFileDialog.getExistingDirectory(self, "Select output folder")
        if p:
            self._out_row.entry.setText(p)
    def _on_drop_lpk(self, path):
        if not path.lower().endswith(".lpk"):
            return
        folder = os.path.dirname(path)
        cfg = os.path.join(folder, "config.json")
        if self._express_mode:
            self._cfg_row.entry.setText(cfg if os.path.exists(cfg) else "")
            self._out_row.entry.setText(os.path.join(folder, "output"))
            if os.path.exists(cfg):
                self._read_name(cfg)
            else:
                self._name_row.entry.setText("character")
        else:
            if os.path.exists(cfg) and not self._cfg_row.entry.text():
                self._cfg_row.entry.setText(cfg)
                self._read_name(cfg)
            if not self._out_row.entry.text():
                self._out_row.entry.setText(os.path.join(folder, "output"))
    def _on_drop_cfg(self, path):
        if not path.lower().endswith(".json"):
            return
        folder = os.path.dirname(path)
        if not self._lpk_row.entry.text():
            for f in os.listdir(folder):
                if f.endswith(".lpk"):
                    self._lpk_row.entry.setText(os.path.join(folder, f))
                    break
        if not self._out_row.entry.text():
            self._out_row.entry.setText(os.path.join(folder, "output"))
        self._read_name(path)
    def _on_drop_out(self, path):
        if os.path.isfile(path):
            self._out_row.entry.setText(os.path.dirname(path))
    def _read_name(self, cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw  = data.get("title", "character")
            safe = "".join(c for c in raw if c not in r'\/:*?"<>|')
            self._name_row.entry.setText(safe)
        except Exception:
            pass
    def _extract(self):
        if self._worker and self._worker.isRunning():
            self._log.append_log("⚠️  Already running…", color=self._theme['warn'])
            return
        lpk    = self._lpk_row.entry.text().strip()
        cfg    = self._cfg_row.entry.text().strip()
        out    = self._out_row.entry.text().strip()
        name   = self._name_row.entry.text().strip() or "character"
        mode   = self._mode_ctrl.get_mode()
        if not lpk or not out:
            self._log.append_log("⚠️  LPK file and output path are required.",
                                 color=self._theme['warn'])
            return
        self._log.clear()
        self._extract_btn.setEnabled(False)
        self._extract_btn.setText("Extracting…")
        self._progress.show()
        self._worker = ExtractionWorker(lpk, cfg, out, name, mode)
        self._worker.signals.log.connect(
            lambda m: self._log.append_log(m))
        self._worker.signals.success.connect(
            lambda m: self._log.append_log(f"✅ {m}", color=self._theme['success']))
        self._worker.signals.error.connect(
            lambda m: self._log.append_log(f"❌ {m}", color=self._theme['error']))
        self._worker.signals.done.connect(self._on_done)
        self._worker.start()
    @pyqtSlot()
    def _on_done(self):
        self._extract_btn.setEnabled(True)
        self._extract_btn.setText("Extract Model")
        self._progress.hide()
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LPK Extractor")
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
