"""お勧め機能のデータの保存と読み出し(商品カタログ・苦手なスイーツの項目・勧めた記録)。

保存と読み出しの処理はこのファイルだけにまとめる。
試作では SQLite を使う。別のデータベースに替えるときは、RecommendStore と同じメソッドを持つ
クラスを作って差し替えれば、ほかのファイルは変えなくてよい。

アレルゲンは登録された表示どおりに保存する。
  None … 不明(表示がない)。お勧めからは除外する。
  ()   … アレルゲンなしと表示されている。
"""

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path

# 記録の種類
#   recommended: 勧めた(システムが記録する)
#   like: 好き / dislike: 苦手 / neutral: どちらでもない … 以前の「1品ずつ聞く」「写真で教える」の記録。
#     データベースには残っているが、今はおすすめに使わず、新しくも記録しない
PREFERENCE_KINDS = ("like", "dislike", "neutral", "recommended")


@dataclass(frozen=True)
class Product:
    """商品カタログの1品"""
    name: str
    description: str
    image_url: str
    price: int                              # 円(税込)
    allergens: tuple[str, ...] | None       # None は不明
    sale_start: date | None                 # 販売期間(None は期間の定めなし)
    sale_end: date | None
    seasonal: bool                          # 季節限定か
    store: str                              # 店舗名
    embedding: tuple[float, ...] | None     # ベクトル
    embedding_model: str | None             # ベクトルを作ったモデル名
    id: int | None = None
    categories: tuple[str, ...] | None = None   # 苦手を選ぶ項目(recommend.SWEET_CATEGORIES のコード)。None はスイーツ以外


@dataclass(frozen=True)
class FamilySettings:
    """家族が設定する項目(利用者ごと)"""
    allergies: tuple[str, ...] = ()             # アレルギー(アレルゲンの名前)
    diet_restrictions: tuple[str, ...] = ()     # 食事制限(recommend.DIET_RESTRICTIONS のコード)
    budget_max: int | None = None               # 予算の上限(円)。None は上限なし
    stores: tuple[str, ...] = ()                # 利用する店舗。空ならすべての店舗
    repeat_avoidance: float = 0.5               # 同じ品の繰り返しを避ける強さ(a)
    region: str | None = None                   # 住んでいる地域(都道府県)。今日の気温を調べるのに使う。None は未設定


REASON_STATUSES = ("ok", "rejected", "error")


@dataclass(frozen=True)
class PickItem:
    """その日のおすすめの1品と、その理由"""
    product_id: int
    reason: str | None          # 検査に通った理由。なければ理由なしで表示する
    reason_status: str          # ok / rejected(検査で外した)/ error(Gemini を呼べなかった)


@dataclass(frozen=True)
class DailyPick:
    """その日のおすすめ(利用者ごとに1日1組)。選んだときのお金の量と気分も持ち、答えが変われば選び直す"""
    user_id: str
    day: str                    # YYYY-MM-DD(日本時間)
    budget: str                 # recommend.BUDGET_LEVELS のコード
    mood: str                   # recommend.MOODS のコード
    items: tuple[PickItem, ...] # 勧める品(点数の高い順)


@dataclass(frozen=True)
class Preference:
    """好みの記録の1件(利用者ごと)。
    カタログの商品についての記録(product_id あり)か、利用者が写真で教えた記録(product_id なし・写真あり)のどちらか。"""
    user_id: str
    product_id: int | None                  # 写真で教えた記録では None
    kind: str
    created_at: datetime
    embedding: tuple[float, ...] | None     # 商品の記録: 記録した時点の商品のベクトル / 写真の記録: 写真のベクトル
    embedding_model: str | None = None
    photo_mime: str | None = None           # 写真で教えた記録の写真の形式(写真そのものは get_photo で読む)
    id: int | None = None


