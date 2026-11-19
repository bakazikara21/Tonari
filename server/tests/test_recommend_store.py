"""お勧め機能の保存と読み出し(recommend_store.py)のテスト。毎回、空のデータベースで行う。"""

import sqlite3
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from demo_data import DEMO_PRODUCTS, seed_demo_products
from recommend import DISLIKE_CODES, product_tags
from recommend_store import DailyPick, FamilySettings, PickItem, Product, RecommendStore


@pytest.fixture
def store(tmp_path):
    store = RecommendStore(tmp_path / "test.db")
    store.init_schema()
    return store


def make_product(name="【架空】ためしのケーキ", allergens=("卵", "乳"), embedding=(0.1, 0.2), **changes):
    values = dict(
        name=name, description="ためしの説明", image_url="data:image/svg+xml,test", price=400,
        allergens=allergens, sale_start=date(2027, 3, 1), sale_end=date(2027, 4, 30), seasonal=True,
        store="架空堂", embedding=embedding, embedding_model=None if embedding is None else "test-model",
    )
    values.update(changes)
    return Product(**values)


# ---- 商品カタログ ----

def test_商品を保存して同じ内容で読み出せる(store):
    saved = store.add_product(make_product())

    assert saved.id is not None
    assert store.get_product(saved.id) == saved


def test_アレルゲンの不明となしを区別して保存する(store):
    unknown = store.add_product(make_product(name="不明", allergens=None))
    none = store.add_product(make_product(name="なし", allergens=()))

    assert store.get_product(unknown.id).allergens is None
    assert store.get_product(none.id).allergens == ()


def test_アレルゲン不明の商品を除いて一覧にできる(store):
    known = store.add_product(make_product(name="分かる"))
    store.add_product(make_product(name="不明", allergens=None))

    assert [p.id for p in store.list_products(allergens_known_only=True)] == [known.id]
    assert len(store.list_products()) == 2


def test_ベクトルのない商品も保存できる(store):
    saved = store.add_product(make_product(embedding=None))

    loaded = store.get_product(saved.id)
    assert loaded.embedding is None and loaded.embedding_model is None


