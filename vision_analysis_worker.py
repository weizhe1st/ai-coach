#!/usr/bin/env python3
"""
Vision Analysis Worker - Kimi K2.5 直接传视频版
视频 → 直接上传给 Kimi → Kimi 自己看完整视频分析
"""

import os
import json
import time
import sqlite3
import traceback
from pathlib import Path
from openai import OpenAI

# 导入共享模块
from core import (
    PROMPT_VERSION, KNOWLEDGE_BASE_VERSION, MODEL_NAME,
    SYSTEM_PROMPT, check_input_quality, validate_response
)

# 配置
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
DB_PATH = '/data/db/xiaolongxia_learning.db'

client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.cn/v1")


def analyze_video(video_path, video_url=None):
    """
    直接上传视频并分析
    
    Args:
        video_path: 本地视频文件路径
        video_url: 视频URL（用于数据库记录）
    
    Returns:
        dict: 包含分析结果或错误信息
    """
    print(f"\n{'='*60}")
    print(f"[Vision Worker] 开始分析: {video_path}")
    print(f"{'='*60}")
    
    # 1. 检查输入质量
    is_valid, quality_info = check_input_quality(video_path)
    if not is_valid:
        print(f"[Vision Worker] ✗ 输入检查失败: {quality_info['reason']}")
        return {
            "success": False,
            "error": quality_info['reason'],
            "quality_check": quality_info
        }
    
    print(f"[Vision Worker] 视频信息: {quality_info}")
    
    file_object = None
    try:
        # 2. 上传视频文件
        print(f"[Vision Worker] 上传视频文件...")
        file_object = client.files.create(
            file=Path(video_path),
            purpose="video"
        )
        print(f"[Vision Worker] 上传成功: {file_object.id}")
        
        # 3. 调用 Chat API
        print(f"[Vision Worker] 调用 Kimi 分析...")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}},
                    {"type": "text", "text": "请分析这段网球发球视频，按照系统提示词的格式输出JSON结果。"}
                ]}
            ],
            temperature=1,
            max_tokens=4000
        )
        
        content = response.choices[0].message.content
        
        # 4. 解析 JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                return {
                    "success": False,
                    "error": "无法解析 JSON 响应",
                    "raw_response": content[:1000]
                }
        
        # 5. 校验响应
        is_valid, errors, validated_result = validate_response(result)
        if not is_valid:
            print(f"[Vision Worker] ⚠ 响应校验警告: {errors}")
        
        # 添加元数据
        validated_result['_meta'] = {
            "prompt_version": PROMPT_VERSION,
            "knowledge_base_version": KNOWLEDGE_BASE_VERSION,
            "model": MODEL_NAME,
            "video_path": video_path,
            "video_url": video_url,
            "file_id": file_object.id,
            "analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "quality_info": quality_info
        }
        
        print(f"[Vision Worker] ✓ 分析完成")
        print(f"[Vision Worker]   NTRP等级: {validated_result.get('ntrp_level', 'unknown')}")
        print(f"[Vision Worker]   置信度: {validated_result.get('confidence', 0):.2f}")
        
        return {
            "success": True,
            "result": validated_result
        }
        
    except Exception as e:
        error_msg = f"分析失败: {str(e)}"
        print(f"[Vision Worker] ✗ {error_msg}")
        traceback.print_exc()
        return {
            "success": False,
            "error": error_msg
        }
    finally:
        # 6. 清理 Moonshot 上传的文件
        if file_object and hasattr(file_object, 'id'):
            try:
                client.files.delete(file_object.id)
                print(f"[Vision Worker] ✓ 已清理上传的文件: {file_object.id}")
            except Exception as e:
                print(f"[Vision Worker] ⚠ 清理文件失败: {e}")


def save_result(video_url, analysis_result):
    """保存分析结果到数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vision_analysis_direct (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_url TEXT UNIQUE,
                filename TEXT,
                ntrp_level TEXT,
                ntrp_level_name TEXT,
                confidence REAL,
                overall_score REAL,
                serves_observed INTEGER,
                phase_analysis TEXT,
                key_strengths TEXT,
                key_issues TEXT,
                training_plan TEXT,
                detection_quality TEXT,
                detection_notes TEXT,
                level_reasoning TEXT,
                full_result TEXT,
                file_id TEXT,
                prompt_version TEXT,
                knowledge_base_version TEXT,
                model TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 修复：正确处理 analysis_result 参数
        if isinstance(analysis_result, dict) and 'result' in analysis_result:
            result = analysis_result['result']
        else:
            result = analysis_result
            
        meta = result.get('_meta', {})
        filename = video_url.split('/')[-1].split('?')[0] if video_url else 'unknown.mp4'
        
        cursor.execute('''
            INSERT OR REPLACE INTO vision_analysis_direct 
            (video_url, filename, ntrp_level, ntrp_level_name, confidence, overall_score,
             serves_observed, phase_analysis, key_strengths, key_issues, training_plan,
             detection_quality, detection_notes, level_reasoning, full_result, file_id,
             prompt_version, knowledge_base_version, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_url,
            filename,
            result.get('ntrp_level'),
            result.get('ntrp_level_name'),
            result.get('confidence'),
            result.get('overall_score'),
            result.get('serves_observed'),
            json.dumps(result.get('phase_analysis', {}), ensure_ascii=False),
            json.dumps(result.get('key_strengths', []), ensure_ascii=False),
            json.dumps(result.get('key_issues', []), ensure_ascii=False),
            json.dumps(result.get('training_plan', []), ensure_ascii=False),
            result.get('detection_quality'),
            result.get('detection_notes'),
            result.get('level_reasoning'),
            json.dumps(result, ensure_ascii=False),
            meta.get('file_id'),
            meta.get('prompt_version', PROMPT_VERSION),
            meta.get('knowledge_base_version', KNOWLEDGE_BASE_VERSION),
            meta.get('model', MODEL_NAME)
        ))
        
        conn.commit()
        conn.close()
        
        print(f"[Vision Worker] ✓ 结果已保存到数据库")
        return True
        
    except Exception as e:
        print(f"[Vision Worker] ✗ 保存失败: {e}")
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Vision Analysis Worker - Kimi K2.5 直接传视频版')
    parser.add_argument('video_path', help='视频文件路径')
    parser.add_argument('--url', help='视频URL（用于数据库记录）')
    parser.add_argument('--api-key', help='Moonshot API Key')
    parser.add_argument('--no-save', action='store_true', help='不保存到数据库')
    
    args = parser.parse_args()
    
    # 设置 API Key
    global MOONSHOT_API_KEY
    if args.api_key:
        MOONSHOT_API_KEY = args.api_key
    
    if not MOONSHOT_API_KEY:
        print("错误: 请提供 Moonshot API Key (--api-key 或环境变量 MOONSHOT_API_KEY)")
        exit(1)
    
    # 更新 client
    global client
    client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.cn/v1")
    
    # 分析视频
    result = analyze_video(args.video_path, args.url)
    
    if result['success']:
        # 保存到数据库
        if not args.no_save:
            url = args.url or args.video_path
            save_result(url, result)
        
        # 输出结果
        print(f"\n{'='*60}")
        print("分析结果:")
        print(f"{'='*60}")
        print(json.dumps(result['result'], indent=2, ensure_ascii=False))
        exit(0)
    else:
        print(f"\n{'='*60}")
        print("分析失败:")
        print(f"{'='*60}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        exit(1)


if __name__ == '__main__':
    main()
