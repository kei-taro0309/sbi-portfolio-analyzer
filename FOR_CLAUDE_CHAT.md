# SBI証券 AI投資判断システム — Claude引き継ぎ用完全資料
# このファイルをClaudeのチャットにアップロードするだけで続きから作業できます

---

## プロジェクト概要

SBI証券モバイルアプリの「信用建玉」スクリーンショットをアップロードするだけで、
全保有銘柄の投資判断（即売却 / 保有継続 / 追加買い）を自動生成するシステム。

- **GitHub**: `https://github.com/kei-taro0309/sbi-portfolio-analyzer`
- **Colab（スマホ用）**: `https://colab.research.google.com/github/kei-taro0309/sbi-portfolio-analyzer/blob/master/SBI_Portfolio_Analyzer.ipynb`
- **ローカル実行**: `py run_portfolio.py --image スクショ.jpg`
- **ユーザーメール**: keitarooe0309@gmail.com

---

## ファイル構成

```
portfolio_system/
├── SBI_Portfolio_Analyzer.ipynb  ← Colabノートブック（スマホメイン）
├── portfolio_ocr.py              ← OCRエンジン v2（Column-aware）
├── portfolio_analyzer.py         ← テクニカル分析 + 投資判断エンジン
├── portfolio_report.py           ← HTMLレポート生成 + Gmail送信
├── run_portfolio.py              ← ローカルPC用CLI
├── test_ocr.py                   ← OCRパーサーユニットテスト
├── requirements.txt              ← yfinance / easyocr / Pillow / pytesseract
└── FOR_CLAUDE_CHAT.md            ← このファイル
```

---

## 現在保有ポジション（2026/04/29時点の参照データ）

全て**信用建玉（6ヶ月）**。評価損益合計 **-61,926円（-2.93%）**

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

---

## 重要：OCRパーサーの設計（v2）

### SBIアプリのレイアウト構造
```
行A: [銘柄名]           [現在値]      [評価損益円]
行B: [コード 建玉/特定]  [平均単価]    [評価損益率%]
行C: [6ヶ月]（任意）
```

### カラム境界（画像幅比）
- L列: x < 38%　→ 銘柄名・証券コード
- M列: 38〜65%　→ 現在値・平均単価
- R列: x > 65%　→ 評価損益円・評価損益率

### 行グループ化トレランス
`tol = max(img_h * 0.012, 5)` ← **ここが最重要**
- 2.5%（21px）にすると行Aと行Bがマージされてヘッダー行(-61,926円)を現在値と誤認する
- 1.2%（10px）で行内ばらつき~5pxに対応しつつ行間~20pxを分離できる

### アルゴリズム（コード行ルックバック方式）
1. 各OCRブロックをL/M/Rカラムに分類
2. y座標±10pxで行グループ化
3. L列に4桁コードを含む行 = コード行(B)を検出
4. コード行から最大3行前をルックバック → M列に価格がある行 = 現在値・損益円
5. コード行のM列 = 平均単価、R列 = 損益率
6. pnl_pctの符号でpnl_yenの符号を自動補正

### テスト結果（test_ocr.py）
9銘柄100%OK + エッジケース4種（符号なし/円なし/コード分離/カンマなし）全OK

---

## 投資判断ロジック優先順位

1. `pnl ≤ -12%` → **即売却（損切）★★★** HIGH（信用追証水域）
2. `pnl ≤ -7%`  → **即売却（損切）★★★** HIGH（損切りライン突破）
3. `pnl ≤ -5%`  → BB<0.15&RSI<30&K14<20なら保有継続（反発監視）、それ以外は**損切り★★**
4. エネルギーセクター&利益圏 → RSI>65なら一部利確、それ以外は保有継続
5. 進化買いシグナル（K14≤30, K14_chg≥1, RSI≤40, BB≤0.3, 出来高≥0.8, MA5>0, pnl>-3） → **追加買い候補★★★**（77.8%勝率）
6. 上昇モメンタム（RSI≥55, MA5↑, MACD改善, 利益圏） → 保有継続（上昇継続）
7. 売られ過ぎ（BB<0.2, RSI<35） → 保有継続（反発待ち）
8. 中立 → 保有継続（様子見）

