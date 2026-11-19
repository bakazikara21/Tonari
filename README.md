# Tonari

スマホに不慣れな高齢の家族が、Web サイトの会員登録を一人で終えられるように手伝う iPhone アプリです。
Safari Web 拡張機能が今のページを見て、「次の1手順」と「押す場所」を案内します。

## 構成

| フォルダ | 中身 |
| --- | --- |
| `Tonari/` | iPhone アプリ本体(SwiftUI) |
| `Tonari Extension/` | Safari Web 拡張機能 |
| `TonariTests/` | アプリと拡張機能スクリプトのテスト |
| `Shared/` | アプリと拡張機能の両方で使うコード(中継サーバーの接続先) |
| `server/` | 中継サーバー(FastAPI)。Gemini(Vertex AI)への問い合わせ・お勧め機能・今日の気温の取得(Open-Meteo) |
| `scripts/` | 開発用のスクリプト |

アプリと拡張機能は、Mac で動く中継サーバーに接続します。
Gemini の認証情報は中継サーバーだけに置き、アプリや拡張機能には入れません。

接続先は `Shared/ServerConfig.swift` の1か所だけで決めます。

- シミュレータ: `http://localhost:8000`(シミュレータは Mac のネットワークをそのまま使うので、Mac 自身につながる)
- 実機の iPhone: 同じ Wi-Fi にある Mac の `http://○○.local:8000`([3. 実機の iPhone で動かす](#3-実機の-iphone-で動かす) を参照)

拡張機能は中継サーバーと直接通信しません。拡張機能のネイティブ側(`Tonari Extension/SafariWebExtensionHandler.swift`)に頼んで問い合わせます。

## 必要なもの

- Xcode(iOS シミュレータを含む)
- Python 3
- Google Cloud のプロジェクト(Vertex AI API を有効にしたもの)と `gcloud` コマンド

共同作業者の方は、先に [共同作業者向けの手順](#共同作業者向けの手順) を読んでください(Google Cloud のプロジェクトは自分で用意しなくてかまいません)。

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

## 3. 実機の iPhone で動かす

実機の iPhone では `localhost` は iPhone 自身を指すため、同じ Wi-Fi にある Mac の名前(`○○.local`)でつなぎます。
Mac と iPhone が同じ Wi-Fi にいて、Mac で中継サーバーが動いている間だけ使えます。

1. Mac の名前を調べて、接続先の設定ファイルを作ります(`Shared/LocalServer.plist`。Mac ごとに違うので Git には入れません)。

   ```sh
   ./scripts/use-this-mac.sh
   ```

2. 中継サーバーを、ほかの機器からもつながるように起動します(`--host 0.0.0.0`)。
   初めてのときに Mac が「受け入れますか」と聞いてきたら「許可」を押します。

   ```sh
   cd server
   .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   この中継サーバーには、まだログインの仕組みがありません。同じ Wi-Fi にいる人は誰でもつなげるので、
   自宅など信頼できる Wi-Fi でだけ、この起動方法を使ってください。

3. iPhone を Mac につなぎ、Xcode の実行先に iPhone を選んで ⌘R で実行します。
4. iPhone で Tonari アプリを開き、「今日のおすすめ」などを開きます。
   「ローカルネットワーク上のデバイスの検索および接続」の確認が出たら「許可」を押します。
5. iPhone の「設定」→「アプリ」→「Safari」→「機能拡張」で `Tonari Extension` をオンにし、「すべての Web サイト」を「許可」にします。

つながらないときは、次のことを確かめてください。

- iPhone の「設定」→「プライバシーとセキュリティ」→「ローカルネットワーク」で Tonari がオンか
- iPhone の Safari で `http://○○.local:8000/settings`(`./scripts/use-this-mac.sh` が表示した URL)が開けるか
- `Shared/LocalServer.plist` を作ったあとに、ビルドし直したか

## テスト

```sh
# 中継サーバー(本物の Gemini は呼ばない)
cd server
.venv/bin/pytest
```

アプリと拡張機能のテストは、Xcode で ⌘U を押して実行します。

どちらのテストも Google Cloud の権限がなくても実行できます。

## 共同作業者向けの手順

上の 1・2 の手順に加えて、次のことを行ってください。

### 1. 招待を受けてリポジトリを取得する

GitHub から届く招待メールで招待を承認してから、リポジトリを取得します。

```sh
git clone https://github.com/bakazikara21/Tonari.git
```

### 2. Gemini を使えるようにする

Gemini は、オーナーの Google Cloud プロジェクトを使います。
**自分でプロジェクトを作ったり、クレジットカードを登録したりする必要はありません**(利用料はオーナーのプロジェクトに付きます)。

1. 自分の Google アカウント(Gmail など)を、オーナーに伝えます。オーナーがそのアカウントに権限を付けます。
2. オーナーから、プロジェクト ID を教えてもらいます。
3. [Google Cloud CLI(gcloud)](https://cloud.google.com/sdk/docs/install) をインストールします。
   途中でプロジェクトの作成や無料トライアルの登録を勧められても、行わなくてかまいません。
4. ログインします。**権限を付けてもらったのと同じ Google アカウントを選んでください。**

   ```sh
   gcloud auth application-default login
   gcloud auth application-default set-quota-project オーナーのプロジェクトID
   ```

5. 「1. 中継サーバーを立ち上げる」の手順で `server/.env` を作り、`GOOGLE_CLOUD_PROJECT` にオーナーのプロジェクト ID を書きます。
6. 商品データとベクトルを作ります(データベースは Git に入っていないので、各自で作ります)。
   `embeddings.py` が成功すれば、権限は正しく付いています。

   ```sh
   cd server
   .venv/bin/python demo_data.py
   .venv/bin/python embeddings.py
   ```

付けてもらった権限は Tonari の開発のためだけに使ってください。ほかの用途で Gemini を呼ばないでください。

うまくいかないとき:

| 症状 | 原因と対処 |
| --- | --- |
| `PERMISSION_DENIED`(403) | 権限の反映に数分かかることがあります。少し待っても直らなければ、手順 4 で別の Google アカウントでログインしていないか確かめてください |
| `serviceusage.services.use` が足りないというエラー | オーナーに「Service Usage ユーザー」(`roles/serviceusage.serviceUsageConsumer`)の権限も付けてもらい、数分待ってから手順 4 の `set-quota-project` を実行し直してください |

Gemini を使えない間も、画面づくり・拡張機能の安全対策・設定画面・テストの作業はできます。
その場合は `server/.env` の `GOOGLE_CLOUD_PROJECT` を仮の値(`dummy` など)にすれば中継サーバーは起動します
(「たすけて」の案内文と「今日のおすすめ」だけが動きません)。

### 3. Xcode の準備

- Xcode 27.2 以降を使ってください(プロジェクトファイルが新しい形式のため、古い Xcode では正しく開けません)。
- 署名にはオーナーの Team が設定されています。署名のエラーでビルドできないときは、
  「Signing & Capabilities」で `Tonari` と `Tonari Extension` の両方のターゲットに自分の Team を選んでください。
  **この変更はコミットしないでください**(コミットすると、ほかの人の環境で署名エラーになります)。

### 4. 「たすけて」が出ないとき

ボタンを出すだけなら、中継サーバーも Gemini も必要ありません。出ないときは、次の順に確かめてください。

1. シミュレータの「設定」→「アプリ」→「Safari」→「機能拡張」で、`Tonari Extension` がオンになっていて、
   「すべての Web サイト」が「許可」になっているか(設定はシミュレータの機種ごとに別です。機種を変えたり初期化したりすると、オフに戻ります)。
2. 拡張機能をオンにする前に開いたページではないか(再読み込みするか、新しいタブで開き直します。Safari のスタートページや空白のページには出ません)。
3. ⌘R のビルドが成功し、シミュレータに Tonari アプリが入っているか(入っていないと、「機能拡張」の一覧に出てきません)。

それでも出ないときは、Mac の Safari の設定で「詳細」→「Web デベロッパ用の機能を表示」をオンにし、
メニューの「開発」→ シミュレータ → 開いているページ からコンソールのエラーを確認してください。

### 5. 作業の流れ

`main` に直接プッシュせず、ブランチを作ってプルリクエスト(PR)を出します。

```sh
# 作業を始めるたびに、main を最新にしてからブランチを作る
git switch main && git pull
git switch -c feature/やること

# 作業してコミットしたら、プッシュして PR を作る
git push -u origin feature/やること
gh pr create
```

PR は、ほかの人がレビューしてからマージします。

### 6. 守ること

- [CLAUDE.md](CLAUDE.md) の開発ルール(安全・プライバシー、お勧め機能、実装の進め方)に従ってください。Claude Code を使う場合は自動で読み込まれます。
- `server/.env` やデータベース(`server/data/`)はコミットしないでください(`.gitignore` で除外しています)。
- 「たすけて」を試すときは、テスト用のページや架空の情報で試してください。実在の個人情報を入力したページでは試さないでください。