def test_ベクトルだけあってモデル名がない商品は保存できない(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.add_product(make_product(embedding=(0.1,), embedding_model=None))


def test_ない商品はNoneを返す(store):
    assert store.get_product(999) is None


# ---- 記録(勧めた記録・以前の好みの記録) ----

def test_好みを記録して読み出せる(store):
    product = store.add_product(make_product())
    when = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    saved = store.add_preference("user-a", product.id, "like", created_at=when)

    assert store.list_preferences("user-a") == [saved]
    assert saved.created_at == when
    # 記録した時点の商品のベクトルを写して持つ
    assert saved.embedding == product.embedding


def test_好みの記録は利用者ごとに分かれる(store):
    product = store.add_product(make_product())
    store.add_preference("user-a", product.id, "like")
    store.add_preference("user-b", product.id, "dislike")

    assert [p.kind for p in store.list_preferences("user-a")] == ["like"]
    assert [p.kind for p in store.list_preferences("user-b")] == ["dislike"]
    assert store.list_preferences("user-c") == []


@pytest.mark.parametrize("kind", ["like", "dislike", "neutral", "recommended"])
def test_4種類の記録を保存できる(store, kind):
    product = store.add_product(make_product())
    assert store.add_preference("user-a", product.id, kind).kind == kind


@pytest.mark.parametrize("user_id, product_id, kind", [
    ("", 1, "like"),             # 利用者 ID がない
    ("user-a", 1, "love"),       # 決まっていない種類
    ("user-a", 999, "like"),     # ない商品
])
def test_正しくない記録は保存しない(store, user_id, product_id, kind):
    store.add_product(make_product())
    with pytest.raises(ValueError):
        store.add_preference(user_id, product_id, kind)
    assert store.list_preferences("user-a") == []


def test_記録は別の接続で開き直しても残っている(tmp_path):
    path = tmp_path / "persist.db"
    first = RecommendStore(path)
    first.init_schema()
    product = first.add_product(make_product())
    first.add_preference("user-a", product.id, "neutral")

    reopened = RecommendStore(path)
    assert [p.kind for p in reopened.list_preferences("user-a")] == ["neutral"]


# ---- 架空の商品データ ----

def test_架空の商品を12品登録し_二重には登録しない(store):
    assert seed_demo_products(store) == 12
    assert seed_demo_products(store) == 0
    assert store.count_products() == 12


def test_架空の商品はすべてスイーツで_選択肢にある項目だけを持つ(store):
    seed_demo_products(store)
    products = {p.name: p for p in store.list_products()}

    assert all(p.categories and set(p.categories) <= set(DISLIKE_CODES) for p in products.values())
    # どの品も、洋菓子か和菓子のどちらか一方に当たる
    for p in products.values():
        assert len(product_tags(p) & {"western", "japanese"}) == 1
    assert products["【架空】いちごのショートケーキ"].categories == ("shortcake", "strawberry")
    assert products["【架空】こしあんの大福"].categories == ("azuki",)
    assert products["【架空】みたらしだんご"].categories == ("japanese",)
    assert products["【架空】やきチーズケーキ"].categories == ("cheesecake",)


def test_以前の項目を持つ架空の商品は_今の項目に書き込み直す(store):
    old = store.add_product(replace(DEMO_PRODUCTS[6], categories=("daifuku",)))   # 以前の「大福」

    seed_demo_products(store)

    assert store.get_product(old.id).categories == ("azuki",)


def test_項目のない架空の商品には項目を書き込み_ほかの商品には触れない(store):
    # 項目を持つ前に登録された架空の品と、スイーツ以外の品があるデータベース
    old = store.add_product(replace(DEMO_PRODUCTS[0], categories=None))
    other = store.add_product(make_product(name="【架空】ひやしうどん", categories=None))

    seed_demo_products(store)

    assert store.get_product(old.id).categories == DEMO_PRODUCTS[0].categories
    assert store.get_product(other.id).categories is None


def test_架空の商品は名前で架空と分かり_アレルゲン不明が2品ある(store):
    seed_demo_products(store)
    products = store.list_products()

    assert all(p.name.startswith("【架空】") for p in products)
    assert sum(p.allergens is None for p in products) == 2
    assert all(p.image_url.startswith("data:image/png;base64,") for p in products)


# ---- 家族の設定・日ごとのおすすめ・ベクトルの書き換え ----

def test_家族の設定を利用者ごとに保存し_上書きできる(store):
    from recommend_store import FamilySettings

    assert store.get_settings("user-a") is None
    store.save_settings("user-a", FamilySettings(allergies=("卵",), budget_max=500))
    store.save_settings("user-a", FamilySettings(allergies=("乳",), stores=("架空堂",), repeat_avoidance=1.0))
    store.save_settings("user-b", FamilySettings())

    assert store.get_settings("user-a") == FamilySettings(allergies=("乳",), stores=("架空堂",), repeat_avoidance=1.0)
    assert store.get_settings("user-b") == FamilySettings()


def test_日ごとのおすすめは利用者と日で1つだけ持ち_答えも一緒に保存する(store):
    first = store.add_product(make_product(name="【架空】1"))
    second = store.add_product(make_product(name="【架空】2"))

    store.save_daily_pick(DailyPick("user-a", "2026-11-16", "large", "normal", (PickItem(first.id, "理由", "ok"),)))
    store.save_daily_pick(DailyPick("user-a", "2026-11-16", "small", "tired", (PickItem(second.id, None, "rejected"),)))

    assert store.get_daily_pick("user-a", "2026-11-16") == DailyPick(
        "user-a", "2026-11-16", "small", "tired", (PickItem(second.id, None, "rejected"),))
    assert store.get_daily_pick("user-a", "2026-11-17") is None
    assert store.get_daily_pick("user-b", "2026-11-16") is None


def test_日ごとのおすすめは複数の品を順番と理由ごと保存する(store):
    ids = [store.add_product(make_product(name=f"【架空】{n}")).id for n in range(5)]
    items = tuple(PickItem(i, f"理由{n}" if n % 2 == 0 else None, "ok" if n % 2 == 0 else "error")
                  for n, i in enumerate(reversed(ids)))

    store.save_daily_pick(DailyPick("user-a", "2026-11-16", "large", "normal", items))

    assert store.get_daily_pick("user-a", "2026-11-16").items == items


@pytest.mark.parametrize("items", [
    (),                                     # 品が1つもない
    (PickItem(1, None, "unknown"),),        # 決まった値でない理由の状態
])
def test_正しくない日ごとのおすすめは保存しない(store, items):
    with pytest.raises(ValueError):
        store.save_daily_pick(DailyPick("user-a", "2026-11-16", "large", "normal", items))
    assert store.get_daily_pick("user-a", "2026-11-16") is None


def test_1日1品だった頃のおすすめは_その1品を持つ記録として移す(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE daily_picks (
            user_id TEXT NOT NULL, day TEXT NOT NULL, budget TEXT NOT NULL, mood TEXT NOT NULL,
            product_id INTEGER NOT NULL, reason TEXT, reason_status TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, day))""")
        conn.execute("""INSERT INTO daily_picks VALUES
            ('user-a', '2026-11-16', 'large', 'good', 3, 'ほっとする味です。', 'ok', '2026-11-16T01:00:00+00:00')""")
    conn.close()

    store = RecommendStore(path)
    store.init_schema()
    store.init_schema()     # 2回目は何もしない

    assert store.get_daily_pick("user-a", "2026-11-16") == DailyPick(
        "user-a", "2026-11-16", "large", "good", (PickItem(3, "ほっとする味です。", "ok"),))


def test_住んでいる地域を設定と一緒に保存する(store):
    store.save_settings("user-a", FamilySettings(region="大阪府"))
    assert store.get_settings("user-a").region == "大阪府"


def test_地域の列がない古い設定の表に列を足し_既存の設定を残す(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE family_settings (
            user_id TEXT PRIMARY KEY, allergies TEXT NOT NULL, diet_restrictions TEXT NOT NULL,
            budget_max INTEGER, stores TEXT NOT NULL, repeat_avoidance REAL NOT NULL, updated_at TEXT NOT NULL)""")
        conn.execute("""INSERT INTO family_settings VALUES ('user-a', '["卵"]', '[]', 500, '[]', 0.6, '2026-11-01')""")
    conn.close()

    store = RecommendStore(path)
    store.init_schema()

    assert store.get_settings("user-a") == FamilySettings(allergies=("卵",), budget_max=500, repeat_avoidance=0.6)


