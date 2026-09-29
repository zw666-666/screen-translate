"""Edge neural speech with fast voice selection and optional local fallback."""

import asyncio
import ctypes
import os
import tempfile
import threading
from collections import OrderedDict

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


LANGUAGE_CODES = {
    "中文": "zh",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
}

VOICE_NAMES = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
}
_audio_cache = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_LIMIT = 8


class _WindowsMediaPlayer:
    """Small MCI wrapper that plays MP3 without the Qt multimedia backend."""

    def __init__(self):
        self._alias = None

    @staticmethod
    def _command(command: str) -> str:
        result = ctypes.create_unicode_buffer(256)
        error = ctypes.windll.winmm.mciSendStringW(command, result, len(result), None)
        if error:
            message = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(error, message, len(message))
            raise RuntimeError(message.value or f"MCI error {error}")
        return result.value

    def play(self, path: str, alias: str):
        self.stop()
        self._command(f'open "{path}" type mpegvideo alias {alias}')
        try:
            self._command(f"play {alias}")
        except Exception:
            self._command(f"close {alias}")
            raise
        self._alias = alias

    def is_playing(self) -> bool:
        if not self._alias:
            return False
        return self._command(f"status {self._alias} mode").strip().lower() == "playing"

    def stop(self):
        if not self._alias:
            return
        alias = self._alias
        self._alias = None
        try:
            self._command(f"stop {alias}")
        except RuntimeError:
            pass
        try:
            self._command(f"close {alias}")
        except RuntimeError:
            pass


def _guess_language(text: str) -> str:
    """Choose a usable voice for the app's automatic source-language mode."""
    if any("\uac00" <= char <= "\ud7af" for char in text):
        return "ko"
    if any("\u3040" <= char <= "\u30ff" for char in text):
        return "ja"
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return "zh"
    return "en"


