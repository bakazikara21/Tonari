"""お勧め機能の Web ページと API(苦手なスイーツの登録・家族の設定・今日のおすすめ)。

ログイン機能はない。利用者は server/.env の TONARI_USER_ID で1人ぶんだけ設定し、
すべての記録にその利用者 ID を付ける。ページ側から利用者 ID は受け取らない。
"""

import json
import logging
import os
from dataclasses import replace
from datetime import datetime
from functools import cache, lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from google.genai import types
from pydantic import BaseModel, Field

import gemini
import weather
from demo_data import update_demo_categories
from embeddings import embed_text
from recommend import (
    ALLERGEN_OPTIONS, BUDGET_LEVELS, DIET_RESTRICTIONS, DISLIKE_CODES, MOODS, SWEET_CATEGORIES, SWEET_GROUPS,
    budget_cap, check_reason,
    context_text, exclusion_reason, recommend, temperature_band,
)
from recommend_store import DailyPick, FamilySettings, PickItem, Product, RecommendStore

SERVER_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = SERVER_DIR / "data" / "tonari.db"

# 日の区切りは日本時間で決める
JST = ZoneInfo("Asia/Tokyo")

router = APIRouter()
logger = logging.getLogger("tonari")


def open_store() -> RecommendStore:
    """設定(TONARI_DB_PATH)の場所にあるデータベースを開く。
    架空の品の項目は、開くたびに今の項目の分け方にそろえる(古い項目のままだと、どの品も勧められなくなるため)"""
    store = RecommendStore(os.environ.get("TONARI_DB_PATH") or DEFAULT_DB_PATH)
    store.init_schema()
    update_demo_categories(store)
    return store


@cache
def get_store() -> RecommendStore:
    return open_store()


def get_user_id() -> str:
    """設定された利用者 ID(1人ぶん)"""
    user_id = os.environ.get("TONARI_USER_ID", "").strip()
    if not user_id:
        raise HTTPException(status_code=500, detail="server/.env に TONARI_USER_ID を設定してください")
    return user_id


def get_now() -> datetime:
    """いまの時刻(日本時間)。テストでは差し替える"""
    return datetime.now(JST)


# ---- ページ ----

@router.get("/preferences", include_in_schema=False)
def preferences_page() -> FileResponse:
    return FileResponse(SERVER_DIR / "static" / "preferences.html")


# ---- API ----

def category_groups() -> list[dict]:
    """苦手を選ぶ項目を、分類(洋菓子・和菓子・フルーツ)ごとにまとめる(分類ごとにプルダウンで選ぶ)。
    分類の code は、分類ごと一括で苦手にするときに使う"""
    return [
        {"code": group, "label": label,
         "items": [{"code": code, "label": name} for code, (g, name) in SWEET_CATEGORIES.items() if g == group]}
        for group, label in SWEET_GROUPS.items()
    ]


def normalize_dislikes(codes) -> tuple[str, ...]:
    """分類ごと一括で苦手にしたときは、その分類の項目もすべて苦手にする。選択肢の並び順にそろえる"""
    selected = set(codes)
    for code, (group, _) in SWEET_CATEGORIES.items():
        if group in selected:
            selected.add(code)
    return tuple(code for code in DISLIKE_CODES if code in selected)


@router.get("/api/preferences/dislikes")
def read_dislikes(store: RecommendStore = Depends(get_store), user_id: str = Depends(get_user_id)) -> dict:
    """いま苦手と選んでいる分類・項目と、選択肢を返す(選び直すときは、いまの選択から始める)。
    項目の分け方が変わる前に選んだ、今の選択肢にないものは返さない"""
    saved = store.get_disliked_categories(user_id)
    selected = list(normalize_dislikes(code for code in (saved or ()) if code in DISLIKE_CODES))
    return {"saved": saved is not None, "selected": selected, "groups": category_groups()}


class DislikesBody(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=len(DISLIKE_CODES))


@router.put("/api/preferences/dislikes", status_code=204)
def save_dislikes(
    body: DislikesBody, store: RecommendStore = Depends(get_store), user_id: str = Depends(get_user_id)
) -> None:
    """苦手な分類・項目を、まとめて置き換える。ページは「記録する」を押したときだけ送るので、
    途中でやめると前の選択のまま残る。選択肢にない値があれば何も保存しない。"""
    unknown = set(body.categories) - set(DISLIKE_CODES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"選択肢にない値があります: {sorted(unknown)}")
    store.save_disliked_categories(user_id, normalize_dislikes(body.categories))


