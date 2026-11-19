"""埋め込みベクトルの計算と保存(embeddings.py)のテスト。Gemini は偽物を使う。"""

import math
from types import SimpleNamespace

import pytest

from demo_data import DEMO_PRODUCTS, seed_demo_products
from embeddings import EMBEDDING_DIMENSIONS, embed_catalog, embed_text, image_from_data_url
from recommend_store import RecommendStore


class FakeEmbeddingClient:
    """決まった長さのベクトルを返し、受け取った入力と設定を記録する偽の Gemini"""

    def __init__(self, dimensions=EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions
        self.calls = []
        self.models = self

    def embed_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        # 正規化されていないベクトルを返す(保存前に正規化されることを確かめるため)
        values = [float(len(self.calls))] * self.dimensions
        return SimpleNamespace(embeddings=[SimpleNamespace(values=values)])


@pytest.fixture
def store(tmp_path):
    store = RecommendStore(tmp_path / "embed.db")
    seed_demo_products(store)
    return store


def test_全商品を768次元で正規化して保存し_モデル名を記録する(store):
    client = FakeEmbeddingClient()

    updated = embed_catalog(store, client, "gemini-embedding-2")

    assert len(updated) == len(DEMO_PRODUCTS)
    for product in store.list_products():
        assert product.embedding_model == "gemini-embedding-2"
        assert len(product.embedding) == 768
        assert math.isclose(math.sqrt(sum(v * v for v in product.embedding)), 1.0)
    assert all(call.config.output_dimensionality == 768 for call in client.calls)


def test_説明文と写真を1つの入力として渡す(store):
    client = FakeEmbeddingClient()
    embed_catalog(store, client, "gemini-embedding-2")

    parts = client.calls[0].contents[0].parts
    assert "いちごのショートケーキ" in parts[0].text
    assert parts[1].inline_data.mime_type == "image/png"


def test_同じモデルで作り済みの商品は計算し直さない(store):
    embed_catalog(store, FakeEmbeddingClient(), "gemini-embedding-2")
    client = FakeEmbeddingClient()

    assert embed_catalog(store, client, "gemini-embedding-2") == []
    assert client.calls == []
    # モデルを替えると全部計算し直す
    assert len(embed_catalog(store, client, "another-model")) == len(DEMO_PRODUCTS)


def test_次元が違うベクトルは保存しない(store):
    with pytest.raises(ValueError):
        embed_catalog(store, FakeEmbeddingClient(dimensions=3072), "gemini-embedding-2")
    assert all(p.embedding_model == "manual-demo-v1" for p in store.list_products())


@pytest.mark.parametrize("url", [
    "data:image/svg+xml;charset=utf-8,%3Csvg%3E",   # SVG は埋め込みに使えない
    "https://example.com/photo.png",               # data URL ではない
])
def test_使えない写真は受け付けない(url):
    with pytest.raises(ValueError):
        image_from_data_url(url)


def test_今日の様子の文は文だけを入力にして768次元で正規化する():
    client = FakeEmbeddingClient()

    vector = embed_text(client, "test-model", "暑い日に食べたい、冷たくてさっぱりした食べ物")

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0)
    [part] = client.calls[0].contents[0].parts
    assert part.text == "暑い日に食べたい、冷たくてさっぱりした食べ物"
    assert client.calls[0].config.output_dimensionality == EMBEDDING_DIMENSIONS
