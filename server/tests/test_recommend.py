"""お勧めの計算(recommend.py)のテスト: ①除外、③点数、④上位の品の選択、理由の検査、今日の様子。"""

import math
from datetime import date, datetime, timezone

import pytest

from recommend import (
    RECOMMENDATION_COUNT, SWEET_CATEGORIES, SWEET_GROUPS, PastRecommendation, budget_cap, check_reason, context_text, cosine, exclude, exclusion_reason,
    normalize, rank, recency_weight, recommend, score, temperature_band,
)
from recommend_store import FamilySettings, Product

TODAY = date(2026, 11, 16)
MODEL = "test-embedding-model"


def product(id, name="【架空】ためしのケーキ", allergens=("卵",), price=400, store="架空堂", seasonal=False,
            sale=(None, None), embedding=(1.0, 0.0), model=MODEL, description="ためしの説明", categories=("cheesecake",)):
    return Product(
        id=id, name=name, description=description, image_url="data:image/png;base64,", price=price,
        allergens=allergens, sale_start=sale[0], sale_end=sale[1], seasonal=seasonal, store=store,
        embedding=embedding, embedding_model=model if embedding is not None else None, categories=categories,
    )


NO_LIMITS = FamilySettings(repeat_avoidance=0.5)
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


# ==== ① 除外 ====

def test_アレルゲンが不明な品は設定がなくても必ず除外する():
    unknown = product(1, allergens=None)
    assert exclusion_reason(unknown, NO_LIMITS, TODAY) == "アレルゲン不明"
    assert exclude([unknown], NO_LIMITS, TODAY) == []


def test_アレルゲンが不明な品は今日の様子にいちばん合っても勧めない():
    unknown_but_best = product(1, allergens=None, embedding=(1.0, 0.0))
    known = product(2, allergens=(), embedding=(0.0, 1.0))

    chosen = recommend([unknown_but_best, known], NO_LIMITS, frozenset(), [], NOW, MODEL, context=(1.0, 0.0))

    assert [p.id for p in chosen] == [2]


def test_項目が登録されていない品はスイーツ以外として勧めない():
    not_sweet = product(1, categories=None, embedding=(1.0, 0.0))
    empty = product(2, categories=(), embedding=(1.0, 0.0))
    unknown_kind = product(3, categories=("cheesecake", "soup"), embedding=(1.0, 0.0))   # 選択肢にない項目が混ざる
    sweet = product(4, embedding=(0.0, 1.0))

    for p in (not_sweet, empty, unknown_kind):
        assert exclusion_reason(p, NO_LIMITS, TODAY) == "スイーツ以外"
    assert recommend([not_sweet, empty, unknown_kind, sweet], NO_LIMITS, frozenset(), [], NOW, MODEL,
                     context=(1.0, 0.0)) == [sweet]


def test_苦手と選んだ項目の品は勧めない_同じケーキでもチーズケーキだけを外せる():
    cheesecake = product(1, categories=("cheesecake",), embedding=(1.0, 0.0))
    shortcake = product(2, categories=("shortcake", "strawberry"), embedding=(0.9, 0.1))
    disliked = frozenset({"cheesecake"})

    assert exclusion_reason(cheesecake, NO_LIMITS, TODAY, disliked) == "苦手な項目"
    assert exclusion_reason(shortcake, NO_LIMITS, TODAY, disliked) is None
    assert recommend([cheesecake, shortcake], NO_LIMITS, disliked, [], NOW, MODEL, context=(1.0, 0.0))[0].id == 2
    assert recommend([cheesecake], NO_LIMITS, disliked, [], NOW, MODEL) == []


def test_苦手なフルーツが入った品は_お菓子の種類が苦手でなくても勧めない():
    shortcake = product(1, categories=("shortcake", "strawberry"))
    assert exclusion_reason(shortcake, NO_LIMITS, TODAY, frozenset({"strawberry"})) == "苦手な項目"


