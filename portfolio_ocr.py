# portfolio_ocr.py — SBI証券スクリーンショット OCR解析エンジン
# easyocr (primary) / pytesseract (fallback) / 手動入力 (ultimate fallback)

import re
import os
from pathlib import Path

# ── OCRバックエンド選択 ──────────────────────────────────────

def _try_easyocr(image_path: str):
    """easyocr で画像からテキストブロック（text, bbox, conf）を返す"""
    import easyocr
    reader = easyocr.Reader(['ja', 'en'], gpu=False, verbose=False)
    results = reader.readtext(image_path)
    # results: [(bbox, text, conf), ...]
    return [(r[1], r[0], r[2]) for r in results]


def _try_tesseract(image_path: str):
    """pytesseract で画像からテキストデータを返す"""
    import pytesseract
    from PIL import Image
    img = Image.open(image_path)
    data = pytesseract.image_to_data(
        img, lang='jpn', output_type=pytesseract.Output.DICT)
    blocks = []
    for i, text in enumerate(data['text']):
        if text.strip():
            x, y = data['left'][i], data['top'][i]
            w, h = data['width'][i], data['height'][i]
            bbox = [[x, y], [x+w, y], [x+w, y+h], [x, y+h]]
            conf = data['conf'][i] / 100.0
            blocks.append((text.strip(), bbox, conf))
    return blocks


def ocr_image(image_path: str):
    """
    画像をOCRして (text, bbox, conf) リストを返す。
    easyocr → pytesseract の順で試みる。
    """
    for fn, name in [(_try_easyocr, "easyocr"), (_try_tesseract, "pytesseract")]:
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


# ── パターン定義 ─────────────────────────────────────────────

_RE_PRICE    = re.compile(r'(\d{1,5}[,，]\d{3}(?:\.\d{1,2})?|\d{2,6}(?:\.\d{1,2})?)(?:円)?')
_RE_PCT      = re.compile(r'([+\-−]?\d{1,3}(?:\.\d{1,2})?)(?:%|％)')
_RE_CODE     = re.compile(r'\b(\d{4})\b')
_RE_PNL_YEN  = re.compile(r'([+\-−]?\d{1,3}(?:[,，]\d{3})*(?:\.\d{1,2})?)(?:円)?')


def _clean_num(s: str) -> float:
    """'1,234.56' や '+6,500' → float"""
    s = s.replace(',', '').replace('，', '').replace('−', '-').replace('＋', '+')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _bbox_y_center(bbox):
    """bboxの中心y座標を返す"""
    ys = [pt[1] for pt in bbox]
    return sum(ys) / len(ys)


def _bbox_x_center(bbox):
    """bboxの中心x座標を返す"""
    xs = [pt[0] for pt in bbox]
    return sum(xs) / len(xs)


# ── SBIスクリーンショット専用パーサー ────────────────────────

