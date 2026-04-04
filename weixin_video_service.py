#!/usr/bin/env python3
"""
微信视频处理服务 - 完整版，包含知识库、样本库、黄金标准
"""

import os
import sys
import json
import time
import sqlite3
import urllib.request
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# 导入共享模块
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
KNOWLEDGE_BASE_URL = 'https://tennis-ai-1411340868.cos.ap-shanghai.myqcloud.com/coaches/unified_knowledge_base/merged/unified_knowledge_v3.json'

client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.cn/v1")

# 知识库缓存
_knowledge_base_cache = None

def load_knowledge_base():
    """加载知识库"""
    global _knowledge_base_cache
    if _knowledge_base_cache:
        return _knowledge_base_cache
    
    try:
        local_path = '/tmp/unified_knowledge_v3.json'
        if os.path.exists(local_path):
            with open(local_path, 'r', encoding='utf-8') as f:
                _knowledge_base_cache = json.load(f)
                return _knowledge_base_cache
        
        req = urllib.request.Request(KNOWLEDGE_BASE_URL)
        with urllib.request.urlopen(req, timeout=30) as response:
            _knowledge_base_cache = json.loads(response.read().decode('utf-8'))
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(_knowledge_base_cache, f, ensure_ascii=False)
            return _knowledge_base_cache
    except Exception as e:
        print(f"[Knowledge] 加载失败: {e}")
        return {'knowledge_items': []}

# 自然语言描述 → 知识库标准 tag 的映射
# key: 自然语言中的关键词（小写），value: 对应的标准 tag
ISSUE_KEYWORD_TO_TAG = {
    '膝盖': 'weak_loading',
    '蓄力': 'weak_loading',
    '抛球': 'toss_backward',
    '偏内': 'toss_backward',
    '偏后': 'toss_backward',
    '抛球过低': 'toss_too_low',
    '抛球过高': 'toss_too_high',
    '旋内': 'incomplete_pronation',
    '收拍': 'incomplete_follow_through',
    '随挥': 'incomplete_follow_through',
    '肘部': 'trophy_not_reached',
    '奖杯': 'trophy_not_reached',
    '站位': 'stance_width_error',
    '握拍': 'grip_error',
    '击球点': 'low_contact_point',
    '击球低': 'low_contact_point',
}

def issues_to_tags(issues: list) -> list:
    """
    将自然语言 issues 列表转换为知识库标准 tag 列表。
    同时保留原始文本，用于内容匹配兜底。
    """
    tags = []
    for issue in issues:
        if not isinstance(issue, str):
            continue
        issue_lower = issue.lower()
        for keyword, tag in ISSUE_KEYWORD_TO_TAG.items():
            if keyword in issue_lower and tag not in tags:
                tags.append(tag)
    # 如果没有匹配到任何 tag，返回原始文本列表（触发内容匹配兜底）
    return tags if tags else issues

def recall_knowledge(phase, issue_tags, limit=2):
    """召回知识点"""
    # 将自然语言转换为标准 tag
    issue_tags = issues_to_tags(issue_tags)
    
    knowledge_base = load_knowledge_base()
    knowledge_items = knowledge_base.get('knowledge_items', [])
    
    if not knowledge_items:
        return {}
    
    coach_map = {
        'coach_yangchao': '杨超',
        'coach_zhaolingxi': '赵凌曦',
        'coach_yellow': 'Yellow'
    }
    
    coaches = {'杨超': [], '赵凌曦': [], 'Yellow': []}
    
    for item in knowledge_items:
        item_phases = item.get('phase', [])
        if isinstance(item_phases, str):
            item_phases = [item_phases]
        
        phase_match = phase in item_phases
        
        item_tags = item.get('issue_tags', [])
        matched_tags = [tag for tag in issue_tags if tag in item_tags]
        tag_match = len(matched_tags) > 0
        
        content_match = False
        if not phase_match and not tag_match and issue_tags:
            summary = item.get('knowledge_summary', '')
            title = item.get('title', '')
            content = summary + title
            for tag in issue_tags:
                if tag in content:
                    content_match = True
                    break
        
        if phase_match or tag_match or content_match:
            score = 0
            if phase_match:
                score += 0.4
            if tag_match:
                score += 0.4 * len(matched_tags) / len(issue_tags) if issue_tags else 0
            if content_match:
                score += 0.2
            
            quality = item.get('quality_grade', 'C')
            if quality == 'A':
                score += 0.1
            elif quality == 'B':
                score += 0.05
            
            item_with_score = {**item, 'match_score': score}
            coach_id = item.get('coach_id', 'Unknown')
            coach_name = coach_map.get(coach_id, 'Unknown')
            if coach_name in coaches:
                coaches[coach_name].append(item_with_score)
    
    for coach in coaches:
        coaches[coach] = sorted(coaches[coach], key=lambda x: x.get('match_score', 0), reverse=True)[:limit]
    
    return coaches

