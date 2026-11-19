"""今日の気温の取得(Open-Meteo、利用キーは不要)。

住んでいる地域は都道府県までしか持たない。外部に送るのは、都道府県庁所在地のおおよその緯度・経度と日付だけで、
利用者 ID や住所は送らない。
取得できなかったときは None を返し、気温を使わずにおすすめを決める(気温がなくても使えるようにするため)。
"""

import json
import logging
from datetime import date
from urllib.parse import urlencode
from urllib.request import urlopen

logger = logging.getLogger("tonari")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 5

# 都道府県と、その都道府県庁所在地のおおよその緯度・経度(北から順)
PREFECTURES: dict[str, tuple[float, float]] = {
    "北海道": (43.06, 141.35), "青森県": (40.82, 140.74), "岩手県": (39.70, 141.15), "宮城県": (38.27, 140.87),
    "秋田県": (39.72, 140.10), "山形県": (38.24, 140.36), "福島県": (37.75, 140.47), "茨城県": (36.34, 140.45),
    "栃木県": (36.57, 139.88), "群馬県": (36.39, 139.06), "埼玉県": (35.86, 139.65), "千葉県": (35.61, 140.12),
    "東京都": (35.69, 139.69), "神奈川県": (35.45, 139.64), "新潟県": (37.90, 139.02), "富山県": (36.70, 137.21),
    "石川県": (36.59, 136.63), "福井県": (36.07, 136.22), "山梨県": (35.66, 138.57), "長野県": (36.65, 138.18),
    "岐阜県": (35.39, 136.72), "静岡県": (34.98, 138.38), "愛知県": (35.18, 136.91), "三重県": (34.73, 136.51),
    "滋賀県": (35.00, 135.87), "京都府": (35.02, 135.76), "大阪府": (34.69, 135.52), "兵庫県": (34.69, 135.18),
    "奈良県": (34.69, 135.83), "和歌山県": (34.23, 135.17), "鳥取県": (35.50, 134.24), "島根県": (35.47, 133.05),
    "岡山県": (34.66, 133.93), "広島県": (34.40, 132.46), "山口県": (34.19, 131.47), "徳島県": (34.07, 134.56),
    "香川県": (34.34, 134.04), "愛媛県": (33.84, 132.77), "高知県": (33.56, 133.53), "福岡県": (33.61, 130.42),
    "佐賀県": (33.25, 130.30), "長崎県": (32.74, 129.87), "熊本県": (32.79, 130.74), "大分県": (33.24, 131.61),
    "宮崎県": (31.91, 131.42), "鹿児島県": (31.56, 130.56), "沖縄県": (26.21, 127.68),
}

# 取得できた気温を、地域と日付ごとに覚えておく(同じ日に何度も外部へ問い合わせないため)
_cache: dict[tuple[str, date], float] = {}


def request_max_temperature(latitude: float, longitude: float, day: date) -> float:
    """Open-Meteo にその日の最高気温(℃)を問い合わせる(テストではこの関数を差し替える)"""
    query = urlencode({
        "latitude": latitude, "longitude": longitude, "daily": "temperature_2m_max",
        "timezone": "Asia/Tokyo", "start_date": day.isoformat(), "end_date": day.isoformat(),
    })
    with urlopen(f"{FORECAST_URL}?{query}", timeout=TIMEOUT_SECONDS) as response:
        data = json.load(response)
    return data["daily"]["temperature_2m_max"][0]


def today_max_temperature(region: str | None, day: date) -> float | None:
    """その地域のその日の最高気温(℃)。地域が未設定・取得できない・ありえない値なら None"""
    if region not in PREFECTURES:
        return None
    if (region, day) in _cache:
        return _cache[(region, day)]
    latitude, longitude = PREFECTURES[region]
    try:
        value = request_max_temperature(latitude, longitude, day)
    except Exception as error:  # 通信の失敗や、形の違う答えなど
        logger.warning("気温を取得できませんでした: %s: %s", type(error).__name__, str(error)[:300])
        return None
    # 数でない値や、ありえない値は使わない
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not -50 <= value <= 60:
        logger.warning("気温の値が正しくありません: %r", value)
        return None
    _cache[(region, day)] = float(value)
    return float(value)