# ==== 家族の設定 ====

# 同じ品の繰り返しを避ける強さ(a)の選択肢
REPEAT_AVOIDANCE_LEVELS = (
    {"value": 0.0, "label": "気にしない"},
    {"value": 0.3, "label": "弱い"},
    {"value": 0.6, "label": "ふつう"},
    {"value": 1.0, "label": "強い"},
)


# 家族の設定がまだないときに使う、繰り返しを避ける強さ(設定ページの「ふつう」)
DEFAULT_REPEAT_AVOIDANCE = 0.6


@router.get("/settings", include_in_schema=False)
def settings_page() -> FileResponse:
    return FileResponse(SERVER_DIR / "static" / "settings.html")


class SettingsBody(BaseModel):
    allergies: list[str] = Field(default_factory=list, max_length=len(ALLERGEN_OPTIONS))
    dietRestrictions: list[str] = Field(default_factory=list, max_length=len(DIET_RESTRICTIONS))
    budgetMax: int | None = Field(default=None, ge=0, le=100000)
    stores: list[str] = Field(default_factory=list, max_length=50)
    repeatAvoidance: float = Field(default=0.6, ge=0, le=2)
    region: str | None = Field(default=None, max_length=10)


@router.get("/api/settings")
def read_settings(store: RecommendStore = Depends(get_store), user_id: str = Depends(get_user_id)) -> dict:
    """いまの設定と、選択肢を返す"""
    saved = store.get_settings(user_id)
    settings = saved or FamilySettings(repeat_avoidance=DEFAULT_REPEAT_AVOIDANCE)
    return {
        "saved": saved is not None,
        "settings": SettingsBody(
            allergies=list(settings.allergies), dietRestrictions=list(settings.diet_restrictions),
            budgetMax=settings.budget_max, stores=list(settings.stores),
            repeatAvoidance=settings.repeat_avoidance, region=settings.region,
        ).model_dump(),
        "options": {
            "allergens": list(ALLERGEN_OPTIONS),
            "dietRestrictions": [{"code": code, "label": label} for code, (label, _) in DIET_RESTRICTIONS.items()],
            "stores": store.store_names(),
            "repeatAvoidance": list(REPEAT_AVOIDANCE_LEVELS),
            "regions": list(weather.PREFECTURES),
        },
    }


@router.put("/api/settings", status_code=204)
def save_settings(
    body: SettingsBody, store: RecommendStore = Depends(get_store), user_id: str = Depends(get_user_id)
) -> None:
    # 選択肢にない値は受け付けない(アレルゲン名の書き間違いで除外がもれるのを防ぐ)
    unknown = (
        set(body.allergies) - set(ALLERGEN_OPTIONS)
        | set(body.dietRestrictions) - set(DIET_RESTRICTIONS)
        | set(body.stores) - set(store.store_names())
    )
    if body.region is not None and body.region not in weather.PREFECTURES:
        unknown.add(body.region)
    if unknown:
        raise HTTPException(status_code=422, detail=f"選択肢にない値があります: {sorted(unknown)}")
    store.save_settings(user_id, FamilySettings(
        allergies=tuple(sorted(set(body.allergies))),
        diet_restrictions=tuple(sorted(set(body.dietRestrictions))),
        budget_max=body.budgetMax,
        stores=tuple(sorted(set(body.stores))),
        repeat_avoidance=body.repeatAvoidance,
        region=body.region,
    ))


# ==== 今日のおすすめ ====

REASON_INSTRUCTION = """\
あなたは、高齢の方にスイーツをすすめる係です。
入力として、すすめる品の一覧(recommended: 番号 number・名前・説明)と、
今日の様子(today: 気温から見た日の様子と、その方の今日の気分。分からなければ null)を JSON で受け取ります。
それぞれの品について、すすめる理由を、やさしい日本語で一言(40文字以内)で書いてください。
答えには、品の番号(number)をそのまま付けてください。今日の様子が分かれば、それに合う理由にしてください。

決まり:
- 1つの理由には、その品以外の商品名は書かないでください。
- 買うことや急ぐことをすすめる言葉(今すぐ、お早めに、残りわずか、お得 など)は使わないでください。
- アレルギー・健康・安全については書かないでください。
- 値段については書かないでください。
"""


