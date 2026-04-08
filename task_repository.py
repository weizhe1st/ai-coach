#!/usr/bin/env python3
"""
任务仓库 - 完整版
支持任务状态机和 Worker 消费
"""

import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_PATH = '/data/db/xiaolongxia_learning.db'

# 任务状态机定义
TASK_STATUS = {
    'PENDING': 'pending',
    'DOWNLOADING': 'downloading',
    'ANALYZING': 'analyzing',
    'GENERATING_REPORT': 'generating_report',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'RETRYING': 'retrying'
}


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_task_table():
    """初始化任务表（完整版）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_analysis_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            channel TEXT NOT NULL,
            user_id TEXT NOT NULL,
            message_id TEXT,
            source_type TEXT NOT NULL,
            source_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_code TEXT,
            error_message TEXT,
            worker_id TEXT,
            raw_result_json TEXT,
            normalized_result_json TEXT,
            report_text TEXT,
            ntrp_level TEXT,
            overall_score INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            finished_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON video_analysis_tasks(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON video_analysis_tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON video_analysis_tasks(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON video_analysis_tasks(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON video_analysis_tasks(status, created_at)')
    
    conn.commit()
    conn.close()
    print("[TaskRepository] 任务表（完整版）初始化完成")


def create_task(channel: str, user_id: str, message_id: str, 
                source_type: str, source_url: str) -> Dict[str, Any]:
    """创建新任务"""
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO video_analysis_tasks 
        (task_id, channel, user_id, message_id, source_type, source_url, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    ''', (task_id, channel, user_id, message_id, source_type, source_url))
    
    conn.commit()
    conn.close()
    
    print(f"[TaskRepository] 任务创建成功: {task_id}")
    
    return {
        "task_id": task_id,
        "status": TASK_STATUS['PENDING'],
        "channel": channel,
        "user_id": user_id
    }


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务详情"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM video_analysis_tasks WHERE task_id = ?
    ''', (task_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def fetch_next_pending_task(worker_id: str) -> Optional[Dict[str, Any]]:
    """
    领取下一个待处理任务（带锁机制）
    
    Args:
        worker_id: Worker 标识
    
    Returns:
        任务字典，如果没有则返回 None
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 查找最老的 pending 任务
        cursor.execute('''
            SELECT * FROM video_analysis_tasks 
            WHERE status = 'pending'
            AND retry_count < max_retries
            ORDER BY created_at ASC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        task = dict(row)
        task_id = task['task_id']
        
        # 锁定任务（更新状态和 worker_id）
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET status = 'downloading',
                worker_id = ?,
                started_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ? AND status = 'pending'
        ''', (worker_id, task_id))
        
        if cursor.rowcount == 0:
            # 任务被其他 worker 抢走
            conn.rollback()
            conn.close()
            return None
        
        conn.commit()
        
        # 返回更新后的任务
        task['status'] = TASK_STATUS['DOWNLOADING']
        task['worker_id'] = worker_id
        
        print(f"[TaskRepository] Worker {worker_id} 领取任务: {task_id}")
        return task
        
    except Exception as e:
        conn.rollback()
        print(f"[TaskRepository] 领取任务失败: {e}")
        return None
    finally:
        conn.close()


def update_task_status(task_id: str, status: str, 
                       error_code: str = None, error_message: str = None):
    """更新任务状态"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET status = ?, 
            updated_at = CURRENT_TIMESTAMP,
            error_code = COALESCE(?, error_code),
            error_message = COALESCE(?, error_message)
        WHERE task_id = ?
    ''', (status, error_code, error_message, task_id))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务状态更新: {task_id} -> {status}")


def mark_task_downloading(task_id: str, worker_id: str):
    """标记任务为下载中"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET status = 'downloading',
            worker_id = ?,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (worker_id, task_id))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务开始下载: {task_id}")


def mark_task_analyzing(task_id: str):
    """标记任务为分析中"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET status = 'analyzing',
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (task_id,))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务开始分析: {task_id}")


def mark_task_generating_report(task_id: str):
    """标记任务为生成报告中"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET status = 'generating_report',
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (task_id,))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务开始生成报告: {task_id}")


def mark_task_completed(task_id: str, result_payload: Dict[str, Any]):
    """标记任务为已完成"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    import json
    
    raw_result = json.dumps(result_payload.get('raw_result', {}), ensure_ascii=False)
    report_text = result_payload.get('report_text', '')
    ntrp_level = result_payload.get('ntrp_level', '')
    overall_score = result_payload.get('overall_score', 0)
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET status = 'completed',
            raw_result_json = ?,
            report_text = ?,
            ntrp_level = ?,
            overall_score = ?,
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (raw_result, report_text, ntrp_level, overall_score, task_id))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务完成: {task_id}")


def mark_task_failed(task_id: str, error_code: str, error_message: str):
    """标记任务为失败"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET status = 'failed',
            error_code = ?,
            error_message = ?,
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (error_code, error_message, task_id))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务失败: {task_id}, 错误: {error_code}")


def increment_retry_count(task_id: str) -> int:
    """增加重试次数，返回当前重试次数"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET retry_count = retry_count + 1,
            status = 'retrying',
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (task_id,))
    
    cursor.execute('SELECT retry_count FROM video_analysis_tasks WHERE task_id = ?', (task_id,))
    row = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    retry_count = row[0] if row else 0
    print(f"[TaskRepository] 任务重试: {task_id}, 次数: {retry_count}")
    return retry_count


def list_tasks_by_status(status: str, limit: int = 10) -> List[Dict[str, Any]]:
    """按状态列出任务"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM video_analysis_tasks 
        WHERE status = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (status, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_task_stats() -> Dict[str, int]:
    """获取任务统计"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT status, COUNT(*) as count 
        FROM video_analysis_tasks 
        GROUP BY status
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    stats = {row[0]: row[1] for row in rows}
    return stats


def update_task_source(task_id: str, source_type: str, source_url: str, resolved_local_path: str = None):
    """
    更新任务的视频源信息（修复版核心函数）
    用于微信视频下载后，将 source 从 wechat_temp_url 更新为 local_file
    
    Args:
        task_id: 任务ID
        source_type: 新的来源类型
        source_url: 新的来源URL（本地文件路径）
        resolved_local_path: 解析后的本地文件路径（用于追踪）
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查是否需要添加 resolved_local_path 字段
    cursor.execute("PRAGMA table_info(video_analysis_tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'resolved_local_path' not in columns:
        cursor.execute('ALTER TABLE video_analysis_tasks ADD COLUMN resolved_local_path TEXT')
        print(f"[TaskRepository] 添加 resolved_local_path 字段")
    
    cursor.execute('''
        UPDATE video_analysis_tasks 
        SET source_type = ?,
            source_url = ?,
            resolved_local_path = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (source_type, source_url, resolved_local_path, task_id))
    
    conn.commit()
    conn.close()
    print(f"[TaskRepository] 任务源已更新: {task_id} -> {source_type}, 路径: {resolved_local_path}")


if __name__ == '__main__':
    # 初始化表
    init_task_table()
    print("任务表（完整版）初始化完成")
