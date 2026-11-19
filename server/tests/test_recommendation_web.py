"""家族の設定と「今日のおすすめ」の API のテスト。Gemini(理由・今日の様子のベクトル)と気温は偽物に差し替える。"""

import re
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import main
import recommend_web
from demo_data import seed_demo_products
from recommend import PUSHY_PATTERN, cosine, exclusion_reason, product_tags
from recommend_store import FamilySettings, RecommendStore
from recommend_web import JST, get_now, get_store, get_user_id

USER_ID = "test-user"
TODAY = datetime(2026, 11, 16).date()     # clock の日(日本時間)
MODEL = "test-embedding-model"   # conftest.py の GEMINI_EMBEDDING_MODEL


@pytest.fixture
def store(tmp_path):
    store = RecommendStore(tmp_path / "rec.db")
    seed_demo_products(store)
    # 架空の商品の仮ベクトルを、テスト用モデルのベクトルとして使う
    for product in store.list_products():
        store.update_product_embedding(product.id, product.embedding, MODEL)
    return store


@pytest.fixture
def clock():
    return {"now": datetime(2026, 11, 16, 10, 0, tzinfo=JST)}


@pytest.fixture
def reasons(monkeypatch):
    """偽の Gemini。どの品にも同じ理由を返す。返す理由を変えられ、呼ばれた回数と渡された品の数を数える"""
    state = {"reason": "やわらかくて、ほっとする味です。", "calls": 0, "fail": False, "today": [], "counts": []}

    def fake(products, today):
        state["calls"] += 1
        state["today"].append(today)
        state["counts"].append(len(products))
        if state["fail"]:
            raise RuntimeError("Gemini に接続できません")
        return [state["reason"]] * len(products)

    monkeypatch.setattr(recommend_web, "generate_reasons", fake)
    return state


@pytest.fixture
def temperature(monkeypatch):
    """偽の気温。地域ごとに返す最高気温を決め、問い合わせを記録する"""
    state = {"by_region": {}, "asked": []}

    def fake(region, now):
        state["asked"].append(region)
        return state["by_region"].get(region)

    monkeypatch.setattr(recommend_web, "get_max_temperature", fake)
    return state


@pytest.fixture
def context_embedding(monkeypatch):
    """偽の「今日の様子」のベクトル。架空の商品の仮ベクトルの次元に合わせて、文の中身で向きを決める
    (仮ベクトルの次元: [和菓子らしさ, 甘さ, 果物, チョコ・洋酒, やわらかさ, 冷たさ])。
    vector を決めると、文の中身にかかわらずその向きを返す"""
    state = {"texts": [], "fail": False, "vector": None}

    def fake(text):
        state["texts"].append(text)
        if state["fail"]:
            return None
        if state["vector"] is not None:
            return state["vector"]
        if "冷たく" in text:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        if "温かい" in text:
            return (0.3, 0.0, 0.0, 0.0, 0.9, -1.0)
        return (0.0, 0.0, 0.0, 0.0, 1.0, 0.0)

    monkeypatch.setattr(recommend_web, "compute_context_embedding", fake)
    return state


@pytest.fixture
def client(store, clock, reasons, temperature, context_embedding):
    main.app.dependency_overrides[get_store] = lambda: store
    main.app.dependency_overrides[get_user_id] = lambda: USER_ID
    main.app.dependency_overrides[get_now] = lambda: clock["now"]
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def dislike(client, *categories):
    assert client.put("/api/preferences/dislikes", json={"categories": list(categories)}).status_code == 204


# 仮ベクトルで、その品の向きになる今日の様子(気分を「げんき」にして、今日の様子で寄せる)
CHOCOLATE = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0)     # こいめのチョコケーキ(チョコレートケーキ・520円)


# ==== 家族の設定 ====

def test_設定ページを開ける(client):
    assert client.get("/settings").status_code == 200


def test_設定を保存して読み出せる(client, store):
    body = {"allergies": ["卵", "くるみ"], "dietRestrictions": ["no-dairy"], "budgetMax": 500,
            "stores": ["架空堂 試作店"], "repeatAvoidance": 1.0, "region": "東京都"}

    assert client.put("/api/settings", json=body).status_code == 204

    data = client.get("/api/settings").json()
    assert data["saved"] is True
    assert data["settings"] == {**body, "allergies": ["くるみ", "卵"]}
    assert store.get_settings(USER_ID) == FamilySettings(
        ("くるみ", "卵"), ("no-dairy",), 500, ("架空堂 試作店",), 1.0, region="東京都")
    assert len(data["options"]["regions"]) == 47


