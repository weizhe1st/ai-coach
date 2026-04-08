#!/usr/bin/env python3
"""
分析结果仓库 - 第五步核心存储层
职责：固化 raw_result、normalized_result、report_text 三层数据闭环
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional, List

DB_PATH = '/data/db/xiaolongxia_learning.db'


class AnalysisRepository:
    """分析结果仓库 - 提供标准化的数据存取接口"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def save_analysis_artifacts(
        self,
        task_id: str,
        raw_result: Dict[str, Any],
        normalized_result: Dict[str, Any],
        report_text: str,
        report_version: str = 'v1'
    ) -> bool:
        """
        保存分析结果三层数据（第五步核心接口）
        
        Args:
            task_id: 任务ID
            raw_result: 模型原始输出
            normalized_result: 标准化后的结果
            report_text: 最终报告文本
            report_version: 报告版本号
        
        Returns:
            bool: 是否保存成功
        """
        try:
            conn = self._get_connection()
            
            # 业务字段只从 normalized_result 读取
            analysis_status = normalized_result.get('analysis_status', 'success')
            overall_score = normalized_result.get('overall_score')
            confidence = normalized_result.get('confidence')
            ntrp_level = normalized_result.get('ntrp_level')
            video_type = normalized_result.get('video_type', 'serve')
            
            conn.execute('''
                UPDATE video_analysis_tasks
                SET status = 'completed',
                    analysis_status = ?,
                    raw_result_json = ?,
                    normalized_result_json = ?,
                    report_text = ?,
                    report_version = ?,
                    overall_score = ?,
                    confidence = ?,
                    ntrp_level = ?,
                    video_type = ?,
                    finished_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE task_id = ?
            ''', (
                analysis_status,
                json.dumps(raw_result, ensure_ascii=False) if raw_result else None,
                json.dumps(normalized_result, ensure_ascii=False) if normalized_result else None,
                report_text,
                report_version,
                overall_score,
                confidence,
                ntrp_level,
                video_type,
                task_id
            ))
            
            conn.commit()
            conn.close()
            print(f"  [Repository] 分析结果已保存: {task_id}")
            return True
            
        except Exception as e:
            print(f"  [Repository] 保存失败: {e}")
            return False
    
    def get_analysis_result_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        按 task_id 查询完整分析结果（第五步核心查询接口）
        
        Returns:
            包含完整结果的字典，或 None
        """
        try:
            conn = self._get_connection()
            row = conn.execute('''
                SELECT 
                    task_id,
                    status,
                    analysis_status,
                    raw_result_json,
                    normalized_result_json,
                    report_text,
                    report_version,
                    overall_score,
                    confidence,
                    ntrp_level,
                    video_type,
                    review_status,
                    review_notes,
                    created_at,
                    started_at,
                    finished_at
                FROM video_analysis_tasks
                WHERE task_id = ?
            ''', (task_id,)).fetchone()
            conn.close()
            
            if not row:
                return None
            
            return {
                'task_id': row['task_id'],
                'status': row['status'],
                'analysis_status': row['analysis_status'],
                'raw_result': json.loads(row['raw_result_json']) if row['raw_result_json'] else None,
                'normalized_result': json.loads(row['normalized_result_json']) if row['normalized_result_json'] else None,
                'report_text': row['report_text'],
                'report_version': row['report_version'],
                'overall_score': row['overall_score'],
                'confidence': row['confidence'],
                'ntrp_level': row['ntrp_level'],
                'video_type': row['video_type'],
                'review_status': row['review_status'],
                'review_notes': row['review_notes'],
                'created_at': row['created_at'],
                'started_at': row['started_at'],
                'finished_at': row['finished_at']
            }
            
        except Exception as e:
            print(f"  [Repository] 查询失败: {e}")
            return None
    
    def get_normalized_result_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """按 task_id 查询标准化结果"""
        try:
            conn = self._get_connection()
            row = conn.execute('''
                SELECT normalized_result_json 
                FROM video_analysis_tasks 
                WHERE task_id = ?
            ''', (task_id,)).fetchone()
            conn.close()
            
            if row and row['normalized_result_json']:
                return json.loads(row['normalized_result_json'])
            return None
            
        except Exception as e:
            print(f"  [Repository] 查询失败: {e}")
            return None
    
    def get_report_by_task_id(self, task_id: str) -> Optional[str]:
        """按 task_id 查询报告文本"""
        try:
            conn = self._get_connection()
            row = conn.execute('''
                SELECT report_text 
                FROM video_analysis_tasks 
                WHERE task_id = ?
            ''', (task_id,)).fetchone()
            conn.close()
            
            return row['report_text'] if row else None
            
        except Exception as e:
            print(f"  [Repository] 查询失败: {e}")
            return None
    
    def get_raw_result_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """按 task_id 查询原始结果（用于追溯和排查）"""
        try:
            conn = self._get_connection()
            row = conn.execute('''
                SELECT raw_result_json 
                FROM video_analysis_tasks 
                WHERE task_id = ?
            ''', (task_id,)).fetchone()
            conn.close()
            
            if row and row['raw_result_json']:
                return json.loads(row['raw_result_json'])
            return None
            
        except Exception as e:
            print(f"  [Repository] 查询失败: {e}")
            return None
    
    def update_review_status(
        self,
        task_id: str,
        review_status: str,
        review_notes: str = None,
        reviewed_result: Dict[str, Any] = None,
        reviewed_by: str = None
    ) -> bool:
        """
        更新复核状态（为第六步人工复核预留）
        
        Args:
            task_id: 任务ID
            review_status: 复核状态 (pending/approved/rejected/modified)
            review_notes: 复核备注
            reviewed_result: 复核后的结果（如有修改）
            reviewed_by: 复核人
        """
        try:
            conn = self._get_connection()
            conn.execute('''
                UPDATE video_analysis_tasks
                SET review_status = ?,
                    review_notes = ?,
                    reviewed_result_json = ?,
                    reviewed_by = ?,
                    reviewed_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE task_id = ?
            ''', (
                review_status,
                review_notes,
                json.dumps(reviewed_result, ensure_ascii=False) if reviewed_result else None,
                reviewed_by,
                task_id
            ))
            conn.commit()
            conn.close()
            print(f"  [Repository] 复核状态已更新: {task_id} -> {review_status}")
            return True
            
        except Exception as e:
            print(f"  [Repository] 更新失败: {e}")
            return False
    
    def mark_delivered(self, task_id: str, channel: str) -> bool:
        """标记报告已发送至某渠道"""
        try:
            conn = self._get_connection()
            
            # 先获取当前已发送渠道
            row = conn.execute('''
                SELECT delivered_channels FROM video_analysis_tasks WHERE task_id = ?
            ''', (task_id,)).fetchone()
            
            current = row['delivered_channels'] if row and row['delivered_channels'] else ''
            channels = set(current.split(',')) if current else set()
            channels.add(channel)
            new_channels = ','.join(sorted(channels))
            
            conn.execute('''
                UPDATE video_analysis_tasks
                SET delivered_channels = ?,
                    updated_at = datetime('now')
                WHERE task_id = ?
            ''', (new_channels, task_id))
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  [Repository] 标记失败: {e}")
            return False
    
    def list_tasks_by_score_range(
        self,
        min_score: int = None,
        max_score: int = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """按分数范围查询任务（用于统计分析）"""
        try:
            conn = self._get_connection()
            
            query = '''
                SELECT task_id, overall_score, ntrp_level, confidence, 
                       created_at, finished_at
                FROM video_analysis_tasks
                WHERE status = 'completed'
            '''
            params = []
            
            if min_score is not None:
                query += ' AND overall_score >= ?'
                params.append(min_score)
            if max_score is not None:
                query += ' AND overall_score <= ?'
                params.append(max_score)
            
            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            conn.close()
            
            return [
                {
                    'task_id': row['task_id'],
                    'overall_score': row['overall_score'],
                    'ntrp_level': row['ntrp_level'],
                    'confidence': row['confidence'],
                    'created_at': row['created_at'],
                    'finished_at': row['finished_at']
                }
                for row in rows
            ]
            
        except Exception as e:
            print(f"  [Repository] 查询失败: {e}")
            return []


# 全局仓库实例
analysis_repository = AnalysisRepository()


if __name__ == '__main__':
    print("=== AnalysisRepository 测试 ===\n")
    
    repo = AnalysisRepository()
    
    # 测试数据
    test_task_id = f"test_task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    test_raw = {"total_score": 78, "critical_issues": ["抛球不稳"]}
    test_normalized = {
        "analysis_status": "success",
        "overall_score": 78,
        "confidence": 0.82,
        "ntrp_level": "3.5",
        "key_issues": [{"issue": "抛球不稳", "severity": "medium"}],
        "training_plan": ["先练抛球"],
        "summary": "整体一般"
    }
    test_report = "🎾 测试报告\n总分: 78\n等级: 3.5"
    
    # 先创建任务记录
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        INSERT OR IGNORE INTO video_analysis_tasks 
        (task_id, channel, user_id, source_type, source_url, status)
        VALUES (?, 'test', 'test_user', 'test', 'test', 'pending')
    ''', (test_task_id,))
    conn.commit()
    conn.close()
    
    # 测试保存
    print("1. 测试保存分析结果...")
    saved = repo.save_analysis_artifacts(
        task_id=test_task_id,
        raw_result=test_raw,
        normalized_result=test_normalized,
        report_text=test_report,
        report_version='v1'
    )
    print(f"   保存结果: {'✅ 成功' if saved else '❌ 失败'}\n")
    
    # 测试查询完整结果
    print("2. 测试查询完整结果...")
    result = repo.get_analysis_result_by_task_id(test_task_id)
    if result:
        print(f"   task_id: {result['task_id']}")
        print(f"   analysis_status: {result['analysis_status']}")
        print(f"   overall_score: {result['overall_score']}")
        print(f"   confidence: {result['confidence']}")
        print(f"   ntrp_level: {result['ntrp_level']}")
        print(f"   report_version: {result['report_version']}")
        print(f"   raw_result: {result['raw_result']}")
        print(f"   normalized_result: {result['normalized_result']}")
        print(f"   report_text: {result['report_text'][:50]}...")
    print()
    
    # 测试单独查询
    print("3. 测试单独查询...")
    norm = repo.get_normalized_result_by_task_id(test_task_id)
    print(f"   normalized_result: {norm}")
    
    report = repo.get_report_by_task_id(test_task_id)
    print(f"   report_text: {report[:50]}..." if report else "   report_text: None")
    
    raw = repo.get_raw_result_by_task_id(test_task_id)
    print(f"   raw_result: {raw}")
    print()
    
    # 测试复核预留
    print("4. 测试复核状态更新...")
    updated = repo.update_review_status(
        task_id=test_task_id,
        review_status='approved',
        review_notes='测试复核通过',
        reviewed_by='test_admin'
    )
    print(f"   更新结果: {'✅ 成功' if updated else '❌ 失败'}")
    
    result2 = repo.get_analysis_result_by_task_id(test_task_id)
    print(f"   review_status: {result2['review_status']}")
    print(f"   review_notes: {result2['review_notes']}")
    print()
    
    print("✅ AnalysisRepository 测试完成!")
