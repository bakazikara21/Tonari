"""お勧めの計算(除外・点数・上位の品の選択)と、お勧めの理由の検査。

ここにはデータベースや Gemini の呼び出しを置かず、計算だけをまとめる(テストしやすくするため)。

アレルゲンは AI に推測させない。商品に登録された表示どおりに扱い、
表示が不明(None)の商品は、設定にかかわらず必ず除外する。
勧めるのはスイーツだけ。洋菓子か和菓子の分類に当たらない品(項目 categories が登録されていない品など)は
スイーツとして扱わず、勧めない。本人が苦手と選んだ分類・項目を1つでも含む品も勧めない。
分類・項目も AI に推測させず、登録されたとおりに扱う。
"""

import math
import re
from dataclasses import dataclass, replace
from datetime import date, datetime

from recommend_store import FamilySettings, Product

# ---- 設定の選択肢 ----

# アレルギーの選択肢(食品表示の特定原材料 8 品目と、それに準ずる 20 品目)
ALLERGEN_OPTIONS = (
    "卵", "乳", "小麦", "そば", "落花生", "えび", "かに", "くるみ",
    "アーモンド", "あわび", "いか", "いくら", "オレンジ", "カシューナッツ", "キウイフルーツ",
    "牛肉", "ごま", "さけ", "さば", "大豆", "鶏肉", "バナナ", "豚肉", "マカダミアナッツ",
    "もも", "やまいも", "りんご", "ゼラチン",
)

# 食事制限の選択肢。商品にはアレルゲンの表示しかないため、
# 表示されたアレルゲンだけで判断できる制限に限っている(推測はしない)。
DIET_RESTRICTIONS: dict[str, tuple[str, frozenset[str]]] = {
    "no-egg": ("卵をひかえる", frozenset({"卵"})),
    "no-dairy": ("乳製品をひかえる", frozenset({"乳"})),
    "no-wheat": ("小麦をひかえる", frozenset({"小麦"})),
    "no-nuts": ("ナッツ類をひかえる", frozenset({"落花生", "くるみ", "アーモンド", "カシューナッツ", "マカダミアナッツ"})),
    "no-animal": ("動物性の食品をひかえる", frozenset({"卵", "乳", "ゼラチン", "えび", "かに", "牛肉", "鶏肉", "豚肉",
                                                    "さけ", "さば", "いか", "いくら", "あわび"})),
}

# 苦手を選ぶ分類(系列)。コード: 表示名。分類ごとにプルダウンで選び、分類ごと一括で苦手にもできる
SWEET_GROUPS: dict[str, str] = {
    "western": "洋菓子",
    "japanese": "和菓子",
    "fruit": "フルーツ",
}

# 苦手を選ぶ項目。コード: (分類のコード, 表示名)。
# 洋菓子の項目は同じ細かさ(「ケーキ」ではなく「チーズケーキ」)にそろえる。
SWEET_CATEGORIES: dict[str, tuple[str, str]] = {
    "shortcake": ("western", "ショートケーキ"),
    "chocolate-cake": ("western", "チョコレートケーキ"),
    "cheesecake": ("western", "チーズケーキ"),
    "montblanc": ("western", "モンブラン"),
    "cookie": ("western", "クッキー"),
    "jelly": ("western", "ゼリー"),
    "western-dried-fruit": ("western", "ドライフルーツ系"),
    "azuki": ("japanese", "あずき系"),
    "custard": ("japanese", "カスタードクリーム系"),
    "chocolate-cream": ("japanese", "チョコクリーム系"),
    "japanese-dried-fruit": ("japanese", "ドライフルーツ系"),
    "strawberry": ("fruit", "いちご"),
    "citrus": ("fruit", "レモン・ゆず"),
    "chestnut": ("fruit", "くり"),
    "apple": ("fruit", "りんご"),
    "dried-fruit": ("fruit", "ドライフルーツ系"),
}

# 苦手として選べるコード(分類ごとの一括と、項目)
DISLIKE_CODES = (*SWEET_GROUPS, *SWEET_CATEGORIES)