@pytest.mark.parametrize("body", [
    {"allergies": ["たまご"]},              # 選択肢にないアレルゲン名(書き間違い)
    {"dietRestrictions": ["low-sugar"]},
    {"stores": ["実在しない店"]},
    {"budgetMax": -1},
    {"repeatAvoidance": 5},
    {"region": "東京"},                     # 選択肢にない地域名(書き間違い)
])
def test_選択肢にない値や範囲外の値は保存しない(client, store, body):
    assert client.put("/api/settings", json=body).status_code == 422
    assert store.get_settings(USER_ID) is None


# ==== 今日のおすすめ ====

def save_settings(client, **changes):
    body = {"allergies": [], "dietRestrictions": [], "budgetMax": None, "stores": [], "repeatAvoidance": 0.6,
            "region": None}
    body.update(changes)
    assert client.put("/api/settings", json=body).status_code == 204


def recommend_today(client, budget="large", mood="normal"):
    response = client.get("/api/recommendation", params={"budget": budget, "mood": mood})
    assert response.status_code == 200
    return response.json()


def product_named(store, name):
    return next(p for p in store.list_products() if p.name == name)


def top_name(data):
    """いちばんのおすすめの品の名前"""
    return data["items"][0]["name"]


def shown_products(store, data):
    """勧められたすべての品(点数の高い順)"""
    return [product_named(store, item["name"]) for item in data["items"]]


def test_おすすめページを開ける(client):
    assert "今日のおすすめ" in client.get("/recommendation").text


def test_今日の気温と_お金の量3段階と_気分5段階の選択肢を返す(client, temperature):
    save_settings(client, region="東京都")
    temperature["by_region"]["東京都"] = 31.0

    data = client.get("/api/recommendation/today").json()

    assert data["maxTemperature"] == 31.0
    assert [b["code"] for b in data["budgets"]] == ["small", "medium", "large"]
    assert [m["code"] for m in data["moods"]] == ["great", "good", "normal", "tired", "exhausted"]


def test_地域が未設定なら気温はnull(client):
    save_settings(client)
    assert client.get("/api/recommendation/today").json()["maxTemperature"] is None


@pytest.mark.parametrize("params", [
    {},                                         # 答えていない
    {"budget": "large"},                        # 気分を答えていない
    {"budget": "huge", "mood": "normal"},       # 選択肢にないお金の量
    {"budget": "large", "mood": "angry"},       # 選択肢にない気分
])
def test_お金の量と気分を選択肢から答えていなければ勧めない(client, store, params):
    save_settings(client)
    assert client.get("/api/recommendation", params=params).status_code == 422
    assert store.list_preferences(USER_ID) == []


def test_家族の設定がまだでも_苦手を選んだだけで勧める(client, store):
    dislike(client, "chestnut", "citrus")

    data = recommend_today(client)

    assert data["status"] == "ok"
    assert data["settingsSaved"] is False          # ページに家族向けの注意を出す
    for chosen in shown_products(store, data):
        assert not {"chestnut", "citrus"} & product_tags(chosen)
        assert chosen.allergens is not None        # 設定がなくても、アレルゲン不明の品は外す


def test_家族の設定がまだのときは_アレルギーを考えずに選んだことを家族向けに伝える(client):
    assert "アレルギーは 考えずに 選んでいます" in client.get("/recommendation").text


def test_家族の設定があれば注意は出さない(client):
    save_settings(client)
    assert recommend_today(client)["settingsSaved"] is True


def test_苦手を記録したあとも_苦手でない品を勧める(client, store):
    # 不具合の再現: 苦手を項目から選んで記録すると、おすすめが表示されなかった
    save_settings(client)
    dislike(client, "chestnut", "citrus")

    data = recommend_today(client)

    assert data["status"] == "ok"
    for chosen in shown_products(store, data):
        assert not {"chestnut", "citrus"} & product_tags(chosen)


def test_スイーツを5品_写真_名前_価格_理由つきで勧め_勧めた記録を残す(client, store, reasons):
    save_settings(client)

    data = recommend_today(client)

    assert data["status"] == "ok"
    assert len(data["items"]) == 5
    assert len({item["name"] for item in data["items"]}) == 5       # 同じ品は2回出さない
    for item in data["items"]:
        assert set(item) == {"name", "imageUrl", "price", "reason"}
        assert item["reason"] == "やわらかくて、ほっとする味です。"
    # 5品の理由は、Gemini を1回だけ呼んでまとめて作る
    assert reasons["calls"] == 1 and reasons["counts"] == [5]
    # 見せた5品をすべて「勧めた」として記録する
    recommended = [p for p in store.list_preferences(USER_ID) if p.kind == "recommended"]
    assert [store.get_product(p.product_id).name for p in recommended] == [item["name"] for item in data["items"]]
    assert all(p.categories for p in shown_products(store, data))