def test_項目は洋菓子_和菓子_フルーツに分かれ_ケーキはケーキの種類ごとに選べる():
    assert list(SWEET_GROUPS.values()) == ["洋菓子", "和菓子", "フルーツ"]
    assert {group for group, _ in SWEET_CATEGORIES.values()} == set(SWEET_GROUPS)
    labels = {label for group, label in SWEET_CATEGORIES.values() if group == "western"}
    assert {"ショートケーキ", "チョコレートケーキ", "チーズケーキ", "モンブラン"} <= labels
    assert "ケーキ" not in labels                  # まとめた項目は置かず、細かさをそろえる


def test_和菓子はあずき_カスタード_チョコクリーム_ドライフルーツの4つ_フルーツにりんご():
    japanese = [label for group, label in SWEET_CATEGORIES.values() if group == "japanese"]
    assert japanese == ["あずき系", "カスタードクリーム系", "チョコクリーム系", "ドライフルーツ系"]
    fruit = [label for group, label in SWEET_CATEGORIES.values() if group == "fruit"]
    assert "りんご" in fruit
    # ドライフルーツ系は、3つの分類すべてにある
    for group in SWEET_GROUPS:
        assert "ドライフルーツ系" in [label for g, label in SWEET_CATEGORIES.values() if g == group]


def test_分類ごと一括で苦手にすると_項目のないその分類の品も勧めない():
    dango = product(1, categories=("japanese",))                  # どの項目にも当たらない和菓子
    daifuku = product(2, categories=("azuki",))
    cake = product(3, categories=("shortcake", "strawberry"))
    disliked = frozenset({"japanese"})

    assert exclusion_reason(dango, NO_LIMITS, TODAY, disliked) == "苦手な項目"
    assert exclusion_reason(daifuku, NO_LIMITS, TODAY, disliked) == "苦手な項目"   # 項目から分類が分かる
    assert exclusion_reason(cake, NO_LIMITS, TODAY, disliked) is None


def test_フルーツを一括で苦手にすると_フルーツの入った品を勧めない():
    cake = product(1, categories=("shortcake", "strawberry"))
    cheese = product(2, categories=("cheesecake",))
    assert exclusion_reason(cake, NO_LIMITS, TODAY, frozenset({"fruit"})) == "苦手な項目"
    assert exclusion_reason(cheese, NO_LIMITS, TODAY, frozenset({"fruit"})) is None


def test_フルーツだけの登録では洋菓子か和菓子か分からないのでスイーツ以外():
    assert exclusion_reason(product(1, categories=("apple",)), NO_LIMITS, TODAY) == "スイーツ以外"


def test_アレルゲンなしと表示された品は除外しない():
    assert exclusion_reason(product(1, allergens=()), NO_LIMITS, TODAY) is None


def test_アレルギーに当たる品を除外する():
    settings = FamilySettings(allergies=("くるみ",))
    assert exclusion_reason(product(1, allergens=("小麦", "くるみ")), settings, TODAY) == "アレルギー・食事制限"
    assert exclusion_reason(product(2, allergens=("小麦",)), settings, TODAY) is None


@pytest.mark.parametrize("code, allergens, excluded", [
    ("no-dairy", ("乳",), True),
    ("no-dairy", ("卵",), False),
    ("no-wheat", ("小麦", "大豆"), True),
    ("no-nuts", ("アーモンド",), True),
    ("no-animal", ("ゼラチン",), True),
    ("no-animal", ("大豆", "ごま"), False),
])
def test_食事制限に当たる品を表示されたアレルゲンで除外する(code, allergens, excluded):
    settings = FamilySettings(diet_restrictions=(code,))
    assert (exclusion_reason(product(1, allergens=allergens), settings, TODAY) is not None) == excluded


def test_予算を超える品を除外し_ちょうどの品は残す():
    settings = FamilySettings(budget_max=400)
    assert exclusion_reason(product(1, price=401), settings, TODAY) == "予算超え"
    assert exclusion_reason(product(2, price=400), settings, TODAY) is None


