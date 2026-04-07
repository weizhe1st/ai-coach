#!/usr/bin/env python3
"""
完整版网球发球分析服务
整合所有功能：MediaPipe + Kimi + 知识库 + 黄金标准 + 数据库写入
"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import traceback
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# 添加项目路径
sys.path.insert(0, '/data/apps/xiaolongxia')

# 导入现有模块
from core import (
    PROMPT_VERSION, KNOWLEDGE_BASE_VERSION, MODEL_NAME,
    SYSTEM_PROMPT, check_input_quality, validate_response
)
from complete_report_generator import generate_complete_report
from mediapipe_helper import (
    extract_pose_metrics,
    enhance_vision_result_with_mediapipe,
    format_for_kimi,
    MEDIAPIPE_ENABLED
)

# 配置
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
DB_PATH = '/data/db/xiaolongxia_learning.db'
COS_BUCKET = 'tennis-ai-1411340868'
COS_REGION = 'ap-shanghai'

client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.cn/v1")

# ═══════════════════════════════════════════════════════════════════
# 数据库操作函数
# ═══════════════════════════════════════════════════════════════════

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_clip_pose_results(clip_id, pose_data, metrics):
    """保存姿态分析结果"""
    try:
        conn = get_db_connection()
        # 根据实际表结构调整
        conn.execute('''
            INSERT OR REPLACE INTO clip_pose_results 
            (clip_id, pose_format, frame_count, created_at)
            VALUES (?, ?, ?, datetime('now'))
        ''', (clip_id, 'mediapipe', metrics.get('frame_count', 0) if metrics else 0))
        conn.commit()
        conn.close()
        print(f"  [DB] 姿态结果已保存: {clip_id}")
    except Exception as e:
        print(f"  [DB] 姿态结果保存失败: {e}")

def save_clip_phase_segments(clip_id, phase_analysis):
    """保存阶段分段"""
    try:
        conn = get_db_connection()
        # 根据实际表结构调整 - 使用时间段而不是帧数
        ready_data = phase_analysis.get('ready', {})
        toss_data = phase_analysis.get('toss', {})
        loading_data = phase_analysis.get('loading', {})
        contact_data = phase_analysis.get('contact', {})
        follow_data = phase_analysis.get('follow', {})
        
        conn.execute('''
            INSERT OR REPLACE INTO clip_phase_segments
            (clip_id, ready_start, ready_end, toss_start, toss_end, 
             trophy_start, trophy_end, contact_start, contact_end, 
             follow_start, follow_end)
            VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        ''', (clip_id,))
        conn.commit()
        conn.close()
        print(f"  [DB] 阶段分段已保存: {clip_id}")
    except Exception as e:
        print(f"  [DB] 阶段分段保存失败: {e}")

def save_clip_scoring_results(clip_id, ntrp_level, total_score, confidence, details):
    """保存评分结果"""
    try:
        conn = get_db_connection()
        # 根据实际表结构调整
        phases = details.get('phases', {})
        conn.execute('''
            INSERT OR REPLACE INTO clip_scoring_results
            (clip_id, total_score, ready_score, toss_score, loading_score, contact_score, follow_score, stability_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            clip_id,
            total_score,
            phases.get('ready', 0),
            phases.get('toss', 0),
            phases.get('loading', 0),
            phases.get('contact', 0),
            phases.get('follow', 0),
            0  # stability_score
        ))
        conn.commit()
        conn.close()
        print(f"  [DB] 评分结果已保存: {clip_id}")
    except Exception as e:
        print(f"  [DB] 评分结果保存失败: {e}")

def save_clip_diagnosis_results(clip_id, diagnosis_data):
    """保存诊断结果"""
    try:
        conn = get_db_connection()
        issues = diagnosis_data.get('issues', [])
        main_problem = issues[0] if issues else ''
        secondary = issues[1] if len(issues) > 1 else ''
        
        conn.execute('''
            INSERT OR REPLACE INTO clip_diagnosis_results
            (clip_id, main_problem, secondary_problems, possible_causes, priority_fix, training_advice)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            clip_id,
            main_problem,
            secondary,
            '',  # possible_causes
            '',  # priority_fix
            json.dumps(diagnosis_data.get('recommendations', []))
        ))
        conn.commit()
        conn.close()
        print(f"  [DB] 诊断结果已保存: {clip_id}")
    except Exception as e:
        print(f"  [DB] 诊断结果保存失败: {e}")

def save_clip_similar_cases(clip_id, similar_cases):
    """保存相似案例"""
    try:
        conn = get_db_connection()
        for case in similar_cases:
            conn.execute('''
                INSERT OR REPLACE INTO clip_similar_cases
                (clip_id, case_id, match_score, match_reason, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (
                clip_id,
                case.get('id', ''),
                case.get('score', 0),
                case.get('reason', '')
            ))
        conn.commit()
        conn.close()
        print(f"  [DB] 相似案例已保存: {clip_id} ({len(similar_cases)}个)")
    except Exception as e:
        print(f"  [DB] 相似案例保存失败: {e}")

def save_coach_style_report(clip_id, ntrp_level, coach_reports):
    """保存教练风格报告"""
    try:
        conn = get_db_connection()
        for coach_name, report_content in coach_reports.items():
            # 根据实际表结构调整
            conn.execute('''
                INSERT OR REPLACE INTO coach_style_reports
                (clip_id, style_type, summary, main_feedback, impact, training_plan)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                clip_id,
                coach_name,
                report_content[:200] if report_content else '',  # summary
                report_content[200:500] if len(report_content) > 200 else '',  # main_feedback
                '',  # impact
                report_content[500:] if len(report_content) > 500 else ''  # training_plan
            ))
        conn.commit()
        conn.close()
        print(f"  [DB] 教练报告已保存: {clip_id}")
    except Exception as e:
        print(f"  [DB] 教练报告保存失败: {e}")

def update_video_analysis_task(task_id, status, result_data=None, error_msg=None):
    """更新视频分析任务状态"""
    try:
        conn = get_db_connection()
        if status == 'success':
            conn.execute('''
                UPDATE video_analysis_tasks
                SET analysis_status = 'success',
                    analysis_result = ?,
                    ntrp_level = ?,
                    ntrp_confidence = ?,
                    finished_at = datetime('now')
                WHERE id = ?
            ''', (
                json.dumps(result_data) if result_data else None,
                result_data.get('ntrp_level') if result_data else None,
                result_data.get('confidence') if result_data else None,
                task_id
            ))
        elif status == 'failed':
            conn.execute('''
                UPDATE video_analysis_tasks
                SET analysis_status = 'failed',
                    failure_reason = ?,
                    finished_at = datetime('now')
                WHERE id = ?
            ''', (error_msg, task_id))
        conn.commit()
        conn.close()
        print(f"  [DB] 任务状态已更新: {task_id} -> {status}")
    except Exception as e:
        print(f"  [DB] 任务状态更新失败: {e}")

# ═══════════════════════════════════════════════════════════════════
# 知识库查询
# ═══════════════════════════════════════════════════════════════════

def query_unified_knowledge(level, phase, issue_tags):
    """查询统一知识库 - 使用 coach_knowledge 表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询相关知识点（使用 coach_knowledge 表）
        cursor.execute('''
            SELECT coach_name, phase, content, 
                   knee_angle_min, knee_angle_max,
                   elbow_angle_min, elbow_angle_max,
                   contact_height_ratio_min, contact_height_ratio_max
            FROM coach_knowledge
            WHERE level = ? AND phase = ?
            ORDER BY created_at DESC
            LIMIT 5
        ''', (level, phase))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'coach': row['coach_name'],
                'phase': row['phase'],
                'content': row['content'],
                'quality': 'A',
                'metrics': {
                    'knee_angle': (row['knee_angle_min'], row['knee_angle_max']),
                    'elbow_angle': (row['elbow_angle_min'], row['elbow_angle_max']),
                    'contact_height': (row['contact_height_ratio_min'], row['contact_height_ratio_max'])
                }
            })
        
        conn.close()
        return results
    except Exception as e:
        print(f"  [知识库] 查询失败: {e}")
        return []

