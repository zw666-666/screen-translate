"""
工具函数模块
"""

from PyQt5.QtWidgets import QApplication


def copy_to_clipboard(text: str):
    """
    将文本复制到系统剪贴板
    """
    clipboard = QApplication.clipboard()
    clipboard.setText(text)
