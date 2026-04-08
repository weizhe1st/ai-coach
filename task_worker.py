#!/usr/bin/env python3
"""
任务 Worker - 后台消费视频分析任务（第四步改造版）
使用 video_fetcher + analysis_normalizer
"""

import os
import sys
import time
import json
import uuid
from datetime import datetime

sys.path.insert(0, '/data/apps/xiaolongxia')

from task_status_service import TaskStatusService
from task_repository import init_task_table
from video_fetcher import fetch_video_to_local, cleanup_fetched_video
from analysis_normalizer import normalize_analysis_result


class VideoAnalysisWorker:
    """视频分析 Worker（第四步改造版）"""
    
    def __init__(self, worker_id: str = None, poll_interval: int = 5):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.running = False
        
        if not os.environ.get('MOONSHOT_API_KEY'):
            raise ValueError("MOONSHOT_API_KEY 环境变量未设置")
        
        print(f"[Worker] Worker 初始化完成: {self.worker_id}")
    
    def start(self):
        """启动 Worker"""
        self.running = True
        print(f"[Worker {self.worker_id}] 启动，开始轮询任务...")
        
        while self.running:
            try:
                task_processed = self.process_one_task()
                if not task_processed:
                    time.sleep(self.poll_interval)
            except Exception as e:
                print(f"[Worker {self.worker_id}] 处理异常: {e}")
                time.sleep(self.poll_interval)
        
        print(f"[Worker {self.worker_id}] 已停止")
    
    def stop(self):
        """停止 Worker"""
        self.running = False
        print(f"[Worker {self.worker_id}] 正在停止...")
    
    def process_one_task(self) -> bool:
        """处理一个任务"""
        # 1. 领取任务
        task = TaskStatusService.fetch_pending_task(self.worker_id)
        if not task:
            return False
        
        task_id = task['task_id']
        print(f"[Worker {self.worker_id}] 开始处理任务: {task_id}")
        
        local_video_path = None
        
        try:
            # 2. 视频输入层处理
            local_video_path = self._fetch_video(task)
            
            # 3. 分析视频（得到 raw_result）
            raw_result = self._analyze_video(task, local_video_path)
            
            # 4. 标准化结果（第四步新增）
            normalized_result = self._normalize_result(task_id, raw_result)
            
            # 5. 保存结果（使用标准化结果）
            self._save_result(task, raw_result, normalized_result)
            
            print(f"[Worker {self.worker_id}] 任务完成: {task_id}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"[Worker {self.worker_id}] 任务失败: {task_id}, 错误: {error_msg}")
            TaskStatusService.mark_failed(task_id, 'PROCESS_ERROR', error_msg)
            return True
        finally:
            if local_video_path:
                cleanup_fetched_video(local_video_path)
    
    def _fetch_video(self, task: dict) -> str:
        """获取视频到本地"""
        task_id = task['task_id']
        source_type = task['source_type']
        source_url = task['source_url']
        
        print(f"[Worker {self.worker_id}] [{task_id}] 开始获取视频...")
        TaskStatusService.mark_downloading(task_id, self.worker_id)
        
        fetch_result = fetch_video_to_local(source_type, source_url, task_id)
        
        if not fetch_result['success']:
            error_code = fetch_result['error_code']
            error_message = fetch_result['error_message']
            TaskStatusService.mark_failed(task_id, error_code, error_message)
            raise Exception(f"视频获取失败 [{error_code}]: {error_message}")
        
        print(f"[Worker {self.worker_id}] [{task_id}] 视频获取成功")
        return fetch_result['local_video_path']
    
    def _analyze_video(self, task: dict, video_path: str) -> dict:
        """分析视频，返回原始结果"""
        task_id = task['task_id']
        user_id = task['user_id']
        
        print(f"[Worker {self.worker_id}] [{task_id}] 开始分析视频...")
        TaskStatusService.mark_analyzing(task_id)
        
        try:
            from complete_analysis_service import analyze_video_complete
            result = analyze_video_complete(video_path, user_id, task_id)
            
            if not result.get('success'):
                error = result.get('error', '分析失败')
                raise Exception(error)
            
            # 返回原始分析结果
            raw_result = result.get('analysis_result', {})
            print(f"[Worker {self.worker_id}] [{task_id}] 视频分析完成")
            return raw_result
            
        except Exception as e:
            print(f"[Worker {self.worker_id}] [{task_id}] 视频分析失败: {e}")
            raise
    
    def _normalize_result(self, task_id: str, raw_result: dict) -> dict:
        """
        标准化分析结果（第四步新增）
        """
        print(f"[Worker {self.worker_id}] [{task_id}] 开始标准化结果...")
        
        model_meta = {
            "provider": "moonshot",
            "model": "kimi-k2.5",
            "latency_ms": 0
        }
        
        normalization = normalize_analysis_result(raw_result, model_meta)
        normalized_result = normalization['normalized_result']
        
        if normalization['warnings']:
            print(f"[Worker {self.worker_id}] [{task_id}] 标准化警告: {normalization['warnings']}")
        
        print(f"[Worker {self.worker_id}] [{task_id}] 标准化完成")
        print(f"  overall_score: {normalized_result['overall_score']}")
        print(f"  ntrp_level: {normalized_result['ntrp_level']}")
        
        return normalized_result
    
    def _save_result(self, task: dict, raw_result: dict, normalized_result: dict):
        """
        保存结果（使用标准化结果）
        """
        task_id = task['task_id']
        
        print(f"[Worker {self.worker_id}] [{task_id}] 开始保存结果...")
        TaskStatusService.mark_generating_report(task_id)
        
        try:
            # 使用标准化结果构造 payload
            result_payload = {
                "raw_result": raw_result,
                "normalized_result": normalized_result,
                "report_text": normalized_result.get('report_text', ''),
                "ntrp_level": normalized_result.get('ntrp_level', ''),
                "overall_score": normalized_result.get('overall_score', 0)
            }
            
            TaskStatusService.mark_completed(task_id, result_payload)
            print(f"[Worker {self.worker_id}] [{task_id}] 结果已保存")
            
        except Exception as e:
            print(f"[Worker {self.worker_id}] [{task_id}] 保存结果失败: {e}")
            raise


def run_worker():
    """运行 Worker"""
    import signal
    
    init_task_table()
    worker = VideoAnalysisWorker()
    
    def signal_handler(signum, frame):
        print("\n收到停止信号，正在关闭 Worker...")
        worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == '__main__':
    run_worker()