---

## 修正済みバグ履歴（重要・同じミスをしないために）

| バグ | 原因 | 修正 |
|------|------|------|
| `NoneType.__format__` | current_price/avg_costがNoneのまま書式化 | safe_float()でNullチェック |
| yfinance MultiIndex | `df['Close'].tolist()`が新版で失敗 | `_col()`でsqueeze().dropna().tolist() |
| データ不足 | days=130で取引日90日未満 | days=200、最低閾値80 |
| OCR価格の取り違え | コード発見後に「次の行」を探す（逆設計） | コード行から「前の行」をルックバック |
| **OCR行マージ誤動作** | **ROW_TOL=2.5%(21px)≥行間隔20px→行AとBがマージ→ヘッダー-61,926を現在値と誤認** | **ROW_TOL=0.012(10px)に修正** |
| 損益符号の欠落 | OCRが`-`を認識しないケース | pnl_pctの符号でpnl_yenを補正 |
| 4550 ticker not found | 住友ファーマの正コードは4506 | SECTOR_MAPに4506と4550両方登録 |
| CP932 UnicodeError | Windows端末が絵文字を出力できない | `.encode('ascii','replace').decode()` |

---

## 全ソースコード

### portfolio_ocr.py

```python
# portfolio_ocr.py v2 — SBI証券スクリーンショット Column-aware OCRパーサー

import re
import os

def _try_easyocr(image_path: str):
    import easyocr
    reader = easyocr.Reader(['ja', 'en'], gpu=False, verbose=False)
    return [(r[1], r[0], r[2]) for r in reader.readtext(image_path)]

def _try_tesseract(image_path: str):
    import pytesseract
    from PIL import Image
    img = Image.open(image_path)
    data = pytesseract.image_to_data(img, lang='jpn', output_type=pytesseract.Output.DICT)
    blocks = []
    for i, text in enumerate(data['text']):
        if text.strip():
            x, y = data['left'][i], data['top'][i]
            w, h = data['width'][i], data['height'][i]
            bbox = [[x, y], [x+w, y], [x+w, y+h], [x, y+h]]
            blocks.append((text.strip(), bbox, data['conf'][i] / 100.0))
    return blocks

def ocr_image(image_path: str):
    for fn, name in [(_try_easyocr, 'easyocr'), (_try_tesseract, 'pytesseract')]:
        try:
            blocks = fn(image_path)
            if blocks:
                print(f"[OCR] {name} で {len(blocks)} ブロック検出")
                return blocks
        except ImportError:
            print(f"[OCR] {name} 未インストール → スキップ")
        except Exception as e:
            print(f"[OCR] {name} 失敗: {e}")
    return []

class SBIPortfolioOCR:
    KNOWN_NAMES = {
        '1605': 'INPEX', '1662': '石油資源開発', '2782': 'セリア',
        '3901': 'アゼアス', '4245': 'ダイキアクシス',
        '4550': '住友ファーマ', '4506': '住友ファーマ',
        '3983': 'モリテック', '9602': '東宝', '9876': 'コックス',
    }
    LEFT_MAX  = 0.38
    RIGHT_MIN = 0.65
    _RE_CODE  = re.compile(r'\b(\d{4})\b')
    _RE_PRICE = re.compile(r'(\d[\d,，]*(?:\.\d{1,2})?)(?:円|¥)?')
    _RE_PCT   = re.compile(r'([+\-−]?\d{1,3}(?:\.\d{1,2})?)(?:%|％)')

    @staticmethod
    def _sf(s: str):
        try:
            return float(str(s).replace(',','').replace('，','')
                               .replace('−','-').replace('＋','+').replace('±',''))
        except Exception:
            return None

    def parse_screenshot(self, image_path: str) -> list:
        blocks = ocr_image(image_path)
        if not blocks:
            print("[OCR] テキスト検出なし → 手動入力モードへ")
            return self._manual_input()
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                img_w, img_h = img.size
        except Exception:
            img_w = img_h = 1000
        return self._parse_v2(blocks, img_w, img_h)

    def _parse_v2(self, blocks: list, img_w: int, img_h: int) -> list:
        enriched = []
        for text, bbox, conf in blocks:
            xs = [p[0] for p in bbox]; ys = [p[1] for p in bbox]
            xn = sum(xs) / 4 / img_w
            ya = sum(ys) / 4
            col = ('L' if xn < self.LEFT_MAX else 'R' if xn > self.RIGHT_MIN else 'M')
            enriched.append({'t': text.strip(), 'xn': xn, 'ya': ya, 'col': col})
        enriched.sort(key=lambda b: (b['ya'], b['xn']))

        # 1.2%トレランス（~10px）← 2.5%にすると行AとBがマージされて誤動作
        tol = max(img_h * 0.012, 5)
        rows, cur, cy = [], [], None
        for b in enriched:
            if cy is None or abs(b['ya'] - cy) <= tol:
                cur.append(b); cy = b['ya'] if cy is None else (cy + b['ya']) / 2
            else:
                rows.append(cur); cur, cy = [b], b['ya']
        if cur: rows.append(cur)

        def lmr(row):
            L = ' '.join(b['t'] for b in row if b['col'] == 'L')
            M = ' '.join(b['t'] for b in row if b['col'] == 'M')
            R = ' '.join(b['t'] for b in row if b['col'] == 'R')
            return L.strip(), M.strip(), R.strip()
        collapsed = [lmr(r) for r in rows]

        def get_code(txt):
            m = self._RE_CODE.search(txt)
            return m.group(1) if m and 1000 <= int(m.group(1)) <= 9999 else None

        def get_prices(txt):
            return [v for p in self._RE_PRICE.findall(txt)
                    for v in [self._sf(p)] if v and v > 50]

        def get_pct(txt):
            for p in self._RE_PCT.findall(txt):
                v = self._sf(p)
                if v is not None and abs(v) < 100: return v
            return None

        def get_yen(txt):
            m = re.search(r'([+\-−±])\s*([\d,，]+(?:\.\d+)?)', txt)
            if m:
                sign = -1 if m.group(1) in ('-', '−') else 1
                v = self._sf(m.group(2))
                return sign * v if v is not None else None
            prices = get_prices(txt)
            if not prices: return None
            neg = bool(re.search(r'[-−]', txt))
            return (-1 if neg else 1) * max(abs(p) for p in prices)

        positions = []
        for i, (L, M, R) in enumerate(collapsed):
            code = get_code(L)
            if not code: continue
            name = self.KNOWN_NAMES.get(code, code)
            cur_price = avg_price = pnl_yen = None
            for j in range(i - 1, max(i - 4, -1), -1):
                pL, pM, pR = collapsed[j]
                prices = get_prices(pM)
                if prices:
                    cur_price = prices[0]; pnl_yen = get_yen(pR)
                    if code not in self.KNOWN_NAMES and pL.strip():
                        name = pL.strip()[:20]
                    break
            avg_candidates = get_prices(M)
            if avg_candidates: avg_price = avg_candidates[0]
            pnl_pct = get_pct(R)
            if cur_price is None or avg_price is None: continue
            if pnl_pct is None:
                pnl_pct = (cur_price - avg_price) / avg_price * 100
            if pnl_yen is not None:
                if pnl_pct < 0 and pnl_yen > 0: pnl_yen = -pnl_yen
                elif pnl_pct > 0 and pnl_yen < 0: pnl_yen = -pnl_yen
            positions.append({
                'code': code, 'name': name,
                'current_price': cur_price, 'avg_cost': avg_price,
                'pnl_pct': round(pnl_pct, 2),
                'pnl_yen': round(pnl_yen) if pnl_yen is not None else None,
            })
        print(f"[OCR] {len(positions)} ポジション検出")
        return positions

    @staticmethod
    def _manual_input() -> list:
        print("\n=== 手動入力モード ===")
        positions = []
        while True:
            code = input("証券コード(4桁) or 'q': ").strip()
            if code.lower() == 'q': break
            if not (code.isdigit() and len(code) == 4):
                print("4桁の数字を入力してください"); continue
            name = input(f"  銘柄名: ").strip()
            try:
                cur = float(input(f"  現在値(円): ").replace(',', ''))
                avg = float(input(f"  平均単価(円): ").replace(',', ''))
            except ValueError:
                print("  数値エラー、スキップ"); continue
            pnl_pct = (cur - avg) / avg * 100
            positions.append({'code': code, 'name': name,
                               'current_price': cur, 'avg_cost': avg,
                               'pnl_yen': None, 'pnl_pct': round(pnl_pct, 2)})
            print(f"  → 追加: {name}({code}) 損益率{pnl_pct:+.2f}%")
        return positions
```

