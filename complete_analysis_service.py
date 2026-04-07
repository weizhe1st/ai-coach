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
DASHSCOPE_API_KEY = os.environ.get('DASHSCOPE_API_KEY', '')
DB_PATH = '/data/db/xiaolongxia_learning.db'
COS_BUCKET = 'tennis-ai-1411340868'
COS_REGION = 'ap-shanghai'

# 根据模型提供商初始化 client
from core import MODEL_PROVIDER
if MODEL_PROVIDER == 'qwen':
    _api_key = DASHSCOPE_API_KEY
    _base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
else:
    _api_key = MOONSHOT_API_KEY
    _base_url = "https://api.moonshot.cn/v1"
client = OpenAI(api_key=_api_key, base_url=_base_url)

# ═══════════════════════════════════════════════════════════════════
# 数据库操作函数
# ═══════════════════════════════════════════════════════════════════

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json_robust(content: str) -> dict:
    """
    鲁棒 JSON 解析，按优先级依次尝试四种策略：
    策略1: 直接解析（Kimi 输出标准 JSON 时走这里，最快）
    策略2: 提取 markdown 代码块（处理 ```json ... ``` 场景）
    策略3: 提取第一个完整 JSON 对象（处理 Extra data 场景）
    策略4: 截断修复（处理 max_tokens 截断场景）
    策略5: 宽松提取（最后兜底）
    Raises:
        ValueError: 四种策略均失败时抛出，附带原始响应片段用于调试
    """
    import re
    content = content.strip()
    
    # ── 策略1: 直接解析 ──────────────────────────────────────
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # ── 策略2: 提取 markdown 代码块 ──────────────────────────
    # 处理 Kimi 在 JSON 外包了 ```json ... ``` 的情况
    code_block_patterns = [
        r'```json\s*(\{[\s\S]*?\})\s*```',  # ```json ... ```
        r'```\s*(\{[\s\S]*?\})\s*```',      # ``` ... ```
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    
    # ── 策略3: 提取第一个完整 JSON 对象 ──────────────────────
    # 找到第一个 { 的位置，然后用括号计数找到配对的 }
    # 解决 "Extra data" 问题：Kimi 在 JSON 后面追加了解释文字
    brace_start = content.find('{')
    if brace_start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(content[brace_start:], start=brace_start):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        # 找到了配对的 }
                        try:
                            return json.loads(content[brace_start:i+1])
                        except json.JSONDecodeError:
                            pass
                        break
    
    # ── 策略4: 截断修复 ──────────────────────────────────────
    # 处理 max_tokens 截断场景：JSON 在最后一个字段处被截断
    # 找到最后一个完整的字段，然后补全 JSON
    truncated_patterns = [
        # 在字符串值中间截断: "key": "value...
        (r'("\w+":\s*"[^"]*)(?:[^"}]*)$', r'\1"}'),
        # 在数字值后面截断: "key": 123...
        (r'("\w+":\s*\d+)(?:[^\d}]*)$', r'\1}'),
        # 在数组/对象中间截断
        (r'("\w+":\s*\[[^\]]*)(?:[^\]]*)$', r'\1]}'),
        (r'("\w+":\s*\{[^}]*)(?:[^}]*)$', r'\1}}'),
    ]
    
    for pattern, replacement in truncated_patterns:
        fixed = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        if fixed != content:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
    
    # ── 策略5: 宽松提取（最后兜底）───────────────────────────
    # 使用更宽松的模式，尝试提取任何看起来像 JSON 对象的内容
    json_like_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_like_pattern, content, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # 所有策略都失败
    raise ValueError(f"无法解析 JSON，已尝试5种策略。原始内容前500字: {content[:500]}")


def _call_kimi_with_retry(client, file_id, user_text=None, max_retries=3, base_delay=5):
    """调用 Kimi API，失败自动重试"""
    last_error = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = base_delay * attempt
            print(f"[重试] 第{attempt}次重试，等待{wait}秒... (上次错误: {last_error})")
            time.sleep(wait)
        
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "video_url", "video_url": {"url": f"ms://{file_id}"}},
                        {"type": "text", "text": f"""请严格按照三步分析法分析这段网球发球视频：

第一步（逐帧观察）：逐阶段描述你看到的具体动作，每个阶段覆盖系统提示中的所有锚点，看不清的写"不可见"。
第二步（标准对照）：将观察结果与三位教练标准对照，明确每个锚点的达标/不达标情况。
第三步（输出JSON）：基于前两步推导，填写最终JSON，不得跳过前两步直接给出结论。

{user_text or ''}

只输出JSON，不含任何其他内容。"""}
                    ]}
                ],
                temperature=1,
                max_tokens=6000,
                timeout=300
            )
            content = response.choices[0].message.content
            return _parse_json_robust(content)
                
        except ValueError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt == max_retries:
                raise RuntimeError(f"Kimi API 调用失败，已重试{max_retries}次。最后错误: {last_error}")
            continue
    
    raise RuntimeError("不应到达此处")

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