def test_予算の上限がなければ値段では除外しない():
    assert exclusion_reason(product(1, price=99999), NO_LIMITS, TODAY) is None


def test_利用する店舗以外の品を除外する_店舗を選んでいなければすべて残す():
    settings = FamilySettings(stores=("架空堂 本店",))
    assert exclusion_reason(product(1, store="架空堂 駅前店"), settings, TODAY) == "店舗違い"
    assert exclusion_reason(product(2, store="架空堂 本店"), settings, TODAY) is None
    assert exclusion_reason(product(3, store="架空堂 駅前店"), NO_LIMITS, TODAY) is None


@pytest.mark.parametrize("sale, reason", [
    ((date(2026, 12, 1), None), "販売期間前"),
    ((None, date(2026, 11, 15)), "販売期間後"),
    ((date(2026, 11, 16), date(2026, 11, 16)), None),   # 初日=最終日=今日
    ((date(2026, 9, 1), date(2026, 11, 30)), None),
    ((None, None), None),                                # 期間の定めなし
])
def test_販売期間外の品を除外する(sale, reason):
    assert exclusion_reason(product(1, sale=sale), NO_LIMITS, TODAY) == reason


def test_除外は条件をすべて満たす品だけを残す():
    settings = FamilySettings(allergies=("卵",), budget_max=500, stores=("架空堂",))
    products = [
        product(1, allergens=()),                   # 残る
        product(2, allergens=None),                 # 不明
        product(3, allergens=("卵",)),              # アレルギー
        product(4, allergens=(), price=600),        # 予算
        product(5, allergens=(), store="別の店"),    # 店舗
        product(6, allergens=(), sale=(None, date(2026, 1, 1))),  # 期間
    ]
    assert [p.id for p in exclude(products, settings, TODAY)] == [1]


# ==== ② ベクトル ====

def test_正規化すると長さが1になる():
    assert math.isclose(math.hypot(*normalize((3.0, 4.0))), 1.0)
    with pytest.raises(ValueError):
        normalize((0.0, 0.0))


# ==== ③ 点数 ====

def test_今日の様子がなければ様子の項は0():
    assert score(product(1), [], repeat_avoidance=0.5) == 0.0


def test_過去に勧めた品と似ているほどaの分だけ下がる():
    p = product(1, embedding=(1.0, 0.0))
    past = [PastRecommendation(embedding=(1.0, 0.0), age_days=0)]
    assert math.isclose(score(p, past, repeat_avoidance=0.3), -0.3)
    assert math.isclose(score(p, past, repeat_avoidance=0.0), 0.0)


def test_古く勧めた品ほど影響が弱まる():
    assert recency_weight(0) == 1.0
    assert math.isclose(recency_weight(90), 0.5)
    assert math.isclose(recency_weight(180), 0.25)

    p = product(1, embedding=(1.0, 0.0))
    recent = score(p, [PastRecommendation((1.0, 0.0), age_days=30)], repeat_avoidance=1.0)
    old = score(p, [PastRecommendation((1.0, 0.0), age_days=300)], repeat_avoidance=1.0)
    assert old > recent


def test_過去に勧めた品が複数あれば影響のいちばん大きいものを使う():
    p = product(1, embedding=(1.0, 0.0))
    past = [PastRecommendation((0.0, 1.0), age_days=0), PastRecommendation((1.0, 0.0), age_days=90)]
    assert math.isclose(score(p, past, repeat_avoidance=1.0), -0.5)


def test_季節限定の品にはbを足す():
    regular = product(1, seasonal=False)
    seasonal = product(2, seasonal=True)
    assert math.isclose(score(seasonal, [], 0.5, seasonal_bonus=0.1) - score(regular, [], 0.5, seasonal_bonus=0.1), 0.1)