PREFERENCES_COLUMNS = """(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL CHECK (user_id <> ''),
    product_id      INTEGER REFERENCES products(id),   -- 写真で教えた記録では NULL
    kind            TEXT    NOT NULL CHECK (kind IN ('like', 'dislike', 'neutral', 'recommended')),
    created_at      TEXT    NOT NULL,                  -- ISO 8601(UTC)
    embedding       TEXT,
    embedding_model TEXT,
    photo           BLOB,                              -- 写真で教えた記録の写真(縮小・付加情報なし)
    photo_mime      TEXT,
    -- 商品か写真のどちらか一方だけを持つ
    CHECK ((product_id IS NULL) = (photo IS NOT NULL)),
    -- 写真の記録は「好き」か「苦手」だけで、ベクトルとモデル名を必ず持つ
    CHECK (photo IS NULL OR (kind IN ('like', 'dislike') AND embedding IS NOT NULL
                             AND embedding_model IS NOT NULL AND photo_mime IN ('image/jpeg', 'image/png')))
)"""

SCHEMA_TEMPLATE = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    image_url       TEXT    NOT NULL,
    price           INTEGER NOT NULL CHECK (price >= 0),
    allergens       TEXT,               -- JSON の配列。NULL は不明
    sale_start      TEXT,               -- YYYY-MM-DD
    sale_end        TEXT,
    seasonal        INTEGER NOT NULL CHECK (seasonal IN (0, 1)),
    store           TEXT    NOT NULL,
    embedding       TEXT,               -- JSON の数値配列
    embedding_model TEXT,
    categories      TEXT,               -- 苦手を選ぶ項目(JSON の配列)。NULL はスイーツ以外
    -- ベクトルとモデル名は必ず組で持つ
    CHECK ((embedding IS NULL) = (embedding_model IS NULL))
);

CREATE TABLE IF NOT EXISTS preferences {preferences_columns};

CREATE INDEX IF NOT EXISTS preferences_by_user ON preferences (user_id, created_at);

-- 本人が苦手と選んだスイーツの項目。利用者ごとに1行だけ持つ(選び直すたびに置き換える)
CREATE TABLE IF NOT EXISTS disliked_categories (
    user_id     TEXT    PRIMARY KEY CHECK (user_id <> ''),
    categories  TEXT    NOT NULL,           -- JSON の配列
    updated_at  TEXT    NOT NULL
);

-- 家族が設定する項目。利用者ごとに1行だけ持つ
CREATE TABLE IF NOT EXISTS family_settings (
    user_id           TEXT    PRIMARY KEY CHECK (user_id <> ''),
    allergies         TEXT    NOT NULL,     -- JSON の配列
    diet_restrictions TEXT    NOT NULL,     -- JSON の配列
    budget_max        INTEGER CHECK (budget_max IS NULL OR budget_max >= 0),
    stores            TEXT    NOT NULL,     -- JSON の配列
    repeat_avoidance  REAL    NOT NULL CHECK (repeat_avoidance >= 0),
    updated_at        TEXT    NOT NULL,
    region            TEXT                  -- 都道府県。NULL は未設定
);

