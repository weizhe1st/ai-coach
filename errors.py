#!/usr/bin/env python3
"""
统一错误码定义 - 第六步核心
职责：建立系统级错误分类体系，替代随意异常字符串
"""

from enum import Enum
from typing import Dict, Any, Optional


class ErrorCode(Enum):
    """系统统一错误码"""
    
    # 成功
    SUCCESS = "SUCCESS"
    
    # 输入层错误 (1xx)
    INPUT_ERROR = "INPUT_ERROR"                    # 通用输入错误
    INVALID_PARAMS = "INVALID_PARAMS"              # 参数不合法
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"  # 缺少必填字段
    
    # 视频获取层错误 (2xx)
    SOURCE_FETCH_ERROR = "SOURCE_FETCH_ERROR"      # 通用获取错误
    DOWNLOAD_TIMEOUT = "DOWNLOAD_TIMEOUT"          # 下载超时
    DOWNLOAD_NETWORK_ERROR = "DOWNLOAD_NETWORK_ERROR"  # 下载网络错误
    LOCAL_FILE_NOT_FOUND = "LOCAL_FILE_NOT_FOUND"  # 本地文件不存在
    VIDEO_VALIDATION_ERROR = "VIDEO_VALIDATION_ERROR"  # 视频验证失败
    VIDEO_FORMAT_ERROR = "VIDEO_FORMAT_ERROR"      # 视频格式不支持
    VIDEO_TOO_LARGE = "VIDEO_TOO_LARGE"            # 视频过大
    VIDEO_TOO_SMALL = "VIDEO_TOO_SMALL"            # 视频过小/空文件
    WECHAT_DOWNLOAD_FAILED = "WECHAT_DOWNLOAD_FAILED"  # 微信视频下载失败
    WECHAT_MEDIA_UNAVAILABLE = "WECHAT_MEDIA_UNAVAILABLE"  # 微信媒体不可用
    
    # 分析层错误 (3xx)
    ANALYSIS_ERROR = "ANALYSIS_ERROR"              # 通用分析错误
    MODEL_RESPONSE_INVALID = "MODEL_RESPONSE_INVALID"  # 模型返回无效
    MODEL_TIMEOUT = "MODEL_TIMEOUT"                # 模型调用超时
    MODEL_RATE_LIMIT = "MODEL_RATE_LIMIT"          # 模型限流
    MODEL_API_ERROR = "MODEL_API_ERROR"            # 模型API错误
    MEDIAPIPE_ERROR = "MEDIAPIPE_ERROR"            # MediaPipe处理错误
    
    # 标准化层错误 (4xx)
    NORMALIZE_ERROR = "NORMALIZE_ERROR"            # 通用标准化错误
    SCHEMA_VALIDATION_ERROR = "SCHEMA_VALIDATION_ERROR"  # Schema验证失败
    
    # 报告层错误 (5xx)
    REPORT_ERROR = "REPORT_ERROR"                  # 通用报告错误
    REPORT_TEMPLATE_ERROR = "REPORT_TEMPLATE_ERROR"  # 报告模板错误
    
    # 存储层错误 (6xx)
    DB_ERROR = "DB_ERROR"                          # 通用数据库错误
    DB_CONNECTION_ERROR = "DB_CONNECTION_ERROR"    # 数据库连接错误
    DB_WRITE_ERROR = "DB_WRITE_ERROR"              # 数据库写入错误
    
    # 回推层错误 (7xx)
    DELIVERY_ERROR = "DELIVERY_ERROR"              # 通用回推错误
    WECHAT_DELIVERY_ERROR = "WECHAT_DELIVERY_ERROR"  # 微信回推错误
    FEISHU_DELIVERY_ERROR = "FEISHU_DELIVERY_ERROR"  # 飞书回推错误
    DELIVERY_TIMEOUT = "DELIVERY_TIMEOUT"          # 回推超时
    DELIVERY_RATE_LIMIT = "DELIVERY_RATE_LIMIT"    # 回推限流
    
    # 系统层错误 (9xx)
    SYSTEM_ERROR = "SYSTEM_ERROR"                  # 通用系统错误
    UNKNOWN_ERROR = "UNKNOWN_ERROR"                # 未知错误
    CONFIG_ERROR = "CONFIG_ERROR"                  # 配置错误


# 错误码分类：可重试 vs 不可重试
RETRYABLE_ERRORS = {
    # 网络/临时问题可重试
    ErrorCode.DOWNLOAD_TIMEOUT,
    ErrorCode.DOWNLOAD_NETWORK_ERROR,
    ErrorCode.MODEL_TIMEOUT,
    ErrorCode.MODEL_RATE_LIMIT,
    ErrorCode.MODEL_API_ERROR,
    ErrorCode.DB_CONNECTION_ERROR,
    ErrorCode.DELIVERY_TIMEOUT,
    ErrorCode.DELIVERY_RATE_LIMIT,
    ErrorCode.SYSTEM_ERROR,  # 系统错误可尝试重试
}

NON_RETRYABLE_ERRORS = {
    # 输入/逻辑问题不可重试
    ErrorCode.INPUT_ERROR,
    ErrorCode.INVALID_PARAMS,
    ErrorCode.MISSING_REQUIRED_FIELD,
    ErrorCode.LOCAL_FILE_NOT_FOUND,
    ErrorCode.VIDEO_FORMAT_ERROR,
    ErrorCode.VIDEO_TOO_SMALL,
    ErrorCode.CONFIG_ERROR,
}

