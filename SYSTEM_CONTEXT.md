# SBI証券 AI投資判断システム — コンテキストまとめ

このファイルをClaudeのチャットに貼り付けることで、システムの全体像を即座に把握できます。

---

## システム概要

SBI証券モバイルアプリの「信用建玉」スクリーンショットをアップロードするだけで、
全保有銘柄の投資判断（即売却 / 保有継続 / 追加買い）を自動生成するシステム。

- **メインアクセス（スマホ）**: Google Colab
  `https://colab.research.google.com/github/kei-taro0309/sbi-portfolio-analyzer/blob/master/SBI_Portfolio_Analyzer.ipynb`
- **GitHub**: `https://github.com/kei-taro0309/sbi-portfolio-analyzer`
- **ローカル実行**: `py run_portfolio.py --image スクショ.jpg`

---

## ファイル構成

```
portfolio_system/
├── SBI_Portfolio_Analyzer.ipynb  ← Colabノートブック（メイン）
├── portfolio_ocr.py              ← OCRエンジン（v2 Column-aware）
├── portfolio_analyzer.py         ← テクニカル分析 + 投資判断エンジン
├── portfolio_report.py           ← HTMLレポート生成 + Gmail送信
├── run_portfolio.py              ← ローカルPC用CLIエントリーポイント
└── requirements.txt              ← yfinance / easyocr / Pillow / pytesseract
```

---

## 各ファイルの役割と現状

### SBI_Portfolio_Analyzer.ipynb（Colabノートブック）

5セル構成：

| セル | 内容 |
|------|------|
| Cell1 | パッケージインストール（easyocr, yfinance, Pillow） |
| Cell2 | 分析エンジン定義（テクニカル指標 + 投資判断ロジック） |
| Cell3 | スクリーンショットアップロード + OCR解析 |
| Cell4 | 全銘柄yfinanceデータ取得 + 分析実行 |
| Cell5 | スマホアプリレベルHTMLレポート表示 |

**重要な実装詳細（Cell3）**:
- easyOCRでブロック検出後、画像幅に基づくColumn-aware方式でL/M/R列を分類
- `LEFT_MAX=0.38`, `RIGHT_MIN=0.65`（画像幅比）
- コード行を発見後に最大3行前をルックバックして現在値・評価損益円を取得
- `pnl_pct`の符号で`pnl_yen`の符号を自動補正

**OCRフォールバック**:
アップロードなし or OCR失敗 → 直近実績データ（2026/04/29）を使用

---

### portfolio_ocr.py（OCRエンジン v2）

**クラス**: `SBIPortfolioOCR`

**設計思想**:
SBIアプリの1銘柄は2〜3行で構成される：
```
行A: [銘柄名]           [現在値]      [評価損益円]   ← 旧実装はここを見逃していた
行B: [コード 建玉/特定]  [平均単価]    [評価損益率%]  ← コードはここ
行C: [6ヶ月] など（任意）
```

旧実装の致命的バグ: コード発見後に「次の行」から価格を探していた（逆方向）。
現在の実装: コード行(B)を発見し「直前の行(A)」をルックバックして価格取得。

**出力フォーマット（1ポジション）**:
```python
{
    'code':          '1605',
    'name':          'INPEX',
    'current_price': 4123.0,
    'avg_cost':      4058.0,
    'pnl_pct':       1.52,     # (%)
    'pnl_yen':       6189,     # 円
}
```

**KNOWN_NAMES（銘柄マスタ）**:
```python
{
    '1605': 'INPEX', '1662': '石油資源開発', '2782': 'セリア',
    '3901': 'アゼアス', '4245': 'ダイキアクシス',
    '4550': '住友ファーマ', '4506': '住友ファーマ',
    '3983': 'モリテック', '9602': '東宝', '9876': 'コックス',
}
```
新銘柄が増えたらここに追加する。

---

### portfolio_analyzer.py（分析エンジン）

**scanner_v12.pyから継承したテクニカル指標**:
- MACD (9/26/6)
- Stochastic K14/3
- RSI14
- Bollinger Band 20日
- MA乖離（25日・75日）
- MA5傾き
- 出来高比（20日MA比）
- 支持線・抵抗線（60日高値/安値）

**yfinance取得**:
```python
def fetch_ohlcv(code, days=200):
    # MultiIndex対応: _col()でsqueeze().dropna().tolist()
    # 最低80取引日必要
```

**投資判断ロジック（`_rule_based`）優先順位**:
1. `pnl ≤ -12%` → **即売却（損切）★★★** 🔴 HIGH（信用追証水域）
2. `pnl ≤ -7%` → **即売却（損切）★★★** 🔴 HIGH（損切りライン突破）
3. `pnl ≤ -5%`
   - BB<0.15 かつ RSI<30 かつ K14<20 → **保有継続（反発監視）★★**
   - それ以外 → **損切り★★** 🟠 MEDIUM