def product_tags(product: Product) -> set[str] | None:
    """商品に登録された分類・項目に、項目が属する分類を足したもの。
    商品には当てはまる項目をすべて登録する(例: いちごのショートケーキ = ショートケーキ + いちご)。
    どの項目にも当たらない品は、分類だけを登録する(例: みたらしだんご = 和菓子)。
    登録がない・選択肢にないコードがあるときは None(確かめられないので勧めない)"""
    if not product.categories or not set(product.categories) <= set(DISLIKE_CODES):
        return None
    tags = set(product.categories)
    return tags | {SWEET_CATEGORIES[code][0] for code in tags if code in SWEET_CATEGORIES}

# 季節限定の品に足す点数(b)
SEASONAL_BONUS = 0.05
# 過去に勧めた品の影響が半分になるまでの日数(古いものほど弱める)
RECOMMENDATION_HALF_LIFE_DAYS = 90
# 今日の様子(気温・気分)に合うかどうかに掛ける重み(c)
CONTEXT_WEIGHT = 0.5
# 1回に勧める品の数(点数の高い順に並べる)
RECOMMENDATION_COUNT = 5


# ---- 今日の様子(本人が選ぶお金の量・気分と、今日の気温) ----

# 今日つかうお金の量(3段階)。上限(円)は家族の設定の予算の上限と組み合わせ、低いほうを使う
BUDGET_LEVELS: dict[str, tuple[str, int | None]] = {
    "small": ("すこし(500円まで)", 500),
    "medium": ("ふつう(1000円まで)", 1000),
    "large": ("ちょっと ぜいたく", None),
}

# 今日の気分(5段階)と、その気分に合う食べ物の言い表し(「ふつう」は気分では寄せない)
MOODS: dict[str, tuple[str, str | None]] = {
    "great": ("とても げんき", "元気な日に楽しめる、食べごたえのあるスイーツ"),
    "good": ("げんき", "気分のよい日に合う、はなやかなスイーツ"),
    "normal": ("ふつう", None),
    "tired": ("すこし つかれた", "少しつかれた日に合う、やさしい味のスイーツ"),
    "exhausted": ("とても つかれた", "つかれた日にほっとする、やわらかくて食べやすいスイーツ"),
}

# 最高気温(℃)の区切りと、その日に合う食べ物の言い表し(上から順に当てはめる)
TEMPERATURE_BANDS: tuple[tuple[float, str, str], ...] = (
    (28, "暑い日", "暑い日に食べたい、冷たくてさっぱりしたスイーツ"),
    (20, "あたたかい日", "あたたかい日に合う、さわやかなスイーツ"),
    (10, "すずしい日", "すずしい日に合う、ほっとするスイーツ"),
    (-100, "寒い日", "寒い日にうれしい、温かいスイーツ"),
)


def budget_cap(settings: FamilySettings, budget: str) -> FamilySettings:
    """家族の設定の予算の上限に、今日つかうお金の量の上限を重ねた設定を返す(低いほうを使う)"""
    level_max = BUDGET_LEVELS[budget][1]
    caps = [cap for cap in (settings.budget_max, level_max) if cap is not None]
    return replace(settings, budget_max=min(caps) if caps else None)


def temperature_band(max_temperature: float | None) -> tuple[str, str] | None:
    """最高気温から (日の言い方, 合う食べ物の言い表し) を返す。気温が分からなければ None"""
    if max_temperature is None:
        return None
    for lower, label, text in TEMPERATURE_BANDS:
        if max_temperature >= lower:
            return label, text
    return None


def context_text(max_temperature: float | None, mood: str) -> str | None:
    """今日の様子に合うスイーツを言い表した文(埋め込みベクトルを作るのに使う)。寄せる様子がなければ None"""
    band = temperature_band(max_temperature)
    parts = [text for text in (band[1] if band else None, MOODS[mood][1]) if text]
    return "。".join(parts) if parts else None


# ---- ① 除外 ----

def avoided_allergens(settings: FamilySettings) -> set[str]:
    """アレルギーと食事制限から、避けるアレルゲンをまとめる"""
    avoided = set(settings.allergies)
    for code in settings.diet_restrictions:
        avoided |= DIET_RESTRICTIONS[code][1]
    return avoided