def _get_cos_url_for_video(video_path: str, task_id: str = None) -> str:
    """
    根据 video_path 或 task_id 获取对应的 COS URL。
    优先从数据库的 video_analysis_tasks + videos 表查询。
    """
    # 方式1：从数据库查询（task_id 已知时）
    if task_id:
        try:
            conn = get_db_connection()
            row = conn.execute('''
                SELECT v.cos_url
                FROM video_analysis_tasks t
                JOIN videos v ON t.video_id = v.id
                WHERE t.id = ?
            ''', (task_id,)).fetchone()
            conn.close()
            if row and row['cos_url']:
                return row['cos_url']
        except Exception as e:
            print(f"  ⚠ 数据库查询COS URL失败: {e}")
    
    # 方式2：从数据库按文件名查询
    file_name = os.path.basename(video_path)
    try:
        conn = get_db_connection()
        row = conn.execute('''
            SELECT cos_url FROM videos
            WHERE file_name = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (file_name,)).fetchone()
        conn.close()
        if row and row['cos_url']:
            return row['cos_url']
    except Exception as e:
        print(f"  ⚠ 按文件名查询COS URL失败: {e}")
    
    # 方式3：构造COS URL（兜底）
    file_name = os.path.basename(video_path)
    cos_url = f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/private-ai-learning/raw_videos/{datetime.now().strftime('%Y-%m-%d')}/{file_name}"
    print(f"  ⚠ 使用构造的COS URL: {cos_url[:60]}...")
    return cos_url

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
        
        # 关键词映射表 - 将常见描述映射到知识库中的关键词
        keyword_mapping = {
            '膝盖蓄力': ['膝盖', '蓄力', '弯曲', '重心', 'loading', '奖杯'],
            '抛球': ['抛球', 'toss', '释放', '落点'],
            '奖杯姿势': ['奖杯', 'trophy', '肘部', '肩膀', 'loading'],
            '旋内': ['旋内', 'pron', '包裹', '刷球', 'contact'],
            '随挥': ['随挥', 'follow', '收拍', 'follow-through'],
            '击球点': ['击球点', 'contact', '高度', '最高点'],
            '握拍': ['握拍', 'grip', '大陆式'],
            '重心': ['重心', '平衡', '转移', '蹬地']
        }
        
        results = []
        for tag in issue_tags:
            tag_str = tag if isinstance(tag, str) else str(tag)
            
            # 扩展搜索关键词
            search_terms = [tag_str]
            for key, synonyms in keyword_mapping.items():
                if key in tag_str:
                    search_terms.extend(synonyms)
            
            # 去重并限制数量
            search_terms = list(set(search_terms))[:5]
            
            for term in search_terms:
                cursor.execute('''
                    SELECT coach_name, knowledge_type, title, summary, 
                           key_elements, common_errors, correction_method
                    FROM coach_knowledge
                    WHERE summary LIKE ? OR title LIKE ? OR key_elements LIKE ?
                    ORDER BY quality_grade DESC, confidence DESC
                    LIMIT 2
                ''', (f'%{term}%', f'%{term}%', f'%{term}%'))
                
                for row in cursor.fetchall():
                    content = f"{row['title']}：{row['summary']}"
                    if row['key_elements']:
                        content += f"\n关键要素：{row['key_elements']}"
                    if row['common_errors']:
                        content += f"\n常见错误：{row['common_errors']}"
                    if row['correction_method']:
                        content += f"\n纠正方法：{row['correction_method']}"
                    
                    results.append({
                        'coach': row['coach_name'],
                        'phase': row['knowledge_type'],
                        'content': content,
                        'quality': 'A'
                    })
        
        conn.close()
        # 去重
        seen = set()
        unique_results = []
        for r in results:
            key = (r['coach'], r['content'][:50])
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        return unique_results[:10]  # 最多返回10条
    except Exception as e:
        print(f"  [知识库] 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def query_similar_cases_from_db(level, limit=3):
    """从数据库查询相似案例 - 使用 level_gold_standards 表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询黄金标准样本
        cursor.execute('''
            SELECT id, level, description, reference_sample_id, sample_count, standards_json
            FROM level_gold_standards
            WHERE level = ?
            ORDER BY sample_count DESC
            LIMIT ?
        ''', (level, limit))
        
        results = []
        for row in cursor.fetchall():
            try:
                standards = json.loads(row['standards_json']) if row['standards_json'] else {}
            except:
                standards = {}
            
            results.append({
                'id': row['id'],
                'level': row['level'],
                'score': 75,  # 默认分数
                'description': f"[{row['level']}级] {row['description']} (样本数: {row['sample_count']})",
                'features': standards
            })
        
        conn.close()
        return results
    except Exception as e:
        print(f"  [案例库] 查询失败: {e}")
        import traceback
        traceback.print_exc()
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
        
        # 3+4. 视觉分析（Qwen-VL 直接用 COS URL，无需上传）
        print("\n[3/8] 准备视频输入...")
        mp_formatted = format_for_kimi(mp_result['metrics'], mp_result['data_quality']) if mp_result else None
        
        # 构建 user message 文本（三步分析法指引 + MediaPipe 数据）
        user_text = f"""请严格按照三步分析法分析这段网球发球视频：
第一步（逐帧观察）：逐阶段描述你看到的具体动作，每个阶段覆盖系统提示中的所有锚点，看不清的写"不可见"。
第二步（标准对照）：将观察结果与三位教练标准对照，明确每个锚点的达标/不达标情况。
第三步（输出JSON）：基于前两步推导，填写最终JSON，不得跳过前两步直接给出结论。
{mp_formatted or ''}
只输出JSON，不含任何其他内容。"""
        
        # 根据提供商选择视频传入方式
        if MODEL_PROVIDER == 'qwen':
            # Qwen-VL：直接传 COS URL（视频已在 COS 上）
            # 从 task_id 或 video_path 推断 COS URL
            cos_url = _get_cos_url_for_video(video_path, task_id)
            print(f"\n[4/8] Qwen-VL 视觉分析（COS URL）...")
            print(f"  视频URL: {cos_url[:60]}...")
            video_content = {"type": "video_url", "video_url": {"url": cos_url}}
            file_object = None  # Qwen-VL 不需要上传
        else:
            # Kimi：先上传文件
            print(f"\n[3/8] 上传视频到 Moonshot...")
            file_object = client.files.create(file=Path(video_path), purpose="video")
            print(f"  ✓ 上传成功: {file_object.id}")
            print(f"\n[4/8] Kimi K2.5 视觉分析...")
            video_content = {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}}
        
        # 构建消息
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                video_content,
                {"type": "text", "text": user_text}
            ]}
        ]
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=1,
            max_tokens=6000
        )
        
        # 解析结果
        result_text = response.choices[0].message.content
        analysis_result = _parse_json_robust(result_text)
        
        print(f"  ✓ {MODEL_PROVIDER.upper()} 分析完成")
        
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
        total_knowledge = 0
        for phase_name, phase_data in phases.items():
            # 使用中文 issues 而不是英文 issue_tags
            issues = phase_data.get('issues', [])
            if issues:
                knowledge_results[phase_name] = query_unified_knowledge(ntrp_level, phase_name, issues)
                total_knowledge += len(knowledge_results[phase_name])
                print(f"  [{phase_name}] 召回 {len(knowledge_results[phase_name])} 条知识点")
        
        # 添加到结果
        analysis_result['knowledge_recall'] = knowledge_results
        analysis_result['knowledge_recall_count'] = total_knowledge
        print(f"  ✓ 知识库查询完成，共 {total_knowledge} 条")
        
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
        
        # 生成完整报告 - 转换知识库格式以兼容 generate_complete_report
        # knowledge_results 是 {phase: [items]}，需要转换为 {phase: {coach: [items]}}
        formatted_knowledge = {}
        for phase, items in knowledge_results.items():
            formatted_knowledge[phase] = {}
            for item in items:
                coach = item.get('coach', 'Unknown')
                if coach not in formatted_knowledge[phase]:
                    formatted_knowledge[phase][coach] = []
                formatted_knowledge[phase][coach].append(item)
        
        report = generate_complete_report(analysis_result, quality_info, formatted_knowledge, similar_cases)
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