class SBIPortfolioOCR:
    """
    SBI証券モバイルアプリ「口座管理→信用建玉」スクリーンショットを解析し、
    ポジションリストを返す。
    """

    # 既知銘柄コードマッピング（OCRが読み誤った際の補完用）
    KNOWN_NAMES = {
        "1605": "INPEX",
        "1662": "石油資源開発",
        "2782": "セリア",
        "3901": "アゼアス",
        "4245": "ダイキアクシス",
        "4550": "住友ファーマ",
        "3983": "モリテック",
        "9602": "東宝",
        "9876": "コックス",
    }

    def parse_screenshot(self, image_path: str) -> list[dict]:
        """
        スクリーンショットを解析してポジションリストを返す。
        各ポジション dict のキー:
          code, name, current_price, avg_cost, pnl_yen, pnl_pct
        """
        blocks = ocr_image(image_path)
        if not blocks:
            print("[OCR] テキスト検出なし → 手動入力モードへ")
            return self._manual_input()

        return self._parse_blocks(blocks)

    def _parse_blocks(self, blocks: list) -> list[dict]:
        """
        bboxを使ってブロックをy座標でクラスタリングし、行ごとにパース。
        """
        # y座標でソート
        sorted_blocks = sorted(blocks, key=lambda b: _bbox_y_center(b[1]))

        # y座標が近いブロックを同一行にグループ化（±20px以内）
        rows = []
        current_row = []
        current_y = None
        for text, bbox, conf in sorted_blocks:
            y = _bbox_y_center(bbox)
            if current_y is None or abs(y - current_y) <= 25:
                current_row.append((text, bbox, conf))
                current_y = y if current_y is None else (current_y + y) / 2
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [(text, bbox, conf)]
                current_y = y
        if current_row:
            rows.append(current_row)

        # 行からポジション情報を抽出
        positions = []
        pending = {}

        for row in rows:
            row_text = ' '.join(t for t, _, _ in sorted(row, key=lambda b: _bbox_x_center(b[1])))
            row_text = row_text.strip()

            # 4桁コードを探す
            code_match = _RE_CODE.search(row_text)
            if code_match:
                code = code_match.group(1)
                if 1000 <= int(code) <= 9999:
                    if pending:
                        positions.append(pending)
                    name = self.KNOWN_NAMES.get(code, row_text.split()[0][:10])
                    pending = {"code": code, "name": name,
                               "current_price": None, "avg_cost": None,
                               "pnl_yen": None, "pnl_pct": None}
                    continue

            if not pending:
                continue

            # 価格行パース（現在値 / 平均単価）
            prices = _RE_PRICE.findall(row_text)
            if prices and pending["current_price"] is None:
                prices_f = [_clean_num(p) for p in prices if _clean_num(p) > 0]
                if len(prices_f) >= 2:
                    pending["current_price"] = prices_f[0]
                    pending["avg_cost"]       = prices_f[1]
                elif len(prices_f) == 1 and prices_f[0] > 100:
                    pending["current_price"]  = prices_f[0]
                continue

            # 損益行パース（評価損益円 / 評価損益率%）
            pct_matches = _RE_PCT.findall(row_text)
            if pct_matches and pending["pnl_pct"] is None:
                pct = _clean_num(pct_matches[-1])
                pending["pnl_pct"] = pct
                # yen amount
                yen_matches = _RE_PNL_YEN.findall(row_text)
                if yen_matches:
                    for ym in yen_matches:
                        v = _clean_num(ym)
                        if abs(v) > 10:
                            pending["pnl_yen"] = v
                            break

        if pending and pending.get("code"):
            positions.append(pending)

        # コードだけあって価格が取れなかった行を除外
        valid = [p for p in positions if p.get("current_price") and p.get("avg_cost")]
        print(f"[OCR] {len(valid)} ポジション検出")

        # avg_cost から pnl_pct を補完
        for p in valid:
            if p["pnl_pct"] is None and p["current_price"] and p["avg_cost"]:
                p["pnl_pct"] = (p["current_price"] - p["avg_cost"]) / p["avg_cost"] * 100

        return valid

    @staticmethod
    def _manual_input() -> list[dict]:
        """OCR失敗時の手動入力インターフェース"""
        print("\n=== 手動入力モード ===")
        print("ポジションを1件ずつ入力してください。終了: コードに 'q' を入力")
        positions = []
        while True:
            code = input("証券コード(4桁) or 'q': ").strip()
            if code.lower() == 'q':
                break
            if not (code.isdigit() and len(code) == 4):
                print("4桁の数字を入力してください")
                continue
            name      = input(f"  銘柄名: ").strip()
            try:
                cur  = float(input(f"  現在値(円): ").replace(',', ''))
                avg  = float(input(f"  平均単価(円): ").replace(',', ''))
            except ValueError:
                print("  数値エラー、スキップ")
                continue
            pnl_pct = (cur - avg) / avg * 100
            positions.append({
                "code": code, "name": name,
                "current_price": cur, "avg_cost": avg,
                "pnl_yen": None, "pnl_pct": round(pnl_pct, 2),
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
        print(f"  {p['code']} {p['name']:12s}  "
              f"現在値{p['current_price']:,.0f}  平均{p['avg_cost']:,.2f}  "
              f"損益率{p['pnl_pct']:+.2f}%")