---

### portfolio_analyzer.py

```python
# portfolio_analyzer.py — テクニカル分析 + 投資判断エンジン（scanner_v12継承）

import math
import yfinance as yf
from datetime import datetime, timedelta
import time

def _ema(data: list, period: int) -> list:
    k = 2 / (period + 1)
    e = [data[0]]
    for v in data[1:]: e.append(v * k + e[-1] * (1 - k))
    return e

def _calc_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 2: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0.0)); losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period; al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period-1) + gains[i]) / period
        al = (al * (period-1) + losses[i]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def _calc_indicators(closes, highs, lows, volumes):
    if len(closes) < 80: return None
    ef = _ema(closes, 9); es = _ema(closes, 26)
    ml = [f - s for f, s in zip(ef, es)]; sl = _ema(ml[25:], 6)
    hist_t = ml[-1] - sl[-1]; hist_p = ml[-2] - sl[-2]
    k14r = []
    for i in range(13, len(closes)):
        hi = max(highs[i-13:i+1]); lo = min(lows[i-13:i+1])
        k14r.append(50 if hi == lo else (closes[i]-lo)/(hi-lo)*100)
    sm14 = _ema(k14r, 3)
    ma25 = sum(closes[-25:])/25; ma25p = sum(closes[-26:-1])/25
    rsi = _calc_rsi(closes[-30:])
    ma20 = sum(closes[-20:])/20
    std20 = math.sqrt(sum((c-ma20)**2 for c in closes[-20:])/20)
    bb_lo = ma20-2*std20; bb_hi = ma20+2*std20
    bb_pos = (closes[-1]-bb_lo)/(bb_hi-bb_lo) if bb_hi > bb_lo else 0.5
    vol_ma20 = sum(volumes[-20:])/20
    vol_ratio = volumes[-1]/vol_ma20 if vol_ma20 > 0 else 1.0
    ma5 = sum(closes[-5:])/5; ma5p = sum(closes[-6:-1])/5
    ma75 = sum(closes[-75:])/75
    return {
        'hist_t': hist_t, 'hist_chg': hist_t-hist_p,
        'k14': sm14[-1], 'k14_chg': sm14[-1]-sm14[-2],
        'dev': (closes[-1]-ma25)/ma25*100, 'rsi': rsi,
        'bb_pos': bb_pos, 'vol_ratio': vol_ratio,
        'ma5_slope': (ma5-ma5p)/ma5p*100,
        'dev75': (closes[-1]-ma75)/ma75*100, 'price': closes[-1],
        'support': min(lows[-60:]), 'resistance': max(highs[-60:]),
        'price_change_1d': (closes[-1]-closes[-2])/closes[-2]*100,
        'price_change_5d': (closes[-1]-closes[-6])/closes[-6]*100 if len(closes)>=6 else 0,
        'price_change_20d': (closes[-1]-closes[-21])/closes[-21]*100 if len(closes)>=21 else 0,
    }

class InvestmentJudge:
    SECTOR_MAP = {
        '1605':('エネルギー','原油・天然ガス開発'), '1662':('エネルギー','石油資源開発'),
        '2782':('小売','100円ショップ'), '3901':('素材','難燃防護服・機能素材'),
        '4245':('環境','水処理・排水設備'), '4506':('医薬品','製薬（住友化学系）'),
        '4550':('医薬品','製薬（住友化学系）'), '3983':('素材','鉄鋼加工・金属資材'),
        '9602':('エンタメ','映画・不動産'), '9876':('小売','ファッション・アパレル'),
    }

    def judge(self, pos: dict, ind) -> dict:
        code = pos['code']; pnl_pct = pos.get('pnl_pct', 0) or 0
        sector, detail = self.SECTOR_MAP.get(code, ('不明', ''))
        action, stars, reason, risk = self._rule_based(code, pnl_pct, ind, sector, detail)
        return {'code': code, 'name': pos['name'], 'sector': sector, 'detail': detail,
                'cur': pos.get('current_price', 0), 'avg': pos.get('avg_cost', 0),
                'pnl_pct': pnl_pct, 'action': action, 'stars': stars,
                'reason': reason, 'risk': risk, 'indicators': ind}

    def _rule_based(self, code, pnl_pct, ind, sector, detail):
        if pnl_pct <= -12:
            return ('即売却（損切）','★★★',
                    f'損益率{pnl_pct:.1f}%は信用取引の危機水域。追証リスク回避のため即座に損切りを実行せよ。','🔴 HIGH')
        if pnl_pct <= -7:
            return ('即売却（損切）','★★★',
                    f'損益率{pnl_pct:.1f}%は損切りライン完全突破。損失拡大前の撤退が鉄則。','🔴 HIGH')
        if pnl_pct <= -5:
            if ind and ind['bb_pos'] < 0.15 and ind['rsi'] < 30 and ind['k14'] < 20:
                return ('保有継続（反発監視）','★★',
                        f'損益{pnl_pct:.1f}%だが売られ過ぎシグナル。反発確認後即利確前提で短期保有継続。','🟠 MEDIUM')
            return ('損切り','★★',
                    f'損益{pnl_pct:.1f}%。テクニカル反発根拠なし。{detail}の業績悪化と複合すると損失拡大リスク大。','🟠 MEDIUM')
        if sector == 'エネルギー' and pnl_pct > 0:
            ts = self._tech_summary(ind)
            if ind and ind['rsi'] > 65:
                return ('一部利確検討','★★',f'損益{pnl_pct:+.1f}%。{ts}RSI過熱圏。利益50%確定推奨。','🟡 LOW-MED')
            return ('保有継続','★★',f'損益{pnl_pct:+.1f}%。{ts}エネルギー安保テーマで支持継続。WTI60ドル割れが損切りトリガー。','🟢 LOW')
        if ind is None:
            return (('保有継続','★','データ取得不可。損益プラスにつき保有継続。','🟡 LOW-MED') if pnl_pct > 0
                    else ('様子見','★','データ取得不可。様子見。','🟡 LOW-MED'))
        rsi=ind['rsi']; bb_pos=ind['bb_pos']; k14=ind['k14']; k14_chg=ind['k14_chg']
        vol=ind['vol_ratio']; dev=ind['dev']; hist_chg=ind['hist_chg']; ma5=ind['ma5_slope']
        ts = self._tech_summary(ind)
        if k14<=30 and k14_chg>=1 and rsi<=40 and bb_pos<=0.3 and vol>=0.8 and ma5>0 and pnl_pct>-3:
            return ('追加買い候補','★★★',
                    f'進化買いシグナル発動(77.8%勝率)。K14={k14:.0f}↑/RSI{rsi:.0f}/BB下位。{ts}','🟢 LOW')
        if rsi>=55 and ma5>0.3 and hist_chg>0 and dev>0 and vol>=1.0 and pnl_pct>0:
            return ('保有継続（上昇継続）','★★',f'損益{pnl_pct:+.1f}%。{ts}上昇モメンタム継続。','🟢 LOW')
        if bb_pos<0.2 and rsi<35 and pnl_pct>-5:
            return ('保有継続（反発待ち）','★★',f'売られ過ぎ。{ts}-5%到達で即損切り。','🟡 LOW-MED')
        if -3 <= pnl_pct <= 1:
            return ('保有継続（様子見）','★',f'損益{pnl_pct:+.1f}%で方向感なし。{ts}-5%達したら即損切り。','🟡 LOW-MED')
        if pnl_pct > 1:
            return ('保有継続','★★',f'損益{pnl_pct:+.1f}%。{ts}上昇余地を観察。','🟢 LOW')
        return ('損切り検討','★',f'損益{pnl_pct:+.1f}%。{ts}明確な反発根拠なし。','🟠 MEDIUM')

    @staticmethod
    def _tech_summary(ind) -> str:
        if not ind: return ''
        parts = []
        if ind['rsi'] <= 30: parts.append(f"RSI{ind['rsi']:.0f}(売られ過ぎ)")
        elif ind['rsi'] >= 70: parts.append(f"RSI{ind['rsi']:.0f}(買われ過ぎ)")
        else: parts.append(f"RSI{ind['rsi']:.0f}")
        if ind['bb_pos'] < 0.2: parts.append('BB下限近傍')
        elif ind['bb_pos'] > 0.8: parts.append('BB上限近傍')
        if ind['hist_chg'] > 0: parts.append('MACD改善')
        elif ind['hist_chg'] < 0: parts.append('MACD悪化')
        return '｜'.join(parts) + '。' if parts else ''

def fetch_ohlcv(code: str, days: int = 200):
    ticker = f'{code}.T'
    end = datetime.now(); start = end - timedelta(days=days)
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or len(df) < 80: return None
        def _col(c):
            s = df[c]
            if hasattr(s, 'squeeze'): s = s.squeeze()
            return s.dropna().tolist()
        return {'closes': _col('Close'), 'highs': _col('High'),
                'lows': _col('Low'), 'volumes': _col('Volume')}
    except Exception as e:
        print(f'  [{code}] 取得失敗: {e}'); return None

def analyze_portfolio(positions: list) -> list:
    judge = InvestmentJudge(); results = []
    print(f'\n[分析] {len(positions)} 銘柄を分析中...')
    for i, pos in enumerate(positions, 1):
        print(f"  [{i}/{len(positions)}] {pos['code']} {pos['name']}", end=' ... ', flush=True)
        data = fetch_ohlcv(pos['code'])
        ind = _calc_indicators(data['closes'],data['highs'],data['lows'],data['volumes']) if data else None
        result = judge.judge(pos, ind); results.append(result)
        print(result['action'])
        if i < len(positions): time.sleep(0.3)
    return results
```

