#!/usr/bin/env python3
"""
任务服务 - 兼容层
为了保持兼容性，保留原有接口，内部调用 TaskStatusService
"""

from typing import Dict, Any, Optional
from task_status_service import TaskStatusService
from task_repository import init_task_table


def create_video_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    创建视频分析任务（兼容接口）
    
    Args:
        payload: 任务数据
            - channel: 渠道
            - user_id: 用户ID
            - message_id: 消息ID
            - source_type: 来源类型
            - source_url: 视频来源URL
    
    Returns:
        包含 task_id 和 status 的字典
    """
    return TaskStatusService.create_video_analysis_task(payload)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务状态（兼容接口）"""
    return TaskStatusService.get_task_status(task_id)


def process_video_task(task_id: str):
    """
    处理视频任务（已废弃，由 Worker 处理）
    保留此函数用于兼容性，但实际处理已移至 task_worker.py
    """
    print(f"[TaskService] process_video_task 已废弃，任务 {task_id} 应由 Worker 处理")
    # 实际处理逻辑已移至 VideoAnalysisWorker


if __name__ == '__main__':
    # 初始化
    init_task_table()
    
    # 测试创建任务
    test_payload = {
        "channel": "wechat",
        "user_id": "test_user_001",
        "message_id": "msg_123",
        "source_type": "wechat_temp_url",
        "source_url": "https://example.com/video.mp4"
    }
    
    result = create_video_analysis_task(test_payload)
    print(f"创建任务结果: {result}")
