#!/usr/bin/env python3
"""
统一日志工具 - 第六步核心
职责：提供结构化日志输出，统一字段规范
"""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # 结构化日志自己控制格式
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger('xiaolongxia')


class StructuredLog:
    """结构化日志"""
    
    # 标准字段
    STANDARD_FIELDS = [
        'timestamp',
        'level',
        'task_id',
        'channel',
        'user_id',
        'session_id',
        'source_type',
        'status',
        'stage',
        'error_code',
        'message',
        'elapsed_ms',
        'retry_count',
        'details'
    ]
    
    @staticmethod
    def _build_log_record(
        level: str,
        message: str,
        task_id: str = None,
        channel: str = None,
        user_id: str = None,
        session_id: str = None,
        source_type: str = None,
        status: str = None,
        stage: str = None,
        error_code: str = None,
        elapsed_ms: int = None,
        retry_count: int = None,
        worker_id: str = None,
        details: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """构建标准日志记录"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        }
        
        # 添加可选字段（只添加非None的）
        if task_id:
            record['task_id'] = task_id
        if channel:
            record['channel'] = channel
        if user_id:
            record['user_id'] = user_id
        if session_id:
            record['session_id'] = session_id
        if source_type:
            record['source_type'] = source_type
        if status:
            record['status'] = status
        if stage:
            record['stage'] = stage
        if error_code:
            record['error_code'] = error_code
        if elapsed_ms is not None:
            record['elapsed_ms'] = elapsed_ms
        if retry_count is not None:
            record['retry_count'] = retry_count
        if worker_id:
            record['worker_id'] = worker_id
        if details:
            record['details'] = details
        
        # 添加其他额外字段
        for key, value in kwargs.items():
            if value is not None and key not in record:
                record[key] = value
        
        return record
    
    @classmethod
    def info(cls, message: str, **kwargs):
        """INFO级别日志"""
        record = cls._build_log_record('INFO', message, **kwargs)
        logger.info(json.dumps(record, ensure_ascii=False))
    
    @classmethod
    def warning(cls, message: str, **kwargs):
        """WARNING级别日志"""
        record = cls._build_log_record('WARNING', message, **kwargs)
        logger.warning(json.dumps(record, ensure_ascii=False))
    
    @classmethod
    def error(cls, message: str, **kwargs):
        """ERROR级别日志"""
        record = cls._build_log_record('ERROR', message, **kwargs)
        logger.error(json.dumps(record, ensure_ascii=False))
    
    @classmethod
    def debug(cls, message: str, **kwargs):
        """DEBUG级别日志"""
        record = cls._build_log_record('DEBUG', message, **kwargs)
        logger.debug(json.dumps(record, ensure_ascii=False))


# 便捷函数
log = StructuredLog


class StageLogger:
    """阶段日志记录器 - 自动记录阶段开始和结束"""
    
    def __init__(
        self,
        task_id: str,
        stage: str,
        channel: str = None,
        user_id: str = None
    ):
        self.task_id = task_id
        self.stage = stage
        self.channel = channel
        self.user_id = user_id
        self.start_time = None
    
    def __enter__(self):
        """进入阶段"""
        self.start_time = datetime.now()
        log.info(
            f"Stage started: {self.stage}",
            task_id=self.task_id,
            stage=self.stage,
            channel=self.channel,
            user_id=self.user_id,
            status='stage_started'
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出阶段"""
        elapsed = int((datetime.now() - self.start_time).total_seconds() * 1000)
        
        if exc_val:
            # 阶段异常退出
            from errors import AnalysisError, create_error_from_exception
            
            if isinstance(exc_val, AnalysisError):
                error_code = exc_val.error_code.value
                error_msg = exc_val.message
            else:
                error = create_error_from_exception(exc_val, self.task_id, self.stage)
                error_code = error.error_code.value
                error_msg = error.message
            
            log.error(
                f"Stage failed: {self.stage}",
                task_id=self.task_id,
                stage=self.stage,
                channel=self.channel,
                user_id=self.user_id,
                status='stage_failed',
                error_code=error_code,
                elapsed_ms=elapsed,
                details={'error': error_msg}
            )
        else:
            # 阶段正常完成
            log.info(
                f"Stage completed: {self.stage}",
                task_id=self.task_id,
                stage=self.stage,
                channel=self.channel,
                user_id=self.user_id,
                status='stage_completed',
                elapsed_ms=elapsed
            )
    
    def log_progress(self, message: str, **kwargs):
        """记录阶段内进度"""
        log.info(
            message,
            task_id=self.task_id,
            stage=self.stage,
            channel=self.channel,
            user_id=self.user_id,
            status='stage_progress',
            **kwargs
        )


def log_task_lifecycle(
    task_id: str,
    event: str,  # created, fetched, started, completed, failed, retrying
    channel: str = None,
    user_id: str = None,
    **kwargs
):
    """记录任务生命周期事件"""
    log.info(
        f"Task {event}: {task_id}",
        task_id=task_id,
        channel=channel,
        user_id=user_id,
        status=event,
        **kwargs
    )


def log_delivery_attempt(
    task_id: str,
    channel: str,
    success: bool,
    error_code: str = None,
    error_message: str = None,
    elapsed_ms: int = None
):
    """记录回推尝试"""
    if success:
        log.info(
            f"Delivery succeeded to {channel}",
            task_id=task_id,
            channel=channel,
            stage='delivering',
            status='delivery_succeeded',
            elapsed_ms=elapsed_ms
        )
    else:
        log.error(
            f"Delivery failed to {channel}",
            task_id=task_id,
            channel=channel,
            stage='delivering',
            status='delivery_failed',
            error_code=error_code,
            elapsed_ms=elapsed_ms,
            details={'error': error_message}
        )


if __name__ == '__main__':
    print("=== 结构化日志测试 ===\n")
    
    # 测试基础日志
    print("1. 基础日志:")
    log.info("测试信息日志", task_id="task_001", channel="wechat", stage="downloading")
    log.error("测试错误日志", task_id="task_001", error_code="DOWNLOAD_TIMEOUT", stage="downloading")
    print()
    
    # 测试阶段日志
    print("2. 阶段日志（正常完成）:")
    with StageLogger(task_id="task_002", stage="analyzing", channel="feishu"):
        log.info("分析进行中...", task_id="task_002", stage="analyzing")
    print()
    
    # 测试阶段日志（异常）
    print("3. 阶段日志（异常退出）:")
    try:
        with StageLogger(task_id="task_003", stage="downloading", channel="wechat"):
            raise TimeoutError("连接超时")
    except:
        pass
    print()
    
    # 测试任务生命周期
    print("4. 任务生命周期:")
    log_task_lifecycle("task_004", "created", channel="wechat", user_id="user_001")
    log_task_lifecycle("task_004", "fetched", channel="wechat", worker_id="worker_001")
    log_task_lifecycle("task_004", "completed", channel="wechat", overall_score=78)
    print()
    
    # 测试回推日志
    print("5. 回推日志:")
    log_delivery_attempt("task_005", "wechat", True, elapsed_ms=500)
    log_delivery_attempt("task_005", "feishu", False, "FEISHU_DELIVERY_ERROR", "发送失败", 1000)
    print()
    
    print("✅ 结构化日志测试完成!")
    print("\n日志格式说明:")
    print("- 所有日志均为JSON格式，便于解析和检索")
    print("- 关键字段: task_id, channel, stage, status, error_code, elapsed_ms")
    print("- 可通过 task_id 追踪完整链路")
    print("- 可通过 channel 区分微信/飞书")
    print("- 可通过 stage 定位具体阶段")