class SpeechService(QObject):
    """Keeps synthesis off the UI thread and ensures only one utterance plays."""

    state_changed = pyqtSignal(str, str, str)
    audio_ready = pyqtSignal(int, str, str)
    sapi_finished = pyqtSignal(int, str)
    sapi_failed = pyqtSignal(int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._token = 0
        self._active_token = None
        self._active_role = None
        self._current_audio_path = None
        self._sapi_engines = {}

        self._player = _WindowsMediaPlayer()
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(250)
        self._playback_timer.timeout.connect(self._poll_playback)
        self.audio_ready.connect(self._play_edge_audio)
        self.sapi_finished.connect(self._on_sapi_finished)
        self.sapi_failed.connect(self._on_sapi_failed)

    def speak(self, text: str, language: str, role: str):
        text = text.strip()
        if not text:
            return

        self.stop()
        with self._lock:
            self._token += 1
            token = self._token
            self._active_token = token
            self._active_role = role

        self.state_changed.emit(role, "preparing", "")
        threading.Thread(
            target=self._edge_worker,
            args=(token, role, text, self._language_code(text, language)),
            daemon=True,
        ).start()

    def stop(self):
        with self._lock:
            role = self._active_role
            self._token += 1
            self._active_token = None
            self._active_role = None
            audio_path = self._current_audio_path
            self._current_audio_path = None
            engines = list(self._sapi_engines.values())

        self._playback_timer.stop()
        self._player.stop()
        if audio_path:
            QTimer.singleShot(0, lambda: self._remove_file(audio_path))
        for engine in engines:
            try:
                engine.stop()
            except Exception:
                pass
        if role:
            self.state_changed.emit(role, "stopped", "")

    def _language_code(self, text: str, language: str) -> str:
        if language == "自动检测":
            return _guess_language(text)
        return LANGUAGE_CODES.get(language, "en")

    def _is_current(self, token: int) -> bool:
        with self._lock:
            return token == self._active_token

    def _edge_worker(self, token: int, role: str, text: str, language_code: str):
        fd, audio_path = tempfile.mkstemp(prefix="screen-translator-", suffix=".mp3")
        os.close(fd)
        cache_key = (text, language_code)
        try:
            with _cache_lock:
                cached = _audio_cache.get(cache_key)
                if cached is not None:
                    _audio_cache.move_to_end(cache_key)
            if cached is not None:
                with open(audio_path, "wb") as output:
                    output.write(cached)
            else:
                asyncio.run(self._save_edge_audio(text, language_code, audio_path))
                if os.path.getsize(audio_path) == 0:
                    raise RuntimeError("语音服务返回空音频")
                if os.path.getsize(audio_path) < 2_000_000:
                    with open(audio_path, "rb") as source:
                        audio_bytes = source.read()
                    with _cache_lock:
                        _audio_cache[cache_key] = audio_bytes
                        _audio_cache.move_to_end(cache_key)
                        while len(_audio_cache) > _CACHE_LIMIT:
                            _audio_cache.popitem(last=False)
        except Exception:
            self._remove_file(audio_path)
            if self._is_current(token):
                self.state_changed.emit(role, "failed", "Edge 朗读失败，请检查网络；可选择系统语音重试")
            return

        if self._is_current(token):
            self.audio_ready.emit(token, role, audio_path)
        else:
            self._remove_file(audio_path)

    async def _save_edge_audio(self, text: str, language_code: str, audio_path: str):
        import edge_tts
        voice_name = VOICE_NAMES.get(language_code, VOICE_NAMES["en"])
        communicate = edge_tts.Communicate(text, voice=voice_name, rate="+0%")
        with open(audio_path, "wb") as output:
            async for message in communicate.stream():
                if message["type"] == "audio":
                    output.write(message["data"])

    def speak_local(self, text: str, language: str, role: str):
        """Called only after the user explicitly accepts lower-quality system speech."""
        language_code = self._language_code(text, language)
        if language_code not in ("zh", "en"):
            self.state_changed.emit(role, "failed", "系统语音未安装该语言，请使用 Edge 朗读")
            return
        self.stop()
        with self._lock:
            self._token += 1
            token = self._token
            self._active_token = token
            self._active_role = role
        self.state_changed.emit(role, "fallback", "")
        threading.Thread(target=self._sapi_worker, args=(token, role, text, language_code), daemon=True).start()

    def _play_edge_audio(self, token: int, role: str, audio_path: str):
        if not self._is_current(token):
            self._remove_file(audio_path)
            return

        with self._lock:
            self._current_audio_path = audio_path
        try:
            self._player.play(audio_path, f"screen_translator_{token}")
        except Exception:
            self._finish_media("failed", "语音播放失败")
            return
        self._playback_timer.start()
        self.state_changed.emit(role, "speaking", "")

    def _sapi_worker(self, token: int, role: str, text: str, language_code: str):
        engine = None
        try:
            import pyttsx3

            engine = pyttsx3.init()
            self._configure_sapi_voice(engine, language_code)
            with self._lock:
                if token != self._active_token:
                    return
                self._sapi_engines[token] = engine
            engine.say(text)
            engine.runAndWait()
            if self._is_current(token):
                self.sapi_finished.emit(token, role)
        except Exception as error:
            if self._is_current(token):
                self.sapi_failed.emit(token, role, str(error))
        finally:
            if engine:
                try:
                    engine.stop()
                except Exception:
                    pass
            with self._lock:
                self._sapi_engines.pop(token, None)

    def _configure_sapi_voice(self, engine, language_code: str):
        engine.setProperty("rate", 180)
        engine.setProperty("volume", 1.0)
        markers = {
            "zh": ("zh", "chinese", "huihui", "yaoyao"),
            "en": ("en", "english"),
            "ja": ("ja", "japanese"),
            "ko": ("ko", "korean"),
            "fr": ("fr", "french"),
            "de": ("de", "german"),
            "es": ("es", "spanish"),
            "pt": ("pt", "portuguese"),
            "ru": ("ru", "russian"),
            "it": ("it", "italian"),
        }.get(language_code, ("en", "english"))
        for voice in engine.getProperty("voices"):
            identity = " ".join(
                str(value) for value in (
                    getattr(voice, "id", ""),
                    getattr(voice, "name", ""),
                    getattr(voice, "languages", ""),
                )
            ).lower()
            if any(marker in identity for marker in markers):
                engine.setProperty("voice", voice.id)
                return

    def _poll_playback(self):
        if not self._active_role:
            self._playback_timer.stop()
            return
        try:
            playing = self._player.is_playing()
        except Exception:
            self._finish_media("failed", "语音播放失败")
            return
        if not playing:
            self._finish_media("finished", "")

    def _finish_media(self, state: str, message: str):
        with self._lock:
            role = self._active_role
            self._active_role = None
            self._active_token = None
            audio_path = self._current_audio_path
            self._current_audio_path = None
        self._playback_timer.stop()
        self._player.stop()
        if audio_path:
            QTimer.singleShot(0, lambda: self._remove_file(audio_path))
        if role:
            self.state_changed.emit(role, state, message)

    def _on_sapi_finished(self, token: int, role: str):
        if self._is_current(token):
            with self._lock:
                self._active_role = None
                self._active_token = None
            self.state_changed.emit(role, "finished", "")

    def _on_sapi_failed(self, token: int, role: str, _error: str):
        if self._is_current(token):
            with self._lock:
                self._active_role = None
                self._active_token = None
            self.state_changed.emit(role, "failed", "朗读服务不可用")

    @staticmethod
    def _remove_file(path: str):
        try:
            os.remove(path)
        except OSError:
            pass
