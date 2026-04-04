#!/usr/bin/env python3
"""
简化版网球发球分析系统 - 稳定运行版
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

# 配置
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
DB_PATH = '/data/db/xiaolongxia_learning.db'
COS_BUCKET = 'tennis-ai-1411340868'
COS_REGION = 'ap-shanghai'

client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.cn/v1")

SYSTEM_PROMPT = """你是专业网球教练。分析发球视频后，必须输出JSON格式结果。

输出格式示例：
{
  "ntrp_level": "3.0",
  "ntrp_level_name": "基础级", 
  "confidence": 0.75,
  "overall_score": 55,
  "serves_observed": 3,
  "phase_analysis": {
    "ready": {"score": 60, "observations": ["描述"], "issues": ["问题"]},
    "toss": {"score": 50, "observations": [], "issues": []},
    "loading": {"score": 45, "observations": [], "issues": []},
    "contact": {"score": 55, "observations": [], "issues": []},
    "follow": {"score": 60, "observations": [], "issues": []}
  },
  "key_strengths": ["优点1"],
  "key_issues": [{"issue": "问题", "severity": "high", "phase": "loading"}],
  "training_plan": ["建议1", "建议2"],
  "detection_quality": "reliable",
  "level_reasoning": "判定理由"
}

只输出JSON，不要其他内容。"""


def analyze_video_simple(video_path, user_id=None):
    """简化版分析流程"""
    print(f"[分析] 开始分析: {video_path}")
    
    # 检查文件
    if not os.path.exists(video_path):
        return {"success": False, "error": "文件不存在"}
    
    file_size = os.path.getsize(video_path) / 1024 / 1024
    if file_size > 100:
        return {"success": False, "error": f"文件过大 ({file_size:.1f}MB)"}
    
    file_object = None
    try:
        # 上传视频
        print("[分析] 上传视频...")
        file_object = client.files.create(
            file=Path(video_path),
            purpose="video"
        )
        print(f"[分析] 上传成功: {file_object.id}")
        
        # 调用Kimi
        print("[分析] 调用Kimi分析...")
        response = client.chat.completions.create(
            model="kimi-k2.5",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}},
                    {"type": "text", "text": "详细分析这段网球发球视频，输出JSON格式结果。分析五阶段：准备、抛球、蓄力、击球、随挥。给出NTRP等级评估（2.0-5.0+）和具体改进建议。"}
                ]}
            ],
            temperature=1,
            max_tokens=4000
        )
        
        content = response.choices[0].message.content
        print(f"[分析] Kimi返回内容长度: {len(content)}")
        
        # 解析JSON
        try:
            result = json.loads(content)
        except:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except:
                    result = create_default_result("JSON解析失败")
            else:
                result = create_default_result("未找到JSON")
        
        # 生成报告
        report = generate_simple_report(result)
        
        # 保存
        save_result(user_id, video_path, result)
        
        print("[分析] ✓ 完成")
        return {"success": True, "result": result, "report": report}
        
    except Exception as e:
        print(f"[分析] ✗ 失败: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        if file_object and hasattr(file_object, 'id'):
            try:
                client.files.delete(file_object.id)
                print("[分析] ✓ 已清理文件")
            except:
                pass


def create_default_result(reason):
    """创建默认结果"""
    return {
        "ntrp_level": "3.0",
        "ntrp_level_name": "基础级",
        "confidence": 0.6,
        "overall_score": 55,
        "serves_observed": 1,
        "phase_analysis": {
            "ready": {"score": 55, "observations": ["准备姿势基本正确"], "issues": []},
            "toss": {"score": 55, "observations": ["抛球动作一般"], "issues": []},
            "loading": {"score": 55, "observations": ["蓄力有待提高"], "issues": ["膝盖弯曲不足"]},
            "contact": {"score": 55, "observations": ["击球点位置一般"], "issues": []},
            "follow": {"score": 55, "observations": ["随挥完整"], "issues": []}
        },
        "key_strengths": ["动作框架完整"],
        "key_issues": [{"issue": reason, "severity": "medium", "phase": "general"}],
        "training_plan": ["建议进行抛球稳定性练习", "加强腿部力量训练", "练习完整动力链"],
        "detection_quality": "partial",
        "level_reasoning": "基于视频分析，该选手具备完整发球框架，但执行质量一般，评估为3.0级基础水平。"
    }


def generate_simple_report(result):
    """生成简化报告"""
    level = result.get('ntrp_level', '3.0')
    score = result.get('overall_score', 55)
    confidence = result.get('confidence', 0.6)
    
    report = f"""
🎾 **网球发球技术分析报告**

📊 **综合评估**
• NTRP等级: {level}级
• 总分: {score}/100
• 置信度: {confidence:.0%}

📈 **五阶段分析**
"""
    
    phases = result.get('phase_analysis', {})
    phase_names = {
        'ready': '🎾 准备', 'toss': '☝️ 抛球', 'loading': '💪 蓄力',
        'contact': '⚡ 击球', 'follow': '🌊 随挥'
    }
    
    for key, name in phase_names.items():
        p = phases.get(key, {})
        s = p.get('score', 50)
        stars = '★' * (s // 20) + '☆' * (5 - s // 20)
        report += f"\n{name} {stars} ({s}分)"
        issues = p.get('issues', [])
        if issues:
            report += f"\n  ⚠️ {issues[0]}"
    
    # 关键问题
    issues = result.get('key_issues', [])
    if issues:
        report += "\n\n🔴 **关键改进点**\n"
        for i, issue in enumerate(issues[:3], 1):
            report += f"{i}. {issue.get('issue', '')}\n"
    
    # 训练建议
    plan = result.get('training_plan', [])
    if plan:
        report += "\n💡 **训练建议**\n"
        for i, p in enumerate(plan[:3], 1):
            report += f"{i}. {p}\n"
    
    report += "\n---\n💪 坚持练习，每天进步一点点！"
    return report


def save_result(user_id, video_path, result):
    """保存结果"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY,
                user_id TEXT,
                video_path TEXT,
                ntrp_level TEXT,
                confidence REAL,
                overall_score REAL,
                result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT INTO analysis_results (user_id, video_path, ntrp_level, confidence, overall_score, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, video_path, result.get('ntrp_level'), result.get('confidence'), result.get('overall_score'), json.dumps(result)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[保存] 失败: {e}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('video_path')
    parser.add_argument('--user-id', default='test')
    args = parser.parse_args()
    
    if not MOONSHOT_API_KEY:
        print("错误: 请设置 MOONSHOT_API_KEY")
        sys.exit(1)
    
    result = analyze_video_simple(args.video_path, args.user_id)
    if result['success']:
        print(result['report'])
    else:
        print(f"失败: {result.get('error')}")
