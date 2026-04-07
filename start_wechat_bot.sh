#!/bin/bash
# 微信机器人启动脚本

cd /data/apps/xiaolongxia

# 加载环境变量
export MOONSHOT_API_KEY=sk-LsZC9HAarYmH6oH4EkOzCEhIIUZ02yvsU6J7xr1u26iifksq
export COS_SECRET_ID=AKIDaHuZDoEKB5qOipqgJkx2uZ1HLPFvXxBC
export COS_SECRET_KEY=sZ3KOG5nIcUaifjjbIwhIgqqfKpAKJ6r
export COS_BUCKET=tennis-ai-1411340868
export COS_REGION=ap-shanghai
export WEBHOOK_PORT=5003
export CALLBACK_SERVICE_URL=http://122.152.207.136:5003/wechat/video
export TASK_STATUS_URL=http://122.152.207.136:5003/task/status

# 启动
exec python3 wechat_video_bot.py
