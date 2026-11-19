"""動作確認用の架空の商品データ(洋菓子・和菓子 12 品)。

すべて架空のデータで、実在の店舗の商品・写真・説明文は使っていない。
名前の先頭に【架空】を付け、写真は単色の仮画像(PNG)にしている。
登録時のベクトルは手で決めた仮の値(モデル名 manual-demo-v1)。
embeddings.py を実行すると、Gemini の埋め込みベクトルに置き換わる。
  仮の値の次元: [和菓子らしさ, 甘さ, 果物, チョコ・洋酒, やわらかさ, 冷たさ]
苦手を選ぶ項目(categories)も、ここで登録したとおりに扱う(AI に推測させない)。

使い方(server フォルダで): .venv/bin/python demo_data.py
"""

import base64
import struct
import zlib
from datetime import date

from recommend_store import Product, RecommendStore

DEMO_EMBEDDING_MODEL = "manual-demo-v1"
DEMO_STORE = "架空堂 試作店"


def placeholder_image(color: str, size: int = 64) -> str:
    """単色の仮画像(PNG)を data URL で返す。埋め込みに使えるよう PNG にしている。"""
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    row = b"\x00" + bytes((red, green, blue)) * size  # 各行の先頭は「フィルタなし」

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))  # 8bit RGB
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _product(name, description, color, price, allergens, vector, categories, *, seasonal=False, sale=(None, None)):
    return Product(
        name=f"【架空】{name}",
        description=description,
        image_url=placeholder_image(color),
        price=price,
        allergens=None if allergens is None else tuple(allergens),
        sale_start=sale[0],
        sale_end=sale[1],
        seasonal=seasonal,
        store=DEMO_STORE,
        embedding=tuple(vector),
        embedding_model=DEMO_EMBEDDING_MODEL,
        categories=tuple(categories),
    )


DEMO_PRODUCTS = [
    # ---- 洋菓子 ----
    _product("いちごのショートケーキ", "ふわふわの生地に、いちごとクリーム。", "#F8C8D0",
             480, ["卵", "乳", "小麦"], [0.0, 0.8, 0.9, 0.0, 0.9, 0.3], ["shortcake", "strawberry"]),
    _product("こいめのチョコケーキ", "ほろにがいチョコの、しっとりケーキ。", "#6B4226",
             520, ["卵", "乳", "小麦", "大豆"], [0.0, 0.7, 0.0, 1.0, 0.6, 0.2], ["chocolate-cake"]),
    _product("やきチーズケーキ", "こんがり焼いた、やさしい味のチーズケーキ。", "#F2D27A",
             450, ["卵", "乳", "小麦"], [0.0, 0.5, 0.1, 0.0, 0.7, 0.3], ["cheesecake"]),
    _product("くるみのクッキー", "さくさくの、くるみ入りクッキー。", "#C9A26B",
             300, ["卵", "乳", "小麦", "くるみ"], [0.1, 0.5, 0.0, 0.0, 0.1, 0.0], ["cookie"]),
    _product("れもんのゼリー", "さっぱりした、れもんのゼリー。", "#F7EE7F",
             350, [], [0.2, 0.4, 0.9, 0.0, 0.8, 1.0], ["jelly", "citrus"], seasonal=True,
             sale=(date(2027, 6, 1), date(2027, 8, 31))),
    _product("くりのモンブラン", "くりのクリームを、たっぷりのせました。", "#B08850",
             560, None, [0.3, 0.8, 0.3, 0.2, 0.8, 0.2], ["montblanc", "chestnut"], seasonal=True,
             sale=(date(2026, 9, 1), date(2026, 11, 30))),  # アレルゲン不明の品
    # ---- 和菓子(あずき・クリーム・ドライフルーツのどれにも当たらない品は、分類 japanese だけを持つ) ----
    _product("こしあんの大福", "やわらかいおもちに、なめらかなこしあん。", "#F5F5F0",
             200, [], [1.0, 0.8, 0.0, 0.0, 0.9, 0.0], ["azuki"]),
    _product("さくらもち", "さくらの葉の、よいかおり。", "#F4B6C2",
             220, [], [1.0, 0.7, 0.1, 0.0, 0.8, 0.0], ["azuki"], seasonal=True,
             sale=(date(2027, 2, 15), date(2027, 4, 15))),
    _product("みたらしだんご", "あまじょっぱい、たれのおだんご。", "#D9A441",
             150, ["小麦", "大豆"], [1.0, 0.5, 0.0, 0.0, 0.7, 0.0], ["japanese"]),
    _product("くろざとうのようかん", "こくのある、くろざとうのようかん。", "#3B2A20",
             380, [], [1.0, 0.9, 0.0, 0.0, 0.4, 0.1], ["azuki"]),
    _product("ゆずのわらびもち", "ぷるぷるのわらびもちに、ゆずのかおり。", "#E8E07A",
             330, None, [0.9, 0.5, 0.6, 0.0, 1.0, 0.8], ["japanese", "citrus"]),  # アレルゲン不明の品
    _product("ごまのせんべい", "ぱりっと香ばしい、ごまのおせんべい。", "#8C7B6B",
             250, ["小麦", "ごま", "大豆"], [0.9, 0.1, 0.0, 0.0, 0.0, 0.0], ["japanese"]),
]


def update_demo_categories(store: RecommendStore) -> int:
    """登録済みの架空の品の項目を、ここで決めた項目にそろえ、書き換えた数を返す。
    項目の分け方を変えたときに、古い項目や項目なしのまま残ると、苦手の除外やおすすめが正しく動かないため
    (サーバーを開くたびに呼ぶ)。架空の品(名前で見分ける)以外の商品には触れない。"""
    demo = {product.name: product for product in DEMO_PRODUCTS}
    updated = 0
    for existing in store.list_products():
        product = demo.get(existing.name)
        if product is not None and existing.categories != product.categories:
            store.update_product_categories(existing.id, product.categories)
            updated += 1
    return updated


def seed_demo_products(store: RecommendStore) -> int:
    """まだ登録されていない架空の商品を登録し、登録した数を返す(同じ名前の品は二重に登録しない)。
    登録済みの架空の品は、項目をそろえる。"""
    store.init_schema()
    registered = {product.name for product in store.list_products()}
    added = 0
    for product in DEMO_PRODUCTS:
        if product.name not in registered:
            store.add_product(product)
            added += 1
    update_demo_categories(store)
    return added


if __name__ == "__main__":
    from recommend_web import open_store

    added = seed_demo_products(open_store())
    print(f"架空の商品を {added} 品登録しました" if added else "架空の商品はすべて登録されています")
