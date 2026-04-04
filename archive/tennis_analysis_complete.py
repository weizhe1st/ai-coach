#!/usr/bin/env python3
"""
整合版网球发球分析系统
视频 → COS存储 → Kimi视觉分析 → 量化指标 → 知识库查询 → 科学评级 → 详细报告
"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import traceback
import requests
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# 导入共享模块
from core import (
    PROMPT_VERSION, KNOWLEDGE_BASE_VERSION, MODEL_NAME,
    SYSTEM_PROMPT, check_input_quality, validate_response
)

# 配置
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
DB_PATH = '/data/db/xiaolongxia_learning.db'
COS_BUCKET = 'tennis-ai-1411340868'
COS_REGION = 'ap-shanghai'
COS_BASE_URL = f'https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com'

client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.cn/v1")

# ═══════════════════════════════════════════════
# COS 上传功能
# ═══════════════════════════════════════════════
def upload_to_cos(local_path, cos_key):
    """上传文件到腾讯云COS"""
    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.cos.v20190318 import cos_client, models
        
        # 从环境变量获取密钥
        secret_id = os.environ.get('TENCENT_SECRET_ID')
        secret_key = os.environ.get('TENCENT_SECRET_KEY')
        
        if not secret_id or not secret_key:
            print(f"[COS] 未配置腾讯云密钥，跳过上传")
            return None
        
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "cos.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        
        cos_cli = cos_client.CosClient(cred, COS_REGION, client_profile)
        
        with open(local_path, 'rb') as f:
            cos_cli.UploadFile(
                Bucket=COS_BUCKET,
                Key=cos_key,
                Body=f
            )
        
        cos_url = f"{COS_BASE_URL}/{cos_key}"
        print(f"[COS] 上传成功: {cos_url}")
        return cos_url
        
    except Exception as e:
        print(f"[COS] 上传失败: {e}")
        return None


# ═══════════════════════════════════════════════
# 知识库查询
# ═══════════════════════════════════════════════
def query_knowledge_base(level, phase, issue_type=None):
    """
    查询三教练知识库
    
    Args:
        level: NTRP等级 (如 '3.0')
        phase: 阶段 (ready/toss/loading/contact/follow)
        issue_type: 问题类型 (可选)
    
    Returns:
        dict: 包含三位教练的建议
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 查询知识库
        cursor.execute('''
            SELECT coach_name, content, evidence_count
            FROM unified_knowledge
            WHERE level = ? AND phase = ?
            ORDER BY evidence_count DESC
            LIMIT 10
        ''', (level, phase))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 按教练分组
        coaches = {'杨超': [], '赵凌曦': [], 'Yellow': []}
        for row in rows:
            coach, content, evidence = row
            if coach in coaches:
                coaches[coach].append({
                    'content': content,
                    'evidence': evidence
                })
        
        return coaches
        
    except Exception as e:
        print(f"[Knowledge] 查询失败: {e}")
        return {}