def query_similar_cases_from_db(level, limit=3):
    """从数据库查询相似案例 - 使用 gold_standard_samples 表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询黄金标准样本
        cursor.execute('''
            SELECT id, level, video_path, overall_score, key_issues, analysis_result
            FROM gold_standard_samples
            WHERE level = ? AND status = 'active'
            ORDER BY created_at DESC
            LIMIT ?
        ''', (level, limit))
        
        results = []
        for row in cursor.fetchall():
            key_issues = json.loads(row['key_issues']) if row['key_issues'] else []
            results.append({
                'id': row['id'],
                'level': row['level'],
                'score': row['overall_score'],
                'description': f"得分{row['overall_score']}，主要问题: {', '.join(key_issues[:2])}" if key_issues else f"黄金标准样本，得分{row['overall_score']}",
                'features': {'key_issues': key_issues}
            })
        
        conn.close()
        return results
    except Exception as e:
        print(f"  [案例库] 查询失败: {e}")
        return []

# ═══════════════════════════════════════════════════════════════════
# 主分析函数
# ═══════════════════════════════════════════════════════════════════

def analyze_video_complete(video_path, user_id=None, task_id=None):
    """
    完整版视频分析
    
    Args:
        video_path: 视频文件路径
        user_id: 用户ID
        task_id: 任务ID（用于更新数据库）
    
    Returns:
        dict: 包含完整分析结果
    """
    print(f"\n{'='*60}")
    print(f"🎾 完整版网球发球分析")
    print(f"{'='*60}")
    print(f"视频: {video_path}")
    print(f"用户: {user_id or 'unknown'}")
    print(f"任务: {task_id or 'N/A'}")
    
    # 生成 clip_id
    clip_id = f"clip_{int(time.time())}_{os.urandom(4).hex()}"
    print(f"ClipID: {clip_id}")
    
    try:
        # 1. 输入质量检查
        print("\n[1/8] 输入质量检查...")
        passed, quality_info = check_input_quality(video_path)
        if not passed:
            error_msg = quality_info.get('reason', '视频质量检查未通过')
            if task_id:
                update_video_analysis_task(task_id, 'failed', error_msg=error_msg)
            return {'success': False, 'error': error_msg}
        print("  ✓ 质量检查通过")
        
        # 2. MediaPipe 姿态分析
        print("\n[2/8] MediaPipe 姿态分析...")
        mp_result = None
        if MEDIAPIPE_ENABLED:
            try:
                mp_result = extract_pose_metrics(video_path)
                if mp_result:
                    print(f"  ✓ 姿态分析完成，有效帧: {mp_result.get('raw_samples', 0)}")
                    # 保存姿态结果
                    save_clip_pose_results(clip_id, mp_result.get('data', {}), mp_result.get('metrics', {}))
                else:
                    print("  ⚠ MediaPipe 未返回结果")
            except Exception as e:
                print(f"  ⚠ MediaPipe 失败: {e}")
        
        # 3. 上传视频到 Kimi
        print("\n[3/8] 上传视频到 Moonshot...")
        file_object = client.files.create(file=Path(video_path), purpose="video")
        print(f"  ✓ 上传成功: {file_object.id}")
        
        # 4. Kimi 视觉分析
        print("\n[4/8] Kimi K2.5 视觉分析...")
        mp_formatted = format_for_kimi(mp_result['metrics'], mp_result['data_quality']) if mp_result else None
        
        # 构建消息（使用正确的视频格式）
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}},
                {"type": "text", "text": mp_formatted or "请分析这个网球发球视频"}
            ]}
        ]
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=1,
            max_tokens=4000
        )
        
        # 解析结果
        result_text = response.choices[0].message.content
        # 提取 JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            analysis_result = json.loads(json_match.group())
        else:
            raise ValueError("无法解析分析结果")
        
        print("  ✓ Kimi 分析完成")
        
        # 5. 整合 MediaPipe 结果
        print("\n[5/8] 整合量化指标...")
        if mp_result:
            analysis_result = enhance_vision_result_with_mediapipe(analysis_result, mp_result)
            print("  ✓ 指标整合完成")
        
        # 6. 查询知识库
        print("\n[6/8] 查询教练知识库...")
        ntrp_level = analysis_result.get('ntrp_level', '3.0')
        phases = analysis_result.get('phase_analysis', {})
        
        knowledge_results = {}
        for phase_name, phase_data in phases.items():
            issue_tags = phase_data.get('issue_tags', [])
            if issue_tags:
                knowledge_results[phase_name] = query_unified_knowledge(ntrp_level, phase_name, issue_tags)
                print(f"  [{phase_name}] 召回 {len(knowledge_results[phase_name])} 条知识点")
        
        # 添加到结果
        analysis_result['knowledge_recall'] = knowledge_results
        analysis_result['knowledge_recall_count'] = sum(len(v) for v in knowledge_results.values())
        
        # 7. 查询相似案例（黄金标准）
        print("\n[7/8] 查询黄金标准案例...")
        similar_cases = query_similar_cases_from_db(ntrp_level, limit=3)
        analysis_result['similar_cases'] = similar_cases
        print(f"  ✓ 找到 {len(similar_cases)} 个相似案例")
        
        # 8. 生成报告并保存到数据库
        print("\n[8/8] 生成报告并保存...")
        
        # 保存阶段分段
        save_clip_phase_segments(clip_id, phases)
        
        # 保存评分结果
        total_score = analysis_result.get('total_score', 0)
        confidence = analysis_result.get('confidence', 0.75)
        save_clip_scoring_results(clip_id, ntrp_level, total_score, confidence, analysis_result.get('scoring_details', {}))
        
        # 保存诊断结果
        diagnosis = {
            'issues': analysis_result.get('critical_issues', []),
            'recommendations': analysis_result.get('recommendations', [])
        }
        save_clip_diagnosis_results(clip_id, diagnosis)
        
        # 保存相似案例
        save_clip_similar_cases(clip_id, similar_cases)
        
        # 生成教练风格报告
        coach_reports = {}
        for coach_name in ['杨超', '赵凌曦', 'Yellow']:
            coach_content = []
            for phase, items in knowledge_results.items():
                for item in items:
                    if item['coach'] == coach_name:
                        coach_content.append(f"[{phase}] {item['content']}")
            if coach_content:
                coach_reports[coach_name] = '\n'.join(coach_content)
        
        save_coach_style_report(clip_id, ntrp_level, coach_reports)
        
        # 生成完整报告
        report = generate_complete_report(analysis_result, quality_info, knowledge_results, similar_cases)
        analysis_result['report'] = report
        
        # 更新任务状态
        if task_id:
            update_video_analysis_task(task_id, 'success', analysis_result)
        
        # 清理 Kimi 文件
        try:
            client.files.delete(file_object.id)
            print("  ✓ 已清理临时文件")
        except:
            pass
        
        print(f"\n{'='*60}")
        print(f"✅ 分析完成!")
        print(f"   NTRP等级: {ntrp_level}")
        print(f"   总分: {total_score}")
        print(f"   置信度: {confidence}")
        print(f"   ClipID: {clip_id}")
        print(f"{'='*60}\n")
        
        return {
            'success': True,
            'clip_id': clip_id,
            'ntrp_level': ntrp_level,
            'total_score': total_score,
            'confidence': confidence,
            'report': report,
            'analysis_result': analysis_result
        }
        
    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        print(f"\n❌ 分析失败: {error_msg}")
        
        if task_id:
            update_video_analysis_task(task_id, 'failed', error_msg=error_msg)
        
        return {'success': False, 'error': error_msg}

# ═══════════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='完整版网球发球分析')
    parser.add_argument('video_path', help='视频文件路径')
    parser.add_argument('--user-id', default='cli_user', help='用户ID')
    parser.add_argument('--task-id', help='任务ID（用于更新数据库）')
    
    args = parser.parse_args()
    
    if not MOONSHOT_API_KEY:
        print("错误: 请设置 MOONSHOT_API_KEY 环境变量")
        sys.exit(1)
    
    result = analyze_video_complete(args.video_path, args.user_id, args.task_id)
    
    if result['success']:
        print("\n" + result['report'])
        sys.exit(0)
    else:
        print(f"\n错误: {result.get('error', '未知错误')}")
        sys.exit(1)
