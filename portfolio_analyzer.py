# portfolio_analyzer.py — ポートフォリオ技術分析 + 投資判断エンジン
# scanner_v12.py のテクニカル分析ロジックを継承・活用

import math
import yfinance as yf
from datetime import datetime, timedelta
import time

# ── テクニカル指標（scanner_v12 から継承）────────────────────

def _ema(data: list, period: int) -> list:
    k = 2 / (period + 1)
    e = [data[0]]
    for v in data[1:]:
        e.append(v * k + e[-1] * (1 - k))
    return e


def _calc_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 2:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def _calc_indicators(closes: list, highs: list, lows: list, volumes: list) -> dict | None:
    if len(closes) < 80:
        return None

    # MACD (9/26/6)
    ef = _ema(closes, 9)
    es = _ema(closes, 26)
    ml = [f - s for f, s in zip(ef, es)]
    sl = _ema(ml[25:], 6)
    hist_t = ml[-1] - sl[-1]
    hist_p = ml[-2] - sl[-2]

    # Stochastic K (21/5)
    k21 = []
    for i in range(20, len(closes)):
        hi = max(highs[i-20:i+1])
        lo = min(lows[i-20:i+1])
        k21.append(50 if hi == lo else (closes[i] - lo) / (hi - lo) * 100)
    sm5 = _ema(k21, 5)

    # Stochastic K14/3
    k14r = []
    for i in range(13, len(closes)):
        hi = max(highs[i-13:i+1])
        lo = min(lows[i-13:i+1])
        k14r.append(50 if hi == lo else (closes[i] - lo) / (hi - lo) * 100)
    sm14 = _ema(k14r, 3)

    # 25日MA乖離
    ma25  = sum(closes[-25:]) / 25
    ma25p = sum(closes[-26:-1]) / 25

    # RSI14
    rsi = _calc_rsi(closes[-30:])

    # Bollinger Band (20日)
    ma20  = sum(closes[-20:]) / 20
    std20 = math.sqrt(sum((c - ma20)**2 for c in closes[-20:]) / 20)
    bb_lo = ma20 - 2 * std20
    bb_hi = ma20 + 2 * std20
    bb_pos = (closes[-1] - bb_lo) / (bb_hi - bb_lo) if bb_hi > bb_lo else 0.5

    # 出来高比率 (20日MA比)
    vol_ma20  = sum(volumes[-20:]) / 20
    vol_ratio = volumes[-1] / vol_ma20 if vol_ma20 > 0 else 1.0

    # MA5傾き
    ma5  = sum(closes[-5:]) / 5
    ma5p = sum(closes[-6:-1]) / 5
    ma5_slope = (ma5 - ma5p) / ma5p * 100

    # 75日MA乖離
    ma75  = sum(closes[-75:]) / 75
    dev75 = (closes[-1] - ma75) / ma75 * 100

    # 支持線・抵抗線（60日高値/安値）
    support    = min(lows[-60:])
    resistance = max(highs[-60:])
    support_pct    = (closes[-1] - support)    / support    * 100
    resistance_pct = (resistance - closes[-1]) / closes[-1] * 100

    return {
        "hist_t":      hist_t,
        "hist_p":      hist_p,
        "hist_chg":    hist_t - hist_p,
        "k_t":         sm5[-1],
        "k_p":         sm5[-2],
        "k_chg":       sm5[-1] - sm5[-2],
        "k14":         sm14[-1],
        "k14_chg":     sm14[-1] - sm14[-2],
        "dev":         (closes[-1] - ma25) / ma25 * 100,
        "slope":       (ma25 - ma25p) / ma25p * 100,
        "rsi":         rsi,
        "bb_pos":      bb_pos,
        "vol_ratio":   vol_ratio,
        "ma5_slope":   ma5_slope,
        "dev75":       dev75,
        "price":       closes[-1],
        "support":     support,
        "resistance":  resistance,
        "support_pct": support_pct,        # 現在値の支持線からの乖離(%)
        "resistance_pct": resistance_pct,  # 抵抗線までの乖離(%)
        "price_change_1d": (closes[-1] - closes[-2]) / closes[-2] * 100,
        "price_change_5d": (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0,
        "price_change_20d": (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0,
    }


# ── 投資判断エンジン ─────────────────────────────────────────

class InvestmentJudge:
    """
    ポジションのテクニカル・ファンダメンタルを総合評価し投資判断を下す。
    判断: 即売却 / 損切り / 保有継続 / 追加買い候補
    """

    # セクター分類
    SECTOR_MAP = {
        "1605": ("エネルギー", "原油・天然ガス開発"),
        "1662": ("エネルギー", "石油資源開発"),
        "2782": ("小売",      "100円ショップ"),
        "3901": ("素材",      "難燃防護服・機能素材"),
        "4245": ("環境",      "水処理・排水設備"),
        "4506": ("医薬品",    "製薬（住友化学系）"),
        "4550": ("医薬品",    "製薬（住友化学系）"),
        "3983": ("素材",      "鉄鋼加工・金属資材"),
        "9602": ("エンタメ",  "映画・不動産"),
        "9876": ("小売",      "ファッション・アパレル"),
    }

    def judge(self, pos: dict, ind: dict | None) -> dict:
        """
        pos: OCR/手動から得たポジション dict
        ind: calc_indicators の結果（None なら価格ベースのみで判断）
        return: action, stars, reason, risk_level
        """
        code     = pos["code"]
        pnl_pct  = pos.get("pnl_pct", 0) or 0
        cur      = pos.get("current_price", 0)
        avg      = pos.get("avg_cost", 0)
        sector, detail = self.SECTOR_MAP.get(code, ("不明", ""))

        action, stars, reason, risk = self._rule_based(
            code, pnl_pct, ind, sector, detail)

        return {
            "code":       code,
            "name":       pos["name"],
            "sector":     sector,
            "detail":     detail,
            "cur":        cur,
            "avg":        avg,
            "pnl_pct":    pnl_pct,
            "action":     action,
            "stars":      stars,
            "reason":     reason,
            "risk":       risk,
            "indicators": ind,
        }

    def _rule_based(self, code, pnl_pct, ind, sector, detail):
        """
        ルールベース判断。
        優先順位: 損失深度 → テクニカルシグナル → セクターファンダ
        """

        # ──────────────── 損切りルール（信用取引） ────────────────
        if pnl_pct <= -12:
            return (
                "即売却（損切）",
                "★★★",
                f"損益率{pnl_pct:.1f}%は信用取引の危機水域。"
                f"追証リスクを回避するため即座に損切りを実行せよ。{detail}の回復を待つ余裕はない。",
                "🔴 HIGH"
            )

        if pnl_pct <= -7:
            return (
                "即売却（損切）",
                "★★★",
                f"損益率{pnl_pct:.1f}%は損切りラインを完全突破。"
                f"テクニカル回復の証拠がない限り、損失拡大前の撤退が鉄則。",
                "🔴 HIGH"
            )

        if pnl_pct <= -5:
            # テクニカルシグナルで「反発の根拠」があれば保有継続を検討
            if ind and ind["bb_pos"] < 0.15 and ind["rsi"] < 30 and ind["k14"] < 20:
                return (
                    "保有継続（反発監視）",
                    "★★",
                    f"損益率{pnl_pct:.1f}%だがBB下限({ind['bb_pos']:.2f}) / "
                    f"RSI{ind['rsi']:.0f} / K14={ind['k14']:.0f}で売られ過ぎシグナル。"
                    f"反発確認後 即利確を前提に短期保有継続。翌日の引け値を確認後に再判断。",
                    "🟠 MEDIUM"
                )
            return (
                "損切り",
                "★★",
                f"損益率{pnl_pct:.1f}%。テクニカル反発根拠なし。"
                f"信用取引の-5%は損切りの基準ライン。{detail}の業績悪化要因と複合すると損失拡大リスク大。",
                "🟠 MEDIUM"
            )

        # ──────────────── セクター別ファンダ考慮 ────────────────
        # エネルギーセクター特別判断
        if sector == "エネルギー" and pnl_pct > 0:
            tech_comment = self._tech_summary(ind)
            if ind and ind["rsi"] > 65:
                return (
                    "一部利確検討",
                    "★★",
                    f"損益率{pnl_pct:+.1f}%で利益圏。{tech_comment}"
                    f"RSI{ind['rsi']:.0f}で過熱圏入り。原油価格は米中摩擦で不安定。"
                    f"利益の50%を確定させ残りを保有するのが現実的。",
                    "🟡 LOW-MED"
                )
            return (
                "保有継続",
                "★★",
                f"損益率{pnl_pct:+.1f}%で利益圏。{tech_comment}"
                f"エネルギー安保テーマで中期的に支持されるセクター。"
                f"ただし原油WTI60ドル割れが損切りトリガー。",
                "🟢 LOW"
            )

        # ──────────────── テクニカルベース判断 ────────────────
        if ind is None:
            # データ取得失敗 → 損益ベースのみ
            if pnl_pct > 0:
                return ("保有継続", "★", "データ取得不可。損益プラスにつき保有継続。要再分析。", "🟡 LOW-MED")
            return ("様子見", "★", "データ取得不可。損益マイナスだが-5%未満につき様子見。", "🟡 LOW-MED")

        rsi      = ind["rsi"]
        bb_pos   = ind["bb_pos"]
        k14      = ind["k14"]
        k14_chg  = ind["k14_chg"]
        vol      = ind["vol_ratio"]
        dev      = ind["dev"]
        hist_chg = ind["hist_chg"]
        ma5_slp  = ind["ma5_slope"]
        tech_s   = self._tech_summary(ind)

        # 追加買い条件（スキャナーv12 進化買いシグナル準拠）
        if (k14 <= 30 and k14_chg >= 1.0 and rsi <= 40
                and bb_pos <= 0.3 and vol >= 0.8 and ma5_slp > 0
                and pnl_pct > -3):
            return (
                "追加買い候補",
                "★★★",
                f"進化買いシグナル発動。{tech_s}"
                f"K14={k14:.0f}(↑+{k14_chg:.1f}pt) / RSI{rsi:.0f} / BB下位({bb_pos:.2f})。"
                f"現在損益{pnl_pct:+.1f}%。エントリー強度高。",
                "🟢 LOW"
            )

        # 上昇モメンタム（買い継続）
        if (rsi >= 55 and ma5_slp > 0.3 and hist_chg > 0 and dev > 0
                and vol >= 1.0 and pnl_pct > 0):
            return (
                "保有継続（上昇継続）",
                "★★",
                f"上昇モメンタム継続中。{tech_s}"
                f"RSI{rsi:.0f} / MA5傾き+{ma5_slp:.2f}% / MACD改善。利益を伸ばせる局面。",
                "🟢 LOW"
            )

        # 売られ過ぎ反発待ち（小幅損失）
        if (bb_pos < 0.2 and rsi < 35 and pnl_pct > -5):
            return (
                "保有継続（反発待ち）",
                "★★",
                f"売られ過ぎ領域。{tech_s}"
                f"BB下位({bb_pos:.2f}) / RSI{rsi:.0f}。短期反発確率高。"
                f"ただし損益{pnl_pct:.1f}%が-5%に達したら即損切り発動。",
                "🟡 LOW-MED"
            )

        # 中立〜弱い局面
        if -3 <= pnl_pct <= 1:
            return (
                "保有継続（様子見）",
                "★",
                f"損益{pnl_pct:+.1f}%で方向感なし。{tech_s}"
                f"明確な上昇シグナルが出るまで現状維持。-5%達したら即損切り。",
                "🟡 LOW-MED"
            )

        if pnl_pct > 1:
            return (
                "保有継続",
                "★★",
                f"損益{pnl_pct:+.1f}%。{tech_s}引き続き上昇余地を探る。",
                "🟢 LOW"
            )

        return (
            "損切り検討",
            "★",
            f"損益{pnl_pct:+.1f}%。{tech_s}明確な反発根拠なし。",
            "🟠 MEDIUM"
        )

    @staticmethod
    def _tech_summary(ind: dict | None) -> str:
        if not ind:
            return ""
        parts = []
        if ind["rsi"] <= 30:   parts.append(f"RSI{ind['rsi']:.0f}(売られ過ぎ)")
        elif ind["rsi"] >= 70: parts.append(f"RSI{ind['rsi']:.0f}(買われ過ぎ)")
        else:                   parts.append(f"RSI{ind['rsi']:.0f}")
        if ind["bb_pos"] < 0.2: parts.append("BB下限近傍")
        elif ind["bb_pos"] > 0.8: parts.append("BB上限近傍")
        if ind["hist_chg"] > 0: parts.append("MACD改善")
        elif ind["hist_chg"] < 0: parts.append("MACD悪化")
        return "｜".join(parts) + "。" if parts else ""


# ── yfinance データ取得 ───────────────────────────────────────

def fetch_ohlcv(code: str, days: int = 200) -> dict | None:
    """yfinance から OHLCV を取得して指標計算用に整形する"""
    ticker = f"{code}.T"
    end    = datetime.now()
    start  = end - timedelta(days=days)
    try:
        df = yf.download(ticker, start=start, end=end,
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 80:
            print(f"  [{code}] データ不足 ({len(df) if df is not None else 0}日)")
            return None
        # yfinance >= 0.2.x は MultiIndex 列の場合あり → squeeze で1銘柄列に平坦化
        def _col(c):
            s = df[c]
            if hasattr(s, "squeeze"): s = s.squeeze()
            return s.dropna().tolist()
        closes  = _col("Close")
        highs   = _col("High")
        lows    = _col("Low")
        volumes = _col("Volume")
        return {"closes": closes, "highs": highs,
                "lows": lows, "volumes": volumes}
    except Exception as e:
        print(f"  [{code}] 取得失敗: {e}")
        return None


# ── メイン分析 ────────────────────────────────────────────────

def analyze_portfolio(positions: list) -> list:
    """
    ポジションリストを受け取り、全銘柄を分析して判断付きリストを返す。
    """
    judge  = InvestmentJudge()
    results = []

    print(f"\n[分析] {len(positions)} 銘柄を分析中...")
    for i, pos in enumerate(positions, 1):
        code = pos["code"]
        name = pos["name"]
        print(f"  [{i}/{len(positions)}] {code} {name}", end=" ... ", flush=True)

        data = fetch_ohlcv(code)
        if data:
            ind = _calc_indicators(
                data["closes"], data["highs"], data["lows"], data["volumes"])
        else:
            ind = None

        result = judge.judge(pos, ind)
        results.append(result)
        print(f"{result['action']}")

        if i < len(positions):
            time.sleep(0.3)  # yfinance レート制限対策

    return results


# ── 直接実行テスト ────────────────────────────────────────────

if __name__ == "__main__":
    # スクリーンショットから読み取ったサンプルデータでテスト
    sample_positions = [
        {"code": "1605", "name": "INPEX",        "current_price": 4123, "avg_cost": 4058.00, "pnl_pct": +1.52},
        {"code": "1662", "name": "石油資源開発",  "current_price": 2295, "avg_cost": 2269.70, "pnl_pct": +1.04},
        {"code": "2782", "name": "セリア",        "current_price": 3440, "avg_cost": 3555.00, "pnl_pct": -3.33},
        {"code": "3901", "name": "アゼアス",      "current_price":  633, "avg_cost":  684.00, "pnl_pct": -7.78},
        {"code": "4245", "name": "ダイキアクシス", "current_price":  703, "avg_cost":  739.00, "pnl_pct": -5.13},
        {"code": "4506", "name": "住友ファーマ",  "current_price": 1851, "avg_cost": 2164.50, "pnl_pct": -14.80},
        {"code": "3983", "name": "モリテック",    "current_price":  234, "avg_cost":  232.86, "pnl_pct": -0.17},
        {"code": "9602", "name": "東宝",          "current_price": 1461, "avg_cost": 1465.00, "pnl_pct": -0.32},
        {"code": "9876", "name": "コックス",      "current_price":  238, "avg_cost":  270.00, "pnl_pct": -12.09},
    ]

    results = analyze_portfolio(sample_positions)
    print("\n=== 投資判断サマリー ===")
    for r in results:
        risk = r['risk'].encode('ascii','replace').decode()
        print(f"  {r['stars']} {r['code']} {r['name']:12s}  {r['action']:16s}  "
              f"損益{r['pnl_pct']:+.2f}%  {risk}")