def exclusion_reason(
    product: Product, settings: FamilySettings, today: date, disliked: frozenset[str] = frozenset()
) -> str | None:
    """お勧めから外す理由。外さなくてよければ None。disliked は本人が苦手と選んだ分類・項目"""
    if product.allergens is None:
        return "アレルゲン不明"
    if avoided_allergens(settings) & set(product.allergens):
        return "アレルギー・食事制限"
    tags = product_tags(product)
    if tags is None or not tags & {"western", "japanese"}:
        return "スイーツ以外"
    if tags & disliked:
        return "苦手な項目"
    if settings.budget_max is not None and product.price > settings.budget_max:
        return "予算超え"
    if settings.stores and product.store not in settings.stores:
        return "店舗違い"
    if product.sale_start is not None and today < product.sale_start:
        return "販売期間前"
    if product.sale_end is not None and today > product.sale_end:
        return "販売期間後"
    return None


def exclude(
    products: list[Product], settings: FamilySettings, today: date, disliked: frozenset[str] = frozenset()
) -> list[Product]:
    """お勧めしてよい品だけを残す"""
    return [p for p in products if exclusion_reason(p, settings, today, disliked) is None]


# ---- ② ベクトル ----

def normalize(vector) -> tuple[float, ...]:
    """長さ 1 にする(長さ 0 のベクトルは扱えないので例外)"""
    length = math.sqrt(sum(v * v for v in vector))
    if length == 0:
        raise ValueError("長さ 0 のベクトルは正規化できません")
    return tuple(v / length for v in vector)


# ---- ③ 点数 ----

def cosine(a, b) -> float:
    """コサイン類似度(-1〜1)"""
    length = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if length == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / length


def recency_weight(age_days: float, half_life_days: float = RECOMMENDATION_HALF_LIFE_DAYS) -> float:
    """勧めてからの日数に応じた重み。勧めた直後は 1、half_life_days ごとに半分になる"""
    return 0.5 ** (max(age_days, 0) / half_life_days)


@dataclass(frozen=True)
class PastRecommendation:
    embedding: tuple[float, ...]
    age_days: float


def score(
    product: Product,
    past: list[PastRecommendation],
    repeat_avoidance: float,
    seasonal_bonus: float = SEASONAL_BONUS,
    context: tuple[float, ...] | None = None,
    context_weight: float = CONTEXT_WEIGHT,
) -> float:
    """c × 今日の様子(気温・気分)を言い表した文との類似度 − a × 過去に勧めた品との類似度(古いほど弱める)
    + b × 季節限定"""
    repetition = _repetition(product, past)
    return (_base_score(product, seasonal_bonus, context, context_weight)
            - repeat_avoidance * (repetition if repetition is not None else 0.0))


def _base_score(
    product: Product, seasonal_bonus: float, context: tuple[float, ...] | None, context_weight: float
) -> float:
    """点数のうち、勧めた品によらない部分(c × 今日の様子との類似度 + b × 季節限定)"""
    fitness = cosine(product.embedding, context) if context is not None else 0.0
    return context_weight * fitness + seasonal_bonus * (1 if product.seasonal else 0)


def _repetition(product: Product, past: list[PastRecommendation]) -> float | None:
    """過去に勧めた品のうち、重みを掛けた類似度がいちばん大きいもの。勧めた品がなければ None"""
    return max((recency_weight(p.age_days) * cosine(product.embedding, p.embedding) for p in past), default=None)


# ---- ④ 上位の品を選ぶ ----

