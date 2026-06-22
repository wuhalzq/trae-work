#!/bin/bash
# A股复盘环境初始化脚本
# 每次新会话执行：
#   export GITHUB_TOKEN="your_token_here"
#   bash /workspace/trae-work/setup.sh
#
# 或者直接在任务指令中设置 GITHUB_TOKEN 环境变量
#
# 功能：clone代码 → 复制脚本到/workspace → 配置git token

set -e

GITHUB_USER="wuhalzq"
GITHUB_REPO="trae-work"
REPO_DIR="/workspace/trae-work"

# Token从环境变量读取，不硬编码
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

echo "=== A股复盘环境初始化 ==="

# 1. 如果已存在则pull，否则clone
if [ -d "$REPO_DIR/.git" ]; then
    echo "[1/4] 仓库已存在，执行 git pull..."
    cd "$REPO_DIR"
    if [ -n "$GITHUB_TOKEN" ]; then
        git remote set-url origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
    fi
    git pull origin main || true
else
    echo "[1/4] 仓库不存在，执行 git clone..."
    cd /workspace
    rm -rf trae-work
    if [ -n "$GITHUB_TOKEN" ]; then
        git clone "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
    else
        git clone "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
    fi
fi

# 2. 复制脚本到 /workspace（确保build_report.py等在/workspace可直接调用）
echo "[2/4] 复制脚本到 /workspace..."
cp -f "$REPO_DIR/stock_images/build_report.py" /workspace/build_report.py 2>/dev/null || echo "  build_report.py 不存在，跳过"
cp -f "$REPO_DIR/stock_images/theme_discovery.py" /workspace/theme_discovery.py 2>/dev/null || echo "  theme_discovery.py 不存在，跳过"

# 3. 配置git用户信息（用于commit）
echo "[3/4] 配置 git 用户信息..."
cd "$REPO_DIR"
git config user.name "trae-bot"
git config user.email "trae-bot@users.noreply.github.com"
# 清理URL中的token，避免泄露
git remote set-url origin "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"

# 4. 保存token到本地配置文件（供后续push使用，此文件不提交到git）
echo "[4/4] 保存 GitHub token 配置..."
if [ -n "$GITHUB_TOKEN" ]; then
    cat > /workspace/.github_config << EOF
GITHUB_USER=${GITHUB_USER}
GITHUB_REPO=${GITHUB_REPO}
GITHUB_TOKEN=${GITHUB_TOKEN}
EOF
    echo "  token 已保存到 /workspace/.github_config"
else
    echo "  ⚠️ 未设置 GITHUB_TOKEN 环境变量，后续push需要手动配置"
    echo "  用法: export GITHUB_TOKEN='your_token' && bash setup.sh"
fi

echo ""
echo "=== 初始化完成 ==="
echo "仓库路径: $REPO_DIR"
echo "脚本路径: /workspace/build_report.py, /workspace/theme_discovery.py"
echo ""
echo "后续如需push代码，执行:"
echo "  source /workspace/.github_config"
echo "  cd /workspace/trae-work"
echo "  git remote set-url origin https://\$GITHUB_USER:\$GITHUB_TOKEN@github.com/\$GITHUB_USER/\$GITHUB_REPO.git"
echo "  git add . && git commit -m 'update' && git push origin main"
