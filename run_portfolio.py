# run_portfolio.py — 投資判断システム メインランナー
# 使い方:
#   python run_portfolio.py --image <SBIスクリーンショット.jpg>
#   python run_portfolio.py --manual
#   python run_portfolio.py --image <path> --email

import argparse
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    parser = argparse.ArgumentParser(description="SBI証券ポートフォリオ投資判断システム")
    parser.add_argument("--image",  type=str, help="SBIスクリーンショット画像パス")
    parser.add_argument("--manual", action="store_true", help="手動入力モード")
    parser.add_argument("--email",  action="store_true", help="結果をGmailで送信")
    parser.add_argument("--output", type=str, default=os.path.join(_DIR, "レポート"),
                        help="HTMLレポート保存先フォルダ")
    args = parser.parse_args()

    if not args.image and not args.manual:
        parser.print_help()
        sys.exit(1)

    print("=" * 55)
    print("  SBI証券ポートフォリオ 投資判断システム")
    print("=" * 55)

    # ── Step 1: ポジション取得 ────────────────────────────────
    from portfolio_ocr      import SBIPortfolioOCR
    from portfolio_analyzer import analyze_portfolio
    from portfolio_report   import save_html, send_report_email

    ocr = SBIPortfolioOCR()

    if args.manual:
        positions = ocr._manual_input()
    else:
        print(f"\n[OCR] 画像解析: {args.image}")
        positions = ocr.parse_screenshot(args.image)

    if not positions:
        print("[エラー] ポジションが取得できませんでした。--manual で手動入力してください。")
        sys.exit(1)

    print(f"\n[取得] {len(positions)} ポジション:")
    for p in positions:
        sign = "+" if p["pnl_pct"] >= 0 else ""
        print(f"  {p['code']} {p['name']:12s}  "
              f"現在値{p['current_price']:>8,.0f}円  "
              f"平均{p['avg_cost']:>9,.2f}円  "
              f"損益率{sign}{p['pnl_pct']:.2f}%")

    # ── Step 2: 分析 ──────────────────────────────────────────
    results = analyze_portfolio(positions)

    # ── Step 3: レポート生成 ──────────────────────────────────
    print("\n" + "=" * 55)
    print("  投資判断サマリー")
    print("=" * 55)

    priority_order = {
        "即売却（損切）": 0, "損切り": 1, "損切り検討": 2,
        "一部利確検討": 3,
        "保有継続（反発監視）": 4, "保有継続（反発待ち）": 5,
        "追加買い候補": 6,
        "保有継続（上昇継続）": 7, "保有継続": 8, "保有継続（様子見）": 9,
        "様子見": 10,
    }
    sorted_results = sorted(results,
        key=lambda r: priority_order.get(r["action"], 99))

    for r in sorted_results:
        sign = "+" if r["pnl_pct"] >= 0 else ""
        print(f"  {r['stars']}  {r['code']} {r['name']:10s}  "
              f"[{r['action']:16s}]  {sign}{r['pnl_pct']:.2f}%  {r['risk']}")

    # HTMLレポート保存
    report_path = save_html(sorted_results, args.output)
    print(f"\nブラウザで開く: {report_path}")

    # メール送信
    if args.email:
        creds_path = os.path.join(os.path.dirname(_DIR), "credentials.json")
        if not os.path.exists(creds_path):
            creds_path = os.path.join(_DIR, "..", "credentials.json")
        send_report_email(sorted_results, creds_path)

    print("\n完了。")


if __name__ == "__main__":
    main()
