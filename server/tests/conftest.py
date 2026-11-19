"""テストの共通設定。本物の Gemini API は呼ばない。"""

import os
import sys
from pathlib import Path

# main.py は起動時に環境変数を要求するので、テスト用の値を入れておく
# (本物の server/.env より先に設定するので、テストではこちらが使われる)
os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GEMINI_MODEL"] = "test-model"
os.environ["GEMINI_EMBEDDING_MODEL"] = "test-embedding-model"

# server フォルダの main.py / safety.py を import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