class ReasonItem(BaseModel):
    number: int = Field(description="品の番号(入力の number)")
    reason: str = Field(description="すすめる理由(一言、40文字以内)")


class ReasonsAnswer(BaseModel):
    reasons: list[ReasonItem]


def generate_reasons(products: list[Product], today: dict) -> list[str | None]:
    """Gemini に、すすめる品それぞれの理由を一言で書かせる(テストではこの関数を差し替える)。
    1回の呼び出しでまとめて書かせ、products と同じ順の理由の一覧を返す(答えのない品は None)。
    送るのは、すすめる品の名前・説明と、今日の様子(「暑い日」などの言い方と気分)だけ
    (利用者 ID・地域・設定・苦手な種類は送らない)。"""
    prompt = json.dumps({
        "recommended": [
            {"number": number, "name": p.name, "description": p.description, "seasonal": p.seasonal}
            for number, p in enumerate(products, start=1)
        ],
        "today": today,
    }, ensure_ascii=False)
    response = gemini.client().models.generate_content(
        model=gemini.text_model(),
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=REASON_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=ReasonsAnswer.model_json_schema(),
        ),
    )
    answer = ReasonsAnswer.model_validate_json(response.text or "")
    # 番号はコードで確かめる。一覧にない番号は使わず、同じ番号が2回あれば最初の答えだけを使う
    by_number: dict[int, str] = {}
    for item in answer.reasons:
        if 1 <= item.number <= len(products):
            by_number.setdefault(item.number, item.reason)
    return [by_number.get(number) for number in range(1, len(products) + 1)]


def make_reasons(chosen: list[Product], products: list[Product], today: dict) -> tuple[PickItem, ...]:
    """勧める品それぞれの理由を作って検査し、品と理由の組を返す。
    理由の状態は ok / rejected(検査で外した・答えがなかった)/ error(Gemini を呼べなかった)"""
    try:
        reasons = generate_reasons(chosen, today)
    except Exception as error:  # 通信の失敗や、形の崩れた答え(ValidationError)など
        logger.warning("おすすめの理由を作れませんでした: %s: %s", type(error).__name__, str(error)[:300])
        return tuple(PickItem(p.id, None, "error") for p in chosen)
    items = []
    for product, reason in zip(chosen, reasons, strict=True):
        # 理由は1品ずつ、その品について検査する(ほかの品の名前が入っていれば外す)
        checked = check_reason(reason, product, products)
        items.append(PickItem(product.id, checked, "ok" if checked else "rejected"))
    return tuple(items)


@lru_cache(maxsize=64)
def _context_embedding(text: str, model: str) -> tuple[float, ...]:
    # 文の組み合わせは限られているので、作ったベクトルを覚えておく(失敗したときは覚えない)
    return embed_text(gemini.client(), model, text)


def compute_context_embedding(text: str) -> tuple[float, ...] | None:
    """今日の様子を言い表した文のベクトル(テストではこの関数を差し替える)。作れなければ None"""
    try:
        return _context_embedding(text, gemini.embedding_model())
    except Exception as error:  # 通信の失敗など。今日の様子を使わずに選ぶ
        logger.warning("今日の様子のベクトルを作れませんでした: %s: %s", type(error).__name__, str(error)[:300])
        return None


def get_max_temperature(region: str | None, now: datetime) -> float | None:
    """住んでいる地域の今日の最高気温(テストではこの関数を差し替える)"""
    return weather.today_max_temperature(region, now.astimezone(JST).date())


def day_of(now: datetime) -> str:
    return now.astimezone(JST).date().isoformat()


@router.get("/recommendation", include_in_schema=False)
def recommendation_page() -> FileResponse:
    return FileResponse(SERVER_DIR / "static" / "recommendation.html")


