"""Persistent Windows translation window matching the approved visual reference."""

from PyQt5.QtCore import Qt, QTimer, QSize, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPalette
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from .speech_service import SpeechService
from .utils import copy_to_clipboard


MAX_CHARS = 2000
FONT_FAMILY = "'Microsoft YaHei UI'"
BLUE = "#2E5BEB"
BLUE_DARK = "#244AC2"
INK = "#17243B"
MUTED = "#4F607A"
LINE = "#D6E0EF"
PANEL = "#FFFFFF"
BACKDROP = "#F2F6FC"
TINT = "#F0F5FF"
TEXT_BODY_SIZE = "16px"

STYLE = f"""
QWidget#translationWindow {{ background: {BACKDROP}; color: {INK};
    font-family: {FONT_FAMILY};
    font-size:14px; font-weight:400; }}
QFrame#inputCard, QFrame#resultCard {{ background:{PANEL}; border:1px solid #E4EAF3;
    border-radius:14px; }}
QFrame#sourceField {{ background:white; border:1px solid {LINE}; border-radius:8px; }}
QFrame#sourceField:focus-within {{ border:2px solid #AFC3FF; }}
QLabel#shortcutHint, QLabel#muted {{ font-family:{FONT_FAMILY}; color:{MUTED}; font-size:13px; font-weight:400; background:transparent; }}
QLabel#sectionTitle {{ font-family:{FONT_FAMILY}; color:{INK}; font-size:18px; font-weight:600; background:transparent; }}
QLabel#charCount {{ font-family:{FONT_FAMILY}; color:{MUTED}; font-size:12px; font-weight:400; background:transparent; }}
QTextEdit#sourceText {{ font-family:{FONT_FAMILY}; border:0; padding:4px 8px; font-size:{TEXT_BODY_SIZE}; font-weight:400; color:{INK};
    background:transparent; selection-background-color:#DCE7FF; }}
QTextEdit#translatedText {{ font-family:{FONT_FAMILY}; border:1px solid #D4E1FF; border-radius:8px; padding:12px;
    font-size:{TEXT_BODY_SIZE}; font-weight:400; color:{INK}; background:{TINT}; selection-background-color:#DCE7FF; }}
QComboBox {{ font-family:{FONT_FAMILY}; background:white; border:1px solid {LINE}; border-radius:8px;
    padding:7px 10px; min-width:132px; min-height:36px; font-size:15px; font-weight:400; color:{INK}; }}
QComboBox:hover {{ border-color:#AABBE0; }}
QComboBox:focus {{ border:2px solid #9EB7FF; }}
QComboBox::drop-down {{ border:0; width:25px; }}
QPushButton {{ font-family:{FONT_FAMILY}; border-radius:8px; min-height:26px; padding:7px 12px; font-size:14px; font-weight:400; }}
QPushButton#primary {{ background:{BLUE}; color:white; border:1px solid {BLUE}; font-size:15px; font-weight:600; }}
QPushButton#primary:hover {{ background:{BLUE_DARK}; border-color:{BLUE_DARK}; }}
QPushButton#primary:pressed {{ background:#1E3F9F; }}
QPushButton#primary:disabled {{ background:#BCC9E3; border-color:#BCC9E3; color:white; }}
QPushButton#secondary {{ background:white; color:{BLUE}; border:1px solid #9FB8FF; font-weight:600; }}
QPushButton#secondary:hover {{ background:#F3F6FF; }}
QPushButton#secondary:disabled {{ color:#91A0BA; border-color:#D8E0EC; }}
QPushButton#quiet {{ background:transparent; color:{MUTED}; border:1px solid transparent; font-size:14px; font-weight:400; }}
QPushButton#quiet:hover {{ background:#F0F4FA; color:{INK}; }}
QPushButton#swapButton {{ background:#EAF0FF; color:{BLUE}; border:1px solid transparent;
    font-size:20px; font-weight:600; padding:2px; min-height:38px; }}
QPushButton#swapButton:hover {{ background:#DEE8FF; }}
QPushButton#swapButton:disabled {{ background:#F4F6FA; color:#A6B2C5; }}
"""


def _make_window_icon():
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(BLUE))
    painter.drawRoundedRect(1, 1, 30, 30, 7, 7)
    painter.setPen(Qt.white)
    painter.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "译")
    painter.end()
    return QIcon(pixmap)


