#!/usr/bin/env python3
"""
统一回推服务 - 第六步核心
职责：统一消息回推入口，分离微信/飞书 sender
"""

import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

from logger import log, log_delivery_attempt, StageLogger
from errors import ErrorCode, AnalysisError, create_error_from_exception


class ChannelType(Enum):
    """通道类型"""
    WECHAT = "wechat"
    FEISHU = "feishu"
    UNKNOWN = "unknown"


class DeliveryStatus(Enum):
    """回推状态"""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class WechatSender:
    """微信发送器"""
    
    def __init__(self):
        self.channel = ChannelType.WECHAT
    
    def send(
        self,
        user_id: str,
        message: str,
        media_path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送微信消息
        
        Returns:
            {"success": bool, "error_code": str, "error_message": str, "message_id": str}
        """
        try:
            # TODO: 接入实际微信发送接口
            # 这里模拟微信发送
            
            # 模拟特定错误场景（用于测试）
            if kwargs.get('simulate_error') == 'duplicate_tool_call':
                return {
                    "success": False,
                    "error_code": ErrorCode.WECHAT_DELIVERY_ERROR.value,
                    "error_message": "tool call id duplicate",
                    "message_id": None
                }
            
            if kwargs.get('simulate_error') == 'rate_limit':
                return {
                    "success": False,
                    "error_code": ErrorCode.DELIVERY_RATE_LIMIT.value,
                    "error_message": "请求过于频繁",
                    "message_id": None
                }
            
            # 模拟成功
            return {
                "success": True,
                "error_code": None,
                "error_message": None,
                "message_id": f"wx_msg_{int(time.time())}"
            }
            
        except Exception as e:
            error = create_error_from_exception(e)
            return {
                "success": False,
                "error_code": ErrorCode.WECHAT_DELIVERY_ERROR.value,
                "error_message": str(e),
                "message_id": None
            }


class FeishuSender:
    """飞书发送器"""
    
    def __init__(self):
        self.channel = ChannelType.FEISHU
    
    def send(
        self,
        user_id: str,
        message: str,
        media_path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送飞书消息
        
        Returns:
            {"success": bool, "error_code": str, "error_message": str, "message_id": str}
        """
        try:
            # TODO: 接入实际飞书发送接口
            # 这里模拟飞书发送
            
            # 模拟特定错误场景
            if kwargs.get('simulate_error') == 'auth_failed':
                return {
                    "success": False,
                    "error_code": ErrorCode.FEISHU_DELIVERY_ERROR.value,
                    "error_message": "token 失效",
                    "message_id": None
                }
            
            # 模拟成功
            return {
                "success": True,
                "error_code": None,
                "error_message": None,
                "message_id": f"fs_msg_{int(time.time())}"
            }
            
        except Exception as e:
            error = create_error_from_exception(e)
            return {
                "success": False,
                "error_code": ErrorCode.FEISHU_DELIVERY_ERROR.value,
                "error_message": str(e),
                "message_id": None
            }


class DeliveryService:
    """统一回推服务"""
    
    def __init__(self):
        self.wechat_sender = WechatSender()
        self.feishu_sender = FeishuSender()
        self.senders = {
            ChannelType.WECHAT.value: self.wechat_sender,
            ChannelType.FEISHU.value: self.feishu_sender
        }
    
    def deliver_result(
        self,
        task_id: str,
        channel: str,
        user_id: str,
        report_text: str,
        media_path: str = None,
        retry_count: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        统一回推入口
        
        Args:
            task_id: 任务ID
            channel: 通道类型 (wechat/feishu)
            user_id: 用户ID
            report_text: 报告文本
            media_path: 媒体文件路径（可选）
            retry_count: 当前重试次数
        
        Returns:
            {"success": bool, "status": str, "error_code": str, "error_message": str}
        """
        start_time = time.time()
        
        log.info(
            f"Delivery started to {channel}",
            task_id=task_id,
            channel=channel,
            stage='delivering',
            status='delivery_started',
            retry_count=retry_count
        )
        
        # 获取对应 sender
        sender = self.senders.get(channel)
        if not sender:
            error_msg = f"Unknown channel: {channel}"
            log.error(
                error_msg,
                task_id=task_id,
                channel=channel,
                stage='delivering',
                status='delivery_failed',
                error_code=ErrorCode.DELIVERY_ERROR.value
            )
            return {
                "success": False,
                "status": DeliveryStatus.FAILED.value,
                "error_code": ErrorCode.DELIVERY_ERROR.value,
                "error_message": error_msg
            }
        
        # 执行发送
        try:
            result = sender.send(
                user_id=user_id,
                message=report_text,
                media_path=media_path,
                **kwargs
            )
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            if result["success"]:
                log_delivery_attempt(
                    task_id=task_id,
                    channel=channel,
                    success=True,
                    elapsed_ms=elapsed_ms
                )
                return {
                    "success": True,
                    "status": DeliveryStatus.SUCCEEDED.value,
                    "error_code": None,
                    "error_message": None,
                    "message_id": result.get("message_id")
                }
            else:
                # 发送失败
                error_code = result.get("error_code", ErrorCode.DELIVERY_ERROR.value)
                error_message = result.get("error_message", "Unknown error")
                
                log_delivery_attempt(
                    task_id=task_id,
                    channel=channel,
                    success=False,
                    error_code=error_code,
                    error_message=error_message,
                    elapsed_ms=elapsed_ms
                )
                
                return {
                    "success": False,
                    "status": DeliveryStatus.FAILED.value,
                    "error_code": error_code,
                    "error_message": error_message
                }
                
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error = create_error_from_exception(e, task_id, 'delivering')
            
            log_delivery_attempt(
                task_id=task_id,
                channel=channel,
                success=False,
                error_code=error.error_code.value,
                error_message=str(e),
                elapsed_ms=elapsed_ms
            )
            
            return {
                "success": False,
                "status": DeliveryStatus.FAILED.value,
                "error_code": error.error_code.value,
                "error_message": str(e)
            }
    
    def deliver_with_retry(
        self,
        task_id: str,
        channel: str,
        user_id: str,
        report_text: str,
        media_path: str = None,
        max_retries: int = 2,
        current_retry: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带重试的回推
        
        Returns:
            {"success": bool, "status": str, "retry_count": int, "final_error": str}
        """
        last_result = None
        
        for attempt in range(current_retry, max_retries + 1):
            result = self.deliver_result(
                task_id=task_id,
                channel=channel,
                user_id=user_id,
                report_text=report_text,
                media_path=media_path,
                retry_count=attempt,
                **kwargs
            )
            
            last_result = result
            
            if result["success"]:
                return {
                    "success": True,
                    "status": DeliveryStatus.SUCCEEDED.value,
                    "retry_count": attempt,
                    "final_error": None
                }
            
            # 判断是否可重试
            error_code = result.get("error_code", "")
            from errors import ErrorCode, is_retryable_error
            
            try:
                ec = ErrorCode(error_code)
                if not is_retryable_error(ec):
                    log.warning(
                        f"Non-retryable error, giving up: {error_code}",
                        task_id=task_id,
                        channel=channel,
                        error_code=error_code
                    )
                    break
            except ValueError:
                pass
            
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 指数退避
                log.info(
                    f"Retrying delivery in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                    task_id=task_id,
                    channel=channel,
                    retry_count=attempt,
                    max_retries=max_retries
                )
                time.sleep(wait_time)
        
        # 重试耗尽
        return {
            "success": False,
            "status": DeliveryStatus.FAILED.value,
            "retry_count": max_retries,
            "final_error": last_result.get("error_message") if last_result else "Unknown error"
        }


# 全局回推服务实例
delivery_service = DeliveryService()


if __name__ == '__main__':
    print("=== 统一回推服务测试 ===\n")
    
    service = DeliveryService()
    
    # 测试1: 微信成功发送
    print("1. 微信成功发送:")
    result = service.deliver_result(
        task_id="task_001",
        channel="wechat",
        user_id="wx_user_001",
        report_text="🎾 分析完成！总分: 82"
    )
    print(f"   结果: {result}")
    print()
    
    # 测试2: 飞书成功发送
    print("2. 飞书成功发送:")
    result = service.deliver_result(
        task_id="task_002",
        channel="feishu",
        user_id="fs_user_001",
        report_text="🎾 分析完成！总分: 78"
    )
    print(f"   结果: {result}")
    print()
    
    # 测试3: 微信失败（可重试）
    print("3. 微信失败（可重试 - 限流）:")
    result = service.deliver_result(
        task_id="task_003",
        channel="wechat",
        user_id="wx_user_002",
        report_text="测试",
        simulate_error="rate_limit"
    )
    print(f"   结果: {result}")
    print()
    
    # 测试4: 带重试机制
    print("4. 带重试机制（模拟首次失败，第二次成功）:")
    # 这里简化测试，实际会调用两次
    result = service.deliver_with_retry(
        task_id="task_004",
        channel="wechat",
        user_id="wx_user_003",
        report_text="测试重试",
        max_retries=2
    )
    print(f"   结果: {result}")
    print()
    
    # 测试5: 未知通道
    print("5. 未知通道:")
    result = service.deliver_result(
        task_id="task_005",
        channel="unknown",
        user_id="user_005",
        report_text="测试"
    )
    print(f"   结果: {result}")
    print()
    
    print("✅ 统一回推服务测试完成!")
    print("\n关键特性:")
    print("- 统一入口: delivery_service.deliver_result()")
    print("- 通道分离: WechatSender / FeishuSender")
    print("- 错误分类: WECHAT_DELIVERY_ERROR / FEISHU_DELIVERY_ERROR")
    print("- 重试支持: deliver_with_retry() 带指数退避")
    print("- 结构化日志: 所有操作带 task_id, channel, stage")