def query_gold_standard(level):
    """查询黄金标准"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT standards_json FROM level_gold_standards WHERE level = ?",
            (level,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        print(f"[GoldStandard] 查询失败: {e}")
    return None


# ═══════════════════════════════════════════════
# 量化评级系统
# ═══════════════════════════════════════════════
def compute_level_from_metrics(metrics):
    """
    基于量化指标计算NTRP等级
    
    关键指标:
    - min_knee_angle: 膝盖最小角度 (深蹲程度)
    - max_elbow_angle: 肘部最大角度 (奖杯姿势)
    - contact_height: 击球点高度
    - stance_width: 站位宽度
    """
    # 黄金标准定义
    LEVEL_MODELS = {
        '5.0+': {
            'min_knee_angle': (90, 110),
            'max_elbow_angle': (170, 180),
            'contact_height': (1.8, 2.2),
            'stance_width': (1.3, 1.6)
        },
        '5.0': {
            'min_knee_angle': (100, 120),
            'max_elbow_angle': (165, 175),
            'contact_height': (1.7, 2.0),
            'stance_width': (1.2, 1.5)
        },
        '4.0': {
            'min_knee_angle': (110, 130),
            'max_elbow_angle': (160, 170),
            'contact_height': (1.6, 1.9),
            'stance_width': (1.1, 1.4)
        },
        '3.0': {
            'min_knee_angle': (120, 140),
            'max_elbow_angle': (150, 165),
            'contact_height': (1.5, 1.8),
            'stance_width': (1.0, 1.3)
        },
        '2.0': {
            'min_knee_angle': (130, 160),
            'max_elbow_angle': (140, 160),
            'contact_height': (1.4, 1.7),
            'stance_width': (0.9, 1.2)
        }
    }
    
    level_scores = {}
    for level, standards in LEVEL_MODELS.items():
        score = 0
        total = 0
        for metric, value in metrics.items():
            if metric in standards:
                min_val, max_val = standards[metric]
                if min_val <= value <= max_val:
                    score += 1
                total += 1
        if total > 0:
            level_scores[level] = score / total
    
    # 选择得分最高的等级
    if level_scores:
        best_level = max(level_scores, key=level_scores.get)
        confidence = level_scores[best_level]
        return best_level, confidence, level_scores
    
    return '2.0', 0.5, {}


def assess_detection_quality(metrics):
    """评估检测质量"""
    total_expected = 5
    valid_count = len(metrics)
    
    if valid_count < 3:
        return 'insufficient', f'仅{valid_count}个有效指标'
    
    # 检查指标一致性
    knee = metrics.get('min_knee_angle', 0)
    elbow = metrics.get('max_elbow_angle', 0)
    
    if knee > 0 and elbow > 0:
        # 膝盖角度越小越好，肘部角度越大越好
        if knee > 140 and elbow < 150:
            return 'contradictory', '膝盖和肘部指标矛盾'
    
    return 'reliable', '检测可靠'


# ═══════════════════════════════════════════════
# 详细报告生成
# ═══════════════════════════════════════════════
def generate_detailed_report(kimi_result, metrics, gold_standard, knowledge_base):
    """生成详细分析报告"""
    
    ntrp_level = kimi_result.get('ntrp_level', '3.0')
    confidence = kimi_result.get('confidence', 0.75)
    overall_score = kimi_result.get('overall_score', 55)
    
    report = f"""
🎾 **网球发球技术详细分析报告**

═══════════════════════════════════════════

📊 **一、综合评估**

┌─────────────────────────────────────────┐
│ NTRP等级: {ntrp_level}级                          │
│ 置信度: {confidence:.1%}                              │
│ 总分: {overall_score}/100                            │
│ 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}          │
└─────────────────────────────────────────┘

"""
    
    # 量化指标对比
    if metrics:
        report += """
📏 **二、量化指标分析**

| 指标 | 实测值 | 黄金标准 | 符合度 |
|------|--------|----------|--------|
"""
        if gold_standard and 'key_features' in gold_standard:
            for metric, value in metrics.items():
                if metric in gold_standard['key_features']:
                    std_range = gold_standard['key_features'][metric]
                    if isinstance(std_range, (list, tuple)):
                        std_str = f"{std_range[0]}-{std_range[1]}"
                        # 计算符合度
                        if std_range[0] <= value <= std_range[1]:
                            match = "✅"
                        else:
                            match = "❌"
                        report += f"| {metric} | {value:.1f} | {std_str} | {match} |\n"
    
    # 五阶段详细分析
    report += """

📈 **三、五阶段详细分析**

"""
    phases = kimi_result.get('phase_analysis', {})
    phase_names = {
        'ready': '🎾 准备阶段',
        'toss': '☝️ 抛球阶段',
        'loading': '💪 蓄力阶段',
        'contact': '⚡ 击球阶段',
        'follow': '🌊 随挥阶段'
    }
    
    for phase_key, phase_name in phase_names.items():
        phase_data = phases.get(phase_key, {})
        score = phase_data.get('score', 0)
        observations = phase_data.get('observations', [])
        issues = phase_data.get('issues', [])
        
        stars = '★' * (score // 20) + '☆' * (5 - score // 20)
        
        report += f"""
{phase_name} {stars} ({score}分)
"""
        if observations:
            report += f"  📋 观察: {observations[0]}\n"
        if issues:
            report += f"  ⚠️ 问题: {issues[0]}\n"
        
        # 添加教练建议
        if knowledge_base and phase_key in knowledge_base:
            report += f"  💡 教练建议:\n"
            for coach, tips in knowledge_base[phase_key].items():
                if tips:
                    report += f"    • {coach}: {tips[0]['content'][:50]}...\n"
    
    # 关键改进点
    key_issues = kimi_result.get('key_issues', [])
    if key_issues:
        report += """