-- その日のおすすめ。同じ日に同じ答え(お金の量・気分)なら同じ品を表示するために持つ
CREATE TABLE IF NOT EXISTS daily_picks {daily_picks_columns};
"""

DAILY_PICKS_COLUMNS = """(
    user_id       TEXT    NOT NULL CHECK (user_id <> ''),
    day           TEXT    NOT NULL,         -- YYYY-MM-DD
    budget        TEXT    NOT NULL,
    mood          TEXT    NOT NULL,
    -- 勧める品(点数の高い順)。JSON の配列で、1品ずつ productId・reason・reasonStatus を持つ
    items         TEXT    NOT NULL CHECK (json_valid(items) AND json_array_length(items) >= 1),
    created_at    TEXT    NOT NULL,
    PRIMARY KEY (user_id, day)
)"""

SCHEMA = (SCHEMA_TEMPLATE.replace("{preferences_columns}", PREFERENCES_COLUMNS)
          .replace("{daily_picks_columns}", DAILY_PICKS_COLUMNS))



class RecommendStore:
    """SQLite に保存する実装"""

    def __init__(self, path: str | Path):
        self.path = str(path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # 呼び出しごとに接続を開いて閉じる(Web サーバーの複数のスレッドから安全に使うため)。
        # 正常に終われば確定(commit)し、例外なら取り消す(rollback)。
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        """表がなければ作る。古い形の好みの記録があれば、記録を残したまま新しい形に移す。"""
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        if self._needs_photo_migration():
            self._migrate_preferences_for_photos()
        self._migrate_daily_picks_to_items()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # 地域の列がない古い家族の設定の表には、列を足す(既存の設定は地域が未設定になる)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(family_settings)")}
            if "region" not in columns:
                conn.execute("ALTER TABLE family_settings ADD COLUMN region TEXT")
            # 項目の列がない古い商品の表には、列を足す(既存の商品はスイーツ以外の扱いになる)。
            # 1品に1つだけ種類を持っていた以前の列(category)は、項目の分け方が変わったので消す
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
            if "categories" not in columns:
                conn.execute("ALTER TABLE products ADD COLUMN categories TEXT")
            if "category" in columns:
                conn.execute("ALTER TABLE products DROP COLUMN category")

    def _needs_photo_migration(self) -> bool:
        with self._connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(preferences)")}
        return bool(columns) and "photo" not in columns

    def _migrate_preferences_for_photos(self) -> None:
        """好みの記録の表を、写真の記録も持てる形に作り直す(既存の記録はすべて写す)"""
        # 念のため、移す前のファイルを残しておく
        if Path(self.path).is_file():
            shutil.copy2(self.path, f"{self.path}.before-photo-migration")
        with self._connect() as conn:
            conn.executescript(f"""
                BEGIN;
                ALTER TABLE preferences RENAME TO preferences_old;
                DROP INDEX IF EXISTS preferences_by_user;
                CREATE TABLE preferences {PREFERENCES_COLUMNS};
                INSERT INTO preferences (id, user_id, product_id, kind, created_at, embedding, embedding_model)
                    SELECT o.id, o.user_id, o.product_id, o.kind, o.created_at, o.embedding,
                           CASE WHEN o.embedding IS NULL THEN NULL ELSE p.embedding_model END
                    FROM preferences_old AS o LEFT JOIN products AS p ON p.id = o.product_id;
                DROP TABLE preferences_old;
                COMMIT;
            """)

    def _migrate_daily_picks_to_items(self) -> None:
        """1日1品だった頃の「その日のおすすめ」の表を、複数の品を持てる形に作り直す。
        前の記録は、その1品だけを持つ記録として写す"""
        with self._connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(daily_picks)")}
            if "product_id" not in columns:
                return
            rows = conn.execute("SELECT * FROM daily_picks").fetchall()
            conn.execute("DROP TABLE daily_picks")
            conn.execute(f"CREATE TABLE daily_picks {DAILY_PICKS_COLUMNS}")
            for row in rows:
                items = (PickItem(row["product_id"], row["reason"], row["reason_status"]),)
                conn.execute(
                    "INSERT INTO daily_picks (user_id, day, budget, mood, items, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (row["user_id"], row["day"], row["budget"], row["mood"], _dump_pick_items(items),
                     row["created_at"]),
                )

    # ---- 商品カタログ ----

    def add_product(self, product: Product) -> Product:
        """商品を登録し、id 付きの商品を返す"""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO products (name, description, image_url, price, allergens, sale_start,
                       sale_end, seasonal, store, embedding, embedding_model, categories)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product.name, product.description, product.image_url, product.price,
                    _dump_list(product.allergens),
                    _dump_date(product.sale_start), _dump_date(product.sale_end),
                    int(product.seasonal), product.store,
                    _dump_list(product.embedding), product.embedding_model, _dump_list(product.categories),
                ),
            )
            return replace(product, id=cursor.lastrowid)

    def get_product(self, product_id: int) -> Product | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _row_to_product(row) if row else None

    def list_products(self, *, allergens_known_only: bool = False) -> list[Product]:
        """商品を id 順に返す。allergens_known_only なら、アレルゲンが不明な商品を除く。"""
        query = "SELECT * FROM products"
        if allergens_known_only:
            query += " WHERE allergens IS NOT NULL"
        with self._connect() as conn:
            rows = conn.execute(query + " ORDER BY id").fetchall()
        return [_row_to_product(row) for row in rows]

    def store_names(self) -> list[str]:
        """カタログにある店舗名(設定ページの選択肢に使う)"""
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT store FROM products ORDER BY store").fetchall()
        return [row[0] for row in rows]

    def update_product_embedding(self, product_id: int, embedding: tuple[float, ...], model: str) -> None:
        """商品のベクトルと、それを作ったモデル名を組で書き換える"""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE products SET embedding = ?, embedding_model = ? WHERE id = ?",
                (_dump_list(embedding), model, product_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"商品がありません: {product_id}")

    def update_product_categories(self, product_id: int, categories: tuple[str, ...] | None) -> None:
        """商品の項目を書き換える"""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE products SET categories = ? WHERE id = ?", (_dump_list(categories), product_id)
            )
            if cursor.rowcount != 1:
                raise ValueError(f"商品がありません: {product_id}")

    def count_products(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    # ---- 勧めた記録 ----

    def add_preference(
        self, user_id: str, product_id: int, kind: str, *, created_at: datetime | None = None
    ) -> Preference:
        """記録を1件残す(今は「勧めた」の記録に使う)。ベクトルは記録した時点の商品のものを写して持つ。"""
        if not user_id:
            raise ValueError("利用者 ID がありません")
        if kind not in PREFERENCE_KINDS:
            raise ValueError(f"記録の種類が正しくありません: {kind}")
        product = self.get_product(product_id)
        if product is None:
            raise ValueError(f"商品がありません: {product_id}")

        preference = Preference(
            user_id=user_id,
            product_id=product_id,
            kind=kind,
            created_at=created_at or datetime.now(timezone.utc),
            embedding=product.embedding,
            embedding_model=product.embedding_model,
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO preferences (user_id, product_id, kind, created_at, embedding, embedding_model)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, product_id, kind, preference.created_at.isoformat(),
                 _dump_list(preference.embedding), preference.embedding_model),
            )
            return replace(preference, id=cursor.lastrowid)

    def list_preferences(self, user_id: str) -> list[Preference]:
        """その利用者の記録だけを古い順に返す"""
        with self._connect() as conn:
            # 写真そのものは重いので、一覧では読まない
            rows = conn.execute(
                """SELECT id, user_id, product_id, kind, created_at, embedding, embedding_model, photo_mime
                   FROM preferences WHERE user_id = ? ORDER BY created_at, id""", (user_id,)
            ).fetchall()
        return [_row_to_preference(row) for row in rows]

    # ---- 苦手なスイーツの項目 ----

    def get_disliked_categories(self, user_id: str) -> tuple[str, ...] | None:
        """本人が苦手と選んだ項目。まだ一度も選んでいなければ None"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT categories FROM disliked_categories WHERE user_id = ?", (user_id,)
            ).fetchone()
        return None if row is None else _load_tuple(row["categories"])

    def save_disliked_categories(self, user_id: str, categories: tuple[str, ...]) -> None:
        """苦手なスイーツの項目を、まとめて置き換える(前に選んだものは残さない)"""
        if not user_id:
            raise ValueError("利用者 ID がありません")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO disliked_categories (user_id, categories, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT (user_id) DO UPDATE SET
                       categories = excluded.categories, updated_at = excluded.updated_at""",
                (user_id, _dump_list(categories), datetime.now(timezone.utc).isoformat()),
            )

    # ---- 家族の設定 ----

    def get_settings(self, user_id: str) -> FamilySettings | None:
        """設定がまだ保存されていなければ None"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM family_settings WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return FamilySettings(
            allergies=_load_tuple(row["allergies"]),
            diet_restrictions=_load_tuple(row["diet_restrictions"]),
            budget_max=row["budget_max"],
            stores=_load_tuple(row["stores"]),
            repeat_avoidance=row["repeat_avoidance"],
            region=row["region"],
        )

    def save_settings(self, user_id: str, settings: FamilySettings) -> None:
        if not user_id:
            raise ValueError("利用者 ID がありません")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO family_settings (user_id, allergies, diet_restrictions, budget_max, stores,
                       repeat_avoidance, updated_at, region)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (user_id) DO UPDATE SET
                       allergies = excluded.allergies, diet_restrictions = excluded.diet_restrictions,
                       budget_max = excluded.budget_max, stores = excluded.stores,
                       repeat_avoidance = excluded.repeat_avoidance, updated_at = excluded.updated_at,
                       region = excluded.region""",
                (user_id, _dump_list(settings.allergies), _dump_list(settings.diet_restrictions),
                 settings.budget_max, _dump_list(settings.stores), settings.repeat_avoidance,
                 datetime.now(timezone.utc).isoformat(), settings.region),
            )

    # ---- 日ごとのおすすめ ----

    def get_daily_pick(self, user_id: str, day: str) -> DailyPick | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_picks WHERE user_id = ? AND day = ?", (user_id, day)
            ).fetchone()
        if row is None:
            return None
        return DailyPick(user_id=row["user_id"], day=row["day"], budget=row["budget"], mood=row["mood"],
                         items=_load_pick_items(row["items"]))

    def save_daily_pick(self, pick: DailyPick) -> None:
        """その日のおすすめを保存する(同じ日にすでにあれば置き換える)。
        品が1つもない・理由の状態が決まった値でない記録は保存しない(ValueError)"""
        if not pick.items:
            raise ValueError("勧める品が1つもありません")
        if any(item.reason_status not in REASON_STATUSES for item in pick.items):
            raise ValueError("理由の状態が正しくありません")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO daily_picks (user_id, day, budget, mood, items, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (user_id, day) DO UPDATE SET
                       budget = excluded.budget, mood = excluded.mood,
                       items = excluded.items, created_at = excluded.created_at""",
                (pick.user_id, pick.day, pick.budget, pick.mood, _dump_pick_items(pick.items),
                 datetime.now(timezone.utc).isoformat()),
            )