---

### portfolio_report.py

```python
# portfolio_report.py — HTMLレポート生成 + Gmail送信

import os, json, smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_ACTION_COLOR = {
    '即売却（損切）':'#d32f2f','損切り':'#e53935','損切り検討':'#f57c00',
    '一部利確検討':'#f9a825','保有継続（反発監視）':'#1565c0',
    '保有継続（反発待ち）':'#1976d2','保有継続（上昇継続）':'#2e7d32',
    '保有継続（様子見）':'#546e7a','保有継続':'#2e7d32',
    '追加買い候補':'#1b5e20','様子見':'#78909c',
}
_ACTION_ICON = {
    '即売却（損切）':'🚨','損切り':'⛔','損切り検討':'⚠️','一部利確検討':'💰',
    '保有継続（反発監視）':'👁','保有継続（反発待ち）':'⏳','保有継続（上昇継続）':'🚀',
    '保有継続（様子見）':'⏸','保有継続':'✅','追加買い候補':'🎯','様子見':'⏸',
}

def generate_html(results, total_pnl_yen=None, total_pnl_pct=None) -> str:
    now = datetime.now().strftime('%Y/%m/%d %H:%M')
    urgent = [r for r in results if '即売却' in r['action'] or r['action']=='損切り']
    caution= [r for r in results if '損切り検討' in r['action'] or '監視' in r['action']]
    hold   = [r for r in results if '保有継続' in r['action']]
    add_buy= [r for r in results if '追加買い' in r['action']]
    # （HTMLテンプレートは省略 — generate_html関数はportfolio_report.pyを参照）
    pass

def save_html(results, output_dir, total_pnl_yen=None, total_pnl_pct=None) -> str:
    os.makedirs(output_dir, exist_ok=True)
    html = generate_html(results, total_pnl_yen, total_pnl_pct)
    fname = f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    fpath = os.path.join(output_dir, fname)
    with open(fpath, 'w', encoding='utf-8') as f: f.write(html)
    return fpath

def send_report_email(results, creds_path, total_pnl_yen=None, total_pnl_pct=None):
    if not os.path.exists(creds_path): return False
    with open(creds_path, encoding='utf-8') as f: creds = json.load(f)
    # credentials.json形式: {"email": "xxx@gmail.com", "app_password": "xxxx xxxx xxxx xxxx"}
    html = generate_html(results, total_pnl_yen, total_pnl_pct)
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"[投資判断] {datetime.now().strftime('%Y/%m/%d %H:%M')}"
    msg['From'] = msg['To'] = creds['email']
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP('smtp.gmail.com', 587) as s:
        s.starttls(); s.login(creds['email'], creds['app_password'].replace(' ',''))
        s.sendmail(creds['email'], [creds['email']], msg.as_string())
    return True
```

