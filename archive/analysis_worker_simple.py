#!/usr/bin/env python3
"""
简化版分析worker - 用于测试
"""

import sqlite3
import time
import json
from datetime import datetime

DB_PATH = '/data/db/xiaolongxia_learning.db'

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_pending_task():
    """获取一个pending状态的任务"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.id, t.video_id, v.cos_url, v.file_name
            FROM video_analysis_tasks t
            JOIN videos v ON t.video_id = v.id
            WHERE t.analysis_status = 'pending'
            ORDER BY t.created_at ASC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row['id'],
                'video_id': row['video_id'],
                'cos_url': row['cos_url'],
                'file_name': row['file_name']
            }
        return None
        
    except Exception as e:
        print(f"[Worker] 获取任务错误: {e}")
        return None

def process_task(task):
    """处理任务"""
    print(f"[Worker] 处理任务: {task['id']}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 更新状态为processing
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET analysis_status = 'processing', started_at = datetime('now')
            WHERE id = ?
        ''', (task['id'],))
        conn.commit()
        
        # 模拟分析过程
        print(f"[Worker] 分析视频: {task['file_name']}")
        time.sleep(2)  # 模拟分析时间
        
        # 生成分析结果
        analysis_result = {
            "total_score": 75.0,
            "bucket": "4.0",
            "problems": [
                {"phase": "toss", "problem_code": "toss_height", "description": "抛球高度偏低"}
            ]
        }
        
        # 更新状态为success
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET analysis_status = 'success',
                ntrp_level = '4.0',
                ntrp_confidence = 0.85,
                knowledge_recall_count = 2,
                sample_saved = 1,
                analysis_result = ?,
                finished_at = datetime('now')
            WHERE id = ?
        ''', (json.dumps(analysis_result), task['id']))
        
        conn.commit()
        conn.close()
        
        print(f"[Worker] 任务完成: {task['id']}")
        
    except Exception as e:
        print(f"[Worker] 处理任务错误: {e}")

def main_loop():
    """主循环"""
    print("[Worker] 启动简化版分析worker...")
    
    while True:
        try:
            task = get_pending_task()
            
            if task:
                print(f"[Worker] 获取任务: {task['id']}")
                process_task(task)
            else:
                print("[Worker] 无pending任务，等待5秒...")
                time.sleep(5)
                
        except Exception as e:
            print(f"[Worker] 错误: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main_loop()