# ---- 変換(SQLite の値 ⇔ Python の値) ----

def _dump_list(values) -> str | None:
    return None if values is None else json.dumps(list(values), ensure_ascii=False)


def _load_tuple(text: str | None):
    return None if text is None else tuple(json.loads(text))


def _dump_pick_items(items: tuple[PickItem, ...]) -> str:
    return json.dumps(
        [{"productId": i.product_id, "reason": i.reason, "reasonStatus": i.reason_status} for i in items],
        ensure_ascii=False,
    )


def _load_pick_items(text: str) -> tuple[PickItem, ...]:
    return tuple(PickItem(i["productId"], i["reason"], i["reasonStatus"]) for i in json.loads(text))


def _dump_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _load_date(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        image_url=row["image_url"],
        price=row["price"],
        allergens=_load_tuple(row["allergens"]),
        sale_start=_load_date(row["sale_start"]),
        sale_end=_load_date(row["sale_end"]),
        seasonal=bool(row["seasonal"]),
        store=row["store"],
        embedding=_load_tuple(row["embedding"]),
        embedding_model=row["embedding_model"],
        categories=_load_tuple(row["categories"]),
    )


def _row_to_preference(row: sqlite3.Row) -> Preference:
    return Preference(
        id=row["id"],
        user_id=row["user_id"],
        product_id=row["product_id"],
        kind=row["kind"],
        created_at=datetime.fromisoformat(row["created_at"]),
        embedding=_load_tuple(row["embedding"]),
        embedding_model=row["embedding_model"],
        photo_mime=row["photo_mime"],
    )
