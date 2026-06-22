#!/bin/bash
# ============================================================
# A股复盘环境初始化脚本
# 每次新会话/定时任务开始时执行
# 
# 用法：
#   export GITHUB_TOKEN="ghp_xxxx"
#   bash /workspace/trae-work/setup.sh
#
# 或直接在任务指令中内嵌执行（见底部示例）
# ============================================================

set -e

GITHUB_USER="wuhalzq"
GITHUB_REPO="trae-work"
REPO_DIR="/workspace/trae-work"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

echo "=== A股复盘环境初始化 ==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

# ---------- 1. Clone 或 Pull ----------
if [ -d "$REPO_DIR/.git" ]; then
    echo "[1/5] 仓库已存在，执行 git pull..."
    cd "$REPO_DIR"
    git remote set-url origin "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
    git pull origin main || echo "  ⚠️ pull失败，继续使用本地版本"
else
    echo "[1/5] 仓库不存在，执行 git clone..."
    cd /workspace
    rm -rf trae-work
    git clone "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git" 2>&1
fi

# ---------- 2. 复制脚本到 /workspace ----------
echo "[2/5] 部署脚本到 /workspace..."
cp -f "$REPO_DIR/stock_images/build_report.py" /workspace/build_report.py 2>/dev/null && echo "  ✅ build_report.py" || echo "  ⚠️ build_report.py 不存在"
cp -f "$REPO_DIR/stock_images/theme_discovery.py" /workspace/theme_discovery.py 2>/dev/null && echo "  ✅ theme_discovery.py" || echo "  ⚠️ theme_discovery.py 不存在"
cp -f "$REPO_DIR/stock_images/daily_stock_screener.py" /workspace/daily_stock_screener.py 2>/dev/null && echo "  ✅ daily_stock_screener.py" || echo "  ⚠️ daily_stock_screener.py 不存在"

# ---------- 3. 配置 git ----------
echo "[3/5] 配置 git..."
cd "$REPO_DIR"
git config user.name "trae-bot"
git config user.email "trae-bot@users.noreply.github.com"
git config pull.rebase false

# ---------- 4. 保存 token ----------
echo "[4/5] 保存配置..."
if [ -n "$GITHUB_TOKEN" ]; then
    cat > /workspace/.github_config << EOF
GITHUB_USER=${GITHUB_USER}
GITHUB_REPO=${GITHUB_REPO}
GITHUB_TOKEN=${GITHUB_TOKEN}
EOF
    echo "  ✅ token 已保存到 /workspace/.github_config"
else
    echo "  ⚠️ 未设置 GITHUB_TOKEN，后续无法 push 代码"
fi

# ---------- 5. 安装依赖 ----------
echo "[5/5] 检查 Python 依赖..."
pip install requests beautifulsoup4 pillow reportlab --break-system-packages -q 2>&1 | tail -1

echo ""
echo "=== 初始化完成 ==="
echo "可用脚本:"
echo "  /workspace/build_report.py        - PDF复盘报告生成+推送"
echo "  /workspace/theme_discovery.py     - 题材发现工具"
echo "  /workspace/daily_stock_screener.py - 股票筛选脚本"
echo "  /workspace/trae-work/setup.sh      - 环境初始化"
echo "  /workspace/trae-work/git_sync.sh   - 代码自动同步"
