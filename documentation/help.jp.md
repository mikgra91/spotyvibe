# SpotyVibe ユーザーガイド

**SpotyVibe** へようこそ — AI を活用した音楽発見アシスタントです。  
このガイドでは、**SpotyVibe のインターフェース**を使って好みを設定し、Spotify を接続し、プレイリストを生成し、時間をかけておすすめ精度を高めていく方法を説明します。

---

## 目次

- [プライバシー — デバイス外に送信される情報](#privacy--what-leaves-your-device)
- [はじめに](#getting-started)
  - [概要](#overview)
  - [始める前に](#before-you-start)
  - [メイン画面を理解する](#understanding-the-main-screen)
  - [クイックスタートガイド](#quick-start-guide)
- [アカウント設定](#account-setup)
  - [メニューを開く](#open-the-menu)
  - [認証情報を入力する](#enter-your-credentials)
  - [Spotify アカウントを接続する](#connect-your-spotify-account)
- [ユーザー設定](#user-preferences)
  - [設定](#settings)
  - [言語](#language)
  - [テーマ](#theme)
- [音楽プロフィール](#music-profile)
  - [音楽プロフィールを作成する](#create-your-music-profile)
    - [プロフィールを選択または作成する](#select-or-create-a-profile)
    - [プロフィールの状態](#profile-status)
    - [あなたの vibe を説明する](#describe-your-vibe)
    - [コア説明](#core-description)
    - [必須条件](#must-have)
    - [希望条件](#soft-preferences)
    - [避けたい要素](#avoid)
    - [保存 または AI Profile Update](#save-or-ai-profile-update)
    - [AI が裏側で行っていること](#what-the-ai-does-behind-the-scenes)
  - [プロフィールのインポート、エクスポート、リセット、削除](#import-export-reset-and-delete-your-profile)
  - [時間とともに好みを更新する](#updating-your-taste-over-time)
- [発見と分析](#discovery--analysis)
  - [Band/Song Analysis](#bandsong-analysis)
- [プレイリスト生成](#playlist-generation)
  - [プレイリストモードを選ぶ](#choose-a-playlist-mode)
  - [音声特徴フィルターを使う](#use-audio-filters)
  - [新規 / 新進アーティストのみ](#emerging-artists-only)
  - [生成を開始する](#start-generation)
  - [途中で停止する / 現在の曲を使う](#stop-early-or-use-current-tracks)
- [曲のレビューとフィードバック](#track-review--feedback)
  - [曲をプレビューする](#preview-a-track)
  - [Spotify リンクを開く](#open-spotify-links)
  - [曲を Like する](#like-a-track)
  - [曲を Dislike する](#dislike-a-track)
  - [曲を削除する](#remove-a-track)
- [プレイリストを洗練する](#refine-playlist)
  - [プレイリストを選択して読み込む](#select-and-load-a-playlist)
  - [曲をレビューする](#review-tracks)
  - [曲を Like する（Refine）](#like-a-track-refine)
  - [曲を Dislike する（Refine）](#dislike-a-track-refine)
  - [曲を Dismiss する](#dismiss-a-track)
- [Taste Dashboard](#taste-dashboard)
  - [ダッシュボードを開く](#opening-the-dashboard)
  - [チャート](#charts)
  - [感情別セクション](#sentiment-sections)
  - [プロフィールごとの分離](#profile-isolation)
- [曲リストと実行履歴](#song-list--run-history)
  - [永続化される曲リスト](#persistent-song-list)
  - [実行履歴](#run-history)
- [モバイル利用](#mobile-usage)
- [トラブルシューティングとヒント](#troubleshooting--tips)
  - [トラブルシューティング](#troubleshooting)
  - [最後のヒント](#final-tips)

---

<a id="privacy--what-leaves-your-device"></a>
## プライバシー — デバイス外に送信される情報

SpotyVibe は、API キーと好みのプロフィールをデバイス上に保持します。プレイリストを生成するとき、あなたの好みは OpenAI に送信され（候補を得るため）、曲名は Spotify に送信されます（確認と保存のため）。それ以外の情報は追跡されません。

| データ | デバイス上 | OpenAI へ | Spotify へ |
|------|-----------|-----------|------------|
| API キー | ✓ | — | — |
| 好みプロフィール（テキスト） | ✓ | ✓（生成ごと） | — |
| 曲への Like / Dislike | ✓ | ✓（生成ごと） | — |
| 提案された曲名 | ✓ | — | ✓（検索 / 追加） |
| 再生履歴 | — | — | ✓（一度だけ読み取り） |

これは SpotyVibe のデフォルト構成に適用されます。カスタム LLM エンドポイントを使用している場合、データの送信先が異なる可能性があります。

---

<a id="getting-started"></a>
## はじめに

<a id="overview"></a>
### 概要

SpotyVibe は、あなた個人の好みに基づいて音楽を見つけるのを助けます。  
好きな音楽を説明し、Spotify アカウントを接続すると、あなた向けに最適化されたプレイリスト候補をアプリが生成します。

フィードバックを多く与えるほど、おすすめはより良くなっていきます。

SpotyVibe は **Windows**、**macOS**、**Linux** で動作します。Windows ではネイティブなデスクトップアプリ（PyInstaller 実行ファイル）として動作します。macOS と Linux では Python パッケージ（`pip install spotyvibe-*.whl`）をインストールして `spotyvibe` を実行してください。サーバーが起動し、ブラウザが自動的に開きます。

![Main home screen](/docs/screenshots/01_main_home_screen.png)

---

<a id="before-you-start"></a>
### 始める前に

SpotyVibe を使うには、次のものを用意してください。

- **Spotify Premium** アカウント
- **OpenAI API Key**
- **Spotify Client ID**
- **Spotify Client Secret**

これらはセットアップ中にアプリ内で入力します。

![Credentials screen](/docs/screenshots/24_onboarding_credentials.png)

---

<a id="understanding-the-main-screen"></a>
### メイン画面を理解する

SpotyVibe を開くと、2 つのプロバイダーセクションを持つメイン画面が表示されます。

- **OpenAI** — 好みプロフィールの編集、AI によるプロフィール更新、AI Band/Song Analysis
- **Spotify** — プレイリスト生成、プレイリスト改善、実行履歴

各セクション上部のステータスピルには、認証情報の設定状況や接続状態が表示されます。

主要コンポーネントはすべて **折りたたみ / 展開可能** です。セクション見出し（タイトル部分のどこでも）または切り替えボタンをクリックすると、展開 / 折りたたみができます。各タイトルの下には、そのコンポーネントの役割を説明する短い説明文があります。

各セクション見出しには小さな **?** ヘルプアイコンもあります。クリックすると、このガイドの該当箇所までスクロールして開きます。

メイン画面は、2 つのプロバイダーセクションの下に整理された折りたたみ式コンポーネントで構成されています。

**OpenAI セクション:**
- **🎯 音楽プロフィール** — ジャンル、ムード、必須条件、避けたい要素など、あなたの音楽の好みを定義します。
- **🔍 Band/Song Analysis** — アーティストや曲を AI で分析し、そのままプロフィールに貼り付けられる提案を得られます。

**Spotify セクション:**
- **🎧 音楽を見つける** — AI でプレイリストを生成し、Spotify アカウントに直接保存します。ムードや質感で候補を絞るための任意の **Audio Filters** サブパネルも含まれます。*(デフォルトでは折りたたみ)*
- **🔄 プレイリストを洗練** — 既存のプレイリストを読み込み、曲ごとのフィードバックで好みプロフィールを洗練します。*(デフォルトでは折りたたみ)*
- **🕓 履歴** — 過去の生成実行を表示します。

全体の流れは次のとおりです。

1. メニューを開き、セットアップを完了する
2. 音楽プロフィールを作成または改善する
3. プレイリストを生成する
4. 曲を確認し、フィードバックを与える
5. 繰り返して今後のおすすめ精度を高める

ページ上部では、次の項目にもアクセスできます。

- **メニュー**
- **言語セレクター**
- **テーマセレクター**

![Header with menu, language, and theme controls](/docs/screenshots/02_header_controls.png)

---

<a id="quick-start-guide"></a>
### クイックスタートガイド

SpotyVibe を初めて開くと、アクティブなプロバイダーセクションに対する **Quick Start Guide** が自動表示されます。このガイドはプロバイダーごとに 2 種類に分かれています。

- **🤖 OpenAI Quick Start** — Setup、Build Your Profile、Repeat & Improve
- **🎵 Spotify Quick Start** — Setup、Generate a Playlist、Review & Feedback、Refine Existing Playlists、Repeat & Improve

各ガイドには、そのプロバイダーに関連する手順のみが表示され、それぞれ独立した「Don't show again」設定があります。

**ガイドの使い方:**

- **Contents** ページには、アクティブなプロバイダーに関連する手順だけが表示されます。任意の項目をクリックすると、その手順へ直接移動できます。
- 各手順には、説明文、**Key Actions** チェックリスト、アプリ内で何をクリックすればよいかを示す **インタラクティブデモ** があります。
- デモは自動再生されます。**▶/⏸** で一時停止、または **‹ / ›** で手動ステップ移動できます。
- 下部の **番号付きドット** または **Back / Next** ボタンで手順間を移動できます。
- 最後の手順では **Next** が **Get Started** に変わり、ガイドを閉じます。

**非表示と再表示:**

- 任意のページで **"Don't show again"** をチェックすると、そのプロバイダーのガイドは次回以降表示されなくなります。
- セッション中に別のプロバイダーへ初めて切り替えたとき、そのガイドが未非表示なら自動表示されます。
- いつでも再表示するには、**☰ → 🚀 Quick Start** をクリックしてください（現在アクティブなプロバイダーのガイドが開きます）。

![Quick Start guide contents page](/docs/screenshots/26_quickstart_toc.png)

---

<a id="account-setup"></a>
## アカウント設定

<a id="open-the-menu"></a>
### メニューを開く

右上の **☰ メニューアイコン**（ハンバーガーメニュー）をクリックしてメニューを開きます。

ここから次の項目にアクセスできます。

- **Credentials**
- **Settings**
- **Disconnect Spotify**（すでに接続済みの場合）

![Burger menu open](/docs/screenshots/03_burger_menu_open.png)

---

<a id="enter-your-credentials"></a>
### 認証情報を入力する

**Credentials** を開き、次を入力します。

- **OpenAI API Key**
- **Spotify Client ID**
- **Spotify Client Secret**

入力が終わったら **Save** をクリックします。API キーは OS のキーチェーン（例: Windows Credential Manager）に安全に保存され、平文では保存されません。アプリ設定（モデル、プレイリストサイズなど）は別の設定ファイルに保存されます。

入力内容が正しければ、次に Spotify を接続できます。

![Credentials form](/docs/screenshots/04_credentials_modal.png)

---

<a id="connect-your-spotify-account"></a>
### Spotify アカウントを接続する

認証情報を保存すると、SpotyVibe は Spotify への接続を促します。

**Connect to Spotify** をクリックし、サインインフローを完了してください。

接続されると、次の状態になります。

- 接続バナーが消える
- プレイリスト生成を開始できる
- SpotyVibe がプレイリストを作成・管理できる

後でセッションの有効期限が切れた場合は、再接続してください。

![Connect to Spotify banner](/docs/screenshots/27_connect_spotify_banner.png)

---

<a id="user-preferences"></a>
## ユーザー設定

<a id="settings"></a>
### 設定

メニューから **Settings** を開くと、SpotyVibe の動作をカスタマイズできます。

設定できる項目には次のようなものがあります。

- **Used Model**  
  SpotyVibe が使用する AI モデルを選びます。

- **Playlist Size**  
  生成したい曲数の目標を設定します。

- **New Artist %**  
  まだ見ていないアーティストをどの程度優先するかを調整します。

- **ChatGPT Language**  
  AI による説明やプロフィール更新で使う言語を選択します。

変更後は **Save** をクリックしてください。

![Settings panel](/docs/screenshots/05_settings_modal.png)

---

<a id="language"></a>
### 言語

ページ上部の **language picker** を使うと、インターフェース言語を切り替えられます。

変更されるのは、たとえば次のようなテキストです。

- ボタン
- ラベル
- メッセージ
- メニュー

![Language selector](/docs/screenshots/06_language_selector.png)

---

<a id="theme"></a>
### テーマ

SpotyVibe には複数のビジュアルテーマがあります。

ページ上部付近の **theme switcher** を使って、好みの見た目を選択できます。

テーマは見た目を変更しますが、プレイリスト結果には影響しません。

![Theme switcher](/docs/screenshots/07_theme_switcher.png)

---

<a id="music-profile"></a>
## 音楽プロフィール

<a id="create-your-music-profile"></a>
### 音楽プロフィールを作成する

SpotyVibe が良いおすすめを生成するには、まずあなたの好みを学習させる必要があります。

**OpenAI** セクションで **Edit profile** をクリックするか、**音楽プロフィール** 見出しのどこかをクリックしてプロフィールエディターを開きます。

エディターは **折りたたみ可能なアコーディオンパネル** で構成されています。各パネル見出しをクリックすると展開 / 折りたたみできます。最初のパネル **Profiles** でプロフィールを管理します。

![Music Profile editor with accordion panels](/docs/screenshots/08_profile_editor_open.png)

---

<a id="select-or-create-a-profile"></a>
#### プロフィールを選択または作成する

**👤 Profiles** アコーディオンは、エディター内の最初のパネルです。ここにはドロップダウンと作成ボタンがあります。

1. ドロップダウンの下にある **+ Create new Profile** をクリックします。
2. たとえば「Workout」「Chill」「Discovery」のような名前を入力し、**Enter** を押すか **✓** をクリックします。名前は最大 40 文字です。
3. 新しいプロフィールが自動的に選択され、すぐに編集できます。

プロフィールはいくつでも作成できます。各プロフィールは完全に独立しているため、気分、用途、家族ごとなどで分けるのに便利です。

プロフィールを切り替えるには、ドロップダウンから別のものを選択してください。切り替えるとフォーム項目も自動的に更新されます。

![Profiles accordion with dropdown and create input](/docs/screenshots/09_profiles_accordion.png)

---

<a id="profile-status"></a>
#### プロフィールの状態

セクション見出しの下には状態行が表示されます。

- **✓ Last trained: [date/time]** — このプロフィールは少なくとも一度、保存または AI 更新されています。これは最後に保存された時刻を示すものであり、プロフィールの品質を示すものではありません。
- **⚠ Not yet trained** — このプロフィールはまだ一度も保存されていません。下で好みを記述し、保存して開始してください。

![Profile status indicators](/docs/screenshots/10_profile_status.png)

---

<a id="describe-your-vibe"></a>
#### あなたの vibe を説明する

**💬 Describe Your Vibe** アコーディオンは、SpotyVibe に「どんな音楽を求めているか」を最も手軽に伝える方法です。

友達に話すような自然な言葉で、聴きたい音楽を説明してください。たとえば次のように書けます。

- "I love energetic rock with theatrical vocals like Queen. Surprise me with something new but keep it high-energy and melodic!"
- "More jazz influence, less electronic. Think Snarky Puppy meets Radiohead."
- "Make my profile darker and heavier, but keep the melodies."

**スマート分類:** **AI Profile Update** を使うと、SpotyVibe は入力された文章をただ保存するだけではありません。メッセージの各部分を **自動的に分類** し、適切なプロフィールセクションへ振り分けます。AI は自然なトリガーフレーズを認識します。

| あなたが書く内容 | 振り分け先 |
|---|---|
| "must have heavy bass", "needs strong vocals" | → **Must Have** |
| "no autotune", "avoid slow songs", "without synths" | → **Avoid** |
| "would be nice to have jazz influence", "ideally some prog elements" | → **Soft Preferences** |
| 一般的な好みの説明、ジャンル / ムード / エネルギー | → **Core Description** |

つまり、すべてを一箇所に自由入力し、AI に整理させることができます。更新が完了すると、このフィールドは **自動的にクリア** されます。入力内容は構造化されたプロフィール各セクションに取り込まれるため、一時的な指示文はもう不要になるからです。

このフィールドを入力した場合、下の **Core Description** は任意になります。AI が自動生成してくれます。

![Describe Your Vibe field with example text](/docs/screenshots/11_vibe_description.png)

---

<a id="core-description"></a>
#### コア説明

**🎵 Core Description** アコーディオンは、プロフィールの土台です。

次のような観点で、求める音楽を自分の言葉で説明してください。

- ジャンル
- ムード
- エネルギー感
- 雰囲気
- 参考アーティスト
- 楽器
- ボーカル

このフィールドでは、あなたの全体的な好みが明確に伝わるように書いてください。

![Core Description field](/docs/screenshots/12_core_description.png)

---

<a id="must-have"></a>
#### 必須条件

**✅ Must Have** アコーディオンには、すべてのおすすめ曲が **必ず** 持っていなければならない、譲れない要素を書きます。これらの条件を一つでも満たさない曲は除外されます。

例:

- 強いメロディ
- 感情的なボーカル
- エネルギッシュなドラム
- 雰囲気のあるギターワーク

1 行に 1 項目ずつ入力してください。

![Must Have section](/docs/screenshots/13_must_have.png)

---

<a id="soft-preferences"></a>
#### 希望条件

**💡 Soft Preferences** アコーディオンには、歓迎するが必須ではない要素を書きます。あると嬉しい、提案の質を高める要素です。

例:

- わずかなプログレ要素
- 温かみのあるプロダクション
- ときどき入るシンセの質感

1 行に 1 項目ずつ入力してください。

![Soft Preferences section](/docs/screenshots/14_soft_preferences.png)

---

<a id="avoid"></a>
#### 避けたい要素

**🚫 Avoid** アコーディオンには、絶対に避けたい要素を書きます。これらは即座に除外理由となる項目です。

例:

- 電子的すぎるプロダクション
- スローバラード
- 激しすぎるボーカル
- 繰り返しが多すぎるサビ

1 行に 1 項目ずつ入力してください。

![Avoid section](/docs/screenshots/15_avoid.png)

---

<a id="save-or-ai-profile-update"></a>
#### 保存 または AI Profile Update

プロフィールを編集すると、エディター下部に 2 つのアクションボタンが表示されます。

- **Save**（右側）  
  入力した内容をそのまま保存します。AI 処理なし、API 呼び出しなし、即時保存です。フィールドが空でも動作します。OpenAI API キーは不要です。

- **AI Profile Update**（左側）  
  入力内容を GPT に送信し、プロフィールを洗練・整理・構造化します。AI は Vibe Description を自動分類し、参考アーティストを抽出し、内部用の好みルールを生成し、各セクションの表現も改善します。OpenAI API キーが必要で、少量のトークンを使用します。Core Description と Vibe Description の両方が空の場合は、黄色い警告が表示されます。

![Save and AI Profile Update buttons](/docs/screenshots/16_save_buttons.png)

---

<a id="what-the-ai-does-behind-the-scenes"></a>
#### AI が裏側で行っていること

**AI Profile Update** を実行すると、GPT は単に文章を保存するだけではありません。あなたが直接編集しない複数の内部フィールドも更新し、それによってプレイリスト生成精度を大きく高めます。

- **Goal & primary reference** — コア説明から導かれる 1 文の要約と、中心となるスタイル指標
- **Confirmed / moderate / rejected artists** — 説明文から抽出されたアーティスト名を、好みへの一致度に応じて分類
- **Taste rules** — 曲を評価する優先順位（例: "melody > energy > style"）と、Avoid セクションから導かれる絶対的な除外条件リスト

これらのフィールドは UI には表示されませんが、すべてのプレイリスト生成プロンプトに含まれます。そのため GPT はより正確な提案ができるようになります。これらを自分で管理する必要はありません。**AI Profile Update** を実行するたびに自動更新されます。

---

<a id="import-export-reset-and-delete-your-profile"></a>
### プロフィールのインポート、エクスポート、リセット、削除

**Profiles** アコーディオン見出しには、折りたたみ用の矢印の横に **⋯**（三点メニュー）ボタンがあります。クリックすると、次の操作を含むドロップダウンが開きます。

- **Upload profile**  
  保存済みのプロフィール JSON ファイルを現在のプロフィールに読み込みます。まず確認ダイアログが表示されます。読み込みで上書きされる前に、以前のプロフィールは自動的に履歴ファイルへバックアップされます。インポートしたファイル内の未知のフィールドは静かに削除され、不足しているフィールドはデフォルトテンプレートから補われます。

- **Export profile**  
  現在のプロフィールを `spotyvibe_profile.json` としてダウンロードします（AI が生成した内部フィールドも含む完全な JSON）。

- **Reset profile**  
  以前のバージョンのプロフィールに戻します（1 段階の取り消し）。これは、最後の保存、AI 更新、またはインポートの前に自動作成されたバックアップを読み込みます。

- **Delete profile**  
  現在のプロフィールとその履歴を完全に削除します。まず確認ダイアログが表示されます。この操作は取り消せません。他のプロフィールが存在する場合は、先頭のプロフィールが自動的に選択されます。

**無効化される項目:** プロフィールが選択されていない場合、**Export**、**Reset**、**Delete** はアクティブなプロフィールが必要なためグレーアウトされます。**Upload** は常に利用可能で、アクティブなプロフィールを作成または置き換えます。

これは、プロフィールのバックアップ、他デバイスへの移行、不要なプロフィールの整理、直近の変更の取り消しに便利です。

![Import / Export / Reset / Delete controls](/docs/screenshots/17_profile_io_controls.png)

---

<a id="updating-your-taste-over-time"></a>
### 時間とともに好みを更新する

あなたの好みは変化します。SpotyVibe は、その変化に合わせて進化するよう設計されています。

好みを更新するには:

1. **OpenAI** セクションに戻る
2. **Edit profile** をクリックする
3. 説明文や各種リストを更新する — または **Describe Your Vibe** フィールドに変化だけを書く
4. **Save** または **AI Profile Update** を実行する
5. もう一度生成する

プロフィールが現在の好みをより正確に反映しているほど、今後のプレイリストはより良くなります。小さな調整なら、たとえば「more acoustic, less electronic」のように Vibe フィールドへ書き、AI に既存プロフィールへ統合させるのが便利です。

![Editing an existing profile](/docs/screenshots/28_editing_existing_profile.png)

---

<a id="discovery--analysis"></a>
## 発見と分析

<a id="bandsong-analysis"></a>
### Band/Song Analysis

**OpenAI** セクションで **Open Analysis** をクリックするか、**Band/Song Analysis** 見出しのどこかをクリックして展開します。

この機能は、アーティストや曲を分析し、その内容をプロフィール用の表現に変換するのに役立ちます。

使い方:

1. **artist name** を入力する
2. 必要に応じて **track name** を入力する
3. **Analyze** をクリックする
4. 結果を確認する
5. 役立つ提案を音楽プロフィールへコピーする

「何が好きかは分かるけれど、それをどう表現すればよいか分からない」という場合に特に便利です。

![Band/Song Analysis panel](/docs/screenshots/18_analysis_panel.png)

---

<a id="playlist-generation"></a>
## プレイリスト生成

プロフィールの準備ができ、Spotify に接続済みであれば、**Spotify** セクションで **音楽を見つける** 見出しの **Show** をクリックするか、見出しのどこかをクリックして展開します。

ここで SpotyVibe は、あなたの好みに基づいてプレイリスト候補を作成します。ページをコンパクトに保つため、このセクションはデフォルトで折りたたまれています。

![Discover Music section expanded](/docs/screenshots/19_discover_section.png)

---

<a id="choose-a-playlist-mode"></a>
### プレイリストモードを選ぶ

生成前に、SpotyVibe がプレイリストをどのように扱うかを選択します。

一般的な選択肢は次のとおりです。

- **Default**  
  標準の SpotyVibe プレイリストを使用します

- **Create new**  
  新しいプレイリストを作成します

- **Append**  
  既存のプレイリストに曲を追加します

- **Replace**  
  既存のプレイリストを空にして、新しい曲で埋め直します

新しいプレイリストを作成する場合は、通常カスタム名を入力できます。

![Playlist mode selector](/docs/screenshots/20_playlist_mode_selector.png)

---

### クイックモード vs 詳細モード

Generate パネルには、上部のピルトグルから切り替えられる 2 つのモードがあります。

- **Quick** — プレイリストサイズ、探索スライダー、Generate ボタンのみを表示します。日常的な利用に最適です。
- **Advanced** — すべてのコントロールを表示します。プリセット選択、プレイリストモード、新進アーティスト指定、音声特徴フィルター、New Artist %、探索スライダーが含まれます。

モード選択は保存され、再読み込み後も復元されます。

---

### 探索スライダー

**探索 vs 精度**スライダーは 5 段階のコントロールで、提案をどれだけ冒険的にするかを調整します。

1. **Familiar** — すでに知っているアーティスト寄り（新規 10%、temperature 0.5）
2. **Cautious** — やや新しめだが安全寄り（新規 30%、temperature 0.7）
3. **Balanced** — 半分程度が新規アーティスト、中程度の新規性（新規 50%、temperature 0.8）
4. **Mostly new** — 発見重視、一部に馴染みのある軸も残す（新規 70%、temperature 0.9）
5. **Adventurous** — 新進アーティストのみ、高い新規性（新規 90%、temperature 1.0）

Advanced モードで "New Artist %" や新進アーティストのチェックボックスを手動調整し、どのノッチにも一致しない値にすると、スライダーは **Custom** 状態になります。いずれかのノッチに戻すと、対応するプリセット値が再適用されます。

---

### 生成プリセット

Advanced モードでは、上部の **Preset** ドロップダウンから、生成設定一式を保存・再利用できます。

- **Built-in presets:** Safe picks、Balanced、Deep discovery。編集はできませんが、複製は可能です。
- **User presets:** 組み込みプリセットの上に表示されます。**"💾 Save current as preset…"** で保存します。
- **Manage presets:** **☰ Menu → 🎛 Manage presets** から開きます。名前変更、削除、並べ替え、インポート、エクスポートができます。
- プリセットはブラウザの localStorage にローカル保存されます。

---

<a id="use-audio-filters"></a>
### 音声特徴フィルターを使う

**音楽を見つける** セクション内の **🎚 Audio Filters (optional)** バーをクリックすると、フィルターパネルを展開できます。これらの任意フィルターにより、希望するムードや質感に合う曲を GPT に提案させやすくなります。

利用できるフィルター:

- **Energy** — 曲の強さ / 活発さ（0–1）
- **Valence** — 曲の明るさ / ポジティブさ（0–1）
- **Tempo** — BPM
- **Danceability** — 踊りやすさ（0–1）
- **Acousticness** — どれだけアコースティックか（対電子的）（0–1）

各フィルターには **min** と **max** の入力欄があります。入力すると右側に人間に分かりやすいヒント（例: "↳ Energetic to Intense"）が表示され、数値の意味を直感的に確認できます。

**Clear All:** フィルターパネル右上の **✕ Clear all** をクリックすると、すべてのフィルターを一括でリセットできます。

#### Band/Song Analysis を使ってフィルターを設定する

音声特徴フィルターを埋める最も簡単な方法は、**Band/Song Analysis** を使うことです。

1. **Band/Song Analysis** を開き、基準にしたい曲を分析します。
2. 結果内の各音声特徴行（Energy、Valence など）には **⇒ Filter** ボタンがあります。
3. 任意の特徴の **⇒ Filter** をクリックすると、音楽を見つける のフィルターパネルに適切な min/max 範囲（±10%、テンポは ±15 BPM）が自動設定されます。
4. または **⇒ Use All as Filters** をクリックすると、すべての特徴を一度に適用できます。
5. フィルターを適用すると、Discover セクションとフィルターパネルが自動的に開きます。

これにより、分析と生成がスムーズにつながり、数値を覚えておく必要がなくなります。

![Audio Filters sub-panel inside Discover Music](/docs/screenshots/21_audio_filters.png)

![Band/Song Analysis with Filter buttons](/docs/screenshots/18_analysis_panel.png)

---

<a id="emerging-artists-only"></a>
### 新規 / 新進アーティストのみ

プレイリスト名 / モードのコントロールと Audio Filters パネルの間に、**"Only new / emerging artists"** チェックボックスがあります。

チェックすると:

- AI は **過去 6 か月以内にデビューしたアーティストの曲のみ** を提案するよう指示されます。
- Spotify での検証後、曲はアルバムの **release date** に基づいてフィルタリングされ、6 か月より古いものは除外されます。
- フィルタリングが厳しくなる分を補うため、AI は 1 バッチあたりにより多くの候補を要求します。
- 最終プレイリストの曲数は、設定したサイズより **少なくなる可能性** があります。

結果を説明するステータスメッセージも表示されます（例: "Showing 14 of 30 checked tracks — only tracks by recently emerged artists are included."）。

通常の生成動作にしたい場合は、このチェックを外したままにしてください。

---

<a id="start-generation"></a>
### 生成を開始する

**Generate & Create Playlist** をクリックして開始します。

音楽を見つける セクション内のボタン下にローディングスピナーが表示されます。SpotyVibe の処理中は、その下に進捗メッセージが表示されます。

1. 曲候補を生成する
2. Spotify で確認する
3. プレイリストを構築する
4. セクション内（区切り線の下）に結果を表示する
5. Spotify でプレイリストを開くリンクを表示する

![Generation in progress with inline spinner](/docs/screenshots/29_generation_spinner.png)

---

<a id="stop-early-or-use-current-tracks"></a>
### 途中で停止する / 現在の曲を使う

生成中、次の 2 つの便利な選択肢が表示される場合があります。

- **Cancel**  
  現在の生成を停止し、変更を適用しません

- **Use X tracks now**  
  生成を停止し、その時点で見つかっている曲だけを使ってプレイリストを作成します

すでに結果に満足していて、これ以上待ちたくない場合に便利です。

![Cancel and Use X Tracks Now buttons](/docs/screenshots/30_cancel_use_tracks.png)

---

<a id="track-review--feedback"></a>
## 曲のレビューとフィードバック

生成後、SpotyVibe は提案された曲を **音楽を見つける セクション内**、Generate ボタンの下に区切り線を挟んで表示します。最初に完了バナーとプレイリストリンクが表示され、その後に曲カードが続きます。曲カードはホバーで緑色に光ります。

各カードには、次のような情報が表示されることがあります。

- 曲名
- アーティスト名
- アルバムアート
- おすすめ理由
- アクションボタン

ここで各曲を確認し、次に何をするか決められます。

![Track cards after generation](/docs/screenshots/31_track_cards.png)

---

<a id="preview-a-track"></a>
### 曲をプレビューする

曲カードのアルバムアートをクリックすると、画面下部にプレビューオーバーレイが開きます。

プレビューは 3 つの領域で構成されます。

1. **Spotify player** — 埋め込みプレイヤー（中央・横長）
2. **Action tabs** — プレイヤー右側にある縦並びのタブ風ボタン（👍 👎 ✕）
3. **Feedback form** — 👍 または 👎 をクリックすると、残りの領域にスライド表示されるフォーム

同じタブをもう一度クリックすると、フィードバックフォームは閉じます。✕ ボタンはフォームを開かずにその曲を即座に取り除きます。アクティブなタブは Like で緑、Dislike で赤く光ります。

‹ と › の矢印で、オーバーレイを閉じずに曲間を移動できます。

> **注:** 埋め込み Spotify プレイヤーでは **約 30 秒のプレビュー** が再生されます。完全再生はできません。埋め込みが独立した iframe 内で動作しており、ブラウザのサードパーティ Cookie 制限のため Spotify セッションにアクセスできないためです。フルで聴くには、プレイヤー内の Spotify アイコンをクリックするか、曲カード上の Spotify リンクを使用してください。

![Preview player open](/docs/screenshots/32_preview_player.png)

---

<a id="open-spotify-links"></a>
### Spotify リンクを開く

各曲カードには、Spotify でコンテンツを開くためのクイックリンクがあります。たとえば次のようなものです。

- 曲
- アーティスト
- アルバム

より詳しく音楽を確認したいときに使ってください。

![Spotify quick links on a song card](/docs/screenshots/33_spotify_quick_links.png)

---

<a id="like-a-track"></a>
### 曲を Like する

曲があなたの好みに合っているなら **Like** をクリックします。

送信前に短い理由を任意で追加できます。

Like した曲は、SpotyVibe が「何がうまく機能しているか」を学ぶ助けになります。

理由の例:

- perfect mood
- great vocals
- strong melody
- exactly the sound I want

![Like feedback form](/docs/screenshots/34_like_feedback_form.png)

---

<a id="dislike-a-track"></a>
### 曲を Dislike する

曲が合わない場合は **Dislike** をクリックします。

必要に応じて、理由を追加してなぜ合わないのかを説明できます。

例:

- too slow
- wrong atmosphere
- too electronic
- weak chorus

これにより、SpotyVibe は今後似た曲を避けやすくなります。

![Dislike feedback form](/docs/screenshots/35_dislike_feedback_form.png)

---

<a id="remove-a-track"></a>
### 曲を削除する

**Remove** をクリックすると、Like / Dislike として記録せずに曲をリストから取り除けます。

特に良くも悪くもない、中立的な曲に使ってください。

![Remove button on song card](/docs/screenshots/36_remove_button.png)

---

<a id="refine-playlist"></a>
## プレイリストを洗練する

**プレイリストを洗練** セクションでは、既存の Spotify プレイリストを読み込み、曲を 1 曲ずつレビューできます。各曲に対して Like、Dislike、Dismiss を行うことで、好みプロフィールを洗練しつつ、プレイリスト自体も整理できます。

これは次のような場合に便利です。

- 以前作成したプレイリストを見直して、あとからフィードバックを付けたい
- 今の好みに合わなくなった曲を削除してプレイリストを整理したい
- 実際のリスニング体験をもとに、SpotyVibe により多くの好み情報を学ばせたい

開くには、Spotify セクション内の **🔄 プレイリストを洗練** 見出しにある **Show** をクリックするか、見出しのどこかをクリックしてください。

![Refine Playlist section expanded](/docs/screenshots/22_refine_playlist_section.png)

---

<a id="select-and-load-a-playlist"></a>
### プレイリストを選択して読み込む

1. **プレイリストを洗練** セクションを展開します — あなたの Spotify プレイリストが自動的にドロップダウンへ読み込まれます
2. **dropdown** からプレイリストを選択します
3. **🔄 Load Playlist** をクリックします

SpotyVibe が曲を取得している間、ボタンの下にローディングスピナーが表示されます。読み込みが完了すると、曲はセクション内のボタン下、区切り線の下に表示されます。曲カードは Discover の候補リストと似た見た目です。

![Playlist dropdown with playlists loaded](/docs/screenshots/37_playlist_dropdown.png)

---

<a id="review-tracks"></a>
### 曲をレビューする

各曲カードには次の内容が表示されます。

- アルバムアート（クリックでプレビュー）
- アーティスト名と曲名
- Spotify リンク（曲、アーティスト、アルバム）
- アクションボタン: **👍 Like**、**👎 Dislike**、**✕ Dismiss**

アルバムアートをクリックすると、Spotify プレビュープレイヤーも開けます。Refine リストからプレビューしている場合、前 / 次の移動はそのレビューリスト内で行われます。

![Review track cards](/docs/screenshots/38_review_track_cards.png)

---

<a id="like-a-track-refine"></a>
### 曲を Like する（Refine）

**👍 Like** をクリックすると、その曲に対するポジティブなフィードバックを記録します。

フィードバックフォームが開き、必要に応じてアーティスト名、曲名、理由を編集 / 追加できます。

送信後、その曲はレビューリストからアニメーションで消えます。曲自体は **Spotify プレイリストに残ったまま** で、更新されるのは好みプロフィールだけです。

![Like feedback form in Refine section](/docs/screenshots/39_review_like_form.png)

---

<a id="dislike-a-track-refine"></a>
### 曲を Dislike する（Refine）

**👎 Dislike** をクリックすると、ネガティブなフィードバックを記録します。

フィードバックフォームが開き、必要に応じてアーティスト名、曲名、理由を編集 / 追加できます。

送信後、その曲は次のように処理されます。

1. 好みプロフィールに **Dislike** として記録される
2. **Spotify プレイリストから削除される**

カードはレビューリストからアニメーションで消えます。

![Dislike feedback form in Refine section](/docs/screenshots/40_review_dislike_form.png)

---

<a id="dismiss-a-track"></a>
### 曲を Dismiss する

**✕ (Dismiss)** をクリックすると、好みプロフィールへのフィードバックを記録せずに、その曲を Spotify プレイリストから削除します。

プレイリストからは消したいが、好みとしては中立的な曲に使ってください。

カードはレビューリストからアニメーションで消えます。

![Dismiss button on review track card](/docs/screenshots/41_review_dismiss_button.png)

---

<a id="taste-dashboard"></a>
## あなたの好みをひと目で

音楽プロフィール エディターの下にある **"Your taste at a glance"** セクションでは、あなたのリスニング傾向を可視化するインタラクティブなチャートが表示されます。データはプレイリスト生成履歴から自動的に集計されます。

<a id="opening-the-dashboard"></a>
### ダッシュボードを開く

**Show** をクリックするか、セクション見出しをクリックしてダッシュボードパネルを展開します。まだ十分な数のプレイリストを生成していない場合、チャートの代わりに **"Not enough data yet"** プレースホルダーが表示されます。チャートは、生成履歴に **少なくとも 10 曲のユニークなトラック** があると表示されます。

<a id="charts"></a>
### チャート

ダッシュボードには 3 種類のチャートが表示されます。

- **Top Genres** — Spotify のアーティストメタデータに基づき、最も多いジャンルをドーナツチャートで表示します。スライスにホバーすると、ジャンル名と曲数を確認できます。
- **Energy × Valence** — 曲のムードを散布図で表示します。横軸は valence（悲しい → 明るい）、縦軸は energy（穏やか → 激しい）です。点にホバーするとアーティスト名と曲名が表示されます。脚注には、energy と valence は AI による推定値であり、厳密な測定値ではないことが示されます。
- **Decades** — Spotify のアルバムデータに基づき、曲のリリース年代を棒グラフで表示します。

<a id="sentiment-sections"></a>
### 感情別セクション

曲にフィードバック（Like / Dislike）を与えている場合、ダッシュボードは最大 3 つのサブセクションに分かれます。

- **All tracks** — 実行内のすべての曲を集計したメイン表示
- **Liked tracks** — Like（👍）した曲だけに基づくチャート
- **Disliked tracks** — Dislike（👎）した曲だけに基づくチャート

Liked / Disliked セクションは、十分なデータがある場合にのみ表示されます。

<a id="profile-isolation"></a>
### プロフィールごとの分離

各プロフィールは、それぞれ独立したダッシュボードデータを持ちます。**プロフィールを切り替えたとき** または **新しいプロフィールを作成したとき**、ダッシュボードは完全にリセットされます。

- すべてのチャートは即座にクリアされます。
- 空状態のプレースホルダーが表示されます。
- ダッシュボードパネルが展開中の場合、新しくアクティブになったプロフィール用の新しいデータが自動取得されます。

つまり、前のプロフィールの古いチャートが残ることはありません。新規プロフィールでは、そこでプレイリスト生成を行うまでは常に "Not enough data yet" が表示されます。

---

<a id="song-list--run-history"></a>
## 曲リストと実行履歴

<a id="run-history"></a>
### 実行履歴

SpotyVibe は、Spotify パネル内の プレイリストを洗練 の下にある **履歴** セクションに、直近 **5 回** のプレイリスト生成実行を保持します。**Show history** をクリックするか、セクション見出しのどこかをクリックして展開します。

各実行では、次の内容を確認できます。

- 実行日時
- 追加された曲数
- プレイリストへのリンク（Spotify 上にまだ存在する場合）

**履歴エントリをクリック** すると展開し、その実行で追加された全曲一覧（Artist — Track）が表示されます。もう一度クリックすると折りたたまれます。

最新 5 件を超えた古い実行は、自動的に削除されて履歴が簡潔に保たれます。

![Run History section with expanded entry](/docs/screenshots/23_run_history.png)

---

<a id="persistent-song-list"></a>
### 永続化される曲リスト

生成済みの曲リストは 音楽を見つける セクション内に保存され、ページを再読み込みしても復元されます。セッションをまたいでも曲カードは失われません。

つまり次のことができます。

- 以前の提案を見返す
- アプリに戻ってもリストを失わない
- 時間をかけて曲をレビューし続ける

リストが多くなりすぎたら、新しく生成する前にいくつかの曲を削除してください。

![Song list with saved tracks](/docs/screenshots/42_history_song_list.png)

---

<a id="mobile-usage"></a>
## モバイル利用

SpotyVibe はスマートフォンやタブレットでも快適に使えます。

モバイル端末では:

- パネルが縦に積み重なって表示される
- ボタンがタップしやすい
- ダイアログやフォームが小さい画面向けに調整される

基本的な流れは同じです。

1. セットアップを完了する
2. Spotify を接続する
3. プロフィールを作る
4. プレイリストを生成する
5. 曲をレビューしてフィードバックする

![Mobile view of the home screen](/docs/screenshots/43_mobile_view.png)

---

<a id="troubleshooting--tips"></a>
## トラブルシューティングとヒント

<a id="troubleshooting"></a>
### トラブルシューティング

**プレイリストを生成できません**  
次を確認してください。

- 必要な認証情報をすべて入力している
- Spotify アカウントを接続している
- 音楽プロフィールを作成済みである

**Spotify 接続がうまくいきません**  
メニューから Spotify を切断し、再度接続してみてください。

**おすすめが自分の好みに合いません**  
音楽プロフィールを、より明確で具体的な好み / 嫌いの記述に更新してください。

**似たような曲ばかり提案されます**  
プロフィールの編集内容をより詳細にし、新しいアーティストへの関心度を上げ、好き / 嫌いな曲に対して直接フィードバックを与えてください。

**追加される曲が少なすぎます**  
音声特徴フィルターの範囲を広げるか、制約を少なくして再実行してください。

![Example warning or error message](/docs/screenshots/44_warning_message.png)

---

<a id="final-tips"></a>
### 最後のヒント

SpotyVibe を最大限活用するには:

- 音楽プロフィールは具体的に書く
- フィードバックをこまめに与える
- 好みが変わったらプロフィールも更新する
- より厳密に絞りたいときだけ音声特徴フィルターを使う
- 実行履歴を使って過去の生成結果を見直す

アプリは使うほど改善されるので、継続的なフィードバックがより良い音楽発見につながります。

---

**SpotyVibe** で、次のお気に入りの音楽をぜひ見つけてください。
