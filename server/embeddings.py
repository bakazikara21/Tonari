"""商品カタログの埋め込みベクトルを、説明文と写真から作って保存する。

モデル(GEMINI_EMBEDDING_MODEL、例: gemini-embedding-2)に、商品名・説明文と写真を
1つのまとまりとして渡し、768 次元のベクトルを1本作る。
gemini-embedding-2 は次元を減らすと正規化して返すが、モデルを替えても同じになるよう、ここでも正規化してから保存する。

使い方(server フォルダで): .venv/bin/python embeddings.py
  まだベクトルがない商品と、別のモデルで作ったベクトルの商品だけを計算する。
"""

import base64
import re
from urllib.parse import unquote_to_bytes

from google.genai import types

from recommend import normalize
from recommend_store import Product, RecommendStore

EMBEDDING_DIMENSIONS = 768

# 埋め込みに使える写真の形式(Gemini の埋め込みは PNG と JPEG に対応)
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg"}


def image_from_data_url(url: str) -> tuple[bytes, str]:
    """data URL から写真のバイト列と形式を取り出す"""
    match = re.fullmatch(r"data:([^;,]+)(;base64)?,(.*)", url, flags=re.DOTALL)
    if not match:
        raise ValueError("写真は data URL で登録してください")
    mime_type, is_base64, payload = match.groups()
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise ValueError(f"埋め込みに使えない写真の形式です: {mime_type}")
    data = base64.b64decode(payload) if is_base64 else unquote_to_bytes(payload)
    return data, mime_type


def embedding_content(product: Product) -> types.Content:
    """商品名・説明文と写真を、1本のベクトルにまとめるための入力"""
    image, mime_type = image_from_data_url(product.image_url)
    return types.Content(parts=[
        types.Part.from_text(text=f"{product.name}\n{product.description}"),
        types.Part.from_bytes(data=image, mime_type=mime_type),
    ])


def embed_product(client, model: str, product: Product) -> tuple[float, ...]:
    """1品のベクトルを作り、768 次元で長さ 1 にして返す"""
    response = client.models.embed_content(
        model=model,
        contents=[embedding_content(product)],
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    return _checked(response.embeddings[0].values)


def embed_text(client, model: str, text: str) -> tuple[float, ...]:
    """文1つのベクトルを作り、768 次元で長さ 1 にして返す(今日の様子に合う品を探すのに使う)"""
    response = client.models.embed_content(
        model=model,
        contents=[types.Content(parts=[types.Part.from_text(text=text)])],
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    return _checked(response.embeddings[0].values)


def _checked(values) -> tuple[float, ...]:
    """次元を確かめてから正規化する"""
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"ベクトルの次元が {len(values)} でした(期待は {EMBEDDING_DIMENSIONS})")
    return normalize(values)


def embed_catalog(store: RecommendStore, client, model: str) -> list[int]:
    """ベクトルがない商品・別のモデルのベクトルの商品を計算して保存し、計算した商品の id を返す"""
    updated = []
    for product in store.list_products():
        if product.embedding is not None and product.embedding_model == model:
            continue
        store.update_product_embedding(product.id, embed_product(client, model, product), model)
        updated.append(product.id)
    return updated


if __name__ == "__main__":
    import gemini
    from recommend_web import open_store

    model = gemini.embedding_model()
    ids = embed_catalog(open_store(), gemini.client(), model)
    print(f"{model} で {len(ids)} 品のベクトルを作りました")