def test_類似度は向きだけを見る():
    assert math.isclose(cosine((2.0, 0.0), (5.0, 0.0)), 1.0)
    assert math.isclose(cosine((1.0, 0.0), (-1.0, 0.0)), -1.0)


# ==== ④ 選択 ====

def test_点数がいちばん高い品を選ぶ():
    near = product(1, embedding=(1.0, 0.1))
    far = product(2, embedding=(0.0, 1.0))
    assert rank([far, near], [], 0.5, context=(1.0, 0.0))[0].id == 1


def test_前に勧めた品と同じ品はaが強いと選ばれにくい():
    # 今日の様子は (1, 0)。前に勧めた品は様子に最も近いが、少し違う向きの別の品もある
    same = product(1, embedding=(0.95, 0.312))
    other = product(2, embedding=(0.9, -0.436))
    past = [PastRecommendation(same.embedding, age_days=30)]
    assert rank([same, other], past, repeat_avoidance=0.0, context=(1.0, 0.0))[0].id == 1
    assert rank([same, other], past, repeat_avoidance=1.0, context=(1.0, 0.0))[0].id == 2


def test_点数が同じなら_idの小さい品を先に並べる():
    assert [p.id for p in rank([product(2), product(1)], [], 0.5)] == [1, 2]


def test_候補がなければ空():
    assert rank([], [], 0.5) == []


def test_点数の高い順に5品まで並べる():
    # 今日の様子 (1, 0) に近い順: id 1 → 7。似た品を避けない(a = 0)ので、点数の順そのまま
    candidates = [product(i, embedding=(1.0, 0.1 * i)) for i in range(7, 0, -1)]

    ranked = rank(candidates, [], repeat_avoidance=0.0, context=(1.0, 0.0))

    assert RECOMMENDATION_COUNT == 5
    assert [p.id for p in ranked] == [1, 2, 3, 4, 5]


def test_候補が5品より少なければ_残った品だけを並べる():
    assert [p.id for p in rank([product(2), product(1)], [], 0.5, limit=5)] == [1, 2]


def test_先に並べた品と似た品は_aが強いと下に回る():
    # 今日の様子 (1, 0) に、1 と 2 はほぼ同じ向きで近い。3 は少し離れているが、1 とは似ていない
    first = product(1, embedding=(1.0, 0.0))
    twin = product(2, embedding=(0.99, 0.14))
    other = product(3, embedding=(0.8, -0.6))

    assert [p.id for p in rank([first, twin, other], [], repeat_avoidance=0.0, context=(1.0, 0.0))] == [1, 2, 3]
    assert [p.id for p in rank([first, twin, other], [], repeat_avoidance=1.0, context=(1.0, 0.0))] == [1, 3, 2]


def test_並べた順の1品めは_点数がいちばん高い品と同じ():
    # 2品め以降の計算の工夫が、1品めの選び方を変えていないことを確かめる
    past = [PastRecommendation((0.6, 0.8), age_days=10), PastRecommendation((-1.0, 0.0), age_days=200)]
    candidates = [product(i, embedding=(math.cos(i), math.sin(i)), seasonal=i % 2 == 0) for i in range(1, 9)]

    best = max(candidates, key=lambda p: score(p, past, 0.6, context=(1.0, 0.0)))

    assert rank(candidates, past, 0.6, context=(1.0, 0.0))[0] == best


def test_勧める品は_点数の高い順に5品まで():
    candidates = [product(i, embedding=(1.0, 0.1 * i)) for i in range(1, 8)]
    settings = FamilySettings(repeat_avoidance=0.0)

    assert [p.id for p in recommend(candidates, settings, frozenset(), [], NOW, MODEL, context=(1.0, 0.0))] \
        == [1, 2, 3, 4, 5]


def test_別のモデルで作ったベクトルの品は使わない():
    old_model = product(1, embedding=(1.0, 0.0), model="manual-demo-v1")
    assert recommend([old_model], NO_LIMITS, frozenset(), [], NOW, MODEL) == []


