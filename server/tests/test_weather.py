"""今日の気温の取得(weather.py)のテスト。本物の Open-Meteo には問い合わせない。"""

from datetime import date

import pytest

import weather

DAY = date(2026, 11, 16)


@pytest.fixture
def requests(monkeypatch):
    """偽の Open-Meteo。返す値を変えられ、問い合わせた緯度・経度・日付を記録する"""
    state = {"value": 18.5, "fail": False, "asked": []}

    def fake(latitude, longitude, day):
        state["asked"].append((latitude, longitude, day))
        if state["fail"]:
            raise OSError("つながりません")
        return state["value"]

    monkeypatch.setattr(weather, "request_max_temperature", fake)
    monkeypatch.setattr(weather, "_cache", {})
    return state


def test_都道府県は47あり_どれも日本の中の緯度経度を持つ():
    assert len(weather.PREFECTURES) == 47
    for latitude, longitude in weather.PREFECTURES.values():
        assert 24 <= latitude <= 46 and 122 <= longitude <= 154


def test_都道府県庁所在地の緯度経度と日付だけで問い合わせる(requests):
    assert weather.today_max_temperature("東京都", DAY) == 18.5
    assert requests["asked"] == [(*weather.PREFECTURES["東京都"], DAY)]


def test_同じ地域と日付では問い合わせ直さない(requests):
    weather.today_max_temperature("東京都", DAY)
    weather.today_max_temperature("東京都", DAY)
    weather.today_max_temperature("東京都", date(2026, 11, 17))
    assert len(requests["asked"]) == 2


@pytest.mark.parametrize("region", [None, "", "東京", "どこか"])
def test_地域が未設定か選択肢にない地域なら問い合わせずNone(requests, region):
    assert weather.today_max_temperature(region, DAY) is None
    assert requests["asked"] == []


def test_取得できなければNoneを返し_覚えない(requests):
    requests["fail"] = True
    assert weather.today_max_temperature("東京都", DAY) is None
    requests["fail"] = False
    assert weather.today_max_temperature("東京都", DAY) == 18.5


@pytest.mark.parametrize("value", [None, "18", True, 99.0, -80.0])
def test_ありえない値は使わない(requests, value):
    requests["value"] = value
    assert weather.today_max_temperature("東京都", DAY) is None
