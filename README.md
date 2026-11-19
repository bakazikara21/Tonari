# Tonari

スマホに不慣れな高齢の家族が、Web サイトの会員登録を一人で終えられるように手伝う iPhone アプリです。
Safari Web 拡張機能が今のページを見て、「次の1手順」と「押す場所」を案内します。

## 構成

| フォルダ | 中身 |
| --- | --- |
| `Tonari/` | iPhone アプリ本体(SwiftUI) |
| `Tonari Extension/` | Safari Web 拡張機能 |
| `TonariTests/` | アプリと拡張機能スクリプトのテスト |
| `server/` | 中継サーバー(FastAPI)。Gemini(Vertex AI)への問い合わせ・お勧め機能・今日の気温の取得(Open-Meteo) |

アプリと拡張機能は、Mac で動く中継サーバー(`http://localhost:8000`)に接続します。
Gemini の認証情報は中継サーバーだけに置き、アプリや拡張機能には入れません。

## 必要なもの

- Xcode(iOS シミュレータを含む)
- Python 3
- Google Cloud のプロジェクト(Vertex AI API を有効にしたもの)と `gcloud` コマンド

## 1. 中継サーバーを立ち上げる

### 初回だけ

```sh
cd server

# Python の仮想環境を作り、必要なものを入れる
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# 設定ファイルを作る(.env は Git に入れない)
cp .env.example .env
```

`server/.env` を開き、`GOOGLE_CLOUD_PROJECT` を自分のプロジェクト ID に書き換えます。

| 項目 | 内容 |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI を使う Google Cloud のプロジェクト ID |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI の接続先(通常は `global`) |
| `GEMINI_MODEL` | 案内文・お勧めの理由を書くモデル |
| `GEMINI_EMBEDDING_MODEL` | 商品の埋め込みベクトルを作るモデル |
| `TONARI_USER_ID` | お勧め機能の利用者 ID(1人ぶん) |
| `TONARI_DB_PATH` | データベースの場所(省略すると `server/data/tonari.db`) |

Google Cloud の認証は Application Default Credentials を使います(利用キーは使いません)。

```sh
gcloud auth application-default login
```

お勧め機能を試す場合は、架空の商品データを登録し、埋め込みベクトルを作ります。
架空の商品を追加したあとも、同じ2つを実行し直してください(登録済みの品は二重に登録せず、ベクトルも作り直しません)。

```sh
# server フォルダで
.venv/bin/python demo_data.py    # 架空の商品を登録(まだない品だけ)
.venv/bin/python embeddings.py   # Gemini の埋め込みベクトルに置き換える(まだない品だけ)
```

### 起動

```sh
cd server
.venv/bin/uvicorn main:app --reload --port 8000
```

ブラウザで次のページが開ければ起動できています。

- お勧めの設定: <http://localhost:8000/settings>
- 苦手なスイーツを教える: <http://localhost:8000/preferences>
- 今日のおすすめ: <http://localhost:8000/recommendation>

お勧めの対象は、高島屋オンラインストアで扱うすべてのスイーツです。
ただし今の実装は、まだ上の架空の商品データ(12 品)だけを使っています。

「苦手なスイーツを教える」では、苦手なものを「洋菓子」「和菓子」「フルーツ」のプルダウンから選びます(チーズケーキ・あずき系・りんご など)。「ぜんぶ にがて」にチェックすると、その分類をまとめて苦手にできます(何回でも選び直せます)。
「今日のおすすめ」では、本人が今日つかうお金の量(3段階)と気分(5段階)を選ぶと、
苦手なものが入ったスイーツを外して、今日の最高気温と気分に合う品を、合う順に最大5品並べます。
似た品ばかりが並ばないよう、2品め以降は上の品と似ていない品を選びやすくしています(「お勧めの設定」の「同じような品の繰り返しを避ける強さ」が強いほど、この効き目も強くなります)。
気温を使うには、「お勧めの設定」で「住んでいる地域」を選んでください。中継サーバーが Open-Meteo(利用キー不要)に
その都道府県庁所在地の今日の最高気温を問い合わせます。取得できないときは、気温を使わずに選びます。

起動時に `server/.env に ○○ を設定してください` と出た場合は、`.env` の該当項目を確認してください。

## 2. アプリをシミュレータで動かす

1. `Tonari.xcodeproj` を Xcode で開きます。
2. スキーム `Tonari` と、実行先に iPhone シミュレータを選びます。
3. ⌘R で実行します。
4. シミュレータで「設定」アプリを開き、拡張機能を有効にします。
   1. 「アプリ」→「Safari」→「機能拡張」を押します。
   2. 「Tonari Extension」をオンにします。
   3. 「すべての Web サイト」を「許可」にします。
5. シミュレータの Safari で会員登録ページを開くと、右下に「たすけて」ボタンが出ます。

シミュレータからは Mac の `localhost:8000` にそのままつながります。
接続先を変える場合は、次の2か所を書き換えます。

- アプリ: `Tonari/AppConfig.swift` の `serverBaseURL`
- 拡張機能: `Tonari Extension/Resources/guide-provider.js` の `SERVER_URL` と、`manifest.json` の `host_permissions`

## テスト

```sh
# 中継サーバー(本物の Gemini は呼ばない)
cd server
.venv/bin/pytest
```

アプリと拡張機能のテストは、Xcode で ⌘U を押して実行します。