# ==== 理由の検査 ====

CHOSEN = product(1, name="【架空】こしあんの大福")
OTHERS = [CHOSEN, product(2, name="【架空】さくらもち"), product(3, name="【架空】くろざとうのようかん")]


@pytest.mark.parametrize("reason", [
    "あんこのお菓子がお好きなので、きっと気に入ります。",
    "やわらかいおもちが好きな方に、ぴったりです。",
    "「こしあんの大福」は、なめらかなあんこが自慢です。",
])
def test_問題のない理由はそのまま使う(reason):
    assert check_reason(reason, CHOSEN, OTHERS) == reason


@pytest.mark.parametrize("reason", [
    "さくらもちがお好きなら、こちらもどうぞ。",            # 候補にない(別の)商品名
    "「ふくふく羊羹」がお好きな方にどうぞ。",             # カタログにない作り話の商品名
    "残りわずかなので、お早めにどうぞ。",                 # 急がせる
    "今だけの味です。ぜひ購入してください。",             # 購入を促す
    "アレルギーの心配がなく、安心して食べられます。",      # アレルギー・安全の言い切り
    "",
    "あ" * 61,                                          # 長すぎる
])
def test_問題のある理由は使わない(reason):
    assert check_reason(reason, CHOSEN, OTHERS) is None


# ==== 今日の様子(お金の量・気分・気温) ====

@pytest.mark.parametrize("family_max, budget, expected", [
    (None, "small", 500),
    (None, "medium", 1000),
    (None, "large", None),      # ちょっとぜいたくは、今日の上限を付けない
    (300, "medium", 300),       # 家族の設定の上限のほうが低ければ、そちらを使う
    (800, "small", 500),
    (800, "large", 800),
])
def test_今日つかうお金の量は家族の上限と低いほうを使う(family_max, budget, expected):
    settings = FamilySettings(budget_max=family_max, allergies=("卵",))
    capped = budget_cap(settings, budget)
    assert capped.budget_max == expected
    assert capped.allergies == ("卵",)      # ほかの設定はそのまま


@pytest.mark.parametrize("temperature, label", [
    (35.0, "暑い日"), (28.0, "暑い日"), (27.9, "あたたかい日"), (20.0, "あたたかい日"),
    (15.0, "すずしい日"), (9.9, "寒い日"), (-5.0, "寒い日"),
])
def test_最高気温から日の様子を決める(temperature, label):
    assert temperature_band(temperature)[0] == label


def test_気温が分からなければ日の様子はNone():
    assert temperature_band(None) is None


def test_今日の様子の文は気温と気分の両方から作り_ふつうの気分は寄せない():
    assert "冷たく" in context_text(33.0, "tired") and "つかれた" in context_text(33.0, "tired")
    assert "冷たく" in context_text(33.0, "normal") and "つかれた" not in context_text(33.0, "normal")
    assert "つかれた" in context_text(None, "exhausted")
    assert context_text(None, "normal") is None


def test_今日の様子の文に近い品をcの分だけ上げる():
    p = product(1, embedding=(1.0, 0.0))
    assert math.isclose(score(p, [], 0.5, context=(1.0, 0.0), context_weight=0.4), 0.4)
    assert math.isclose(score(p, [], 0.5, context=(0.0, 1.0), context_weight=0.4), 0.0)
    assert math.isclose(score(p, [], 0.5, context=None, context_weight=0.4), 0.0)


def test_今日の様子に近い品を選ぶ():
    cold = product(1, embedding=(0.7, 0.7))
    warm = product(2, embedding=(0.7, -0.7))
    assert recommend([cold, warm], NO_LIMITS, frozenset(), [], NOW, MODEL, context=(0.0, 1.0))[0].id == 1
    assert recommend([cold, warm], NO_LIMITS, frozenset(), [], NOW, MODEL, context=(0.0, -1.0))[0].id == 2