🔴 **四、关键改进点（按优先级排序）**

"""
        for i, issue in enumerate(key_issues[:5], 1):
            severity = issue.get('severity', 'medium')
            emoji = '🔴' if severity == 'high' else '🟡' if severity == 'medium' else '🟢'
            report += f"{i}. {emoji} {issue.get('issue', '')}\n"
            if 'coach_advice' in issue:
                report += f"   💡 {issue['coach_advice']}\n"
    
    # 训练计划
    training_plan = kimi_result.get('training_plan', [])
    if training_plan:
        report += """

💪 **五、个性化训练计划**

"""
        for i, plan in enumerate(training_plan, 1):
            report += f"{i}. {plan}\n"
    
    # 等级判定依据
    level_reasoning = kimi_result.get('level_reasoning', '')
    if level_reasoning:
        report += f"""

📝 **六、等级判定依据**

{level_reasoning}
"""
    
    # 检测质量
    detection_quality = kimi_result.get('detection_quality', 'reliable')
    detection_notes = kimi_result.get('detection_notes', '')
    report += f"""

ℹ️ **七、检测质量说明**

质量评级: {detection_quality}
{detection_notes}

═══════════════════════════════════════════
💪 坚持练习，每天进步一点点！
"""
    
    return report


# ═══════════════════════════════════════════════
# 主分析流程
# ═══════════════════════════════════════════════
def analyze_video_complete(video_path, user_id=None, upload_cos=True):
    """
    完整的视频分析流程
    
    Args:
        video_path: 本地视频路径
        user_id: 用户ID
        upload_cos: 是否上传到COS
    
    Returns:
        dict: 包含详细报告和分析结果
    """
    print(f"\n{'='*60}")
    print(f"[完整分析系统] 开始分析: {video_path}")
    print(f"{'='*60}")
    
    # 1. 检查输入质量
    passed, quality_info = check_input_quality(video_path)
    if not passed:
        return {
            "success": False,
            "error": quality_info['reason'],
            "report": f"❌ 视频质量检查未通过: {quality_info['reason']}"
        }
    
    # 2. 上传到COS（如果启用）
    cos_url = None
    if upload_cos:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        cos_key = f"videos/{user_id or 'anonymous'}/{timestamp}_{os.path.basename(video_path)}"
        cos_url = upload_to_cos(video_path, cos_key)
    
    file_object = None
    try:
        # 3. 上传视频到Moonshot
        print("[分析] 上传视频到Moonshot...")
        file_object = client.files.create(
            file=Path(video_path),
            purpose="video"
        )
        print(f"[分析] 上传成功: {file_object.id}")
        
        # 4. 调用Kimi分析
        print("[分析] 调用Kimi K2.5分析...")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}},
                    {"type": "text", "text": "请详细分析这段网球发球视频，输出JSON格式的分析结果。重点关注：1)五阶段动作质量 2)量化指标（膝盖角度、肘部角度、击球点高度）3)与标准动作的对比 4)具体的改进建议"}
                ]}
            ],
            temperature=1,
            max_tokens=4000
        )
        
        content = response.choices[0].message.content
        
        # 5. 解析JSON
        try:
            kimi_result = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[分析] JSON解析失败，尝试修复: {e}")
            import re
            # 尝试提取JSON部分
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    json_str = match.group()
                    # 尝试修复常见的JSON错误
                    # 1. 移除末尾的逗号
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    # 2. 修复未闭合的字符串
                    json_str = re.sub(r'"([^"]*)$', r'"\1"', json_str)
                    kimi_result = json.loads(json_str)
                except Exception as e2:
                    print(f"[分析] JSON修复失败: {e2}")
                    # 使用原始响应创建一个简化结果
                    kimi_result = {
                        "ntrp_level": "3.0",
                        "ntrp_level_name": "基础级",
                        "confidence": 0.5,
                        "overall_score": 50,
                        "serves_observed": 1,
                        "phase_analysis": {
                            "ready": {"score": 50, "observations": [], "issues": []},
                            "toss": {"score": 50, "observations": [], "issues": []},
                            "loading": {"score": 50, "observations": [], "issues": []},
                            "contact": {"score": 50, "observations": [], "issues": []},
                            "follow": {"score": 50, "observations": [], "issues": []}
                        },
                        "key_strengths": [],
                        "key_issues": [{"issue": "JSON解析失败，使用默认评级", "severity": "medium"}],
                        "training_plan": ["请重新上传视频进行分析"],
                        "detection_quality": "poor",
                        "detection_notes": f"JSON解析错误: {str(e)[:100]}",
                        "level_reasoning": "由于解析错误，使用默认3.0级评估",
                        "raw_response": content[:500]
                    }
            else:
                return {"success": False, "error": "JSON解析失败"}
        
        # 6. 校验响应
        is_valid, errors, validated_result = validate_response(kimi_result)
        
        # 7. 提取量化指标（从Kimi分析结果中）
        metrics = {}
        phase_analysis = validated_result.get('phase_analysis', {})
        for phase, data in phase_analysis.items():
            if 'metrics' in data:
                metrics.update(data['metrics'])
        
        # 8. 查询黄金标准
        ntrp_level = validated_result.get('ntrp_level', '3.0')
        gold_standard = query_gold_standard(ntrp_level)
        
        # 9. 查询知识库
        knowledge_base = {}
        for phase in ['ready', 'toss', 'loading', 'contact', 'follow']:
            knowledge_base[phase] = query_knowledge_base(ntrp_level, phase)
        
        # 10. 科学评级（如果有量化指标）
        if metrics:
            computed_level, confidence, level_scores = compute_level_from_metrics(metrics)
            # 如果Kimi评级与量化评级差距大，使用量化评级
            if computed_level != ntrp_level:
                print(f"[分析] 评级修正: Kimi={ntrp_level}, 量化={computed_level}")
                validated_result['ntrp_level'] = computed_level
                validated_result['confidence'] = confidence
                validated_result['level_scores'] = level_scores
        
        # 11. 生成详细报告
        detailed_report = generate_detailed_report(
            validated_result, metrics, gold_standard, knowledge_base
        )
        
        # 12. 保存到数据库
        save_analysis_complete(user_id, video_path, cos_url, validated_result, metrics)
        
        print("[分析] ✓ 分析完成")
        
        return {
            "success": True,
            "result": validated_result,
            "report": detailed_report,
            "cos_url": cos_url
        }
        
    except Exception as e:
        print(f"[分析] ✗ 分析失败: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        # 清理Moonshot文件
        if file_object and hasattr(file_object, 'id'):
            try:
                client.files.delete(file_object.id)
                print(f"[分析] ✓ 已清理上传的文件")
            except:
                pass


def save_analysis_complete(user_id, video_path, cos_url, result, metrics):
    """保存完整分析结果到数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tennis_analysis_complete (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                video_path TEXT,
                cos_url TEXT,
                ntrp_level TEXT,
                confidence REAL,
                overall_score REAL,
                phase_analysis TEXT,
                key_issues TEXT,
                training_plan TEXT,
                metrics TEXT,
                full_result TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT INTO tennis_analysis_complete 
            (user_id, video_path, cos_url, ntrp_level, confidence, overall_score,
             phase_analysis, key_issues, training_plan, metrics, full_result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            video_path,
            cos_url,
            result.get('ntrp_level'),
            result.get('confidence'),
            result.get('overall_score'),
            json.dumps(result.get('phase_analysis', {}), ensure_ascii=False),
            json.dumps(result.get('key_issues', []), ensure_ascii=False),
            json.dumps(result.get('training_plan', []), ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False)
        ))
        
        conn.commit()
        conn.close()
        print("[分析] ✓ 结果已保存到数据库")
        return True
    except Exception as e:
        print(f"[分析] ✗ 保存失败: {e}")
        return False


# 测试入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('video_path', help='视频文件路径')
    parser.add_argument('--user-id', default='test_user')
    parser.add_argument('--no-cos', action='store_true', help='不上传到COS')
    
    args = parser.parse_args()
    
    if not MOONSHOT_API_KEY:
        print("错误: 请设置 MOONSHOT_API_KEY 环境变量")
        sys.exit(1)
    
    result = analyze_video_complete(
        args.video_path, 
        args.user_id, 
        upload_cos=not args.no_cos
    )
    
    if result['success']:
        print(result['report'])
        if result.get('cos_url'):
            print(f"\n📎 COS链接: {result['cos_url']}")
    else:
        print(f"分析失败: {result.get('error', '未知错误')}")
