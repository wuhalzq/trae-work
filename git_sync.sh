#!/bin/bash
# ============================================================
# Git 自动同步脚本
# 在代码改动后自动 commit + push 到 GitHub
#
# 用法：
#   bash /workspace/trae-work/git_sync.sh "提交说明"
#
# 如果不传提交说明，自动生成带时间戳的默认信息
# ============================================================

set -e

REPO_DIR="/workspace/trae-work"
COMMIT_MSG="${1:-auto sync $(date '+%Y-%m-%d %H:%M:%S')}"

# 读取 token
if [ -f /workspace/.github_config ]; then
    source /workspace/.github_config
fi

cd "$REPO_DIR"

# 检查是否有改动
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "无代码改动，跳过同步"
    exit 0
fi

echo "=== Git 自动同步 ==="

# 同步 /workspace 下的脚本回仓库
echo "[1/3] 同步脚本到仓库..."
cp -f /workspace/build_report.py "$REPO_DIR/stock_images/build_report.py" 2>/dev/null && echo "  ✅ build_report.py" || true
cp -f /workspace/theme_discovery.py "$REPO_DIR/stock_images/theme_discovery.py" 2>/dev/null && echo "  ✅ theme_discovery.py" || true
cp -f /workspace/daily_stock_screener.py "$REPO_DIR/stock_images/daily_stock_screener.py" 2>/dev/null && echo "  ✅ daily_stock_screener.py" || true

# Commit
echo "[2/3] 提交代码..."
git add -A
git commit -m "$COMMIT_MSG" 2>&1 || echo "  ⚠️ commit失败（可能无改动）"

# Push
echo "[3/3] 推送到远程..."
if [ -n "$GITHUB_TOKEN" ]; then
    git remote set-url origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
    git push origin main 2>&1
    # 清理 URL 中的 token
    git remote set-url origin "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
    echo "✅ 推送成功"
else
    echo "❌ 无 GITHUB_TOKEN，无法推送"
    echo "   请先执行: export GITHUB_TOKEN='your_token'"
    exit 1
fi
