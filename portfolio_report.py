# portfolio_report.py — HTMLレポート生成 + メール送信

import os
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_ACTION_COLOR = {
    "即売却（損切）":      "#d32f2f",
    "損切り":              "#e53935",
    "損切り検討":          "#f57c00",
    "一部利確検討":        "#f9a825",
    "保有継続（反発監視）": "#1565c0",
    "保有継続（反発待ち）": "#1976d2",
    "保有継続（上昇継続）": "#2e7d32",
    "保有継続（様子見）":  "#546e7a",
    "保有継続":            "#2e7d32",
    "追加買い候補":        "#1b5e20",
    "様子見":             "#78909c",
}

_ACTION_ICON = {
    "即売却（損切）":      "🚨",
    "損切り":              "⛔",
    "損切り検討":          "⚠️",
    "一部利確検討":        "💰",
    "保有継続（反発監視）": "👁",
    "保有継続（反発待ち）": "⏳",
    "保有継続（上昇継続）": "🚀",
    "保有継続（様子見）":  "⏸",
    "保有継続":            "✅",
    "追加買い候補":        "🎯",
    "様子見":             "⏸",
}


def _pnl_color(pnl_pct: float) -> str:
    if pnl_pct > 0:  return "#c62828"
    if pnl_pct < 0:  return "#1565c0"
    return "#424242"


def _ind_row(ind: dict | None) -> str:
    if not ind:
        return ""
    bb_str = f"{ind['bb_pos']:.2f}"
    return (
        f"<div class='ind-row'>"
        f"<span>RSI: <b>{ind['rsi']:.0f}</b></span>"
        f"<span>BB位置: <b>{bb_str}</b></span>"
        f"<span>K14: <b>{ind['k14']:.0f}</b></span>"
        f"<span>MA乖離: <b>{ind['dev']:+.1f}%</b></span>"
        f"<span>出来高比: <b>{ind['vol_ratio']:.1f}x</b></span>"
        f"<span>5D騰落: <b>{ind['price_change_5d']:+.1f}%</b></span>"
        f"</div>"
    )


