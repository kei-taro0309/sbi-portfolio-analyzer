@echo off
chcp 65001 >nul
echo ================================================
echo  SBI投資判断システム — GitHub自動セットアップ
echo ================================================
echo.

REM ── Step 1: gh auth login ─────────────────────────
echo [1/3] GitHubにログインします（ブラウザが開きます）
echo   ※ GitHubアカウントがない場合は github.com で無料作成してください
echo.
gh auth login --web --git-protocol https
if %ERRORLEVEL% NEQ 0 (
  echo [エラー] ログイン失敗。gh がインストールされているか確認してください。
  pause
  exit /b 1
)

REM ── Step 2: リポジトリ作成 & プッシュ ────────────
echo.
echo [2/3] GitHubにリポジトリを作成してコードをアップロードします...
cd /d "%~dp0"
gh repo create sbi-portfolio-analyzer --public --source=. --remote=origin --push
if %ERRORLEVEL% NEQ 0 (
  echo [エラー] リポジトリ作成に失敗しました。
  pause
  exit /b 1
)

REM ── Step 3: Colabリンクを表示 ─────────────────────
echo.
echo [3/3] 完了！スマートフォン用URLをコピーしてください
echo.
for /f "tokens=*" %%i in ('gh repo view --json nameWithOwner -q .nameWithOwner') do set REPO=%%i
echo ====================================================
echo  Google Colab URL（スマートフォンでブックマーク）:
echo.
echo  https://colab.research.google.com/github/%REPO%/blob/main/SBI_Portfolio_Analyzer.ipynb
echo.
echo ====================================================
echo.
echo このURLをスマートフォンのブラウザで開き、
echo ホーム画面に追加するとアプリのように使えます。
echo.
pause