def test_5品は今日の様子に合う順に並べる(client, store, context_embedding):
    save_settings(client, repeatAvoidance=0.0)
    context_embedding["vector"] = CHOCOLATE

    data = recommend_today(client, mood="good")

    fitness = [cosine(p.embedding, CHOCOLATE) for p in shown_products(store, data)]
    assert top_name(data) == "【架空】こいめのチョコケーキ"
    assert fitness == sorted(fitness, reverse=True)


def test_候補が5品より少なければ_残った品だけを勧める(client, store):
    save_settings(client, budgetMax=200)
    affordable = [p for p in store.list_products() if exclusion_reason(p, FamilySettings(budget_max=200),
                                                                        TODAY, frozenset()) is None]
    assert 0 < len(affordable) < 5      # 前提: 200円までで勧められる品は5品より少ない

    data = recommend_today(client)

    assert {item["name"] for item in data["items"]} == {p.name for p in affordable}


def test_スイーツ以外の品は今日の様子にいちばん合っても勧めない(client, store, context_embedding):
    save_settings(client)
    udon = store.add_product(replace(store.list_products()[0], id=None, name="【架空】ひやしうどん", categories=None))
    store.update_product_embedding(udon.id, CHOCOLATE, MODEL)
    context_embedding["vector"] = CHOCOLATE

    data = recommend_today(client, mood="good")

    assert top_name(data) == "【架空】こいめのチョコケーキ"
    assert "【架空】ひやしうどん" not in {item["name"] for item in data["items"]}


def test_苦手と選んだ項目の品は勧めない(client, store, context_embedding):
    save_settings(client)
    context_embedding["vector"] = CHOCOLATE
    dislike(client, "chocolate-cake")

    for chosen in shown_products(store, recommend_today(client, mood="good")):
        assert "chocolate-cake" not in chosen.categories


def test_チーズケーキだけを苦手にしても_ほかのケーキは勧める(client, store, context_embedding):
    save_settings(client)
    # チーズケーキの向き(仮ベクトル)に寄せる。次に近いのはほかのケーキ
    context_embedding["vector"] = (0.0, 0.5, 0.1, 0.0, 0.7, 0.3)
    dislike(client, "cheesecake")

    chosen = product_named(store, top_name(recommend_today(client, mood="good")))

    assert chosen.name != "【架空】やきチーズケーキ"
    assert {"shortcake", "chocolate-cake"} & set(chosen.categories)


def test_和菓子を一括で苦手にすると_あずきの品も項目のない和菓子も勧めない(client, store, context_embedding):
    save_settings(client)
    context_embedding["vector"] = (1.0, 0.5, 0.0, 0.0, 0.7, 0.0)   # みたらしだんごの向き
    dislike(client, "japanese")

    for chosen in shown_products(store, recommend_today(client, mood="good")):
        assert "western" in product_tags(chosen)


def test_苦手なフルーツが入った品は勧めない(client, store, context_embedding):
    save_settings(client)
    context_embedding["vector"] = (0.0, 0.8, 0.9, 0.0, 0.9, 0.3)   # いちごのショートケーキの向き
    dislike(client, "strawberry")

    for chosen in shown_products(store, recommend_today(client, mood="good")):
        assert "strawberry" not in chosen.categories


def test_洋菓子と和菓子を一括で苦手にすると勧められる品がない(client, store):
    save_settings(client)
    dislike(client, "western", "japanese")

    assert recommend_today(client)["status"] == "none"


def test_苦手を選び直して今日の品が当たれば同じ日でも選び直す(client, store, context_embedding):
    save_settings(client)
    context_embedding["vector"] = CHOCOLATE
    first = top_name(recommend_today(client, mood="good"))
    assert first == "【架空】こいめのチョコケーキ"

    dislike(client, "chocolate-cake")
    for chosen in shown_products(store, recommend_today(client, mood="good")):
        assert "chocolate-cake" not in chosen.categories


def test_アレルゲン不明の品は勧めない(client, store, context_embedding):
    save_settings(client)
    # 不明の品(ゆずのわらびもち)の向きに寄せても、その品は勧めない
    context_embedding["vector"] = (0.9, 0.5, 0.6, 0.0, 1.0, 0.8)

    names = {item["name"] for item in recommend_today(client, mood="good")["items"]}

    assert not names & {"【架空】くりのモンブラン", "【架空】ゆずのわらびもち"}