def _make_action_icon(kind, color=BLUE):
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if kind == "selection":
        painter.setPen(QPen(QColor(color), 1.8, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawRect(QRect(4, 4, 16, 16))
    elif kind == "trash":
        painter.drawLine(6, 7, 18, 7)
        painter.drawLine(9, 4, 15, 4)
        painter.drawLine(8, 8, 9, 20)
        painter.drawLine(16, 8, 15, 20)
        painter.drawLine(9, 20, 15, 20)
        painter.drawLine(11, 10, 11, 17)
        painter.drawLine(13, 10, 13, 17)
    elif kind in ("paste", "copy"):
        painter.drawRoundedRect(QRect(8, 5, 11, 14), 2, 2)
        painter.drawRoundedRect(QRect(5, 8, 11, 13), 2, 2)
        if kind == "paste":
            painter.drawRoundedRect(QRect(9, 3, 7, 4), 2, 2)
    elif kind == "speaker":
        painter.setBrush(QColor(color))
        painter.drawPolygon(QPoint(3, 9), QPoint(7, 9), QPoint(12, 5), QPoint(12, 19), QPoint(7, 15), QPoint(3, 15))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRect(11, 7, 8, 10), -60 * 16, 120 * 16)
        painter.drawArc(QRect(11, 4, 12, 16), -60 * 16, 120 * 16)
    elif kind == "refresh":
        painter.drawArc(QRect(4, 4, 16, 16), 35 * 16, 300 * 16)
        painter.drawLine(17, 4, 20, 8)
        painter.drawLine(17, 4, 12, 5)
    painter.end()
    return QIcon(pixmap)


class Composer(QWidget):
    translate_requested = pyqtSignal(str, str, str)
    capture_requested = pyqtSignal(str, str)
    reocr_requested = pyqtSignal(str, str)
    preferences_changed = pyqtSignal(str, str)
    context_changed = pyqtSignal()

    def __init__(self, source_list, target_list, source, target):
        super().__init__()
        # Keep normal Windows titlebar controls: minimize, maximize and close.
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
                            Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint |
                            Qt.WindowCloseButtonHint)
        self.setObjectName("translationWindow")
        self.setWindowTitle("翻译工具")
        self.setWindowIcon(_make_window_icon())
        self.setMinimumSize(480, 560)
        self.resize(580, 720)
        self.setStyleSheet(STYLE)
        self.translation_ok = False
        self._ocr_info = ""
        self._setting_source = False
        self._truncating_source = False
        self._has_screenshot = False
        self._speech = None
        self._speaking_role = None
        self._build_ui(source_list, target_list, source, target)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            width = min(self.width(), available.width() - 32)
            height = min(self.height(), available.height() - 32)
            self.resize(max(self.minimumWidth(), width), max(self.minimumHeight(), height))
            self.move(available.center() - self.rect().center())

    def _build_ui(self, source_list, target_list, source, target):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 14)
        outer.setSpacing(10)

        self.shortcut_hint = QLabel("Shift + Win + Z   快捷键")
        self.shortcut_hint.setObjectName("shortcutHint")
        outer.addWidget(self.shortcut_hint)

        input_card = QFrame()
        input_card.setObjectName("inputCard")
        outer.addWidget(input_card, 3)
        upper = QVBoxLayout(input_card)
        upper.setContentsMargins(16, 14, 16, 14)
        upper.setSpacing(10)

        languages = QHBoxLayout()
        languages.setSpacing(10)
        self.src_combo = QComboBox()
        self.src_combo.setAccessibleName("源语言")
        self.src_combo.addItems(source_list)
        self.src_combo.setCurrentText(source)
        self.swap_button = QPushButton("⇄")
        self.swap_button.setObjectName("swapButton")
        self.swap_button.setAccessibleName("对调源语言和目标语言")
        self.swap_button.setFixedSize(42, 42)
        self.swap_button.clicked.connect(self._swap_languages)
        self.tgt_combo = QComboBox()
        self.tgt_combo.setAccessibleName("目标语言")
        self.tgt_combo.addItems(target_list)
        self.tgt_combo.setCurrentText(target)
        languages.addWidget(self.src_combo)
        languages.addWidget(self.swap_button)
        languages.addWidget(self.tgt_combo)
        languages.addStretch(1)
        upper.addLayout(languages)

        source_header = QHBoxLayout()
        source_title = QLabel("原文")
        source_title.setObjectName("sectionTitle")
        source_header.addWidget(source_title)
        source_header.addStretch()
        self.original_speak_btn = self._make_speech_button("original", "朗读原文")
        source_header.addWidget(self.original_speak_btn)
        self.reocr_button = QPushButton("重新识别")
        self.reocr_button.setObjectName("quiet")
        self.reocr_button.setIcon(_make_action_icon("refresh", MUTED))
        self.reocr_button.setIconSize(QSize(18, 18))
        self.reocr_button.setToolTip("重新识别上次框选的区域")
        self.reocr_button.setAccessibleName("重新识别上次框选的区域")
        self.reocr_button.setVisible(False)
        self.reocr_button.clicked.connect(self._reocr)
        source_header.addWidget(self.reocr_button)
        self.paste_button = QPushButton("粘贴")
        self.paste_button.setObjectName("quiet")
        self.paste_button.setIcon(_make_action_icon("paste", MUTED))
        self.paste_button.setIconSize(QSize(18, 18))
        self.paste_button.setToolTip("从剪贴板粘贴文字")
        self.paste_button.clicked.connect(self._paste_from_clipboard)
        source_header.addWidget(self.paste_button)
        upper.addLayout(source_header)

        source_field = QFrame()
        source_field.setObjectName("sourceField")
        source_layout = QVBoxLayout(source_field)
        source_layout.setContentsMargins(9, 7, 9, 6)
        source_layout.setSpacing(2)
        self.input_text = QTextEdit()
        self.input_text.setObjectName("sourceText")
        self.input_text.setAccessibleName("待翻译文字")
        self.input_text.setPlaceholderText("请输入要翻译的文字，或粘贴内容...")
        self.input_text.setMinimumHeight(105)
        palette = self.input_text.palette()
        palette.setColor(QPalette.PlaceholderText, QColor(MUTED))
        self.input_text.setPalette(palette)
        self.input_text.textChanged.connect(self._source_edited)
        source_layout.addWidget(self.input_text, 1)
        self.char_count = QLabel(f"0/{MAX_CHARS}")
        self.char_count.setObjectName("charCount")
        self.char_count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        source_layout.addWidget(self.char_count)
        upper.addWidget(source_field, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.capture_button = QPushButton("框选翻译")
        self.capture_button.setObjectName("secondary")
        self.capture_button.setIcon(_make_action_icon("selection", BLUE))
        self.capture_button.setIconSize(QSize(18, 18))
        self.capture_button.clicked.connect(self._capture)
        actions.addWidget(self.capture_button)
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("quiet")
        self.clear_button.setIcon(_make_action_icon("trash", MUTED))
        self.clear_button.setIconSize(QSize(18, 18))
        self.clear_button.clicked.connect(self.input_text.clear)
        actions.addWidget(self.clear_button)
        self.activity_label = QLabel("")
        self.activity_label.setObjectName("muted")
        self.activity_label.setWordWrap(True)
        actions.addWidget(self.activity_label, 1)
        self.translate_button = QPushButton("翻译")
        self.translate_button.setObjectName("primary")
        self.translate_button.setFixedSize(92, 42)
        self.translate_button.setEnabled(False)
        self.translate_button.clicked.connect(self._translate)
        actions.addWidget(self.translate_button)
        upper.addLayout(actions)

        self.result_card = QFrame()
        self.result_card.setObjectName("resultCard")
        outer.addWidget(self.result_card, 2)
        lower = QVBoxLayout(self.result_card)
        lower.setContentsMargins(16, 14, 16, 14)
        lower.setSpacing(9)

        result_header = QHBoxLayout()
        result_title = QLabel("译文")
        result_title.setObjectName("sectionTitle")
        result_header.addWidget(result_title)
        result_header.addStretch()
        self.translated_speak_btn = self._make_speech_button("translated", "朗读译文")
        result_header.addWidget(self.translated_speak_btn)
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("quiet")
        self.copy_button.setIcon(_make_action_icon("copy", MUTED))
        self.copy_button.setIconSize(QSize(18, 18))
        self.copy_button.clicked.connect(self._copy_result)
        result_header.addWidget(self.copy_button)
        lower.addLayout(result_header)

        self.translated_text = QTextEdit()
        self.translated_text.setObjectName("translatedText")
        self.translated_text.setAccessibleName("翻译结果")
        self.translated_text.setReadOnly(True)
        self.translated_text.setPlaceholderText("翻译结果将在这里显示")
        self.translated_text.setMinimumHeight(95)
        palette = self.translated_text.palette()
        palette.setColor(QPalette.PlaceholderText, QColor(MUTED))
        self.translated_text.setPalette(palette)
        lower.addWidget(self.translated_text, 1)

        result_footer = QHBoxLayout()
        result_footer.addStretch()
        self.timing_label = QLabel("")
        self.timing_label.setObjectName("muted")
        result_footer.addWidget(self.timing_label)
        lower.addLayout(result_footer)

        self.src_combo.currentTextChanged.connect(self._language_changed)
        self.tgt_combo.currentTextChanged.connect(self._language_changed)
        self._update_swap_button()
        self._update_buttons()

    def set_languages(self, source, target):
        self.src_combo.blockSignals(True)
        self.tgt_combo.blockSignals(True)
        self.src_combo.setCurrentText(source)
        self.tgt_combo.setCurrentText(target)
        self.src_combo.blockSignals(False)
        self.tgt_combo.blockSignals(False)
        self._update_swap_button()

    def open_blank(self):
        self._setting_source = True
        self.input_text.clear()
        self._setting_source = False
        self.input_text.setReadOnly(False)
        self.input_text.setPlaceholderText("请输入要翻译的文字，或粘贴内容...")
        self.char_count.setText(f"0/{MAX_CHARS}")
        self._has_screenshot = False
        self.reocr_button.hide()
        self.translated_text.clear()
        self.translated_text.setPlaceholderText("翻译结果将在这里显示")
        self.translation_ok = False
        self._ocr_info = ""
        self.activity_label.clear()
        self.timing_label.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_text.setFocus()
        self._update_buttons()

    def show_after_capture(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def set_screenshot_available(self, available):
        self._has_screenshot = available
        self.reocr_button.setVisible(available)

    def begin_translation(self):
        self._stop_speech()
        self.translation_ok = False
        self.translated_text.setPlainText("正在翻译...")
        self.activity_label.setText("正在翻译")
        self.timing_label.setText(self._ocr_info)
        self._update_buttons()

    def begin_recognition(self):
        self._stop_speech()
        self._setting_source = True
        self.input_text.clear()
        self._setting_source = False
        self.input_text.setReadOnly(True)
        self.input_text.setPlaceholderText("正在识别框选区域...")
        self.char_count.setText(f"0/{MAX_CHARS}")
        self.translated_text.setPlainText("正在识别...")
        self.activity_label.setText("正在识别")
        self.translation_ok = False
        self._ocr_info = ""
        self.timing_label.clear()
        self._update_buttons()

    def set_ocr_result(self, text, ocr_info):
        self._ocr_info = ocr_info
        self._setting_source = True
        self.input_text.setPlainText(text[:MAX_CHARS])
        self._setting_source = False
        self.input_text.setReadOnly(False)
        self.input_text.setPlaceholderText("可在这里修正识别出的文字")
        self.char_count.setText(f"{min(len(text), MAX_CHARS)}/{MAX_CHARS}")
        self.translated_text.setPlainText("正在翻译..." if text.strip() else "未检测到文字")
        self.activity_label.setText("正在翻译" if text.strip() else "可选择源语言后重新识别")
        self.timing_label.setText(ocr_info)
        self._update_buttons()

    def set_translation_result(self, translated, success, translation_seconds=None, ocr_info=""):
        self.translated_text.setPlainText(translated)
        self.translation_ok = bool(success and translated.strip())
        self.activity_label.setText("" if success else "可修改原文后重试")
        if ocr_info:
            self._ocr_info = ocr_info
        timing = self._ocr_info
        if translation_seconds is not None:
            timing += ("  ·  " if timing else "") + f"翻译 {translation_seconds:.1f} 秒"
        self.timing_label.setText(timing)
        self.input_text.setReadOnly(False)
        self._update_buttons()

    def show_capture_error(self, message):
        self.translated_text.setPlainText(message)
        self.translation_ok = False
        self.activity_label.setText("请重新框选")
        self._update_buttons()

    def _source_edited(self):
        if self._truncating_source:
            return
        text = self.input_text.toPlainText()
        if len(text) > MAX_CHARS:
            cursor_position = self.input_text.textCursor().position()
            self._truncating_source = True
            self.input_text.blockSignals(True)
            self.input_text.setPlainText(text[:MAX_CHARS])
            cursor = self.input_text.textCursor()
            cursor.setPosition(min(cursor_position, MAX_CHARS))
            self.input_text.setTextCursor(cursor)
            self.input_text.blockSignals(False)
            self._truncating_source = False
            self.activity_label.setText(f"最多输入 {MAX_CHARS} 个字符，已保留前 {MAX_CHARS} 个")
            text = text[:MAX_CHARS]
        self.char_count.setText(f"{len(text)}/{MAX_CHARS}")
        if self._setting_source:
            self._update_buttons()
            return
        self._ocr_info = ""
        self.context_changed.emit()
        if text:
            self.activity_label.setText("原文已修改，点击翻译更新译文" if self.translation_ok else self.activity_label.text())
        if self.translation_ok or self.translated_text.toPlainText():
            self.translation_ok = False
            self.translated_text.clear()
            self.translated_text.setPlaceholderText("原文已修改，点击翻译更新译文")
            self.timing_label.clear()
        self._update_buttons()

    def _update_buttons(self):
        has_text = bool(self.input_text.toPlainText().strip()) and not self.input_text.isReadOnly()
        self.translate_button.setEnabled(has_text)
        self.clear_button.setEnabled(bool(self.input_text.toPlainText()))
        self.original_speak_btn.setEnabled(has_text)
        self.translated_speak_btn.setEnabled(self.translation_ok)
        self.copy_button.setEnabled(self.translation_ok)

    def _update_swap_button(self):
        auto = self.src_combo.currentText() == "自动检测"
        self.swap_button.setEnabled(not auto)
        self.swap_button.setToolTip("自动检测不能对调，请先选择具体源语言" if auto else "对调源语言和目标语言")

    def _language_changed(self):
        self._update_swap_button()
        self._ocr_info = ""
        self.preferences_changed.emit(self.src_combo.currentText(), self.tgt_combo.currentText())
        self.context_changed.emit()
        if self.translation_ok or self.translated_text.toPlainText():
            self.translation_ok = False
            self.translated_text.clear()
            self.translated_text.setPlaceholderText("语言已更改，点击翻译更新译文")
            self.timing_label.clear()
            self._update_buttons()

    def _swap_languages(self):
        source = self.src_combo.currentText()
        target = self.tgt_combo.currentText()
        if source == "自动检测":
            return
        self.set_languages(target, source)
        self._language_changed()

    def _paste_from_clipboard(self):
        text = QApplication.clipboard().text()
        if text:
            self.input_text.setPlainText(text)
            self.input_text.setFocus()

    def _translate(self):
        text = self.input_text.toPlainText()
        if text.strip():
            self.begin_translation()
            self.translate_requested.emit(text, self.src_combo.currentText(), self.tgt_combo.currentText())

    def _capture(self):
        self.capture_requested.emit(self.src_combo.currentText(), self.tgt_combo.currentText())

    def _reocr(self):
        if self._has_screenshot:
            self.reocr_requested.emit(self.src_combo.currentText(), self.tgt_combo.currentText())

    def _copy_result(self):
        if self.translation_ok:
            copy_to_clipboard(self.translated_text.toPlainText())
            self.activity_label.setText("已复制译文")
            QTimer.singleShot(1800, lambda: self.activity_label.clear() if self.translation_ok else None)

    def _make_speech_button(self, role, tooltip):
        button = QPushButton("朗读")
        button.setObjectName("quiet")
        button.setMinimumWidth(58)
        button.setIcon(_make_action_icon("speaker", MUTED))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(lambda: self._on_speech_clicked(role))
        return button

    def _ensure_speech_service(self):
        if self._speech is None:
            self._speech = SpeechService(self)
            self._speech.state_changed.connect(self._on_speech_state_changed)
        return self._speech

    def _stop_speech(self):
        if self._speech is not None:
            self._speech.stop()

    def _on_speech_clicked(self, role):
        if role == "original":
            text, language = self.input_text.toPlainText(), self.src_combo.currentText()
        else:
            text, language = self.translated_text.toPlainText(), self.tgt_combo.currentText()
        if role == self._speaking_role:
            self._stop_speech()
        elif text.strip():
            self._ensure_speech_service().speak(text, language, role)

    def _on_speech_state_changed(self, role, state, message):
        if state in ("preparing", "speaking", "fallback"):
            self._speaking_role = role
            self.original_speak_btn.setText("停止" if role == "original" else "朗读")
            self.translated_speak_btn.setText("停止" if role == "translated" else "朗读")
            self.activity_label.setText({"preparing": "正在准备朗读...",
                                         "speaking": "正在朗读...",
                                         "fallback": "正在使用系统语音..."}[state])
            return
        if role == self._speaking_role:
            self._speaking_role = None
        self.original_speak_btn.setText("朗读")
        self.translated_speak_btn.setText("朗读")
        if state == "failed":
            self.activity_label.setText(message or "朗读失败")
            if "Edge 朗读失败" in message and self.isVisible():
                choice = QMessageBox.question(self, "朗读失败", message + "\n\n是否改用电脑的系统语音？音质可能较低。",
                                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if choice == QMessageBox.Yes:
                    if role == "original":
                        text, language = self.input_text.toPlainText(), self.src_combo.currentText()
                    else:
                        text, language = self.translated_text.toPlainText(), self.tgt_combo.currentText()
                    self._ensure_speech_service().speak_local(text, language, role)
        else:
            self.activity_label.clear()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._stop_speech()
        super().closeEvent(event)
