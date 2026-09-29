"""Tesseract OCR with one primary pass and a conditional recovery pass."""

from dataclasses import dataclass
import re
import shutil

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


_tesseract = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = _tesseract

LANG_MAP = {
    "自动检测": "eng+chi_sim+jpn+kor",
    "中文": "chi_sim+eng",
    "English": "eng",
    "日本語": "jpn+eng",
    "한국어": "kor+eng",
}
_CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_KANA = "\u3040-\u30ff"
_CIRCLED_DIGITS = {chr(0x2460 + index): str(index + 1) for index in range(20)}
_CIRCLED_DIGITS["⓪"] = "0"
_CIRCLED_DIGIT_CHARS = re.escape("".join(_CIRCLED_DIGITS))
_NUMBER_UNITS = r"(?:周年|年|月|日|号|頁|页|ページ|週|周|回|巻|話|章|節|時|分|秒|番|位)"


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float
    model: str


def _scale(image: Image.Image) -> Image.Image:
    shortest = min(image.size)
    factor = 3 if shortest < 70 else 2 if shortest < 180 else 1
    if factor > 1:
        return image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
    return image


def _prepare(image: Image.Image, binary: bool = False) -> Image.Image:
    gray = ImageOps.autocontrast(ImageOps.grayscale(_scale(image)), cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.15)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1, percent=110, threshold=3))
    if binary:
        gray = gray.point(lambda pixel: 255 if pixel > 145 else 0, mode="1")
    return gray


def _normalise_enclosed_digits(text: str) -> str:
    digit_chars = f"0-9{_CIRCLED_DIGIT_CHARS}"

    # Tesseract can read a zero as "o" inside a number, e.g. ⑤o! for 50!.
    text = re.sub(
        rf"(?<=[{digit_chars}])[oO](?=\s*(?:[{digit_chars}]|[!！?？]|{_NUMBER_UNITS}))",
        "0",
        text,
    )

    def convert(match: re.Match) -> str:
        token = match.group(0)
        if not any(char in _CIRCLED_DIGITS for char in token):
            return token
        return "".join(_CIRCLED_DIGITS.get(char, char) for char in token)

    # Keep spaces between OCR-separated digits only when the following unit
    # confirms they form one number (for example, ③ ⑥ 号 -> 36 号).
    separated_sequence = re.compile(
        rf"[{digit_chars}](?:\s*[{digit_chars}])+(?=\s*{_NUMBER_UNITS})"
    )
    text = separated_sequence.sub(lambda match: convert(match).replace(" ", ""), text)

    def convert_in_context(match: re.Match) -> str:
        token = match.group(0)
        if not any(char in _CIRCLED_DIGITS for char in token):
            return token
        following = re.match(rf"\s*{_NUMBER_UNITS}", text[match.end():])
        preceding = re.search(
            r"(?:第|No\.?|号|頁|页|ページ)\s*$",
            text[max(0, match.start() - 16):match.start()],
            re.IGNORECASE,
        )
        if len(token) == 1 and not following and not preceding:
            return token
        return convert(match)

    return re.sub(rf"[{digit_chars}]+", convert_in_context, text)


def _normalise(text: str) -> str:
    text = _normalise_enclosed_digits(text)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(rf"(?<=[{_CJK}{_KANA}])\s+(?=[{_CJK}{_KANA}])", "", line)
        korean_tokens = line.split(" ")
        if len(korean_tokens) > 1 and all(len(token) == 1 and "\uac00" <= token <= "\ud7af" for token in korean_tokens):
            line = "".join(korean_tokens)
        lines.append(line)
    return "\n".join(lines)


def _one_pass(image: Image.Image, model: str, binary: bool = False) -> OCRResult:
    # A wide selection can still contain several lines (for example a paragraph
    # cropped from a browser). Treat it as a text block instead of inferring a
    # single line from its aspect ratio.
    psm = 6
    data = pytesseract.image_to_data(
        _prepare(image, binary), lang=model, config=f"--oem 3 --psm {psm} --dpi 300",
        output_type=pytesseract.Output.DICT,
    )
    lines = []
    words = []
    current = None
    scores = []
    for i, raw in enumerate(data["text"]):
        word = raw.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if current is not None and key != current:
            lines.append(" ".join(words))
            words = []
        words.append(word)
        current = key
        try:
            score = float(data["conf"][i])
        except (TypeError, ValueError):
            score = -1
        if score >= 0:
            scores.append(score)
    if words:
        lines.append(" ".join(words))
    text = _normalise("\n".join(lines))
    confidence = sum(scores) / len(scores) if scores else 0.0
    return OCRResult(text, confidence, model)


def _script_model(text: str) -> str:
    if re.search(r"[\uac00-\ud7af]", text):
        return "kor+eng"
    if re.search(rf"[{_KANA}]", text):
        return "jpn+eng"
    if re.search(rf"[{_CJK}]", text):
        return "chi_sim+eng"
    return "eng"


def recognize(image: Image.Image, source_lang: str = "自动检测") -> OCRResult:
    model = LANG_MAP.get(source_lang, LANG_MAP["自动检测"])
    primary = _one_pass(image, model)
    # A low score or empty text is worth one extra OCR call, not six calls per capture.
    if primary.text and primary.confidence >= 68:
        return primary
    recovery_model = _script_model(primary.text) if source_lang == "自动检测" else model
    try:
        recovery = _one_pass(image, recovery_model, binary=True)
    except pytesseract.TesseractError:
        return primary
    if recovery.text and (not primary.text or recovery.confidence > primary.confidence + 3):
        return recovery
    return primary


def ocr_from_image(image: Image.Image, source_lang: str = "自动检测") -> str:
    return recognize(image, source_lang).text
