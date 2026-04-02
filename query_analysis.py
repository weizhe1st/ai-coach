#!/usr/bin/env python3
"""
统一分析查询接口 - 供所有渠道调用
返回标准化的分析结果
"""

import sqlite3
import json
from typing import Dict, Any, Optional

DB_PATH = '/data/db/xiaolongxia_learning.db'


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query_analysis_result(video_id: str) -> Optional[Dict[str, Any]]:
    """
    查询视频分析结果
    
    Args:
        video_id: 视频ID
    
    Returns:
        分析结果字典，如果未找到返回None
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.id, t.video_id, t.analysis_status, t.ntrp_level, 
               t.ntrp_confidence, t.knowledge_recall_count, 
               t.analysis_result, t.phase_marks, t.created_at, t.finished_at,
               v.file_name, v.cos_url
        FROM video_analysis_tasks t
        JOIN videos v ON t.video_id = v.id
        WHERE v.id = ?
        ORDER BY t.created_at DESC
        LIMIT 1
    ''', (video_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    result = {
        'task_id': row['id'],
        'video_id': row['video_id'],
        'analysis_status': row['analysis_status'],
        'ntrp_level': row['ntrp_level'],
        'ntrp_confidence': row['ntrp_confidence'],
        'knowledge_recall_count': row['knowledge_recall_count'],
        'file_name': row['file_name'],
        'cos_url': row['cos_url'],
        'created_at': row['created_at'],
        'finished_at': row['finished_at']
    }
    
    # 解析analysis_result JSON
    if row['analysis_result']:
        try:
            analysis_data = json.loads(row['analysis_result'])
            result['analysis_data'] = analysis_data
            
            # 提取关键信息
            result['total_score'] = analysis_data.get('total_score')
            result['bucket'] = analysis_data.get('bucket')
            result['phase_analysis'] = analysis_data.get('phase_analysis')
            result['problems'] = analysis_data.get('problems', [])
            result['recommendations'] = analysis_data.get('recommendations', [])
            result['coach_feedback'] = analysis_data.get('coach_feedback', [])
            result['coach_stats'] = analysis_data.get('coach_stats', {})
        except:
            pass
    
    return result


def format_analysis_report(result: Dict[str, Any]) -> str:
    """
    格式化分析报告为可读文本
    """
    if not result:
        return "未找到分析结果"
    
    status = result.get('analysis_status')
    
    if status == 'pending':
        return "视频正在排队等待分析..."
    
    if status == 'running':
        return "视频正在分析中，请稍候..."
    
    if status == 'failed':
        return "分析失败，请重新上传视频"
    
    if status != 'success':
        return f"未知状态: {status}"
    
    # 构建报告
    report_lines = [
        "🎾 网球发球分析报告",
        "",
        f"📊 综合评分: {result.get('total_score', 'N/A')}/100",
        f"🎯 NTRP档位: {result.get('bucket', 'N/A')}",
        "",
        "📈 五阶段评分:"
    ]
    
    phase_analysis = result.get('phase_analysis', {})
    phase_names = {
        'ready': '准备',
        'toss': '抛球',
        'loading': '蓄力',
        'contact': '击球',
        'follow': '随挥'
    }
    
    for phase_key, phase_name in phase_names.items():
        phase_data = phase_analysis.get(phase_key, {})
        score = phase_data.get('score', 'N/A')
        issues = phase_data.get('issues', [])
        issue_str = f" ⚠️ {', '.join(issues)}" if issues else " ✅"
        report_lines.append(f"  • {phase_name}: {score}分{issue_str}")
    
    # 问题列表
    problems = result.get('problems', [])
    if problems:
        report_lines.extend(["", "🔍 发现问题:"])
        for p in problems[:3]:
            report_lines.append(f"  • {p.get('description', '未知问题')}")
    
    # 改进建议
    recommendations = result.get('recommendations', [])
    if recommendations:
        report_lines.extend(["", "💡 改进建议:"])
        for r in recommendations[:3]:
            if r:
                report_lines.append(f"  • {r}")
    
    # 教练知识库引用
    coach_stats = result.get('coach_stats', {})
    if coach_stats:
        report_lines.extend(["", "📚 教练知识库引用:"])
        for coach, count in coach_stats.items():
            report_lines.append(f"  • {coach}: {count}条知识点")
    
    report_lines.extend([
        "",
        f"📹 视频: {result.get('file_name', '未知')}",
        f"✅ 分析完成时间: {result.get('finished_at', '未知')}"
    ])
    
    return "\n".join(report_lines)


def get_latest_analysis_by_filename(file_name: str) -> Optional[Dict[str, Any]]:
    """
    根据文件名查询最新的分析结果
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.id, t.video_id
        FROM video_analysis_tasks t
        JOIN videos v ON t.video_id = v.id
        WHERE v.file_name = ?
        ORDER BY t.created_at DESC
        LIMIT 1
    ''', (file_name,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return query_analysis_result(row['video_id'])
    
    return None


# CLI接口
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python query_analysis.py <video_id>")
        sys.exit(1)
    
    video_id = sys.argv[1]
    result = query_analysis_result(video_id)
    
    if result:
        print(format_analysis_report(result))
    else:
        print("未找到分析结果")
