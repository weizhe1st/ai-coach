#!/usr/bin/env python3
"""
微信消息处理器 - 异步版本
只负责任务创建，不执行分析
"""

import sys
sys.path.insert(0, '/data/apps/xiaolongxia')

from task_status_service import TaskStatusService
from task_repository import init_task_table

# 初始化任务表
init_task_table()


def handle_weixin_message(message_data):
    """
    处理微信消息 - 异步版本
    只创建任务，不执行分析
    
    Args:
        message_data: 微信消息数据
        
    Returns:
        str: 回复消息
    """
    msg_type = message_data.get('MsgType', '')
    user_id = message_data.get('FromUserName', '')
    message_id = message_data.get('MsgId', '')
    
    # 处理视频消息
    if msg_type == 'video':
        video_url = message_data.get('VideoUrl', '')
        
        if not video_url:
            return "❌ 无法获取视频，请重新上传"
        
        try:
            # 创建任务
            payload = {
                "channel": "wechat",
                "user_id": user_id,
                "message_id": message_id,
                "source_type": "wechat_temp_url",
                "source_url": video_url
            }
            
            result = TaskStatusService.create_video_analysis_task(payload)
            task_id = result['task_id']
            
            print(f"[WeixinHandler] 任务已创建: {task_id}, 用户: {user_id}")
            
            # 立即返回受理消息
            return f"""🎾 视频已接收！

任务ID：{task_id}
状态：正在进入分析队列

系统正在分析你的发球视频，请稍后查看结果。
分析通常需要 1-3 分钟，完成后会推送报告。"""
            
        except Exception as e:
            print(f"[WeixinHandler] 创建任务失败: {e}")
            return f"❌ 任务创建失败，请稍后重试"
    
    # 处理文本消息
    elif msg_type == 'text':
        content = message_data.get('Content', '').strip()
        
        if content in ['帮助', 'help', '?']:
            return """🎾 网球发球分析助手

发送视频给我，我将为你分析发球技术！

📸 拍摄建议：
• 侧面或背面角度
• 光线充足
• 包含完整发球动作
• 时长5-60秒

📊 分析内容：
• NTRP等级评估
• 五阶段技术分析
• 个性化训练建议

开始上传你的发球视频吧！"""
        
        # 查询任务状态
        if content.startswith('查询'):
            task_id = content.replace('查询', '').strip()
            if task_id:
                status = TaskStatusService.get_task_status(task_id)
                if status:
                    return f"""📋 任务状态查询

任务ID：{status['task_id']}
状态：{status['status']}
创建时间：{status['created_at']}
开始时间：{status.get('started_at', '未开始')}
完成时间：{status.get('finished_at', '未完成')}

NTRP等级: {status.get('ntrp_level', '待评估')} | 总分: {status.get('overall_score', '待评分')}"""
                else:
                    return "❌ 任务不存在"
        
        return "请上传你的网球发球视频，我将为你分析技术动作！"
    
    # 其他消息类型
    else:
        return "请上传视频文件，目前仅支持视频分析"


# 命令行测试入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', help='测试视频路径')
    parser.add_argument('--user-id', default='test_user', help='用户ID')
    
    args = parser.parse_args()
    
    if args.video:
        # 模拟微信消息
        message_data = {
            'MsgType': 'video',
            'FromUserName': args.user_id,
            'MsgId': 'test_msg_001',
            'VideoUrl': f'file://{args.video}'
        }
        
        result = handle_weixin_message(message_data)
        print(result)
    else:
        print("用法: python3 weixin_handler.py --video <视频路径>")