def generate_html(results: list, total_pnl_yen: float | None = None,
                  total_pnl_pct: float | None = None) -> str:
    now = datetime.now().strftime("%Y/%m/%d %H:%M")

    # サマリー
    urgent   = [r for r in results if "即売却" in r["action"] or r["action"] == "損切り"]
    caution  = [r for r in results if "損切り検討" in r["action"] or "監視" in r["action"]]
    hold     = [r for r in results if "保有継続" in r["action"]]
    add_buy  = [r for r in results if "追加買い" in r["action"]]

    total_str = ""
    if total_pnl_yen is not None:
        color = _pnl_color(total_pnl_yen)
        sign  = "+" if total_pnl_yen >= 0 else ""
        pct_str = f" ({sign}{total_pnl_pct:.2f}%)" if total_pnl_pct is not None else ""
        total_str = (f"<div class='total-pnl' style='color:{color}'>"
                     f"評価損益合計: {sign}{total_pnl_yen:,.0f}円{pct_str}</div>")

    # カードHTML
    cards = []
    for r in results:
        act    = r["action"]
        color  = _ACTION_COLOR.get(act, "#607d8b")
        icon   = _ACTION_ICON.get(act, "")
        pnl_c  = _pnl_color(r["pnl_pct"])
        sign   = "+" if r["pnl_pct"] >= 0 else ""
        stars  = r["stars"]
        ind_h  = _ind_row(r.get("indicators"))

        cards.append(f"""
<div class="card">
  <div class="card-header" style="border-left: 5px solid {color}">
    <div class="ticker">{r['code']} <span class="name">{r['name']}</span>
      <span class="sector-tag">{r['sector']}</span>
    </div>
    <div class="pnl" style="color:{pnl_c}">{sign}{r['pnl_pct']:.2f}%
      <span class="price-info">現在値 {r['cur']:,.1f}円 / 平均 {r['avg']:,.2f}円</span>
    </div>
  </div>
  <div class="action-row">
    <span class="action-badge" style="background:{color}">{icon} {act}</span>
    <span class="stars">{stars}</span>
    <span class="risk">{r['risk']}</span>
  </div>
  {ind_h}
  <div class="reason">{r['reason']}</div>
</div>""")

    cards_html = "\n".join(cards)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>投資判断レポート {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif;
         background:#f0f2f5; color:#212121; padding:12px; }}
  h1   {{ font-size:18px; margin-bottom:8px; color:#1a237e; }}
  .meta {{ font-size:12px; color:#757575; margin-bottom:16px; }}
  .total-pnl {{ font-size:20px; font-weight:700; margin-bottom:12px; }}
  .summary-bar {{ display:flex; gap:10px; margin-bottom:20px; flex-wrap:wrap; }}
  .sum-chip {{ padding:6px 14px; border-radius:20px; font-size:13px; font-weight:600; color:#fff; }}
  .card {{ background:#fff; border-radius:10px; padding:14px; margin-bottom:12px;
           box-shadow:0 1px 4px rgba(0,0,0,.12); }}
  .card-header {{ display:flex; justify-content:space-between; align-items:flex-start;
                  margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid #e0e0e0; }}
  .ticker {{ font-size:16px; font-weight:700; }}
  .name   {{ font-size:14px; font-weight:400; color:#424242; margin-left:6px; }}
  .sector-tag {{ font-size:11px; background:#e8eaf6; color:#3949ab; border-radius:4px;
                 padding:2px 6px; margin-left:6px; }}
  .pnl    {{ font-size:18px; font-weight:700; text-align:right; }}
  .price-info {{ display:block; font-size:11px; color:#757575; font-weight:400; }}
  .action-row {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap; }}
  .action-badge {{ padding:5px 12px; border-radius:6px; font-size:13px; font-weight:700;
                   color:#fff; }}
  .stars {{ font-size:14px; }}
  .risk  {{ font-size:12px; }}
  .ind-row {{ display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color:#546e7a;
              background:#f5f5f5; padding:6px 10px; border-radius:6px; margin-bottom:8px; }}
  .ind-row span {{ white-space:nowrap; }}
  .reason {{ font-size:13px; line-height:1.6; color:#424242; }}
  @media(max-width:480px) {{
    .card-header {{ flex-direction:column; }}
    .pnl {{ text-align:left; margin-top:6px; }}
  }}
</style>
</head>
<body>
<h1>📊 投資判断レポート</h1>
<div class="meta">生成: {now} ｜ 対象: 信用建玉</div>
{total_str}
<div class="summary-bar">
  <span class="sum-chip" style="background:#d32f2f">🚨 即損切り: {len(urgent)}件</span>
  <span class="sum-chip" style="background:#f57c00">⚠️ 要注意: {len(caution)}件</span>
  <span class="sum-chip" style="background:#2e7d32">✅ 保有継続: {len(hold)}件</span>
  <span class="sum-chip" style="background:#1b5e20">🎯 追加買い: {len(add_buy)}件</span>
</div>
{cards_html}
<div style="font-size:11px;color:#9e9e9e;margin-top:16px;text-align:center;">
  本レポートは参考情報です。投資判断はご自身の責任で行ってください。
</div>
</body>
</html>"""
    return html


def save_html(results: list, output_dir: str,
              total_pnl_yen=None, total_pnl_pct=None) -> str:
    os.makedirs(output_dir, exist_ok=True)
    html    = generate_html(results, total_pnl_yen, total_pnl_pct)
    fname   = f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    fpath   = os.path.join(output_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[レポート] 保存: {fpath}")
    return fpath


def send_report_email(results: list, creds_path: str,
                      total_pnl_yen=None, total_pnl_pct=None):
    """credentials.json を使ってレポートをメール送信する"""
    if not os.path.exists(creds_path):
        print(f"[メール] credentials.json が見つかりません: {creds_path}")
        return False
    with open(creds_path, encoding="utf-8") as f:
        creds = json.load(f)

    html = generate_html(results, total_pnl_yen, total_pnl_pct)
    now  = datetime.now().strftime("%Y/%m/%d %H:%M")

    urgent_n = sum(1 for r in results if "即売却" in r["action"] or r["action"] == "損切り")
    add_n    = sum(1 for r in results if "追加買い" in r["action"])

    msg = MIMEMultipart("alternative")
    recipients = [creds["email"]]
    msg["Subject"] = f"[投資判断] {now}  要損切り{urgent_n}件 / 追加買い候補{add_n}件"
    msg["From"]    = creds["email"]
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))

    app_pw = creds["app_password"].replace(" ", "")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(creds["email"], app_pw)
            s.sendmail(creds["email"], recipients, msg.as_string())
        print(f"[メール] 送信完了 → {creds['email']}")
        return True
    except Exception as e:
        print(f"[メール] 送信失敗: {e}")
        return False