# 错误码对用户显示文案
USER_FRIENDLY_MESSAGES = {
    ErrorCode.SUCCESS: "分析完成",
    ErrorCode.INPUT_ERROR: "输入参数有误，请检查后重试",
    ErrorCode.INVALID_PARAMS: "请求参数不合法",
    ErrorCode.SOURCE_FETCH_ERROR: "视频获取失败，请检查链接是否有效",
    ErrorCode.DOWNLOAD_TIMEOUT: "视频下载超时，请稍后重试",
    ErrorCode.LOCAL_FILE_NOT_FOUND: "本地视频文件不存在",
    ErrorCode.VIDEO_VALIDATION_ERROR: "视频验证失败，可能格式不支持或文件损坏",
    ErrorCode.VIDEO_TOO_LARGE: "视频文件过大，请压缩后重试",
    ErrorCode.WECHAT_DOWNLOAD_FAILED: "微信视频下载失败，请重新上传",
    ErrorCode.WECHAT_MEDIA_UNAVAILABLE: "微信视频链接失效，请重新上传",
    ErrorCode.ANALYSIS_ERROR: "视频分析失败，请稍后重试",
    ErrorCode.MODEL_TIMEOUT: "分析服务超时，请稍后重试",
    ErrorCode.MODEL_RATE_LIMIT: "分析服务繁忙，请稍后重试",
    ErrorCode.REPORT_ERROR: "报告生成失败",
    ErrorCode.DB_ERROR: "数据保存失败",
    ErrorCode.DELIVERY_ERROR: "结果回传失败，请稍后重试",
    ErrorCode.WECHAT_DELIVERY_ERROR: "微信消息发送失败",
    ErrorCode.FEISHU_DELIVERY_ERROR: "飞书消息发送失败",
    ErrorCode.SYSTEM_ERROR: "系统暂时异常，请稍后重试",
    ErrorCode.UNKNOWN_ERROR: "发生未知错误，请联系管理员",
}


class AnalysisError(Exception):
    """统一分析异常"""
    
    def __init__(
        self,
        error_code: ErrorCode,
        message: str = None,
        task_id: str = None,
        stage: str = None,
        details: Dict[str, Any] = None,
        retryable: bool = None
    ):
        self.error_code = error_code
        self.message = message or error_code.value
        self.task_id = task_id
        self.stage = stage
        self.details = details or {}
        
        # 自动判断可重试性
        if retryable is None:
            self.retryable = error_code in RETRYABLE_ERRORS
        else:
            self.retryable = retryable
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于日志和存储"""
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "task_id": self.task_id,
            "stage": self.stage,
            "retryable": self.retryable,
            "details": self.details
        }
    
    def get_user_message(self) -> str:
        """获取对用户友好的错误信息"""
        return USER_FRIENDLY_MESSAGES.get(self.error_code, self.message)


def is_retryable_error(error_code: ErrorCode) -> bool:
    """判断错误是否可重试"""
    return error_code in RETRYABLE_ERRORS


def create_error_from_exception(
    exc: Exception,
    task_id: str = None,
    stage: str = None
) -> AnalysisError:
    """从异常创建统一错误"""
    
    # 已经是 AnalysisError 直接返回
    if isinstance(exc, AnalysisError):
        return exc
    
    # 根据异常类型映射错误码
    error_code = ErrorCode.UNKNOWN_ERROR
    message = str(exc)
    
    exc_type = type(exc).__name__
    
    if exc_type in ('TimeoutError', 'asyncio.TimeoutError'):
        error_code = ErrorCode.DOWNLOAD_TIMEOUT if stage == 'downloading' else ErrorCode.MODEL_TIMEOUT
    elif exc_type in ('ConnectionError', 'NetworkError'):
        error_code = ErrorCode.DOWNLOAD_NETWORK_ERROR
    elif exc_type == 'FileNotFoundError':
        error_code = ErrorCode.LOCAL_FILE_NOT_FOUND
    elif exc_type == 'ValueError':
        error_code = ErrorCode.INPUT_ERROR
    elif exc_type == 'KeyError':
        error_code = ErrorCode.SCHEMA_VALIDATION_ERROR
    
    return AnalysisError(
        error_code=error_code,
        message=message,
        task_id=task_id,
        stage=stage
    )


if __name__ == '__main__':
    print("=== 错误码系统测试 ===\n")
    
    # 测试错误创建
    err = AnalysisError(
        error_code=ErrorCode.DOWNLOAD_TIMEOUT,
        message="下载超时，等待30秒",
        task_id="test_task_001",
        stage="downloading",
        details={"url": "http://example.com/video.mp4", "timeout": 30}
    )
    
    print(f"错误码: {err.error_code.value}")
    print(f"消息: {err.message}")
    print(f"task_id: {err.task_id}")
    print(f"stage: {err.stage}")
    print(f"可重试: {err.retryable}")
    print(f"用户文案: {err.get_user_message()}")
    print(f"字典: {err.to_dict()}")
    print()
    
    # 测试可重试判断
    print("可重试错误测试:")
    for code in [ErrorCode.DOWNLOAD_TIMEOUT, ErrorCode.INPUT_ERROR, ErrorCode.MODEL_RATE_LIMIT]:
        print(f"  {code.value}: {'可重试' if is_retryable_error(code) else '不可重试'}")
    print()
    
    # 测试从异常创建
    print("从异常创建错误:")
    try:
        raise TimeoutError("连接超时")
    except Exception as e:
        err2 = create_error_from_exception(e, task_id="test_002", stage="downloading")
        print(f"  原始异常: {type(e).__name__}")
        print(f"  转换后: {err2.error_code.value}, 可重试: {err2.retryable}")
    
    print("\n✅ 错误码系统测试完成!")
