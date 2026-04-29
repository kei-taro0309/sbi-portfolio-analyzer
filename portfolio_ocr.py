# portfolio_ocr.py v2 — SBI証券スクリーンショット Column-aware OCRパーサー
#
# SBIレイアウト構造（1銘柄 = 2〜3行）:
#   行A: [銘柄名]           [現在値]      [評価損益円]
#   行B: [コード 建玉/特定]  [平均単価]    [評価損益率%]
#   行C: [6ヶ月] など（任意）
#
# 旧実装の問題: コード発見後に「次の行」から価格を探していた（逆）
# 新実装の方針: コード行(B)を発見し「前の行(A)」をルックバックで価格取得

import re
import os

# ── OCRバックエンド ──────────────────────────────────────────────

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


# ── SBIスクリーンショット専用パーサー v2 ─────────────────────────

class SBIPortfolioOCR:
    """
    Column-aware SBI証券「信用建玉」スクリーンショットパーサー。

    カラム分類は画像幅に対する相対比率で決定:
      L列 (x < 38%) : 銘柄名・証券コード
      M列 (38-65%)  : 現在値・平均単価
      R列 (x > 65%) : 評価損益円・評価損益率

    アルゴリズム:
      1. 各ブロックをL/M/Rカラムに分類
      2. y座標でグループ化して行を形成
      3. L列に4桁コードが含まれる行 = コード行(B)
      4. コード行から最大3行前をルックバック → 現在値・評価損益円を取得
      5. コード行自身から平均単価・評価損益率を取得
    """

    KNOWN_NAMES = {
        '1605': 'INPEX',
        '1662': '石油資源開発',
        '2782': 'セリア',
        '3901': 'アゼアス',
        '4245': 'ダイキアクシス',
        '4550': '住友ファーマ',
        '4506': '住友ファーマ',
        '3983': 'モリテック',
        '9602': '東宝',
        '9876': 'コックス',
    }

    # カラム境界（画像幅比）
    LEFT_MAX  = 0.38   # L列上限
    RIGHT_MIN = 0.65   # R列下限

    _RE_CODE  = re.compile(r'\b(\d{4})\b')
    _RE_PRICE = re.compile(r'(\d[\d,，]*(?:\.\d{1,2})?)(?:円|¥)?')
    _RE_PCT   = re.compile(r'([+\-−]?\d{1,3}(?:\.\d{1,2})?)(?:%|％)')

    @staticmethod
    def _sf(s: str):
        """文字列 → float。変換失敗時は None"""
        try:
            return float(str(s)
                         .replace(',', '').replace('，', '')
                         .replace('−', '-').replace('＋', '+')
                         .replace('±', ''))
        except Exception:
            return None

    # ── 公開API ──────────────────────────────────────────────────

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

    # ── 内部処理 ─────────────────────────────────────────────────

    def _parse_v2(self, blocks: list, img_w: int, img_h: int) -> list:

        # 1. カラム分類 ────────────────────────────────────────────
        enriched = []
        for text, bbox, conf in blocks:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            xn = sum(xs) / 4 / img_w   # 正規化 x
            ya = sum(ys) / 4            # 絶対 y（行グループ用）
            col = ('L' if xn < self.LEFT_MAX
                   else 'R' if xn > self.RIGHT_MIN
                   else 'M')
            enriched.append({'t': text.strip(), 'xn': xn, 'ya': ya, 'col': col})

        enriched.sort(key=lambda b: (b['ya'], b['xn']))

        # 2. 行グループ化（y 方向 ±2.5% of img_h） ───────────────
        tol = max(img_h * 0.025, 8)
        rows, cur, cy = [], [], None
        for b in enriched:
            if cy is None or abs(b['ya'] - cy) <= tol:
                cur.append(b)
                cy = b['ya'] if cy is None else (cy + b['ya']) / 2
            else:
                rows.append(cur)
                cur, cy = [b], b['ya']
        if cur:
            rows.append(cur)

        # 3. L/M/R テキストに集約 ──────────────────────────────────
        def lmr(row):
            L = ' '.join(b['t'] for b in row if b['col'] == 'L')
            M = ' '.join(b['t'] for b in row if b['col'] == 'M')
            R = ' '.join(b['t'] for b in row if b['col'] == 'R')
            return L.strip(), M.strip(), R.strip()

        collapsed = [lmr(r) for r in rows]

        # 4. ヘルパー関数 ──────────────────────────────────────────
        def get_code(txt):
            m = self._RE_CODE.search(txt)
            return m.group(1) if m and 1000 <= int(m.group(1)) <= 9999 else None

        def get_prices(txt):
            return [v for p in self._RE_PRICE.findall(txt)
                    for v in [self._sf(p)] if v and v > 50]

        def get_pct(txt):
            for p in self._RE_PCT.findall(txt):
                v = self._sf(p)
                if v is not None and abs(v) < 100:
                    return v
            return None

        def get_yen(txt):
            # 符号付き金額 (+6,189 / -10,677)
            m = re.search(r'([+\-−±])\s*([\d,，]+(?:\.\d+)?)', txt)
            if m:
                sign = -1 if m.group(1) in ('-', '−') else 1
                v = self._sf(m.group(2))
                return sign * v if v is not None else None
            # フォールバック: 最大金額に符号推定
            prices = get_prices(txt)
            if not prices:
                return None
            neg = bool(re.search(r'[-−]', txt))
            return (-1 if neg else 1) * max(abs(p) for p in prices)

        # 5. コード行 → ルックバックでペアリング ──────────────────
        positions = []
        for i, (L, M, R) in enumerate(collapsed):
            code = get_code(L)
            if not code:
                continue

            name = self.KNOWN_NAMES.get(code, code)
            cur_price = avg_price = pnl_yen = None

            # コード行の直前（最大3行前）に現在値が載っている行を探す
            for j in range(i - 1, max(i - 4, -1), -1):
                pL, pM, pR = collapsed[j]
                prices = get_prices(pM)
                if prices:
                    cur_price = prices[0]
                    pnl_yen   = get_yen(pR)
                    if code not in self.KNOWN_NAMES and pL.strip():
                        name = pL.strip()[:20]
                    break

            # このコード行から平均単価・損益率を取得
            avg_candidates = get_prices(M)
            if avg_candidates:
                avg_price = avg_candidates[0]
            pnl_pct = get_pct(R)

            if cur_price is None or avg_price is None:
                continue

            if pnl_pct is None:
                pnl_pct = (cur_price - avg_price) / avg_price * 100

            # pnl_yen の符号を pnl_pct で補正（OCRが符号を落とすケース対策）
            if pnl_yen is not None:
                if pnl_pct < 0 and pnl_yen > 0:
                    pnl_yen = -pnl_yen
                elif pnl_pct > 0 and pnl_yen < 0:
                    pnl_yen = -pnl_yen

            positions.append({
                'code':          code,
                'name':          name,
                'current_price': cur_price,
                'avg_cost':      avg_price,
                'pnl_pct':       round(pnl_pct, 2),
                'pnl_yen':       round(pnl_yen) if pnl_yen is not None else None,
            })

        print(f"[OCR] {len(positions)} ポジション検出")
        return positions

    @staticmethod
    def _manual_input() -> list:
        print("\n=== 手動入力モード ===")
        print("ポジションを1件ずつ入力（終了: コードに 'q'）")
        positions = []
        while True:
            code = input("証券コード(4桁) or 'q': ").strip()
            if code.lower() == 'q':
                break
            if not (code.isdigit() and len(code) == 4):
                print("4桁の数字を入力してください")
                continue
            name = input(f"  銘柄名: ").strip()
            try:
                cur = float(input(f"  現在値(円): ").replace(',', ''))
                avg = float(input(f"  平均単価(円): ").replace(',', ''))
            except ValueError:
                print("  数値エラー、スキップ")
                continue
            pnl_pct = (cur - avg) / avg * 100
            positions.append({
                'code': code, 'name': name,
                'current_price': cur, 'avg_cost': avg,
                'pnl_yen': None, 'pnl_pct': round(pnl_pct, 2),
            })
            print(f"  → 追加: {name}({code}) 損益率{pnl_pct:+.2f}%")
        return positions


# ── 直接実行テスト ────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("使い方: python portfolio_ocr.py <画像パス>")
        sys.exit(1)
    ocr = SBIPortfolioOCR()
    positions = ocr.parse_screenshot(sys.argv[1])
    print("\n=== 検出ポジション ===")
    for p in positions:
        cur = p['current_price']
        avg = p['avg_cost']
        pnl = p['pnl_pct']
        print(f"  {p['code']} {p['name']:12s}  "
              f"現在値{cur:>8,.1f}  平均{avg:>9,.2f}  損益率{pnl:+.2f}%")
