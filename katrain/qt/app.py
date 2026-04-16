from __future__ import annotations

import os
import signal
import sys
from collections import deque

try:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
    from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QLineEdit,
        QSplitter,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
        QDoubleSpinBox,
        QSpinBox,
    )
except ImportError as exc:
    raise SystemExit("PySide6 is required for the Qt frontend. Install with `uv sync --extra pyside6`.") from exc

from katrain.core.ai import generate_ai_move
from katrain.core.base_katrain import KaTrainBase
from katrain.core.constants import OUTPUT_ERROR, OUTPUT_INFO, PROGRAM_NAME, VERSION
from katrain.core.engine import BaseEngine, KataGoEngine
from katrain.core.game import BaseGame, Game, IllegalMoveException, KaTrainSGF
from katrain.core.game_node import GameNode
from katrain.core.sgf_parser import Move
from katrain.core.utils import evaluation_class, format_visits, var_to_grid
from katrain.gui.theme import Theme


class SignalBus(QWidget):
    state_changed = Signal()
    status_changed = Signal(str, float)
    engine_error = Signal(str, str)
    log_line = Signal(str)


class ControlsBridge:
    def __init__(self, signals: SignalBus):
        self._signals = signals

    def set_status(self, message, level=OUTPUT_INFO, check_level=True):
        del check_level
        self._signals.status_changed.emit(str(message), float(level))

    def update_players(self):
        return None


class QtKaTrain(KaTrainBase):
    def __init__(self, signals: SignalBus):
        self._signals = signals
        self.controls = ControlsBridge(signals)
        super().__init__()

    def log(self, message, level=OUTPUT_INFO):
        super().log(message, level)
        self._signals.log_line.emit(str(message))
        if level == OUTPUT_ERROR:
            self._signals.status_changed.emit(f"ERROR: {message}", float(level))

    def update_state(self, redraw_board=False):
        del redraw_board
        self._signals.state_changed.emit()

    def __call__(self, message, *args, **kwargs):
        del kwargs
        if message == "engine_recovery_popup":
            text = str(args[0]) if args else "Engine error"
            code = str(args[1]) if len(args) > 1 else ""
            self._signals.engine_error.emit(text, code)
            return
        self.log(f"Unhandled Qt UI message: {message}", OUTPUT_INFO)


class NewGameDialog(QDialog):
    def __init__(self, katrain: QtKaTrain, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Game")

        game_cfg = katrain.config("game")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.board_size = QComboBox()
        for size in ["19", "13", "9"]:
            self.board_size.addItem(size)
        self.board_size.setCurrentText(str(game_cfg["size"]))
        form.addRow("Board size", self.board_size)

        self.komi = QDoubleSpinBox()
        self.komi.setRange(-50.0, 50.0)
        self.komi.setSingleStep(0.5)
        self.komi.setValue(float(game_cfg["komi"]))
        form.addRow("Komi", self.komi)

        self.handicap = QSpinBox()
        self.handicap.setRange(0, 9)
        self.handicap.setValue(int(game_cfg["handicap"]))
        form.addRow("Handicap", self.handicap)

        self.rules = QComboBox()
        for abbr, label in BaseEngine.RULESETS_ABBR:
            self.rules.addItem(label.title(), abbr)
        current_rule = str(game_cfg["rules"]).lower()
        ix = max(0, self.rules.findData(current_rule))
        self.rules.setCurrentIndex(ix)
        form.addRow("Rules", self.rules)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            "size": self.board_size.currentText(),
            "komi": self.komi.value(),
            "handicap": self.handicap.value(),
            "rules": self.rules.currentData(),
        }


