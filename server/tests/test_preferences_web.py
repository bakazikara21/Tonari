"""苦手なスイーツの項目を選ぶページの API のテスト。データベースはテストごとに一時ファイルを使う。"""

import pytest
from fastapi.testclient import TestClient

import main
from demo_data import seed_demo_products
from recommend_store import RecommendStore
from recommend_web import get_store, get_user_id

USER_ID = "test-user"


@pytest.fixture
def store(tmp_path):
    store = RecommendStore(tmp_path / "web.db")
    seed_demo_products(store)
    return store


@pytest.fixture
def client(store):
    main.app.dependency_overrides[get_store] = lambda: store
    main.app.dependency_overrides[get_user_id] = lambda: USER_ID
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def save(client, *categories):
    return client.put("/api/preferences/dislikes", json={"categories": list(categories)})


def test_ページを開ける(client):
    response = client.get("/preferences")
    assert response.status_code == 200
    assert "にがてな おかし" in response.text


def test_選択肢を洋菓子_和菓子_フルーツに分けて返す(client):
    data = client.get("/api/preferences/dislikes").json()

    assert [(group["code"], group["label"]) for group in data["groups"]] == [
        ("western", "洋菓子"), ("japanese", "和菓子"), ("fruit", "フルーツ")]
    western, japanese, fruit = data["groups"]
    assert [item["label"] for item in western["items"]] == [
        "ショートケーキ", "チョコレートケーキ", "チーズケーキ", "モンブラン", "クッキー", "ゼリー", "ドライフルーツ系"]
    assert [item["label"] for item in japanese["items"]] == [
        "あずき系", "カスタードクリーム系", "チョコクリーム系", "ドライフルーツ系"]
    assert [item["label"] for item in fruit["items"]] == ["いちご", "レモン・ゆず", "くり", "りんご", "ドライフルーツ系"]


def test_ページは分類ごとのプルダウンで_分類ごと一括のチェックがある(client):
    html = client.get("/preferences").text
    assert 'createElement("details")' in html
    assert "全部 にがて" in html and "ぜんぶ" not in html


def test_記録し終わった画面では_選び直すボタンの上に終了するボタンがある(client):
    html = client.get("/preferences").text
    assert html.index(">終了する<") < html.index(">えらびなおす<")
    assert 'postMessage("close")' in html     # アプリに知らせて画面を閉じる


def test_ページの文言は漢字の記録と全てを使う(client):
    html = client.get("/preferences").text
    assert "これで 記録する" in html and "記録せずに やめる" in html
    assert "きろく" not in html and "すべて" not in html


def test_まだ選んでいなければ何も選ばれていない状態から始める(client):
    data = client.get("/api/preferences/dislikes").json()
    assert (data["saved"], data["selected"]) == (False, [])


def test_選んだ項目を設定された利用者IDで記録し_次に開くとその状態から始める(client, store):
    assert save(client, "apple", "cheesecake", "azuki").status_code == 204

    # 選択肢の並び順で保存する
    assert store.get_disliked_categories(USER_ID) == ("cheesecake", "azuki", "apple")
    data = client.get("/api/preferences/dislikes").json()
    assert (data["saved"], data["selected"]) == (True, ["cheesecake", "azuki", "apple"])


def test_分類ごと一括で苦手にすると_分類と項目すべてを記録する(client, store):
    assert save(client, "japanese").status_code == 204

    assert store.get_disliked_categories(USER_ID) == (
        "japanese", "azuki", "custard", "chocolate-cream", "japanese-dried-fruit")


def test_以前の分け方で選んだ項目は_今の選択肢にないので選ばれていない状態で始める(client, store):
    store.save_disliked_categories(USER_ID, ("cake", "daifuku", "cheesecake"))   # 以前の「ケーキ」「大福」

    assert client.get("/api/preferences/dislikes").json()["selected"] == ["cheesecake"]


def test_何回でも選び直せ_最後に記録した内容だけが残る(client, store):
    save(client, "cheesecake", "fruit")
    save(client, "azuki")
    save(client)                         # 苦手なものはない

    assert store.get_disliked_categories(USER_ID) == ()


def test_途中でやめて何も送らなければ前の状態のまま残る(client, store):
    save(client, "cheesecake")

    # 選び直しのためにページを開いて、記録せずにやめる(ページは途中の選択を送らない)
    client.get("/api/preferences/dislikes")

    assert store.get_disliked_categories(USER_ID) == ("cheesecake",)


@pytest.mark.parametrize("categories", [
    ["cheesecake", "チーズケーキ"],      # コードでなく表示名
    ["daifuku"],                         # 以前の分け方の項目(今の選択肢にない)
])
def test_選択肢にない値が1つでもあれば何も記録しない(client, store, categories):
    save(client, "azuki")

    assert save(client, *categories).status_code == 422
    assert store.get_disliked_categories(USER_ID) == ("azuki",)


def test_以前の1品ずつ聞く画面と写真で教える画面のAPIはない(client):
    assert client.get("/api/preferences/queue").status_code == 404
    assert client.post("/api/preferences", json={"ratings": []}).status_code in (404, 405)
    assert client.post("/api/preferences/photo", json={}).status_code in (404, 405)


def test_利用者IDが設定されていなければ記録しない(store, monkeypatch):
    monkeypatch.delenv("TONARI_USER_ID", raising=False)
    main.app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(main.app).put("/api/preferences/dislikes", json={"categories": ["cheesecake"]})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 500
    assert store.get_disliked_categories("") is None