def test_苦手な項目を利用者ごとにまとめて置き換える(store):
    assert store.get_disliked_categories("user-a") is None

    store.save_disliked_categories("user-a", ("cheesecake", "senbei"))
    store.save_disliked_categories("user-a", ("dango",))      # 選び直すと、前の選択は残さない
    store.save_disliked_categories("user-b", ())

    assert store.get_disliked_categories("user-a") == ("dango",)
    assert store.get_disliked_categories("user-b") == ()


def test_商品の項目を保存して読み出せる(store):
    saved = store.add_product(make_product(categories=("shortcake", "strawberry")))
    assert store.get_product(saved.id).categories == ("shortcake", "strawberry")
    store.update_product_categories(saved.id, ("jelly",))
    assert store.get_product(saved.id).categories == ("jelly",)


def test_1品に1つの種類を持つ以前の列を消し_項目の列に移す(tmp_path):
    path = tmp_path / "before-items.db"
    first = RecommendStore(path)
    first.init_schema()
    with first._connect() as conn:
        conn.execute("ALTER TABLE products ADD COLUMN category TEXT")
    first.add_product(make_product())

    reopened = RecommendStore(path)
    reopened.init_schema()

    with reopened._connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
    assert "category" not in columns and "categories" in columns
    assert reopened.list_products()[0].categories == make_product().categories


