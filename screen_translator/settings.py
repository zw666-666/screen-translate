"""User preferences and credentials live outside the program directory."""

import json
import os
from pathlib import Path


DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ScreenTranslator"
CONFIG_FILE = DATA_DIR / "config.json"
KEY_FILE = DATA_DIR / "deepseek_key.txt"


def migrate_legacy(project_root: Path) -> list[str]:
    """Move old files only after byte-for-byte verification, preserving conflicts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    messages = []
    for name, target in (("config.json", CONFIG_FILE), ("deepseek_key.txt", KEY_FILE)):
        legacy = project_root / name
        if not legacy.is_file():
            continue
        original = legacy.read_bytes()
        if target.exists():
            if target.read_bytes() != original:
                messages.append(f"{name}: 目标文件已有不同内容，旧文件保留")
                continue
        else:
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_bytes(original)
            if temporary.read_bytes() != original:
                temporary.unlink(missing_ok=True)
                raise OSError(f"{name} 迁移校验失败")
            temporary.replace(target)
        if target.read_bytes() == original:
            legacy.unlink()
            messages.append(f"{name}: 已迁移")
    return messages


def load_preferences(valid_sources, valid_targets, default_source, default_target):
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    source = data.get("source_lang", default_source)
    target = data.get("target_lang", default_target)
    return (source if source in valid_sources else default_source,
            target if target in valid_targets else default_target)


def save_preferences(source, target):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_name("config.json.tmp")
    temporary.write_text(json.dumps({"source_lang": source, "target_lang": target}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(CONFIG_FILE)
