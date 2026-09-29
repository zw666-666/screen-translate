"""
屏幕选区覆盖层
全屏半透明遮罩，用户拖拽鼠标框选需要翻译的区域
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QCursor


class ScreenOverlay(QWidget):
    """全屏选区覆盖层"""

    selection_done = pyqtSignal(int, int, int, int)
    selection_cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._update_screen_geometry()

        self._reset_state()

        self.setCursor(Qt.CrossCursor)
        self.mask_color = QColor(0, 0, 0, 120)
        self.border_color = QColor(0, 122, 255)
        self.border_pen = QPen(self.border_color, 2, Qt.DashLine)

    def _reset_state(self):
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_selecting = False
        self.selection_rect = QRect()

    def _update_screen_geometry(self):
        total_rect = QRect()
        for screen in QApplication.screens():
            total_rect = total_rect.united(screen.geometry())
        self.setGeometry(total_rect)

    def show(self):
        self._reset_state()
        self._update_screen_geometry()
        super().show()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._reset_state()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_selecting = True
            self.selection_rect = QRect()
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_point = event.pos()
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.end_point = event.pos()
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()

            if self.selection_rect.width() < 20 or self.selection_rect.height() < 20:
                self._reset_state()
                self.hide()
                self.selection_cancelled.emit()
                return

            global_top_left = self.mapToGlobal(self.selection_rect.topLeft())
            rx = global_top_left.x()
            ry = global_top_left.y()
            rw = self.selection_rect.width()
            rh = self.selection_rect.height()
            self._reset_state()
            self.hide()
            self.selection_done.emit(rx, ry, rw, rh)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.selection_cancelled.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(self.mask_color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())

        if not self.selection_rect.isNull() and self.selection_rect.width() > 0:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.drawRect(self.selection_rect)

            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(self.border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.selection_rect)

            self._draw_corners(painter, self.selection_rect)

            if self.is_selecting:
                self._draw_size_label(painter, self.selection_rect)

        if not self.is_selecting and self.selection_rect.isNull():
            painter.setPen(QColor(255, 255, 255, 180))
            painter.setFont(QFont("Microsoft YaHei", 16))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "拖拽鼠标框选需要翻译的区域 | ESC 取消")

        painter.end()

    def _draw_size_label(self, painter, rect):
        size_text = f"{rect.width()} x {rect.height()}"
        painter.setPen(Qt.white)
        painter.setFont(QFont("Microsoft YaHei", 10))
        tr = QRect(rect.right() - 140, rect.top() - 30, 130, 25)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(tr, 4, 4)
        painter.setPen(Qt.white)
        painter.drawText(tr, Qt.AlignCenter, size_text)

    def _draw_corners(self, painter, rect):
        corner_len, corner_width = 10, 3
        pen = QPen(self.border_color, corner_width, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), QPoint(rect.left() + corner_len, rect.top()))
        painter.drawLine(rect.topLeft(), QPoint(rect.left(), rect.top() + corner_len))
        painter.drawLine(rect.topRight(), QPoint(rect.right() - corner_len, rect.top()))
        painter.drawLine(rect.topRight(), QPoint(rect.right(), rect.top() + corner_len))
        painter.drawLine(rect.bottomLeft(), QPoint(rect.left() + corner_len, rect.bottom()))
        painter.drawLine(rect.bottomLeft(), QPoint(rect.left(), rect.bottom() - corner_len))
        painter.drawLine(rect.bottomRight(), QPoint(rect.right() - corner_len, rect.bottom()))
        painter.drawLine(rect.bottomRight(), QPoint(rect.right(), rect.bottom() - corner_len))
