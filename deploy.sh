#!/bin/bash
# 部署微信视频分析服务

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🎾 部署网球发球分析服务..."

# 检查环境变量
if [ -z "$MOONSHOT_API_KEY" ]; then
    echo "❌ 错误: 请设置 MOONSHOT_API_KEY 环境变量"
    exit 1
fi

# 安装依赖
echo "📦 安装依赖..."
pip install -q openai opencv-python numpy requests

# 创建必要目录
mkdir -p /data/db
mkdir -p /data/tmp/analysis_frames
mkdir -p /data/apps/xiaolongxia

# 复制代码（使用相对路径）
echo "📁 复制代码文件..."
cp "${SCRIPT_DIR}/vision_analysis_worker.py" /data/apps/xiaolongxia/
cp "${SCRIPT_DIR}/weixin_video_service.py" /data/apps/xiaolongxia/
cp "${SCRIPT_DIR}/weixin_handler.py" /data/apps/xiaolongxia/
cp "${SCRIPT_DIR}/core.py" /data/apps/xiaolongxia/
cp "${SCRIPT_DIR}/deploy.sh" /data/apps/xiaolongxia/

# 设置权限
chmod +x /data/apps/xiaolongxia/*.py

echo "✅ 部署完成！"
echo ""
echo "📋 文件位置:"
echo "  - 主分析服务: /data/apps/xiaolongxia/vision_analysis_worker.py"
echo "  - 微信处理器: /data/apps/xiaolongxia/weixin_handler.py"
echo "  - 共享模块: /data/apps/xiaolongxia/core.py"
echo "  - 数据库: /data/db/xiaolongxia_learning.db"
echo ""
echo "🚀 使用方法:"
echo "  python3 /data/apps/xiaolongxia/weixin_handler.py --video <视频路径>"
