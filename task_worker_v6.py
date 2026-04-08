#!/usr/bin/env python3
"""
任务 Worker - 第六步改造版
使用统一日志、错误码、回推服务
"""

import os
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, '/data/apps/xiaolongxia')

from task_status_service import TaskStatusService
from task_repository import init_task_table
from video_fetcher import fetch_video_to_local, cleanup_fetched_video
from analysis_normalizer import normalize_analysis_result
from logger import log, log_task_lifecycle, StageLogger
from errors import ErrorCode, AnalysisError, create_error_from_exception, is_retryable_error
from delivery_service import delivery_service, DeliveryStatus


class VideoAnalysisWorker:
    """视频分析 Worker（第六步改造版）"""
    
    # 任务阶段定义
    STAGE_PENDING = "pending"
    STAGE_DOWNLOADING = "downloading"
    STAGE_ANALYZING = "analyzing"
    STAGE_NORMALIZING = "normalizing"
    STAGE_GENERATING_REPORT = "generating_report"
    STAGE_SAVING_RESULTS = "saving_results"
    STAGE_DELIVERING = "delivering"
    STAGE_COMPLETED = "completed"
    STAGE_FAILED = "failed"
    STAGE_RETRYING = "retrying"
    
    def __init__(self, worker_id: str = None, poll_interval: int = 5, max_retries: int = 2):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.running = False
        
        if not os.environ.get('MOONSHOT_API_KEY'):
            raise ValueError("MOONSHOT_API_KEY 环境变量未设置")
        
        log.info(
            "Worker initialized",
            worker_id=self.worker_id,
            poll_interval=poll_interval,
            max_retries=max_retries,
            stage='worker_init'
        )
    
    def start(self):
        """启动 Worker"""
        self.running = True
        log.info(
            "Worker started",
            worker_id=self.worker_id,
            stage='worker_start'
        )
        
        while self.running:
            try:
                task_processed = self.process_one_task()
                if not task_processed:
                    time.sleep(self.poll_interval)
            except Exception as e:
                error = create_error_from_exception(e, stage='worker_loop')
                log.error(
                    "Worker processing error",
                    worker_id=self.worker_id,
                    error_code=error.error_code.value,
                    error_message=str(e),
                    stage='worker_loop'
                )
                time.sleep(self.poll_interval)
        
        log.info(
            "Worker stopped",
            worker_id=self.worker_id,
            stage='worker_stop'
        )
    
    def stop(self):
        """停止 Worker"""
        self.running = False
        log.info(
            "Worker stopping...",
            worker_id=self.worker_id,
            stage='worker_stop'
        )
    
    def process_one_task(self) -> bool:
        """处理一个任务（第六步：完整阶段追踪）"""
        # 1. 领取任务
        task = TaskStatusService.fetch_pending_task(self.worker_id)
        if not task:
            return False
        
        task_id = task['task_id']
        channel = task.get('channel', 'unknown')
        user_id = task.get('user_id', 'unknown')
        
        log_task_lifecycle(
            task_id=task_id,
            event='fetched',
            channel=channel,
            user_id=user_id,
            worker_id=self.worker_id
        )
        
        local_video_path = None
        raw_result = None
        normalized_result = None
        
        try:
            # 2. 视频输入层处理
            with StageLogger(task_id, self.STAGE_DOWNLOADING, channel, user_id):
                local_video_path = self._fetch_video(task)
            
            # 3. 分析视频
            with StageLogger(task_id, self.STAGE_ANALYZING, channel, user_id):
                raw_result = self._analyze_video(task, local_video_path)
            
            # 4. 标准化结果
            with StageLogger(task_id, self.STAGE_NORMALIZING, channel, user_id):
                normalized_result = self._normalize_result(task_id, raw_result)
            
            # 5. 生成报告
            with StageLogger(task_id, self.STAGE_GENERATING_REPORT, channel, user_id):
                report_text = self._generate_report(normalized_result)
                normalized_result['report_text'] = report_text
            
            # 6. 保存结果
            with StageLogger(task_id, self.STAGE_SAVING_RESULTS, channel, user_id):
                self._save_result(task, raw_result, normalized_result)
            
            # 7. 回推结果（第六步新增）
            with StageLogger(task_id, self.STAGE_DELIVERING, channel, user_id):
                self._deliver_result(task, normalized_result)
            
            # 任务完成
            log_task_lifecycle(
                task_id=task_id,
                event='completed',
                channel=channel,
                user_id=user_id,
                overall_score=normalized_result.get('overall_score'),
                ntrp_level=normalized_result.get('ntrp_level')
            )
            
            return True
            
        except AnalysisError as e:
            # 统一错误处理
            self._handle_error(task, e, local_video_path)
            return True
            
        except Exception as e:
            # 未知异常转换
            error = create_error_from_exception(e, task_id, 'processing')
            self._handle_error(task, error, local_video_path)
            return True
            
        finally:
            if local_video_path:
                cleanup_fetched_video(local_video_path)
    
    def _fetch_video(self, task: dict) -> str:
        """获取视频到本地（修复版：添加 resolved_local_path 日志）"""
        task_id = task['task_id']
        source_type = task['source_type']
        source_url = task['source_url']
        
        # 修复版：打印关键信息，确保可追溯
        log.info(
            f"Fetching video for analysis",
            task_id=task_id,
            source_type=source_type,
            source_url=source_url[:100] + '...' if len(source_url) > 100 else source_url,
            stage=self.STAGE_DOWNLOADING
        )
        
        TaskStatusService.mark_downloading(task_id, self.worker_id)
        
        fetch_result = fetch_video_to_local(source_type, source_url, task_id)
        
        if not fetch_result['success']:
            error_code = fetch_result.get('error_code', 'SOURCE_FETCH_ERROR')
            error_message = fetch_result.get('error_message', '视频获取失败')
            
            # 修复版：明确禁止回退到默认测试视频
            # 任何获取失败都必须直接报错，不能静默回退
            log.error(
                f"Video fetch failed - NO FALLBACK ALLOWED",
                task_id=task_id,
                source_type=source_type,
                error_code=error_code,
                error_message=error_message,
                stage=self.STAGE_DOWNLOADING
            )
            
            # 转换为统一错误
            from errors import ErrorCode
            try:
                ec = ErrorCode(error_code)
            except ValueError:
                ec = ErrorCode.SOURCE_FETCH_ERROR
            
            raise AnalysisError(
                error_code=ec,
                message=error_message,
                task_id=task_id,
                stage=self.STAGE_DOWNLOADING,
                details={'source_type': source_type, 'source_url': source_url}
            )
        
        # 修复版：明确打印最终分析文件路径
        resolved_local_path = fetch_result['local_video_path']
        log.info(
            f"Video resolved for analysis",
            task_id=task_id,
            source_type=source_type,
            source_url=source_url,
            resolved_local_path=resolved_local_path,
            file_size=os.path.getsize(resolved_local_path) if os.path.exists(resolved_local_path) else 0,
            stage=self.STAGE_DOWNLOADING
        )
        
        return resolved_local_path
        
        return fetch_result['local_video_path']
    
    def _analyze_video(self, task: dict, video_path: str) -> dict:
        """分析视频（第六步：统一错误处理）"""
        task_id = task['task_id']
        user_id = task['user_id']
        
        TaskStatusService.mark_analyzing(task_id)
        
        try:
            from complete_analysis_service import analyze_video_complete
            result = analyze_video_complete(video_path, user_id, task_id)
            
            if not result.get('success'):
                error = result.get('error', '分析失败')
                raise AnalysisError(
                    error_code=ErrorCode.ANALYSIS_ERROR,
                    message=error,
                    task_id=task_id,
                    stage=self.STAGE_ANALYZING
                )
            
            return result.get('analysis_result', {})
            
        except Exception as e:
            if isinstance(e, AnalysisError):
                raise
            raise AnalysisError(
                error_code=ErrorCode.ANALYSIS_ERROR,
                message=str(e),
                task_id=task_id,
                stage=self.STAGE_ANALYZING
            )
    
    def _normalize_result(self, task_id: str, raw_result: dict) -> dict:
        """标准化分析结果"""
        model_meta = {
            "provider": "moonshot",
            "model": "kimi-k2.5",
            "latency_ms": 0
        }
        
        normalization = normalize_analysis_result(raw_result, model_meta)
        normalized_result = normalization['normalized_result']
        
        if normalization['warnings']:
            log.warning(
                f"Normalization warnings: {len(normalization['warnings'])}",
                task_id=task_id,
                stage=self.STAGE_NORMALIZING,
                details={'warnings': normalization['warnings']}
            )
        
        return normalized_result
    
    def _generate_report(self, normalized_result: dict) -> str:
        """生成报告"""
        from complete_report_generator import generate_complete_report
        
        report = generate_complete_report(
            normalized_result,
            {'status': 'ok'},
            report_version='v1'
        )
        
        return report
    
    def _save_result(self, task: dict, raw_result: dict, normalized_result: dict):
        """保存结果（第六步：使用 Repository）"""
        task_id = task['task_id']
        
        TaskStatusService.mark_generating_report(task_id)
        
        try:
            from analysis_repository import analysis_repository
            
            saved = analysis_repository.save_analysis_artifacts(
                task_id=task_id,
                raw_result=raw_result,
                normalized_result=normalized_result,
                report_text=normalized_result.get('report_text', ''),
                report_version='v1'
            )
            
            if not saved:
                raise AnalysisError(
                    error_code=ErrorCode.DB_WRITE_ERROR,
                    message="保存分析结果失败",
                    task_id=task_id,
                    stage=self.STAGE_SAVING_RESULTS
                )
                
        except Exception as e:
            if isinstance(e, AnalysisError):
                raise
            raise AnalysisError(
                error_code=ErrorCode.DB_WRITE_ERROR,
                message=str(e),
                task_id=task_id,
                stage=self.STAGE_SAVING_RESULTS
            )
    
    def _deliver_result(self, task: dict, normalized_result: dict):
        """回推结果（第六步：统一回推服务）"""
        task_id = task['task_id']
        channel = task.get('channel', 'unknown')
        user_id = task.get('user_id', 'unknown')
        report_text = normalized_result.get('report_text', '')
        
        # 只支持已知通道
        if channel not in ['wechat', 'feishu']:
            log.warning(
                f"Unknown channel for delivery: {channel}",
                task_id=task_id,
                channel=channel
            )
            return
        
        # 使用统一回推服务
        result = delivery_service.deliver_with_retry(
            task_id=task_id,
            channel=channel,
            user_id=user_id,
            report_text=report_text,
            max_retries=self.max_retries
        )
        
        if not result['success']:
            # 回推失败但分析已完成，记录状态但不标记任务失败
            log.error(
                f"Delivery failed after {result['retry_count']} retries",
                task_id=task_id,
                channel=channel,
                error_code=result.get('final_error'),
                stage=self.STAGE_DELIVERING
            )
            
            # 更新任务为部分成功状态（分析完成但回推失败）
            TaskStatusService.mark_completed_with_delivery_warning(
                task_id=task_id,
                delivery_error=result.get('final_error')
            )
    
    def _handle_error(self, task: dict, error: AnalysisError, local_video_path: str = None):
        """统一错误处理（第六步：区分可重试/不可重试）"""
        task_id = task['task_id']
        channel = task.get('channel', 'unknown')
        user_id = task.get('user_id', 'unknown')
        
        # 获取当前重试次数
        task_status = TaskStatusService.get_task_status(task_id)
        retry_count = task_status.get('retry_count', 0)
        
        log.error(
            f"Task failed: {error.error_code.value}",
            task_id=task_id,
            channel=channel,
            user_id=user_id,
            error_code=error.error_code.value,
            error_message=error.message,
            stage=error.stage,
            retry_count=retry_count,
            retryable=error.retryable
        )
        
        # 判断是否可重试
        if error.retryable and retry_count < self.max_retries:
            # 进入重试状态
            new_retry_count = retry_count + 1
            TaskStatusService.mark_retrying(
                task_id=task_id,
                error_code=error.error_code.value,
                error_message=error.message,
                retry_count=new_retry_count
            )
            
            log.info(
                f"Task marked for retry ({new_retry_count}/{self.max_retries})",
                task_id=task_id,
                retry_count=new_retry_count,
                max_retries=self.max_retries,
                stage=self.STAGE_RETRYING
            )
        else:
            # 不可重试或重试次数耗尽，标记失败
            TaskStatusService.mark_failed(
                task_id=task_id,
                error_code=error.error_code.value,
                error_message=error.get_user_message()  # 使用用户友好文案
            )
            
            log_task_lifecycle(
                task_id=task_id,
                event='failed',
                channel=channel,
                user_id=user_id,
                error_code=error.error_code.value,
                retry_count=retry_count
            )
        
        # 清理资源
        if local_video_path:
            cleanup_fetched_video(local_video_path)


def run_worker():
    """运行 Worker"""
    import signal
    
    init_task_table()
    worker = VideoAnalysisWorker()
    
    def signal_handler(signum, frame):
        log.info("Received stop signal", stage='signal_handler')
        worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == '__main__':
    run_worker()
