# スマートフォンからの使い方

## 方法A：Google Colab経由（推奨・GitHubあり）

GitHubにアップロード後、以下のURLをスマートフォンでブックマーク：

```
https://colab.research.google.com/github/[あなたのGitHubユーザー名]/sbi-portfolio-analyzer/blob/main/SBI_Portfolio_Analyzer.ipynb
```

## 方法B：Google Drive直接（GitHubなし）

1. PCのGoogle Drive (drive.google.com) を開く
2. `SBI_Portfolio_Analyzer.ipynb` をドラッグ&ドロップでアップロード
3. Drive上でファイルを右クリック → 「アプリで開く」→「Google Colaboratory」
4. 表示されたURLをスマートフォンでブックマーク

## スマートフォンでの毎回の手順

1. ブックマークからColabを開く
2. セル1〜2を実行（▶ボタン）
3. セル3でSBIスクリーンショットをアップロード
4. セル4〜5を実行 → 投資判断レポートが表示される

## ローカルPC での実行（毎日の簡単実行）

```
py run_portfolio.py --image SBIのスクショ.jpg --email
```
結果はHTML + Gmailで届きます。