---

### run_portfolio.py

```python
# run_portfolio.py — CLIエントリーポイント
# 使い方: py run_portfolio.py --image SBIのスクショ.jpg [--email] [--manual]

import argparse, os, sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image',  type=str)
    parser.add_argument('--manual', action='store_true')
    parser.add_argument('--email',  action='store_true')
    parser.add_argument('--output', type=str, default='レポート')
    args = parser.parse_args()
    if not args.image and not args.manual:
        parser.print_help(); sys.exit(1)

    from portfolio_ocr      import SBIPortfolioOCR
    from portfolio_analyzer import analyze_portfolio
    from portfolio_report   import save_html, send_report_email

    ocr = SBIPortfolioOCR()
    positions = ocr._manual_input() if args.manual else ocr.parse_screenshot(args.image)
    if not positions: sys.exit(1)

    results = analyze_portfolio(positions)
    report_path = save_html(results, args.output)
    print(f'レポート: {report_path}')
    if args.email:
        send_report_email(results, os.path.join(os.path.dirname(__file__), '..', 'credentials.json'))

if __name__ == '__main__': main()
```

---

## Colabノートブック構成（SBI_Portfolio_Analyzer.ipynb）

5セル構成。GitHubに最新版がある。

- **Cell1**: easyocr/yfinance/Pillowインストール
- **Cell2**: テクニカル指標+投資判断エンジン（portfolio_analyzer.pyと同等のインライン実装）
- **Cell3**: スクリーンショットアップロード + OCR解析（portfolio_ocr.pyと同等のインライン実装。ROW_TOL=0.012が重要）
- **Cell4**: yfinance取得+分析実行
- **Cell5**: スマホアプリレベルHTMLレポート表示（グラデーションヘッダー、RSI/BB/K14ゲージバー付き）

---

## TODOリスト

- [ ] 新しく買った銘柄をKNOWN_NAMESとSECTOR_MAPに追加
- [ ] Gmail通知設定（credentials.jsonの作成）
  - Gmailアカウント設定 → セキュリティ → 2段階認証ON → アプリパスワード生成
  - `{"email": "keitarooe0309@gmail.com", "app_password": "生成された16文字"}` で保存
- [ ] 実際のスクリーンショットでOCR精度を確認（test_ocr.pyのモックでは9/9 100%確認済み）
- [ ] 他のSBI画面（保有証券タブ）への対応

---

## よく使うコマンド

```bash
# ローカル実行
py run_portfolio.py --image SBIのスクショ.jpg

# メール送信付き
py run_portfolio.py --image SBIのスクショ.jpg --email

# OCRテスト実行
py test_ocr.py

# GitHubへプッシュ
cd "C:\Users\keita\OneDrive\デスクトップ\portfolio_system"
git add -A && git commit -m "変更内容" && git push origin master
```

---

*最終更新: 2026/04/30 | v2.1 | OCRテスト100%合格済み*