@router.get("/api/recommendation/today")
def today_choices(
    store: RecommendStore = Depends(get_store),
    user_id: str = Depends(get_user_id),
    now: datetime = Depends(get_now),
) -> dict:
    """今日の最高気温(分からなければ null)と、本人が選ぶお金の量・気分の選択肢を返す"""
    settings = store.get_settings(user_id)
    return {
        "maxTemperature": get_max_temperature(settings.region if settings else None, now),
        "budgets": [{"code": code, "label": label} for code, (label, _) in BUDGET_LEVELS.items()],
        "moods": [{"code": code, "label": label} for code, (label, _) in MOODS.items()],
    }


@router.get("/api/recommendation")
def daily_recommendation(
    budget: Literal["small", "medium", "large"] = Query(),
    mood: Literal["great", "good", "normal", "tired", "exhausted"] = Query(),
    store: RecommendStore = Depends(get_store),
    user_id: str = Depends(get_user_id),
    now: datetime = Depends(get_now),
) -> dict:
    """今日のおすすめ(スイーツを点数の高い順に最大5品)を返す。苦手な種類を外し、本人が選んだお金の量・気分と、
    今日の気温をもとに選ぶ。同じ日に同じ答えなら同じ品を返し、新しく選んだ品はすべて「勧めた」として記録する
    (次の日からは、見せた品と似た品が上に来にくくなる)。
    家族の設定がまだなくても、苦手を選んだだけで勧める(アレルギー・食事制限・予算・店舗の条件なしで選ぶ)。
    その場合も、アレルゲンの表示がない品は必ず外し、ページには家族向けの注意を出す(settingsSaved)。"""
    saved_settings = store.get_settings(user_id)
    settings_saved = saved_settings is not None
    settings = saved_settings or FamilySettings(repeat_avoidance=DEFAULT_REPEAT_AVOIDANCE)

    today = now.astimezone(JST).date()
    day = day_of(now)
    # 今日つかうお金の量の上限を、家族の設定の予算の上限に重ねる
    settings = budget_cap(settings, budget)
    max_temperature = get_max_temperature(settings.region, now)
    band = temperature_band(max_temperature)
    # 理由を書かせるときに渡す今日の様子(気温の数字や地域は渡さない)
    today_hint = {"weather": band[0] if band else None, "mood": MOODS[mood][0]}

    products = store.list_products()
    disliked = frozenset(store.get_disliked_categories(user_id) or ())

    pick = store.get_daily_pick(user_id, day)
    if pick is not None and (pick.budget, pick.mood) == (budget, mood):
        shown = [store.get_product(item.product_id) for item in pick.items]
        # 設定や苦手な種類が変わって、1品でも除外に当たるようになったら、同じ日でも選び直す
        if all(p is not None and exclusion_reason(p, settings, today, disliked) is None for p in shown):
            if any(item.reason_status == "error" for item in pick.items):
                # 前回 Gemini を呼べなかったときだけ、理由を作り直す
                pick = replace(pick, items=make_reasons(shown, products, today_hint))
                store.save_daily_pick(pick)
            return _recommendation_body(shown, pick.items, max_temperature, settings_saved)

    text = context_text(max_temperature, mood)
    context = compute_context_embedding(text) if text else None
    past = [(p.product_id, p.created_at) for p in store.list_preferences(user_id) if p.kind == "recommended"]
    model = gemini.embedding_model()
    chosen = recommend(products, settings, disliked, past, now, model, context=context)
    if not chosen:
        return {"status": "none", "maxTemperature": max_temperature, "settingsSaved": settings_saved}

    items = make_reasons(chosen, products, today_hint)
    store.save_daily_pick(DailyPick(user_id, day, budget, mood, items))
    for product in chosen:
        store.add_preference(user_id, product.id, "recommended")
    return _recommendation_body(chosen, items, max_temperature, settings_saved)


def _recommendation_body(
    products: list[Product], items: tuple[PickItem, ...], max_temperature: float | None, settings_saved: bool
) -> dict:
    # 店舗や購入の案内は返さない(購入を促す表示にしないため)。品は点数の高い順
    return {
        "status": "ok",
        "items": [
            {"name": p.name, "imageUrl": p.image_url, "price": p.price, "reason": item.reason}
            for p, item in zip(products, items, strict=True)
        ],
        "maxTemperature": max_temperature,
        "settingsSaved": settings_saved,
    }