@pytest.mark.parametrize("budget, family_max, limit", [
    ("small", None, 500),
    ("medium", 300, 300),       # 家族の設定の上限のほうが低ければ、そちらを使う
])
def test_今日つかうお金の量と家族の上限の低いほうを超える品は勧めない(
    client, store, context_embedding, budget, family_max, limit
):
    save_settings(client, budgetMax=family_max)
    # 上限を超える品(チョコケーキ 520円)の向きに寄せても、上限を超えるなら勧めない
    context_embedding["vector"] = CHOCOLATE

    data = recommend_today(client, budget=budget, mood="good")

    assert all(item["price"] <= limit for item in data["items"])


def test_ちょっとぜいたくなら家族の上限までの品を勧める(client, store, context_embedding):
    save_settings(client)
    context_embedding["vector"] = CHOCOLATE
    assert top_name(recommend_today(client, budget="large", mood="good")) == "【架空】こいめのチョコケーキ"


def test_暑い日には冷たい品を_寒い日には温かい品を勧める(client, store, clock, temperature, context_embedding):
    save_settings(client, region="東京都", repeatAvoidance=0.0)

    clock["now"] = datetime(2027, 7, 10, 10, 0, tzinfo=JST)     # れもんのゼリーの販売期間
    temperature["by_region"]["東京都"] = 33.0
    hot = product_named(store, top_name(recommend_today(client)))
    clock["now"] = datetime(2027, 1, 10, 10, 0, tzinfo=JST)
    temperature["by_region"]["東京都"] = 3.0
    cold = product_named(store, top_name(recommend_today(client)))

    assert hot.name == "【架空】れもんのゼリー"
    assert cold.embedding[5] <= 0.1       # 冷たさの次元
    assert "暑い" in context_embedding["texts"][0] and "寒い" in context_embedding["texts"][1]


def test_気分に合う言い表しで品を寄せる(client, store, context_embedding):
    save_settings(client)
    recommend_today(client, mood="exhausted")
    assert "つかれた" in context_embedding["texts"][0]


def test_気温が分からず気分もふつうなら今日の様子では寄せない(client, store, context_embedding):
    save_settings(client)

    assert recommend_today(client, mood="normal")["status"] == "ok"
    assert context_embedding["texts"] == []


def test_今日の様子のベクトルを作れなくても勧める(client, store, temperature, context_embedding):
    save_settings(client, region="東京都")
    temperature["by_region"]["東京都"] = 33.0
    context_embedding["fail"] = True

    assert recommend_today(client)["status"] == "ok"


def test_理由を書かせるときは気温の言い方と気分だけを渡し_地域や数字は渡さない(client, store, temperature, reasons):
    save_settings(client, region="東京都")
    temperature["by_region"]["東京都"] = 33.0

    data = recommend_today(client, mood="tired")

    assert reasons["today"] == [{"weather": "暑い日", "mood": "すこし つかれた"}]
    assert data["maxTemperature"] == 33.0


def test_同じ日に同じ答えなら同じ品を返し_Geminiも呼び直さない(client, store, clock, reasons):
    save_settings(client)
    first = recommend_today(client, mood="good")

    clock["now"] = datetime(2026, 11, 16, 23, 59, tzinfo=JST)
    second = recommend_today(client, mood="good")

    assert second == first
    assert reasons["calls"] == 1
    assert sum(p.kind == "recommended" for p in store.list_preferences(USER_ID)) == len(first["items"])


def test_同じ日でも答えを変えると選び直す(client, store, reasons):
    save_settings(client)
    first = recommend_today(client, budget="large")

    data = recommend_today(client, budget="small")

    assert reasons["calls"] == 2
    assert all(item["price"] <= 500 for item in data["items"])
    assert sum(p.kind == "recommended" for p in store.list_preferences(USER_ID)) \
        == len(first["items"]) + len(data["items"])


def test_日が変わると選び直し_前の日の品は避けられる(client, store, clock):
    save_settings(client, repeatAvoidance=1.0)
    first_day = recommend_today(client)

    clock["now"] = datetime(2026, 11, 17, 9, 0, tzinfo=JST)
    next_day = recommend_today(client)

    assert top_name(next_day) != top_name(first_day)
    assert sum(p.kind == "recommended" for p in store.list_preferences(USER_ID)) \
        == len(first_day["items"]) + len(next_day["items"])


def test_設定を変えて今日の品が除外に当たれば選び直す(client, store):
    save_settings(client)
    first = top_name(recommend_today(client))
    first_product = product_named(store, first)

    # 今日の品のアレルゲンをすべてアレルギーに登録する
    save_settings(client, allergies=list(first_product.allergens) or ["卵"], budgetMax=first_product.price - 1)
    data = recommend_today(client)

    assert data["status"] in ("ok", "none")
    if data["status"] == "ok":
        assert top_name(data) != first