class SettingsDialog(QDialog):
    def __init__(self, katrain: QtKaTrain, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")

        engine_cfg = katrain.config("engine")

        layout = QVBoxLayout(self)

        engine_box = QGroupBox("Engine")
        engine_form = QFormLayout(engine_box)

        self.katago = QLineEdit(engine_cfg.get("katago", ""))
        engine_form.addRow("KataGo executable", self.katago)

        self.model = QLineEdit(engine_cfg.get("model", ""))
        engine_form.addRow("Main model", self.model)

        self.human_model = QLineEdit(engine_cfg.get("humanlike_model", ""))
        engine_form.addRow("Human model", self.human_model)

        self.config_path = QLineEdit(engine_cfg.get("config", ""))
        engine_form.addRow("Analysis config", self.config_path)

        self.max_visits = QSpinBox()
        self.max_visits.setRange(1, 1_000_000)
        self.max_visits.setValue(int(engine_cfg.get("max_visits", 500)))
        engine_form.addRow("Max visits", self.max_visits)

        self.fast_visits = QSpinBox()
        self.fast_visits.setRange(1, 1_000_000)
        self.fast_visits.setValue(int(engine_cfg.get("fast_visits", 25)))
        engine_form.addRow("Fast visits", self.fast_visits)

        self.max_time = QDoubleSpinBox()
        self.max_time.setRange(0.0, 600.0)
        self.max_time.setSingleStep(0.5)
        self.max_time.setValue(float(engine_cfg.get("max_time", 8.0)))
        engine_form.addRow("Max time", self.max_time)

        self.wide_root_noise = QDoubleSpinBox()
        self.wide_root_noise.setRange(0.0, 1.0)
        self.wide_root_noise.setSingleStep(0.01)
        self.wide_root_noise.setDecimals(3)
        self.wide_root_noise.setValue(float(engine_cfg.get("wide_root_noise", 0.04)))
        engine_form.addRow("Wide root noise", self.wide_root_noise)

        self.enable_ownership = QCheckBox("Include ownership in analysis")
        self.enable_ownership.setChecked(bool(engine_cfg.get("_enable_ownership", True)))
        engine_form.addRow("", self.enable_ownership)

        layout.addWidget(engine_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            "katago": self.katago.text().strip(),
            "model": self.model.text().strip(),
            "humanlike_model": self.human_model.text().strip(),
            "config": self.config_path.text().strip(),
            "max_visits": self.max_visits.value(),
            "fast_visits": self.fast_visits.value(),
            "max_time": self.max_time.value(),
            "wide_root_noise": self.wide_root_noise.value(),
            "_enable_ownership": self.enable_ownership.isChecked(),
        }


class MoveTreeWidget(QTreeWidget):
    node_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Move", "Score"])
        self.itemSelectionChanged.connect(self._emit_selection)

    def _emit_selection(self):
        items = self.selectedItems()
        if items:
            self.node_selected.emit(items[0].data(0, Qt.UserRole))

    def populate(self, root: GameNode, current: GameNode):
        self.blockSignals(True)
        self.clear()

        def add_node(parent_item, node):
            if node.is_root:
                text = "Root"
            else:
                text = f"{node.depth}. {node.player} {node.move.gtp() if node.move else 'pass'}"
            score = node.format_score() or ""
            item = QTreeWidgetItem([text, score])
            item.setData(0, Qt.UserRole, node)
            parent_item.addChild(item)
            for child in node.children:
                add_node(item, child)
            if node is current:
                self.setCurrentItem(item)
                item.setExpanded(True)
            elif current in node.nodes_in_tree:
                item.setExpanded(True)

        root_item = QTreeWidgetItem(["Game", ""])
        root_item.setData(0, Qt.UserRole, root)
        self.addTopLevelItem(root_item)
        for child in root.children:
            add_node(root_item, child)
        root_item.setExpanded(True)
        if current.is_root:
            self.setCurrentItem(root_item)
        self.blockSignals(False)


class AnalysisTable(QTableWidget):
    move_requested = Signal(str)
    selection_payload_changed = Signal(object)

    MAX_CANDIDATES = 4
    HEADERS = ["Move", "Loss"]

    def __init__(self, parent=None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.cellDoubleClicked.connect(self._request_move)
        self.itemSelectionChanged.connect(self._emit_payload)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setShowGrid(False)

    def _request_move(self, row, _column):
        item = self.item(row, 0)
        if item:
            self.move_requested.emit(item.text())

    def _emit_payload(self):
        items = self.selectedItems()
        if items:
            self.selection_payload_changed.emit(items[0].data(Qt.UserRole))
        else:
            self.selection_payload_changed.emit(None)

    def populate(self, node: GameNode):
        candidates = node.candidate_moves[: self.MAX_CANDIDATES]
        self.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            values = [
                candidate["move"],
                f"{candidate.get('pointsLost', 0):.1f}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setData(Qt.UserRole, candidate)
                self.setItem(row, col, item)
        self.resizeColumnsToContents()
        if candidates:
            self.selectRow(0)


class BoardWidget(QWidget):
    move_played = Signal(tuple)
    MAX_HINTS = 4
    _PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap] = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game: BaseGame | None = None
        self.show_hints = True
        self.show_ownership = True
        self.setMinimumSize(560, 560)

    @staticmethod
    def _hint_color(relative_points_lost: float) -> QColor:
        eval_thresholds = [12, 6, 3, 1.5, 0.5, 0]
        color = Theme.EVAL_COLORS["theme:normal"][evaluation_class(relative_points_lost, eval_thresholds)]
        return QColor.fromRgbF(color[0], color[1], color[2], 1.0)

    @staticmethod
    def _hint_layers(color: QColor, strength: float) -> list[tuple[float, float]]:
        return [
            (1.55, 0.12 * strength),
            (1.18, 0.20 * strength),
            (0.86, 0.34 * strength),
        ]

    @staticmethod
    def _hint_label(points_lost: float) -> str:
        rounded = round(points_lost, 1)
        if abs(rounded) < 0.05:
            return "0"
        return f"{rounded:.1f}".rstrip("0").rstrip(".")

    @staticmethod
    def _image_path(name: str) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "img", name)

    @classmethod
    def _scaled_pixmap(cls, name: str, width: int, height: int) -> QPixmap:
        key = (name, width, height)
        cached = cls._PIXMAP_CACHE.get(key)
        if cached is not None:
            return cached
        pixmap = QPixmap(cls._image_path(name)).scaled(
            width,
            height,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        cls._PIXMAP_CACHE[key] = pixmap
        return pixmap

    @classmethod
    def _tinted_pixmap(cls, name: str, width: int, height: int, color: QColor, alpha: float = 1.0) -> QPixmap:
        key = (f"{name}:{color.rgba()}:{alpha:.3f}", width, height)
        cached = cls._PIXMAP_CACHE.get(key)
        if cached is not None:
            return cached
        base = cls._scaled_pixmap(name, width, height)
        tinted = QPixmap(width, height)
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, base)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        overlay = QColor(color)
        overlay.setAlphaF(alpha)
        painter.fillRect(0, 0, width, height, overlay)
        painter.end()
        cls._PIXMAP_CACHE[key] = tinted
        return tinted

    def set_game(self, game: BaseGame):
        self.game = game
        self.update()

    def _metrics(self):
        if not self.game:
            return 0.0, 0.0, 1.0
        size_x, size_y = self.game.board_size
        extent = max(120, min(self.width(), self.height()) - 48)
        cell = extent / max(size_x - 1, size_y - 1)
        board_w = cell * (size_x - 1)
        board_h = cell * (size_y - 1)
        origin_x = (self.width() - board_w) / 2
        origin_y = (self.height() - board_h) / 2
        return origin_x, origin_y, cell

    def _coords_to_pixel(self, x: int, y: int) -> QPointF:
        origin_x, origin_y, cell = self._metrics()
        board_size_y = self.game.board_size[1]
        return QPointF(origin_x + x * cell, origin_y + (board_size_y - 1 - y) * cell)

    def _pixel_to_coords(self, pos) -> tuple[int, int] | None:
        origin_x, origin_y, cell = self._metrics()
        board_size_x, board_size_y = self.game.board_size
        best = None
        best_distance = cell * 0.45
        for y in range(board_size_y):
            for x in range(board_size_x):
                point = self._coords_to_pixel(x, y)
                distance = ((point.x() - pos.x()) ** 2 + (point.y() - pos.y()) ** 2) ** 0.5
                if distance < best_distance:
                    best = (x, y)
                    best_distance = distance
        return best

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#d7c49b"))
        if not self.game:
            return

        board_size_x, board_size_y = self.game.board_size
        origin_x, origin_y, cell = self._metrics()
        board_rect = QRectF(origin_x - cell * 0.6, origin_y - cell * 0.6, cell * board_size_x, cell * board_size_y)
        board_pm = self._scaled_pixmap(Theme.BOARD_TEXTURE, int(board_rect.width()), int(board_rect.height()))
        painter.drawPixmap(board_rect.toRect(), board_pm)

        line_pen = QPen(QColor("#4a3215"))
        line_pen.setWidth(2)
        painter.setPen(line_pen)
        for x in range(board_size_x):
            start = QPointF(origin_x + x * cell, origin_y)
            end = QPointF(origin_x + x * cell, origin_y + (board_size_y - 1) * cell)
            painter.drawLine(start, end)
        for y in range(board_size_y):
            start = QPointF(origin_x, origin_y + y * cell)
            end = QPointF(origin_x + (board_size_x - 1) * cell, origin_y + y * cell)
            painter.drawLine(start, end)

        if self.show_ownership and self.game.current_node.ownership:
            ownership_grid = var_to_grid(self.game.current_node.ownership, self.game.board_size)
            half = cell * 0.42
            for y in range(board_size_y):
                for x in range(board_size_x):
                    value = ownership_grid[y][x]
                    if abs(value) < 0.15:
                        continue
                    color = QColor("#1f5ba8" if value > 0 else "#d9483b")
                    color.setAlphaF(min(0.28, abs(value) * 0.28))
                    point = self._coords_to_pixel(x, y)
                    painter.fillRect(QRectF(point.x() - half, point.y() - half, half * 2, half * 2), color)

        if self.show_hints and self.game.current_node.analysis_exists:
            low_visits_threshold = self.game.katrain.config("trainer/low_visits", 25)
            for candidate in self.game.current_node.candidate_moves[: self.MAX_HINTS]:
                move = candidate.get("move")
                if not move or move == "pass":
                    continue
                point = self._coords_to_pixel(*Move.from_gtp(move).coords)
                is_best = candidate.get("order", 99) == 0
                visits = candidate.get("visits", 0)
                scale = 1.0 if visits >= low_visits_threshold or is_best else 0.78
                strength = 1.0 if visits >= low_visits_threshold or is_best else 0.72
                show_text = visits >= low_visits_threshold or is_best
                color = self._hint_color(candidate.get("pointsLost", 0.0))
                eval_radius = max(16, int(cell * 1.02 * scale))
                board_dot = self._tinted_pixmap(
                    Theme.EVAL_DOT_TEXTURE,
                    eval_radius * 2,
                    eval_radius * 2,
                    QColor("#d3a862"),
                    0.92,
                )
                painter.drawPixmap(
                    int(point.x() - eval_radius),
                    int(point.y() - eval_radius),
                    board_dot,
                )
                for radius_scale, alpha in self._hint_layers(color, strength):
                    layer_size = max(14, int(eval_radius * radius_scale))
                    overlay = self._tinted_pixmap(Theme.TOP_MOVE_TEXTURE, layer_size * 2, layer_size * 2, color, alpha)
                    painter.drawPixmap(
                        int(point.x() - layer_size),
                        int(point.y() - layer_size),
                        overlay,
                    )
                if show_text:
                    painter.setPen(QColor("#2f2416"))
                    font = painter.font()
                    font.setBold(is_best)
                    font.setPointSizeF(max(8.5, cell * 0.18))
                    painter.setFont(font)
                    painter.drawText(
                        QRectF(point.x() - eval_radius * 0.72, point.y() - eval_radius * 0.5, eval_radius * 1.44, eval_radius),
                        Qt.AlignCenter,
                        self._hint_label(candidate.get("pointsLost", 0.0)),
                    )
                if is_best:
                    accent = QColor("#15b7ff")
                    overlay = self._tinted_pixmap(
                        Theme.EVAL_DOT_TEXTURE,
                        eval_radius * 2,
                        eval_radius * 2,
                        accent,
                        0.95,
                    )
                    painter.drawPixmap(
                        int(point.x() - eval_radius),
                        int(point.y() - eval_radius),
                        overlay,
                    )

        radius = max(6, int(cell * 0.42))
        stone_size = max(14, radius * 2)
        for stone in self.game.stones:
            point = self._coords_to_pixel(*stone.coords)
            stone_pm = self._scaled_pixmap(Theme.STONE_TEXTURE[stone.player], stone_size, stone_size)
            painter.drawPixmap(int(point.x() - stone_size / 2), int(point.y() - stone_size / 2), stone_pm)

        current_move = self.game.current_node.move
        if current_move and current_move.coords:
            point = self._coords_to_pixel(*current_move.coords)
            marker_size = max(12, int(stone_size * 0.8))
            marker = self._tinted_pixmap(Theme.LAST_MOVE_TEXTURE, marker_size, marker_size, QColor("#f3bf3a"), 0.95)
            painter.drawPixmap(int(point.x() - marker_size / 2), int(point.y() - marker_size / 2), marker)

    def mousePressEvent(self, event):
        if not self.game or event.button() != Qt.LeftButton:
            return
        coords = self._pixel_to_coords(event.position())
        if coords is not None:
            self.move_played.emit(coords)


class MainWindow(QMainWindow):
    LOG_LIMIT = 400

    def __init__(self):
        super().__init__()
        self.signal_bus = SignalBus()
        self.katrain = QtKaTrain(self.signal_bus)
        self.engine: KataGoEngine | None = None
        self.game = self._create_game()
        self.log_lines = deque(maxlen=self.LOG_LIMIT)
        self._updating_note = False

        self.setWindowTitle(f"{PROGRAM_NAME} Qt")
        self.resize(1460, 920)
        self.setStyleSheet(
            """
            QMainWindow { background: #e8dfcf; }
            QToolBar { background: #ddd3c0; border: none; spacing: 6px; padding: 4px; }
            QToolButton { background: #f6f1e7; border: 1px solid #d8c6a4; border-radius: 6px; padding: 4px 8px; }
            QToolButton:checked { background: #cfb06c; color: #2b2113; }
            QGroupBox { border: 1px solid #d6c7ae; border-radius: 10px; margin-top: 8px; background: #f7f4ee; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #5a4631; }
            QTabWidget::pane { border: none; }
            QTabBar::tab { background: #efe7d8; border: 1px solid #d6c7ae; border-radius: 6px; padding: 4px 10px; margin-right: 4px; }
            QTabBar::tab:selected { background: #cfb06c; color: #2b2113; }
            QPlainTextEdit, QTreeWidget, QTableWidget, QListWidget {
                background: #fbf9f4;
                border: 1px solid #d6c7ae;
                border-radius: 8px;
            }
            """
        )

        self._build_ui()
        self._connect_signals()
        self._refresh()
        self.start_engine()

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        new_action = QAction("New", self)
        new_action.triggered.connect(self.new_game_dialog)
        toolbar.addAction(new_action)

        open_action = QAction("Open SGF", self)
        open_action.triggered.connect(self.open_sgf)
        toolbar.addAction(open_action)

        save_action = QAction("Save SGF", self)
        save_action.triggered.connect(self.save_sgf)
        toolbar.addAction(save_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        toolbar.addSeparator()

        start_engine_action = QAction("Start Engine", self)
        start_engine_action.triggered.connect(self.start_engine)
        toolbar.addAction(start_engine_action)

        restart_engine_action = QAction("Restart Engine", self)
        restart_engine_action.triggered.connect(self.restart_engine)
        toolbar.addAction(restart_engine_action)

        analyze_action = QAction("Analyze Node", self)
        analyze_action.triggered.connect(self.analyze_current_node)
        toolbar.addAction(analyze_action)

        ai_action = QAction("AI Move", self)
        ai_action.triggered.connect(self.play_ai_move)
        toolbar.addAction(ai_action)

        toolbar.addSeparator()

        undo_action = QAction("Undo", self)
        undo_action.triggered.connect(self.undo_move)
        toolbar.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.triggered.connect(self.redo_move)
        toolbar.addAction(redo_action)

        pass_action = QAction("Pass", self)
        pass_action.triggered.connect(self.pass_move)
        toolbar.addAction(pass_action)

        self.hints_action = QAction("Hints", self)
        self.hints_action.setCheckable(True)
        self.hints_action.setChecked(True)
        self.hints_action.triggered.connect(self._toggle_hints)
        toolbar.addAction(self.hints_action)

        self.ownership_action = QAction("Ownership", self)
        self.ownership_action.setCheckable(True)
        self.ownership_action.setChecked(True)
        self.ownership_action.triggered.connect(self._toggle_ownership)
        toolbar.addAction(self.ownership_action)

        central = QSplitter()
        self.setCentralWidget(central)

        self.board = BoardWidget()
        self.board.set_game(self.game)
        central.addWidget(self.board)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(
            "QLabel { background: #f4efe4; border: 1px solid #d9c7aa; border-radius: 10px; padding: 8px 10px; color: #4a3215; }"
        )
        right_layout.addWidget(self.status)

        self.sidebar_tabs = QTabWidget()
        right_layout.addWidget(self.sidebar_tabs, 1)

        review_tab = QWidget()
        review_layout = QVBoxLayout(review_tab)
        review_layout.setContentsMargins(0, 0, 0, 0)

        review_header = QGroupBox("Overview")
        review_header_layout = QVBoxLayout(review_header)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        review_header_layout.addWidget(self.summary)
        review_layout.addWidget(review_header)

        top_panel = QWidget()
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.move_tree = MoveTreeWidget()
        top_layout.addWidget(self.move_tree, 2)

        analysis_box = QWidget()
        analysis_layout = QVBoxLayout(analysis_box)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        self.analysis_table = AnalysisTable()
        analysis_layout.addWidget(self.analysis_table)
        self.comments = QPlainTextEdit()
        self.comments.setReadOnly(True)
        self.comments.setPlaceholderText("Selected hint details.")
        analysis_layout.addWidget(self.comments, 1)
        top_layout.addWidget(analysis_box, 3)
        review_layout.addWidget(top_panel, 1)

        self.sidebar_tabs.addTab(review_tab, "Play")

        notes_panel = QWidget()
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.addWidget(QLabel("Notes"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Private notes for the current node.")
        notes_layout.addWidget(self.notes)
        self.sidebar_tabs.addTab(notes_panel, "Notes")

        engine_panel = QWidget()
        engine_layout = QVBoxLayout(engine_panel)
        engine_layout.setContentsMargins(0, 0, 0, 0)
        engine_summary_box = QGroupBox("System")
        engine_summary_layout = QVBoxLayout(engine_summary_box)
        self.engine_summary = QLabel()
        self.engine_summary.setWordWrap(True)
        engine_summary_layout.addWidget(self.engine_summary)
        engine_layout.addWidget(engine_summary_box)
        engine_layout.addWidget(QLabel("Console"))
        self.log_view = QListWidget()
        engine_layout.addWidget(self.log_view, 1)

        self.sidebar_tabs.addTab(engine_panel, "System")
        self.sidebar_tabs.setCurrentIndex(0)

        central.addWidget(right)
        central.setStretchFactor(0, 3)
        central.setStretchFactor(1, 4)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(350)
        self.poll_timer.timeout.connect(self._refresh)
        self.poll_timer.start()

    def _connect_signals(self):
        self.board.move_played.connect(self.play_move)
        self.move_tree.node_selected.connect(self.select_node)
        self.analysis_table.move_requested.connect(self.play_candidate_move)
        self.analysis_table.selection_payload_changed.connect(self._show_candidate_details)
        self.notes.textChanged.connect(self._save_note)

        self.signal_bus.state_changed.connect(self._refresh)
        self.signal_bus.status_changed.connect(self._set_status)
        self.signal_bus.engine_error.connect(self._show_engine_error)
        self.signal_bus.log_line.connect(self._append_log)

    def _create_game(
        self,
        move_tree: GameNode | None = None,
        sgf_filename: str | None = None,
        analyze_fast: bool = False,
    ):
        if self.engine and self.engine.katago_process:
            game = Game(
                self.katrain, self.engine, move_tree=move_tree, sgf_filename=sgf_filename, analyze_fast=analyze_fast
            )
        else:
            game = BaseGame(self.katrain, move_tree=move_tree, sgf_filename=sgf_filename)
        self.katrain.game = game
        return game

    def _rebuild_game(self):
        if not self.game:
            self.game = self._create_game()
            return
        current = self.game.current_node
        self.game = self._create_game(move_tree=self.game.root, sgf_filename=self.game.sgf_filename, analyze_fast=True)
        self.game.set_current_node(current)

    def _append_log(self, line: str):
        if not line.strip():
            return
        self.log_lines.append(line)
        self.log_view.clear()
        self.log_view.addItems(list(self.log_lines)[-120:])
        self.log_view.scrollToBottom()

    def _set_status(self, message: str, _level: float):
        self.status.setText(message)

    def _show_engine_error(self, message: str, code: str):
        details = f"{message}\n\nCode: {code}" if code else message
        QMessageBox.critical(self, "Engine Error", details)

    def _toggle_hints(self):
        self.board.show_hints = self.hints_action.isChecked()
        self.board.update()

    def _toggle_ownership(self):
        self.board.show_ownership = self.ownership_action.isChecked()
        self.board.update()

    def _show_candidate_details(self, candidate: dict | None):
        if not candidate:
            self.comments.clear()
            return
        pv = " ".join(candidate.get("pv", [])[:8])
        lines = [
            f"{candidate.get('move', '')}  loss {candidate.get('pointsLost', 0):+.1f}  visits {format_visits(candidate.get('visits', 0))}",
        ]
        if pv:
            lines.append(f"PV {pv}")
        self.comments.setPlainText("\n".join(lines))

    def _is_scoring_position(self) -> bool:
        current = self.game.current_node
        return bool(current.parent and current.is_pass and current.parent.is_pass)

    def _refresh(self):
        if not self.game:
            return
        current = self.game.current_node
        engine_state = "Not running"
        if self.engine and self.engine.katago_process:
            if self.engine.katago_process.poll() is not None:
                engine_state = "Exited"
            elif self.engine.is_idle():
                engine_state = "Ready"
            else:
                engine_state = f"Busy ({self.engine.queries_remaining()} queries)"

        summary_lines = [f"<b>{self.game.board_size[0]}x{self.game.board_size[1]}</b>", f"move <b>{current.depth}</b>"]
        if current.analysis_exists and current.format_score():
            summary_lines.append(current.format_score())
        if self._is_scoring_position() and self.game.manual_score:
            summary_lines.append(f"result {self.game.manual_score}")
        summary_lines.append(f"to play <b>{current.next_player}</b>")
        self.summary.setText("  •  ".join(summary_lines))

        engine_lines = [
            f"Engine: {engine_state}",
            f"File: {self.game.sgf_filename or 'Unsaved game'}",
        ]
        if current.analysis_exists:
            engine_lines.append(f"Visits: {format_visits(current.root_visits)}")
        engine_lines.append(f"KaTrain {VERSION}")
        self.engine_summary.setText("\n".join(engine_lines))

        self.board.set_game(self.game)
        self.move_tree.populate(self.game.root, current)
        self.analysis_table.populate(current)
        if not current.candidate_moves:
            self.comments.setPlainText(current.comment(details=True, interactive=False))

        note = current.note or ""
        if self.notes.toPlainText() != note:
            self._updating_note = True
            self.notes.setPlainText(note)
            self._updating_note = False

    def _save_note(self):
        if self._updating_note or not self.game:
            return
        self.game.current_node.note = self.notes.toPlainText()

    def closeEvent(self, event):
        if self.engine:
            self.engine.shutdown(finish=False)
        super().closeEvent(event)

    def new_game_dialog(self):
        dialog = NewGameDialog(self.katrain, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.katrain._config["game"].update(dialog.values())
        self.katrain.save_config("game")
        self.game = self._create_game(analyze_fast=True)
        self._refresh()

    def open_sgf(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open SGF", "", "Game files (*.sgf *.gib *.ngf)")
        if not filename:
            return
        try:
            root = KaTrainSGF.parse_file(filename)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open SGF", str(exc))
            return
        self.game = self._create_game(move_tree=root, sgf_filename=filename, analyze_fast=True)
        self._refresh()

    def save_sgf(self):
        default_name = self.game.sgf_filename or os.path.join(os.getcwd(), self.game.generate_filename())
        filename, _ = QFileDialog.getSaveFileName(self, "Save SGF", default_name, "SGF files (*.sgf)")
        if not filename:
            return
        try:
            self.game.write_sgf(filename)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save SGF", str(exc))
            return
        self._refresh()

    def open_settings(self):
        dialog = SettingsDialog(self.katrain, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.katrain._config["engine"].update(dialog.values())
        self.katrain.save_config("engine")
        if self.engine and self.engine.katago_process and self.engine.katago_process.poll() is None:
            self.restart_engine()
        else:
            self._set_status("Settings saved.", OUTPUT_INFO)
        self._refresh()

    def start_engine(self):
        if self.engine and self.engine.katago_process and self.engine.katago_process.poll() is None:
            self._set_status("Engine already running.", OUTPUT_INFO)
            return
        engine = KataGoEngine(self.katrain, self.katrain.config("engine"))
        if engine.katago_process is None:
            self.engine = None
            self._set_status("Engine did not start. Check KataGo path and model settings.", OUTPUT_ERROR)
            return
        self.engine = engine
        self._rebuild_game()
        self._set_status("Engine started.", OUTPUT_INFO)
        if self.game.current_node and not self.game.current_node.analysis_exists:
            self.analyze_current_node()
        self._refresh()

    def restart_engine(self):
        if not self.engine:
            self.start_engine()
            return
        self.engine.restart()
        self._rebuild_game()
        self._set_status("Engine restarted.", OUTPUT_INFO)
        self._refresh()

    def analyze_current_node(self):
        if not self.engine or not isinstance(self.game, Game):
            self._set_status("Start the engine to analyze positions.", OUTPUT_INFO)
            return
        self.game.current_node.analyze(self.engine)
        self._set_status("Analysis requested.", OUTPUT_INFO)

    def play_ai_move(self):
        if not self.engine or not isinstance(self.game, Game):
            self._set_status("AI move requires the engine.", OUTPUT_INFO)
            return
        try:
            generate_ai_move(self.game, "ai:default", self.katrain.config("ai/ai:default") or {})
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "AI Move", str(exc))
            return
        self._refresh()

    def play_move(self, coords: tuple[int, int]):
        try:
            self.game.play(Move(coords=coords, player=self.game.current_node.next_player))
        except IllegalMoveException as exc:
            self._set_status(f"Illegal move: {exc}", OUTPUT_ERROR)
            return
        self._refresh()

    def play_candidate_move(self, move_gtp: str):
        try:
            move = Move.from_gtp(move_gtp, player=self.game.current_node.next_player)
            self.game.play(move)
        except IllegalMoveException as exc:
            self._set_status(f"Illegal move: {exc}", OUTPUT_ERROR)
            return
        self._refresh()

    def pass_move(self):
        self.game.play(Move(None, player=self.game.current_node.next_player))
        self._refresh()

    def undo_move(self):
        self.game.undo()
        self._refresh()

    def redo_move(self):
        self.game.redo()
        self._refresh()

    def select_node(self, node: GameNode):
        if not node or node is self.game.current_node:
            return
        self.game.set_current_node(node)
        self._refresh()


def run_app():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    signal.signal(signal.SIGINT, lambda *_args: (window.close(), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
