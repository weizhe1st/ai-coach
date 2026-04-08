#!/usr/bin/env python3
"""
微信消息处理器 - 修复版
核心修复：微信视频立即下载到本地，禁止静默回退到默认测试视频
"""

import os
import sys
import tempfile
import requests
from datetime import datetime

sys.path.insert(0, '/data/apps/xiaolongxia')

from task_status_service import TaskStatusService
from task_repository import init_task_table
from logger import log, log_task_lifecycle
from errors import ErrorCode, AnalysisError

# 初始化任务表
init_task_table()

# 本地视频保存目录
LOCAL_VIDEO_DIR = '/data/apps/xiaolongxia/temp_videos'
os.makedirs(LOCAL_VIDEO_DIR, exist_ok=True)


def download_wechat_video(video_url: str, task_id: str) -> str:
    """
    下载微信视频到本地
    
    Args:
        video_url: 微信临时视频URL
        task_id: 任务ID
        
    Returns:
        本地文件路径
        
    Raises:
        AnalysisError: 下载失败时
    """
    log.info(
        f"Downloading wechat video",
        task_id=task_id,
        stage='video_download',
        source_type='wechat_temp_url'
    )
    
    try:
        # 下载视频
        response = requests.get(video_url, timeout=30, stream=True)
        response.raise_for_status()
        
        # 保存到本地
        local_path = os.path.join(LOCAL_VIDEO_DIR, f"{task_id}.mp4")
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # 验证文件
        if not os.path.exists(local_path):
            raise AnalysisError(
                error_code=ErrorCode.WECHAT_DOWNLOAD_FAILED,
                message="视频保存后文件不存在",
                task_id=task_id,
                stage='video_download'
            )
        
        file_size = os.path.getsize(local_path)
        if file_size == 0:
            os.remove(local_path)
            raise AnalysisError(
                error_code=ErrorCode.WECHAT_DOWNLOAD_FAILED,
                message="下载的视频文件为空",
                task_id=task_id,
                stage='video_download'
            )
        
        log.info(
            f"Video downloaded successfully",
            task_id=task_id,
            stage='video_download',
            local_path=local_path,
            file_size=file_size
        )
        
        return local_path
        
    except requests.exceptions.Timeout:
        raise AnalysisError(
            error_code=ErrorCode.DOWNLOAD_TIMEOUT,
            message="微信视频下载超时",
            task_id=task_id,
            stage='video_download'
        )
    except requests.exceptions.RequestException as e:
        raise AnalysisError(
            error_code=ErrorCode.WECHAT_DOWNLOAD_FAILED,
            message=f"微信视频下载失败: {str(e)}",
            task_id=task_id,
            stage='video_download'
        )
    except Exception as e:
        raise AnalysisError(
            error_code=ErrorCode.WECHAT_DOWNLOAD_FAILED,
            message=f"视频下载异常: {str(e)}",
            task_id=task_id,
            stage='video_download'
        )


def handle_weixin_message(message_data):
    """
    处理微信消息 - 修复版
    核心：微信视频立即下载到本地，Worker 分析本地文件
    
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
            log.error(
                "Video URL is empty",
                user_id=user_id,
                message_id=message_id,
                error_code=ErrorCode.WECHAT_MEDIA_UNAVAILABLE.value
            )
            return "❌ 无法获取视频链接，请重新上传"
        
        # 先创建任务（pending状态）
        try:
            payload = {
                "channel": "wechat",
                "user_id": user_id,
                "message_id": message_id,
                "source_type": "wechat_temp_url",
                "source_url": video_url
            }
            
            result = TaskStatusService.create_video_analysis_task(payload)
            task_id = result['task_id']
            
            log_task_lifecycle(
                task_id=task_id,
                event='created',
                channel='wechat',
                user_id=user_id,
                source_type='wechat_temp_url',
                original_url=video_url[:100] + '...' if len(video_url) > 100 else video_url
            )
            
        except Exception as e:
            log.error(
                f"Failed to create task: {e}",
                user_id=user_id,
                error_code=ErrorCode.SYSTEM_ERROR.value
            )
            return "❌ 任务创建失败，请稍后重试"
        
        # 立即下载微信视频到本地
        try:
            local_path = download_wechat_video(video_url, task_id)
            
            # 更新任务：将 source 改为本地文件
            # Worker 将分析这个本地文件
            TaskStatusService.update_task_source(
                task_id=task_id,
                source_type='local_file',
                source_url=local_path,
                resolved_local_path=local_path
            )
            
            log.info(
                f"Task source updated to local file",
                task_id=task_id,
                local_path=local_path,
                stage='source_resolved'
            )
            
            return f"""🎾 视频已接收并保存！

任务ID：{task_id}
本地路径：{local_path}
状态：已进入分析队列

系统正在分析你的发球视频，请稍后查看结果。
分析通常需要 1-3 分钟，完成后会推送报告。"""
            
        except AnalysisError as e:
            # 下载失败，标记任务失败
            TaskStatusService.mark_failed(
                task_id=task_id,
                error_code=e.error_code.value,
                error_message=e.get_user_message()
            )
            
            log.error(
                f"Video download failed: {e.message}",
                task_id=task_id,
                error_code=e.error_code.value,
                stage='video_download'
            )
            
            return f"""❌ 视频下载失败

任务ID：{task_id}
错误：{e.get_user_message()}

请检查网络后重新上传视频。"""
        
        except Exception as e:
            # 未知异常，标记任务失败
            TaskStatusService.mark_failed(
                task_id=task_id,
                error_code=ErrorCode.SYSTEM_ERROR.value,
                error_message=str(e)
            )
            
            log.error(
                f"Unexpected error during video download: {e}",
                task_id=task_id,
                error_code=ErrorCode.SYSTEM_ERROR.value
            )
            
            return f"""❌ 视频处理失败

任务ID：{task_id}
请稍后重试或联系管理员。"""
    
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
                    resolved_path = status.get('resolved_local_path', 'N/A')
                    return f"""📋 任务状态查询

任务ID：{status['task_id']}
状态：{status['status']}
创建时间：{status['created_at']}
开始时间：{status.get('started_at', '未开始')}
完成时间：{status.get('finished_at', '未完成')}

NTRP等级: {status.get('ntrp_level', '待评估')} | 总分: {status.get('overall_score', '待评分')}

分析文件: {resolved_path}"""
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
        print("用法: python3 weixin_handler_fixed.py --video <视频路径>")
