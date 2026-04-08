#!/usr/bin/env python3
"""
任务状态服务 - 统一的状态流转入口
"""

from typing import Dict, Any, Optional
from task_repository import (
    create_task, get_task,
    mark_task_downloading, mark_task_analyzing,
    mark_task_generating_report, mark_task_completed,
    mark_task_failed, increment_retry_count,
    fetch_next_pending_task, list_tasks_by_status,
    get_task_stats
)


class TaskStatusService:
    """任务状态服务类"""
    
    @staticmethod
    def create_video_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建视频分析任务
        
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
        channel = payload.get('channel', 'unknown')
        user_id = payload.get('user_id')
        message_id = payload.get('message_id', '')
        source_type = payload.get('source_type', 'unknown')
        source_url = payload.get('source_url')
        
        if not user_id:
            raise ValueError("user_id 不能为空")
        
        if not source_url:
            raise ValueError("source_url 不能为空")
        
        task = create_task(
            channel=channel,
            user_id=user_id,
            message_id=message_id,
            source_type=source_type,
            source_url=source_url
        )
        
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "message": "任务已创建，正在进入分析队列"
        }
    
    @staticmethod
    def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task = get_task(task_id)
        if not task:
            return None
        
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "channel": task["channel"],
            "user_id": task["user_id"],
            "retry_count": task.get("retry_count", 0),
            "max_retries": task.get("max_retries", 3),
            "worker_id": task.get("worker_id"),
            "error_code": task.get("error_code"),
            "error_message": task.get("error_message"),
            "created_at": task["created_at"],
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "updated_at": task.get("updated_at"),
            "ntrp_level": task.get("ntrp_level"),
            "overall_score": task.get("overall_score")
        }
    
    @staticmethod
    def mark_downloading(task_id: str, worker_id: str):
        """标记任务为下载中"""
        mark_task_downloading(task_id, worker_id)
    
    @staticmethod
    def mark_analyzing(task_id: str):
        """标记任务为分析中"""
        mark_task_analyzing(task_id)
    
    @staticmethod
    def mark_generating_report(task_id: str):
        """标记任务为生成报告中"""
        mark_task_generating_report(task_id)
    
    @staticmethod
    def mark_completed(task_id: str, result_payload: Dict[str, Any]):
        """
        标记任务为已完成
        
        Args:
            result_payload: 结果数据
                - raw_result: 原始分析结果
                - report_text: 报告文本
                - ntrp_level: 评估等级
                - overall_score: 总分
        """
        mark_task_completed(task_id, result_payload)
    
    @staticmethod
    def mark_failed(task_id: str, error_code: str, error_message: str):
        """
        标记任务为失败
        
        Args:
            error_code: 错误码，如 'DOWNLOAD_FAILED', 'ANALYSIS_FAILED'
            error_message: 错误描述
        """
        mark_task_failed(task_id, error_code, error_message)
    
    @staticmethod
    def update_task_source(task_id: str, source_type: str, source_url: str, resolved_local_path: str = None):
        """
        更新任务的视频源信息（修复版：微信视频下载后更新为本地文件）
        
        Args:
            task_id: 任务ID
            source_type: 新的来源类型（如 'local_file'）
            source_url: 新的来源URL（本地文件路径）
            resolved_local_path: 解析后的本地文件路径
        """
        from task_repository import update_task_source
        update_task_source(task_id, source_type, source_url, resolved_local_path)
    
    @staticmethod
    def retry_task(task_id: str) -> bool:
        """
        重试任务
        
        Returns:
            True 表示可以重试，False 表示已超过最大重试次数
        """
        task = get_task(task_id)
        if not task:
            return False
        
        retry_count = increment_retry_count(task_id)
        max_retries = task.get('max_retries', 3)
        
        if retry_count >= max_retries:
            # 超过最大重试次数，标记为失败
            mark_task_failed(task_id, 'MAX_RETRIES_EXCEEDED', 
                           f'超过最大重试次数 ({max_retries})')
            return False
        
        return True
    
    @staticmethod
    def fetch_pending_task(worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Worker 领取待处理任务
        
        Args:
            worker_id: Worker 标识
        
        Returns:
            任务字典，如果没有则返回 None
        """
        return fetch_next_pending_task(worker_id)
    
    @staticmethod
    def list_pending_tasks(limit: int = 10) -> list:
        """列出待处理任务"""
        return list_tasks_by_status('pending', limit)
    
    @staticmethod
    def list_failed_tasks(limit: int = 10) -> list:
        """列出失败任务"""
        return list_tasks_by_status('failed', limit)
    
    @staticmethod
    def get_stats() -> Dict[str, int]:
        """获取任务统计"""
        return get_task_stats()


# 便捷函数接口
def create_video_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """创建视频分析任务"""
    return TaskStatusService.create_video_analysis_task(payload)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务状态"""
    return TaskStatusService.get_task_status(task_id)


if __name__ == '__main__':
    # 测试
    from task_repository import init_task_table
    init_task_table()
    
    # 创建测试任务
    test_payload = {
        "channel": "wechat",
        "user_id": "test_user_001",
        "message_id": "msg_123",
        "source_type": "wechat_temp_url",
        "source_url": "https://example.com/video.mp4"
    }
    
    result = create_video_analysis_task(test_payload)
    print(f"创建任务: {result}")
    
    # 查询状态
    task_id = result['task_id']
    status = get_task_status(task_id)
    print(f"任务状态: {status}")
