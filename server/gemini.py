"""Gemini(Vertex AI 経由)のクライアントとモデル名。

接続先とモデル名は server/.env(Git には入れない)から読む。すでに環境変数があればそちらを優先する。
認証は Application Default Credentials を使い、利用キーはどこにも置かない。
"""

import os
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"server/.env に {name} を設定してください")
    return value


def text_model() -> str:
    """案内文・お勧めの理由を書くモデル"""
    return _require("GEMINI_MODEL")


def embedding_model() -> str:
    """商品の埋め込みベクトルを作るモデル"""
    return _require("GEMINI_EMBEDDING_MODEL")


def check_settings() -> None:
    """必要な設定がそろっているか確かめる(足りなければ RuntimeError)"""
    for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GEMINI_MODEL", "GEMINI_EMBEDDING_MODEL"):
        _require(name)


@cache
def client() -> genai.Client:
    """Vertex AI(現 Gemini Enterprise Agent Platform)用のクライアントを、最初に使うときに1つだけ作る"""
    return genai.Client(
        enterprise=True,
        project=_require("GOOGLE_CLOUD_PROJECT"),
        location=_require("GOOGLE_CLOUD_LOCATION"),
    )