def get_similar_cases(level, limit=3):
    """获取相似案例"""
    try:
        gold_path = '/root/.openclaw/workspace/level_sample_library/gold_standard.json'
        if os.path.exists(gold_path):
            with open(gold_path, 'r') as f:
                data = json.load(f)
            level_data = data.get('by_level', {}).get(level, {})
            return level_data.get('all_samples', [])[:limit]
    except Exception as e:
        print(f"[SimilarCases] 获取失败: {e}")
    return []

def get_level_standards(level):
    """获取等级标准"""
    default_standards = {
        '2.0': {'name': '入门', 'description': '动作不完整，无背挠，抛球不稳'},
        '2.5': {'name': '初级', 'description': '动作基本完整，但质量一般'},
        '3.0': {'name': '基础', 'description': '框架完整但执行质量一般'},
        '3.5': {'name': '进阶', 'description': '框架完整有流畅性'},
        '4.0': {'name': '熟练', 'description': '流畅连贯，膝盖深蹲'},
        '4.5': {'name': '高级', 'description': '高度流畅，明确旋转意图'},
        '5.0': {'name': '精通', 'description': '教科书标准，完整动力链'},
        '5.0+': {'name': '专业', 'description': '职业水平，完美动力链'}
    }
    return default_standards.get(level, {'name': '未知', 'description': ''})


def check_level_consistency(result: dict) -> dict:
    """
    用黄金标准样本库对 Kimi 定级做一致性校验。
    
    校验维度：
    1. 等级偏差：与同等级样本的平均分对比
    2. 阶段分异常：某阶段分与同等级样本差距超过20分
    3. 置信度过低：低于0.6时标记为不可靠
    
    Returns:
        dict: 包含校验结果和警告信息
    """
    warnings = []
    ntrp_level = result.get('ntrp_level', '3.0')
    overall_score = result.get('overall_score', 50)
    confidence = result.get('confidence', 0.5)
    phase_analysis = result.get('phase_analysis', {})
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # 1. 检查同等级样本的平均分
        avg_row = conn.execute("""
            SELECT AVG(overall_score) as avg_score, COUNT(*) as cnt
            FROM gold_standard_samples
            WHERE level = ? AND status = 'active'
        """, (ntrp_level,)).fetchone()
        
        if avg_row and avg_row['cnt'] > 0:
            avg_score = avg_row['avg_score']
            score_diff = abs(overall_score - avg_score)
            
            # 如果偏差超过15分，发出警告
            if score_diff > 15:
                warnings.append(
                    f"总分异常：{overall_score}分，"
                    f"同等级{ntrp_level}样本平均{avg_score:.1f}分，"
                    f"偏差{score_diff:.1f}分"
                )
        
        # 2. 检查阶段分异常
        phase_scores = {}
        for phase_key in ['ready', 'toss', 'loading', 'contact', 'follow']:
            phase_data = phase_analysis.get(phase_key, {})
            if isinstance(phase_data, dict):
                phase_scores[phase_key] = phase_data.get('score', 50)
        
        if phase_scores:
            # 查询同等级样本的阶段平均分
            for phase_key, score in phase_scores.items():
                avg_phase_row = conn.execute(f"""
                    SELECT AVG(
                        CASE 
                            WHEN json_extract(phase_analysis, '$.{phase_key}.score') IS NOT NULL
                            THEN json_extract(phase_analysis, '$.{phase_key}.score')
                            ELSE 50
                        END
                    ) as avg_phase_score
                    FROM gold_standard_samples
                    WHERE level = ? AND status = 'active'
                """, (ntrp_level,)).fetchone()
                
                if avg_phase_row and avg_phase_row['avg_phase_score']:
                    avg_phase = avg_phase_row['avg_phase_score']
                    phase_diff = abs(score - avg_phase)
                    
                    if phase_diff > 20:
                        warnings.append(
                            f"阶段分异常：{phase_key}={score}分，"
                            f"同等级平均{avg_phase:.1f}分，"
                            f"偏差{phase_diff:.1f}分"
                        )
        
        conn.close()
        
    except Exception as e:
        print(f"[一致性校验] 查询样本库失败: {e}")
    
    # 3. 检查置信度
    if confidence < 0.6:
        warnings.append(f"置信度过低：{confidence:.2f}，建议人工复核")
    
    return {
        'level': ntrp_level,
        'score': overall_score,
        'confidence': confidence,
        'warnings': warnings,
        'is_consistent': len(warnings) == 0
    }