def rank(
    candidates: list[Product],
    past: list[PastRecommendation],
    repeat_avoidance: float,
    context: tuple[float, ...] | None = None,
    limit: int = RECOMMENDATION_COUNT,
) -> list[Product]:
    """点数の高い順に、limit 品まで並べる(同点なら id の小さい品を先に)。候補がなければ空。
    2品め以降は、先に並べた品も「いま勧めた品」として点数に入れる。こうすると、似た品ばかりが
    並ばない(a が 0 なら、点数の順そのまま)。
    並べるたびに変わるのは「勧めた品との類似度」だけなので、そこだけを足して計算し直す(商品が多くても速くするため)。"""
    base = [_base_score(p, SEASONAL_BONUS, context, CONTEXT_WEIGHT) for p in candidates]
    repetition = [_repetition(p, past) for p in candidates]
    remaining = list(range(len(candidates)))
    ranked: list[Product] = []

    def current_score(i: int) -> tuple[float, int]:
        penalty = repeat_avoidance * (repetition[i] if repetition[i] is not None else 0.0)
        return base[i] - penalty, -(candidates[i].id or 0)

    while remaining and len(ranked) < limit:
        best = max(remaining, key=current_score)
        remaining.remove(best)
        ranked.append(candidates[best])
        # いま並べた品(勧めてから 0 日 = 重み 1)との類似度で、残りの品の「勧めた品との類似度」を更新する
        for i in remaining:
            similarity = cosine(candidates[i].embedding, candidates[best].embedding)
            repetition[i] = similarity if repetition[i] is None else max(repetition[i], similarity)
    return ranked


def recommend(
    products: list[Product],
    settings: FamilySettings,
    disliked: frozenset[str],
    past_recommendations: list[tuple[int, datetime]],
    now: datetime,
    embedding_model: str,
    context: tuple[float, ...] | None = None,
    limit: int = RECOMMENDATION_COUNT,
) -> list[Product]:
    """①〜④をまとめて行い、勧める品を点数の高い順に limit 品まで返す(候補がなければ空)。
    ベクトルは embedding_model で作ったものだけを使う。
    disliked は本人が苦手と選んだ分類・項目。①で外す。
    context は、今日の様子を言い表した文のベクトル(同じモデルで作ったもの)。③で近い品を上げる。"""
    vectors = {p.id: p.embedding for p in products if p.embedding_model == embedding_model and p.embedding}
    candidates = [p for p in exclude(products, settings, now.date(), disliked) if p.id in vectors]
    past = [
        PastRecommendation(vectors[product_id], (now - when).total_seconds() / 86400)
        for product_id, when in past_recommendations if product_id in vectors
    ]
    return rank(candidates, past, settings.repeat_avoidance, context, limit)


# ---- お勧めの理由の検査 ----

MAX_REASON_LENGTH = 60

# 購入を急がせる・促す言い回し
PUSHY_PATTERN = re.compile(
    r"今すぐ|いますぐ|急いで|お早め|早めに|お見逃し|見逃さ|残りわずか|残り少な|なくなり次第|売り切れ|品切れ|在庫|"
    r"今だけ|いまだけ|本日限り|今日だけ|期間限定|セール|お得|チャンス|"
    r"買って|買いましょう|買わな|お買い|購入|ご購入|注文|予約"
)
# アレルギーや健康・安全についての言い切り(AI に判断させないため、理由に書かせない)
HEALTH_CLAIM_PATTERN = re.compile(r"アレルギ|アレルゲン|健康|体にいい|からだにいい|安心して食べ|安全")


def _core_name(product: Product) -> str:
    """表示名から【架空】などの飾りを外した名前"""
    return re.sub(r"^【[^】]*】", "", product.name).strip()


def check_reason(reason: str | None, chosen: Product, all_products: list[Product]) -> str | None:
    """理由を検査し、問題がなければ整えた理由を、問題があれば None を返す"""
    if not reason:
        return None
    reason = reason.strip()
    if not reason or len(reason) > MAX_REASON_LENGTH:
        return None
    if PUSHY_PATTERN.search(reason) or HEALTH_CLAIM_PATTERN.search(reason):
        return None
    # 選んだ品以外の商品名が入っていないか
    chosen_name = _core_name(chosen)
    for product in all_products:
        name = _core_name(product)
        if product.id != chosen.id and name and name not in chosen_name and name in reason:
            return None
    # 「」で囲んだ名前は、選んだ品の名前の一部でなければいけない(カタログにない商品名の作り話を防ぐ)
    for quoted in re.findall(r"「([^」]*)」", reason):
        if quoted not in chosen_name:
            return None
    return reason