4. エネルギーセクター かつ 利益圏 → **保有継続** or **一部利確検討**
5. 進化買いシグナル（K14≤30, K14_chg≥1, RSI≤40, BB≤0.3, 出来高≥0.8, MA5>0, pnl>-3） → **追加買い候補★★★**（77.8%勝率）
6. 上昇モメンタム → **保有継続（上昇継続）★★**
7. 売られ過ぎ → **保有継続（反発待ち）★★**
8. 中立 → **保有継続（様子見）★**

**SECTOR_MAP**:
```python
'1605':('エネルギー','原油・天然ガス開発')
'1662':('エネルギー','石油資源開発')
'2782':('小売','100円ショップ')
'3901':('素材','難燃防護服・機能素材')
'4245':('環境','水処理・排水設備')
'4506':('医薬品','製薬（住友化学系）')
'4550':('医薬品','製薬（住友化学系）')
'3983':('素材','鉄鋼加工・金属資材')
'9602':('エンタメ','映画・不動産')
'9876':('小売','ファッション・アパレル')
```

---

### portfolio_report.py（レポート生成）

- `generate_html(results, total_pnl_yen, total_pnl_pct)` → HTML文字列
- `save_html(...)` → `レポート/portfolio_YYYYMMDD_HHMM.html` に保存
- `send_report_email(...)` → `credentials.json`（SMTP設定）を使ってGmail送信

**credentials.json フォーマット**（.gitignoreで除外済み）:
```json
{"email": "xxx@gmail.com", "app_password": "xxxx xxxx xxxx xxxx"}
```

---

## 現在保有中の9銘柄（2026/04/29時点の参照データ）

| コード | 銘柄 | 現在値 | 平均単価 | 損益率 |
|--------|------|--------|---------|--------|
| 1605 | INPEX | 4,123 | 4,058.00 | +1.52% |
| 1662 | 石油資源開発 | 2,295 | 2,269.70 | +1.04% |
| 2782 | セリア | 3,440 | 3,555.00 | -3.33% |
| 3901 | アゼアス | 633 | 684.00 | -7.78% |
| 4245 | ダイキアクシス | 703 | 739.00 | -5.13% |
| 4506 | 住友ファーマ | 1,851 | 2,164.50 | -14.80% |
| 3983 | モリテック | 234 | 232.86 | -0.17% |
| 9602 | 東宝 | 1,461 | 1,465.00 | -0.32% |
| 9876 | コックス | 238 | 270.00 | -12.09% |

全て**信用建玉（6ヶ月）**。評価損益合計 -61,926円（-2.93%）。

---

## 既知の修正済みバグ履歴

| バグ | 原因 | 修正内容 |
|------|------|---------|
| `NoneType.__format__` | current_price/avg_cost がNone | safe_float()でNullチェック追加 |
| yfinance MultiIndex | `df['Close'].tolist()`が新版で失敗 | `_col()`でsqueeze().dropna().tolist() |
| データ不足 | days=130で取引日90日に足りない | days=200、最低閾値80に変更 |
| OCR価格の取り違え | コード後の行から価格を探す（逆） | Column-aware + ルックバック方式に全面刷新 |
| 損益符号の欠落 | OCRが`-`を認識しない場合あり | pnl_pctの符号でpnl_yenを補正 |
| 4550 ticker not found | 住友ファーマは4506が正しいコード | SECTOR_MAPに両方登録 |
| CP932 UnicodeError | Windows端末が絵文字を出力できない | `.encode('ascii','replace').decode()` |

---

## OCRの現在の限界（完全に解決できない部分）

1. **easyocr自体の文字誤読**: 桁が似た文字（`4,123` → `4,l23`）は検出不可
2. **スクロール途中の画面**: 銘柄が上下に切れている場合はずれる可能性あり
3. **KNOWN_NAMES未登録銘柄**: コードをそのまま名前として使用（名前欄が変になる）
4. **高解像度/低解像度端末**: カラム境界の比率がずれる可能性（38%/65%で設計）

新銘柄を追加したときは `KNOWN_NAMES` と `SECTOR_MAP` の両方に追加が必要。

---

## 依存パッケージ

```
yfinance>=0.2.40   # 日本株データ取得（{code}.T形式）
easyocr>=1.7.0    # 日本語OCR（pytesseractより精度高い）
Pillow>=10.0.0    # 画像処理・サイズ取得
pytesseract>=0.3.10 # OCRフォールバック（任意）
tqdm>=4.65.0      # プログレスバー
```

---

## よく使うコマンド

```bash
# ローカル実行
py run_portfolio.py --image SBIのスクショ.jpg

# メール送信付き
py run_portfolio.py --image SBIのスクショ.jpg --email

# 手動入力モード（OCRなし）
py run_portfolio.py --manual

# GitHubへプッシュ
cd "C:\Users\keita\OneDrive\デスクトップ\portfolio_system"
git add -A && git commit -m "更新内容" && git push origin master
```

---

## 今後やりたいこと（TODO）

- [ ] 新しく買った銘柄をKNOWN_NAMESとSECTOR_MAPに追加する作業
- [ ] OCR精度検証：新しいスクリーンショットで実際にテスト
- [ ] Gmail通知設定（credentials.jsonの作成）
- [ ] 他のSBI画面（保有証券タブ）への対応

---

*最終更新: 2026/04/29 | バージョン: v2.0*
