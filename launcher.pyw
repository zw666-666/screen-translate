"""Windowless Windows launcher for the screen translator."""

import importlib.util
import os
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True


def _prepare_qt():
    spec = importlib.util.find_spec("PyQt5")
    if spec and spec.origin:
        platforms = Path(spec.origin).parent / "Qt5" / "plugins" / "platforms"
        if platforms.is_dir():
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)


def main():
    _prepare_qt()
    from screen_translator.main import main as run
    return run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ScreenTranslator"
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "app.log").open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc() + "\n")
        raise
