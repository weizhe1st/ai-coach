# 明早待办

## 必做
1. 去阿里云生成新的 DashScope API Key
2. export DASHSCOPE_API_KEY="新key"
3. echo "DASHSCOPE_API_KEY=新key" >> /data/apps/xiaolongxia/.env
4. 重启 webhook 服务
5. 发测试视频确认 Qwen-VL 生效

## 确认点
- 日志里出现 dashscope 字样 = Qwen 生效
- 分析速度比 Kimi 快 = 切换成功
- 报告质量对比 Kimi 有提升

## 当前系统状态
- Webhook 服务：端口 5003
- Auto Monitor：30秒间隔
- 模型配置：core.py 已改为 qwen-vl-max，等 Key 配置
- 知识库：169条（Yellow57/杨超71/灵犀41）
- 样本库：32条黄金标准样本