def test_設定を変えて今日の品の1つでも除外に当たれば選び直す(client, store):
    save_settings(client)
    first = shown_products(store, recommend_today(client))
    # 2品め以降のどれかにだけあって、いちばんのおすすめにはないアレルゲンを、アレルギーに登録する
    target = next(p for p in first[1:] if set(p.allergens) - set(first[0].allergens))
    allergen = sorted(set(target.allergens) - set(first[0].allergens))[0]
    save_settings(client, allergies=[allergen])

    data = recommend_today(client)

    assert target.name not in {item["name"] for item in data["items"]}
    assert all(allergen not in p.allergens for p in shown_products(store, data))


def test_候補が1つも残らなければおすすめできる品がない(client, store):
    save_settings(client, budgetMax=10)
    assert recommend_today(client) == {"status": "none", "maxTemperature": None, "settingsSaved": True}
    assert store.list_preferences(USER_ID) == []


@pytest.mark.parametrize("bad_reason", [
    "さくらもちもおすすめです。",           # 別の商品名
    "残りわずか!お早めにどうぞ。",         # 急がせる
])
def test_検査に通らない理由は外して理由なしで表示する(client, store, reasons, bad_reason):
    save_settings(client)
    reasons["reason"] = bad_reason

    data = recommend_today(client)

    assert data["status"] == "ok"
    # 理由は1品ずつ、その品について検査する(さくらもち自身の理由に「さくらもち」とあるのはよい)
    for item in data["items"]:
        if "さくらもち" not in item["name"]:
            assert item["reason"] is None


def test_Geminiの答えに番号がない品は理由なしで表示する(client, store, monkeypatch):
    save_settings(client)
    monkeypatch.setattr(recommend_web, "generate_reasons",
                        lambda products, today: ["ほっとする味です。"] + [None] * (len(products) - 1))

    data = recommend_today(client)

    assert [item["reason"] for item in data["items"]] == ["ほっとする味です。"] + [None] * (len(data["items"]) - 1)


def test_Geminiを呼べなければ理由なしで表示し_次に開いたときに作り直す(client, store, reasons):
    save_settings(client)
    reasons["fail"] = True
    first = recommend_today(client)

    reasons["fail"] = False
    second = recommend_today(client)

    assert all(item["reason"] is None for item in first["items"])
    assert [item["name"] for item in second["items"]] == [item["name"] for item in first["items"]]
    assert all(item["reason"] == "やわらかくて、ほっとする味です。" for item in second["items"])
    assert reasons["counts"] == [5, 5]      # 作り直すときも、5品ぶんをまとめて1回で


def test_おすすめのページに購入や注文に進む操作はない(client):
    # 置いてよいのは、お金の量・気分を答えるボタンと、もどる・こたえなおすボタンだけ
    html = client.get("/recommendation").text
    assert "<a " not in html
    assert "<form" not in html
    assert set(re.findall(r"<button[^>]*>([^<]*)</button>", html)) == {"もどる", "こたえなおす"}
    # 答えのボタンの文字(サーバーが返す選択肢)にも、購入や注文を促す言葉はない
    data = client.get("/api/recommendation/today").json()
    for item in data["budgets"] + data["moods"]:
        assert not PUSHY_PATTERN.search(item["label"])


def test_Geminiの答えの番号はコードで確かめ_品の順にそろえる(store, monkeypatch):
    # 番号 3 の答えがなく、番号 1 は2回、一覧にない番号 9 もある答え
    answer = ('{"reasons": [{"number": 2, "reason": "二"}, {"number": 1, "reason": "一"},'
              ' {"number": 1, "reason": "一の2回め"}, {"number": 9, "reason": "九"}]}')
    sent = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            sent["contents"] = contents
            return type("Response", (), {"text": answer})()

    monkeypatch.setattr(recommend_web.gemini, "client", lambda: type("Client", (), {"models": FakeModels()})())
    monkeypatch.setattr(recommend_web.gemini, "text_model", lambda: "test-model")
    products = store.list_products()[:3]

    reasons = recommend_web.generate_reasons(products, {"weather": None, "mood": "ふつう"})

    assert reasons == ["一", "二", None]
    # 送るのは品の番号・名前・説明・季節限定かどうかと、今日の様子だけ
    assert '"number": 3' in sent["contents"] and products[2].name in sent["contents"]
    assert USER_ID not in sent["contents"]
