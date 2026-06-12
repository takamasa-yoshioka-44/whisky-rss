"""英語記事の言語判定と DeepL による翻訳。

- 言語判定は langdetect で行う(未インストールなら「翻訳しない」へフォールバック)。
- 翻訳は DeepL API を requests で叩く(公式 SDK は使わない)。
- DEEPL_API_KEY が未設定なら翻訳機能を丸ごと無効化し、従来どおり原文のまま扱う。
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "").strip()
DEEPL_API_URL = os.environ.get(
    "DEEPL_API_URL", "https://api-free.deepl.com/v2/translate"
).strip()
TRANSLATE_TARGET_LANG = os.environ.get("TRANSLATE_TARGET_LANG", "JA").strip() or "JA"

# langdetect は任意依存。無ければ言語判定を諦めて「翻訳しない」へ倒す。
try:
    from langdetect import DetectorFactory, LangDetectException, detect

    # 実行ごとに結果がブレないよう seed を固定
    DetectorFactory.seed = 0
    _LANGDETECT_OK = True
except Exception as e:  # pragma: no cover - import 環境依存
    log.warning("[translate] langdetect unavailable; translation disabled: %s", e)
    _LANGDETECT_OK = False


def translation_enabled() -> bool:
    """翻訳機能が利用可能か(キーあり & langdetect あり)。"""
    return bool(DEEPL_API_KEY) and _LANGDETECT_OK


def detect_lang(text: str) -> str:
    """言語コードを返す。判定不能・短文・空文字は "unknown"。"""
    if not _LANGDETECT_OK:
        return "unknown"
    text = (text or "").strip()
    if len(text) < 3:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def is_english(text: str) -> bool:
    return detect_lang(text) == "en"


def translate(text: str, target: str | None = None) -> str | None:
    """DeepL で翻訳。失敗時は None(呼び出し側で原文フォールバック)。"""
    if not DEEPL_API_KEY:
        return None
    text = (text or "").strip()
    if not text:
        return None
    target = target or TRANSLATE_TARGET_LANG
    try:
        resp = requests.post(
            DEEPL_API_URL,
            data={"text": text, "target_lang": target},
            headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
            timeout=15,
        )
        if resp.status_code >= 300:
            log.warning(
                "[translate] DeepL failed: status=%s body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return None
        translations = resp.json().get("translations") or []
        if not translations:
            log.warning("[translate] DeepL returned no translations")
            return None
        return translations[0].get("text") or None
    except requests.RequestException as e:
        log.warning("[translate] DeepL exception: %s", e)
        return None
    except (ValueError, KeyError) as e:
        log.warning("[translate] DeepL response parse error: %s", e)
        return None


def maybe_translate(text: str) -> tuple[str | None, bool]:
    """英語と判定された場合のみ翻訳する。

    Returns:
        (訳文, True)  英語を翻訳できたとき
        (None, False) 非英語 / キー未設定 / 翻訳失敗のとき
    """
    if not translation_enabled():
        return (None, False)
    if not is_english(text):
        return (None, False)
    translated = translate(text)
    if translated is None:
        return (None, False)
    return (translated, True)
