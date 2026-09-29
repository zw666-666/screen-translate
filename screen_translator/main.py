"""Tray app with one persistent window for input and translation results."""

import ctypes
import queue
import sys
import threading
import time
from pathlib import Path

import mss
from PIL import Image
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from . import tray_icon
from .composer import Composer
from .ocr_engine import recognize
from .overlay import ScreenOverlay
from .settings import load_preferences, migrate_legacy, save_preferences
from .translator import DEFAULT_SOURCE, DEFAULT_TARGET, SOURCE_LANGS, TARGET_LANGS, translate


class TranslatorApplication:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.source, self.target = load_preferences(SOURCE_LANGS, TARGET_LANGS, DEFAULT_SOURCE, DEFAULT_TARGET)
        self.composer = Composer(list(SOURCE_LANGS), list(TARGET_LANGS), self.source, self.target)
        self.composer.translate_requested.connect(self._translate_text)
        self.composer.capture_requested.connect(self._start_capture)
        self.composer.reocr_requested.connect(self._reocr)
        self.composer.preferences_changed.connect(self._save_preferences)
        self.composer.context_changed.connect(self._invalidate_job)
        self.overlay = ScreenOverlay()
        self.overlay.selection_done.connect(self._on_selection)
        self.overlay.selection_cancelled.connect(self._on_cancel_selection)
        self._events = queue.Queue()
        self._tray_requests = queue.Queue()
        self._job_counter = 0
        self._active_job_id = None
        self._screenshot = None
        self._last_hotkey = 0.0
        self._hotkey_down = False
        self._capture_from_composer = False

        self.timer = QTimer()
        self.timer.timeout.connect(self._poll_hotkey)
        self.timer.timeout.connect(self._poll_queues)
        self.timer.start(60)
        tray_icon.on_open_triggered = lambda: self._tray_requests.put("open")
        tray_icon.on_capture_triggered = lambda: self._tray_requests.put("capture")
        tray_icon.on_quit = lambda: self._tray_requests.put("quit")
        threading.Thread(target=tray_icon.start_tray, daemon=True).start()

    def run(self):
        return self.qt_app.exec_()

    def _save_preferences(self, source, target):
        if source in SOURCE_LANGS and target in TARGET_LANGS:
            self.source, self.target = source, target
            save_preferences(source, target)

    def _invalidate_job(self):
        # A result for a previous source text or language must not overwrite the current input.
        self._active_job_id = None

    @staticmethod
    def _down(code):
        return bool(ctypes.windll.user32.GetAsyncKeyState(code) & 0x8000)

    def _poll_hotkey(self):
        down = self._down(0x5B) and self._down(0x10) and self._down(0x5A)
        if down and not self._hotkey_down and time.monotonic() - self._last_hotkey > 0.5:
            self._last_hotkey = time.monotonic()
            self.open_composer()
        self._hotkey_down = down

    def _poll_queues(self):
        for _ in range(20):
            try:
                request = self._tray_requests.get_nowait()
            except queue.Empty:
                break
            if request == "open":
                self.open_composer()
            elif request == "capture":
                self._start_capture(self.source, self.target)
            elif request == "quit":
                self.qt_app.quit()
        for _ in range(20):
            try:
                job_id, phase, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if job_id != self._active_job_id:
                continue
            if phase == "ocr":
                self.composer.set_ocr_result(payload["text"], payload["ocr_info"])
            else:
                self.composer.set_translation_result(
                    payload["translated"], payload["success"],
                    payload.get("translation_seconds"), payload.get("ocr_info", ""),
                )

    def open_composer(self):
        if self.composer.isVisible():
            if self.composer.isMinimized():
                self.composer.showNormal()
            self.composer.raise_()
            self.composer.activateWindow()
            self.composer.input_text.setFocus()
            return
        self._invalidate_job()
        self._screenshot = None
        self.composer.set_languages(self.source, self.target)
        self.composer.open_blank()

    def _start_capture(self, source, target):
        self._save_preferences(source, target)
        self._capture_from_composer = self.composer.isVisible()
        self.composer.hide()
        QTimer.singleShot(100, self._show_overlay)

    def _show_overlay(self):
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()

    def _on_cancel_selection(self):
        if self._capture_from_composer:
            self.composer.show_after_capture()
            self.composer.input_text.setFocus()
        self._capture_from_composer = False

    def _on_selection(self, x, y, width, height):
        # Give Windows time to remove the translucent overlay before grabbing pixels.
        QTimer.singleShot(90, lambda: self._capture_region(x, y, width, height))

    def _capture_region(self, x, y, width, height):
        try:
            with mss.mss() as camera:
                shot = camera.grab({"left": x, "top": y, "width": width, "height": height})
                image = Image.frombytes("RGB", shot.size, shot.rgb)
        except Exception as exc:
            self.composer.show_after_capture()
            self.composer.show_capture_error(f"截图失败：{exc}")
            return
        self._screenshot = image
        self.composer.show_after_capture()
        self.composer.set_screenshot_available(True)
        self.composer.begin_recognition()
        self._start_job(image, self.source, self.target, need_ocr=True)

    def _translate_text(self, text, source, target):
        self._save_preferences(source, target)
        self._start_job(text, source, target)

    def _reocr(self, source, target):
        if self._screenshot is None:
            return
        self._save_preferences(source, target)
        self.composer.begin_recognition()
        self._start_job(self._screenshot, source, target, need_ocr=True)

    def _start_job(self, input_data, source, target, need_ocr=False):
        self._job_counter += 1
        job_id = self._job_counter
        self._active_job_id = job_id
        threading.Thread(target=self._worker,
                         args=(job_id, input_data, source, target, need_ocr), daemon=True).start()

    def _worker(self, job_id, input_data, source, target, need_ocr):
        ocr_info = ""
        text = input_data
        try:
            if need_ocr:
                started = time.monotonic()
                ocr_result = recognize(input_data, source)
                text = ocr_result.text
                ocr_info = f"识别 {time.monotonic() - started:.1f} 秒 · 置信度 {ocr_result.confidence:.0f}%"
                self._events.put((job_id, "ocr", {"text": text, "ocr_info": ocr_info}))
            if not text or not text.strip():
                translated = "未检测到文字，请缩小框选范围或选择源语言后重新识别。"
                success = False
                elapsed = None
            else:
                started = time.monotonic()
                result = translate(text, target_lang=target, source_lang=source)
                elapsed = time.monotonic() - started
                success = result["success"]
                translated = result["translated"] if success else f"翻译失败：{result.get('error', '未知错误')}"
        except Exception as exc:
            translated = f"处理失败：{exc}"
            success = False
            elapsed = None
        self._events.put((job_id, "done", {
            "translated": translated, "success": success,
            "ocr_info": ocr_info, "translation_seconds": elapsed,
        }))


def main():
    migrate_legacy(Path(__file__).resolve().parent.parent)
    return TranslatorApplication().run()


if __name__ == "__main__":
    sys.exit(main())