def test_商品のベクトルとモデル名を組で書き換える(store):
    saved = store.add_product(make_product())
    store.update_product_embedding(saved.id, (0.6, 0.8), "gemini-embedding-2")

    loaded = store.get_product(saved.id)
    assert (loaded.embedding, loaded.embedding_model) == ((0.6, 0.8), "gemini-embedding-2")
    with pytest.raises(ValueError):
        store.update_product_embedding(999, (1.0,), "gemini-embedding-2")


# ---- 以前の「写真で教える」記録の形(データベースには残す) ----

def test_写真の記録はデータベースでも商品か写真のどちらか一方しか持てない(store):
    product = store.add_product(make_product())
    with store._connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO preferences (user_id, product_id, kind, created_at, embedding, embedding_model, photo, photo_mime)
               VALUES ('user-a', ?, 'like', '2026-11-16', '[1.0]', 'm', x'00', 'image/jpeg')""", (product.id,))


def test_古い形の好みの記録を残したまま写真を持てる形に移す(tmp_path):
    path = tmp_path / "old.db"
    # 写真に対応する前の形の表を作り、記録を1件入れておく
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL,
            image_url TEXT NOT NULL, price INTEGER NOT NULL, allergens TEXT, sale_start TEXT, sale_end TEXT,
            seasonal INTEGER NOT NULL, store TEXT NOT NULL, embedding TEXT, embedding_model TEXT);
        CREATE TABLE preferences (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id), kind TEXT NOT NULL, created_at TEXT NOT NULL,
            embedding TEXT);
        INSERT INTO products VALUES (1, '【架空】ためし', '説明', 'data:', 100, '[]', NULL, NULL, 0, '架空堂', '[1.0, 0.0]', 'manual-demo-v1');
        INSERT INTO preferences VALUES (7, 'user-a', 1, 'like', '2026-11-15T00:00:00+00:00', '[1.0, 0.0]');
    """)
    old.commit()
    old.close()

    store = RecommendStore(path)
    store.init_schema()

    [moved] = store.list_preferences("user-a")
    assert (moved.id, moved.product_id, moved.kind, moved.embedding) == (7, 1, "like", (1.0, 0.0))
    assert moved.embedding_model == "manual-demo-v1"
    # 移す前のファイルを残している
    assert (tmp_path / "old.db.before-photo-migration").exists()
    # お菓子の種類の列も足され、古い商品はスイーツ以外の扱いになる
    assert store.get_product(1).categories is None
    # 2回目は移し直さない
    store.init_schema()
    assert len(store.list_preferences("user-a")) == 1


# ---- サーバーを開くときの項目のそろえ直し ----

def test_サーバーを開くと_項目のない架空の品にも項目が入り_おすすめの対象になる(tmp_path, monkeypatch):
    # 不具合の再現: 項目の列を足したあと demo_data.py を実行し直していないデータベース
    path = tmp_path / "no-items.db"
    store = RecommendStore(path)
    store.init_schema()
    for product in DEMO_PRODUCTS:
        store.add_product(replace(product, categories=None))

    monkeypatch.setenv("TONARI_DB_PATH", str(path))
    from recommend_web import open_store
    opened = open_store()

    by_name = {p.name: p for p in opened.list_products()}
    assert all(by_name[p.name].categories == p.categories for p in DEMO_PRODUCTS)


def test_項目のそろえ直しは架空の品以外に触れず_そろっていれば何もしない(store):
    from demo_data import update_demo_categories
    seed_demo_products(store)
    real = store.add_product(make_product(name="ほかの店の品", categories=("cheesecake",)))

    assert update_demo_categories(store) == 0
    assert store.get_product(real.id).categories == ("cheesecake",)