def _parse_json_robust(content: str) -> dict:
    """
    鲁棒 JSON 解析，按优先级依次尝试四种策略：
    策略1: 直接解析（Kimi 输出标准 JSON 时走这里，最快）
    策略2: 提取第一个完整 JSON 对象（处理 Extra data 场景）
    策略3: 截断修复（处理 max_tokens 截断场景）
    策略4: 宽松提取（最后兜底）
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
    
    # ── 策略2: 提取第一个完整 JSON 对象 ──────────────────────
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
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = content[brace_start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # 括号匹配到了但内容有问题，继续下一策略
    
    # ── 策略3: 截断修复 ──────────────────────────────────────
    # 处理 max_tokens 截断导致的不完整 JSON
    # 找到最后一个完整的顶级字段，截断到那里并补全结构
    if brace_start != -1:
        truncated = content[brace_start:]
        # 找到最后一个完整的键值对结束位置（逗号或嵌套对象结束）
        # 策略：从末尾倒找最后一个完整的 "key": ... 结构
        last_complete = -1
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(truncated):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ('{', '['):
                depth += 1
            elif ch in ('}', ']'):
                depth -= 1
                if depth == 1:  # 回到顶层，记录位置
                    last_complete = i
        if last_complete > 0:
            # 在最后一个完整嵌套结构后截断并补全
            repaired = truncated[:last_complete + 1].rstrip().rstrip(',') + '\n}'
            try:
                result = json.loads(repaired)
                print(f"  ⚠ JSON 截断修复成功（补全了 {len(content) - last_complete} 字符）")
                # 补全缺失的必要字段防止校验失败
                result.setdefault('ntrp_level', '3.0')
                result.setdefault('confidence', 0.5)
                result.setdefault('overall_score', 50)
                result.setdefault('detection_notes', '输出被截断，部分字段已自动补全')
                if 'phase_analysis' not in result:
                    result['phase_analysis'] = {
                        p: {'score': 50, 'observations': [], 'issues': [], 'coach_reference': []}
                        for p in ['ready', 'toss', 'loading', 'contact', 'follow']
                    }
                return result
            except json.JSONDecodeError:
                pass
    
    # ── 策略4: 宽松正则提取（最后兜底）────────────────────────
    # 处理 Kimi 在 JSON 外包了 markdown 代码块的情况
    patterns = [
        r'```json\s*(\{.*?\})\s*```',  # ```json ... ```
        r'```\s*(\{.*?\})\s*```',      # ``` ... ```
        r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',  # 嵌套一层的简单 JSON
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    
    # 全部策略失败
    preview = content[:300].replace('\n', ' ')
    raise ValueError(
        f"JSON 解析失败（已尝试 4 种策略）。\n"
        f"原始响应前300字符: {preview}\n"
        f"总长度: {len(content)} 字符"
    )


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

def save_analysis(user_id, video_path, result, quality_info):
    """保存分析结果"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weixin_analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                video_path TEXT,
                ntrp_level TEXT,
                ntrp_level_name TEXT,
                confidence REAL,
                overall_score REAL,
                serves_observed INTEGER,
                phase_analysis TEXT,
                key_issues TEXT,
                training_plan TEXT,
                full_result TEXT,
                quality_info TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT INTO weixin_analysis_results 
            (user_id, video_path, ntrp_level, ntrp_level_name, confidence, overall_score,
             serves_observed, phase_analysis, key_issues, training_plan,
             full_result, quality_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            video_path,
            result.get('ntrp_level'),
            result.get('ntrp_level_name'),
            result.get('confidence'),
            result.get('overall_score'),
            result.get('serves_observed'),
            json.dumps(result.get('phase_analysis', {}), ensure_ascii=False),
            json.dumps(result.get('key_issues', []), ensure_ascii=False),
            json.dumps(result.get('training_plan', []), ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            json.dumps(quality_info, ensure_ascii=False)
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"保存失败: {e}")
        return False

def analyze_video(video_path, user_id=None):
    """分析视频 - 完整版"""
    print(f"[分析服务] 开始分析: {video_path}")
    
    # 1. 输入质量检查
    passed, quality_info = check_input_quality(video_path)
    if not passed:
        return {
            "success": False,
            "error": quality_info['reason'],
            "report": f"❌ 视频质量检查未通过\n\n原因：{quality_info['reason']}"
        }
    
    file_object = None
    try:
        # 2. MediaPipe 辅助分析（可选，失败不影响主流程）
        mp_result = None
        mp_formatted_text = None
        
        if MEDIAPIPE_ENABLED:
            try:
                print("[分析服务] MediaPipe 提取量化指标...")
                mp_result = extract_pose_metrics(video_path)
                if mp_result:
                    print(f"  ✓ MediaPipe 完成，有效帧: {mp_result.get('raw_samples', 0)}")
                    # 格式化为 Kimi 可读的辅助文字
                    mp_formatted_text = format_for_kimi(mp_result['metrics'], mp_result['data_quality'])
                    print(f"    辅助文字预览：{mp_formatted_text[:100]}...")
                else:
                    print("  ⚠ MediaPipe 未返回结果，继续Kimi分析")
            except Exception as e:
                print(f"  ⚠ MediaPipe 失败: {e}，继续Kimi分析（不影响主流程）")
                mp_result = None
        else:
            print("[分析服务] MediaPipe 已禁用，跳过")
        
        # 3. 上传视频到 Kimi
        print(f"[分析服务] 上传视频到 Moonshot...")
        file_object = client.files.create(file=Path(video_path), purpose="video")
        print(f"[分析服务] 视频上传成功: {file_object.id}")
        
        # 3. 调用 Kimi 分析（带重试）
        print("[分析服务] 调用 Kimi K2.5 分析视频（最多重试3次，超时60秒）...")
        try:
            result = _call_kimi_with_retry(client, file_object.id, user_text=mp_formatted_text, max_retries=3, base_delay=5)
            print("  ✓ Kimi 分析完成")
        except RuntimeError as e:
            return {
                "success": False,
                "error": str(e),
                "report": "❌ 视频分析服务暂时不可用，请稍后重试\n（Kimi API 多次重试后仍失败）"
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "report": "❌ 分析结果格式异常，请重新上传视频"
            }
        
        # 4. JSON 校验
        is_valid, errors, validated_result = validate_response(result)
        
        # 5. 整合 MediaPipe 量化指标（如果有）
        if mp_result:
            print("[分析服务] 整合 MediaPipe 量化指标...")
            validated_result = enhance_vision_result_with_mediapipe(validated_result, mp_result)
            
            # 显示一致性检查
            comparison = validated_result.get('_mp_comparison', {})
            if comparison.get('knee_level_discrepancy'):
                disc = comparison['knee_level_discrepancy']
                print(f"  ⚠ 评级差异: Vision={disc['vision_level']}, 膝盖指标={disc['knee_inferred_level']}")
            print("  ✓ 整合完成")
        
        # 6. 查询知识库
        print("[分析服务] 查询教练知识库...")
        knowledge_results = {}
        phases = validated_result.get('phase_analysis', {})
        for phase_key, phase_data in phases.items():
            # 兼容 issue_tags 和 issues 两种字段名
            issue_tags = phase_data.get('issue_tags', []) or phase_data.get('issues', [])
            if issue_tags:
                knowledge_results[phase_key] = recall_knowledge(phase_key, issue_tags)
                print(f"  [{phase_key}] 召回 {len(knowledge_results[phase_key])} 位教练的知识点")
        print(f"  ✓ 知识库查询完成")
        
        # 6. 查询相似案例
        print("[分析服务] 查询相似案例...")
        ntrp_level = validated_result.get('ntrp_level', '3.0')
        similar_cases = get_similar_cases(ntrp_level)
        print(f"  ✓ 找到 {len(similar_cases)} 个相似案例")
        
        # 7. 获取等级标准
        level_standards = get_level_standards(ntrp_level)
        
        # 8. 生成完整报告
        print("[分析服务] 生成完整报告...")
        # 从 validated_result 中取出已整合的量化指标传给报告生成器
        mp_metrics_for_report = validated_result.get('quantitative_metrics') if mp_result else None
        report = generate_complete_report(
            validated_result, 
            quality_info, 
            knowledge_results, 
            similar_cases,
            mp_metrics_for_report,
            level_standards
        )
        print("  ✓ 完整报告生成完成")
        
        # 9. 保存到数据库
        save_analysis(user_id, video_path, validated_result, quality_info)
        
        return {
            "success": True,
            "result": validated_result,
            "report": report,
            "knowledge_results": knowledge_results,
            "similar_cases": similar_cases
        }
        
    except Exception as e:
        print(f"[错误] 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        # 10. 清理文件
        if file_object and hasattr(file_object, 'id'):
            try:
                client.files.delete(file_object.id)
                print("[分析服务] ✓ 已清理上传的文件")
            except:
                pass

# 测试入口
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('video_path')
    parser.add_argument('--user-id', default='test')
    args = parser.parse_args()
    
    if not MOONSHOT_API_KEY:
        print("错误: 请设置 MOONSHOT_API_KEY")
        sys.exit(1)
    
    result = analyze_video(args.video_path, args.user_id)
    
    if result['success']:
        print(result['report'])
    else:
        print(f"失败: {result.get('error', '')}")
