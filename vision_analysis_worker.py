#!/usr/bin/env python3
"""
vision_analysis_worker.py
Kimi K2.5 视觉分析 — 极简直接传视频版
去掉 ffmpeg、cv2、numpy，直接上传视频给 Kimi
"""

import os
import json
import time
import sqlite3
import traceback
from openai import OpenAI

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', 'A8dY7k6zEYhxc7E80jlhj2vtSr5iWXVJh2oyuLO63a8zNk6w')
DB_PATH = '/data/db/xiaolongxia_learning.db'
PROMPT_VERSION = 'v3.0_minimal'
KNOWLEDGE_BASE_VERSION = 'v5.0_3coaches_169items'
MODEL_NAME = 'kimi-k2.5'

client = OpenAI(
    api_key=MOONSHOT_API_KEY,
    base_url="https://api.moonshot.cn/v1"
)

# ═══════════════════════════════════════════════
# System Prompt（三教练知识库 + 评分标准）
# ═══════════════════════════════════════════════
SYSTEM_PROMPT = """你是一个专业的网球发球分析系统。你将收到一段网球发球视频，需要仔细观看完整视频，分析发球技术并给出NTRP等级评估。

## 三位教练的评估标准（169条知识点）

### 杨超教练（71条）— 分级标准权威
等级定义：
- 3.0级：成功率70%+，动作基本规范不变形，能控制落点。四大核心：稳定抛球、大陆式握拍、完整挥拍轨迹、合理击球点。
- 4.0级：能控制旋转方向和旋转量，一发成功率65%+，二发成功率85%+，有明确落点策略。
- 5.0级：加入腿部动力链，力量占比为腿部40%、核心转体30%、手臂挥拍20%、手腕旋内10%。膝盖弯曲约120-130度。

关键技术标准：
- 大陆式握拍：虎口对准2号面
- 抛球：前上方向、手臂直度、落点稳定
- 奖杯位置：球拍背后最低点，肘部高于肩膀
- 击球点：身体前上方，手臂完全伸展
- 旋内：前臂从外旋到内旋，收拍到非持拍手侧
- 挥拍轨迹：倒C形 → 背挠 → 加速 → 旋内

### 赵凌曦教练（41条）— 节奏与纠错
- 发球节奏1-2-3：拉拍停顿 → 蓄力奖杯 → 加速击球
- 顶髋是重心后摆后自然前倾，不是后仰
- 架拍僵硬说明手腕手肘过紧
- 抛球方向必须与发球方向一致

### Yellow教练（57条）— 动作细节
- 完整动作链条和各阶段要点
- 站位、握拍、抛球、蓄力、击球、随挥标准

## NTRP 等级标准（严格执行）
2.0级（入门）：动作不完整，无背挠，抛球不稳，无膝盖蓄力
3.0级（基础）：有完整框架但执行质量一般，膝盖蓄力不够，旋内不充分
3.5级（进阶）：框架完整有流畅性，有一定蓄力但不够深
4.0级（熟练）：流畅连贯，膝盖深蹲蓄力(90-100度)，明显转肩，完整旋内
4.5级（高级）：高度流畅，明确旋转意图，腿部蹬地有力
5.0级（精通）：教科书标准，完整动力链，击球腾空，极为放松
5.0+级（专业）：职业水平，完美动力链，极高击球点

## 评分红线
1. 看"质"不看"形"：有框架 ≠ 执行到位
2. 膝盖蓄力是分水岭：不弯 → 2.0-3.0；浅弯 → 3.0-3.5；深蹲 → 4.0+
3. 短板决定上限
4. 看不清就说看不清，不猜测
5. 业余选手容易高估，4.5+要非常谨慎
6. 如果视频中有多个发球，综合评估整体水平

## 输出格式（只输出 JSON，不要任何其他内容）
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
  "key_strengths": ["优点1", "优点2"],
  "key_issues": [{"issue": "问题", "severity": "high/medium/low", "phase": "阶段", "coach_advice": "建议"}],
  "training_plan": ["建议1", "建议2", "建议3"],
  "detection_quality": "reliable/partial/poor",
  "detection_notes": "视频质量影响说明",
  "level_reasoning": "等级推理过程"
}"""

# ═══════════════════════════════════════════════
# 极简输入检查
# ═══════════════════════════════════════════════

def check_input_quality(video_path):
    """极简检查：文件存在、大小合适"""
    if not os.path.exists(video_path):
        return False, "视频文件不存在"
    
    file_size = os.path.getsize(video_path) / 1024 / 1024  # MB
    if file_size < 0.1:
        return False, "文件过小"
    if file_size > 100:
        return False, f"文件过大 ({file_size:.0f}MB)"
    
    return True, f"文件大小: {file_size:.1f}MB"

# ═══════════════════════════════════════════════
# JSON 校验
# ═══════════════════════════════════════════════

def validate_response(result):
    """校验 JSON 结构"""
    errors = []
    required = ['ntrp_level', 'confidence', 'phase_analysis']
    
    for f in required:
        if f not in result:
            errors.append(f"缺少: {f}")
    
    valid_levels = ['2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.0+']
    if result.get('ntrp_level') not in valid_levels:
        errors.append(f"无效等级: {result.get('ntrp_level')}")
    
    return len(errors) == 0, errors

# ═══════════════════════════════════════════════
# Kimi 分析（直接传视频）
# ═══════════════════════════════════════════════

def analyze_with_kimi(video_path):
    """直接上传视频给 Kimi 分析"""
    try:
        print(f"[Kimi] 分析视频: {os.path.basename(video_path)}")
        
        # 打开视频文件
        with open(video_path, 'rb') as video_file:
            # 创建文件对象
            file_object = client.files.create(file=video_file, purpose="user-content")
        
        # 调用 API
        response = client.chat.completions.create(
            model="kimi-k2.5",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请仔细观看这段网球发球视频，分析完整的发球动作过程，给出NTRP等级评估和详细技术分析。"},
                        {"type": "file", "file_url": {"url": file_object.url}}
                    ]
                }
            ],
            temperature=0.3,
            max_tokens=2500
        )
        
        # 解析 JSON
        content = response.choices[0].message.content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content.strip()
        
        return True, json.loads(json_str)
        
    except Exception as e:
        print(f"[Kimi] 错误: {e}")
        return False, {"error": str(e)}

# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def analyze_video(video_path, task_id):
    """分析视频"""
    print(f"\n{'='*50}")
    print(f"任务: {task_id}")
    print(f"视频: {os.path.basename(video_path)}")
    print(f"{'='*50}\n")
    
    # 1. 检查
    print("[1] 检查视频...")
    ok, info = check_input_quality(video_path)
    if not ok:
        print(f"  ✗ {info}")
        return {"status": "low_quality", "reason": info}
    print(f"  ✓ {info}")
    
    # 2. 分析
    print("[2] Kimi 分析视频...")
    success, result = analyze_with_kimi(video_path)
    if not success:
        print(f"  ✗ 失败: {result.get('error')}")
        return {"status": "failed", "reason": result.get('error')}
    print(f"  ✓ 完成")
    
    # 3. 校验
    print("[3] 校验结果...")
    valid, errors = validate_response(result)
    if not valid:
        print(f"  ✗ {errors}")
        return {"status": "failed", "reason": "JSON无效", "errors": errors}
    print(f"  ✓ 通过")
    
    # 结果
    print(f"\n{'='*50}")
    print(f"等级: {result.get('ntrp_level')}")
    print(f"置信度: {result.get('confidence')}")
    print(f"发球数: {result.get('serves_observed', 1)}")
    print(f"{'='*50}\n")
    
    return {
        "status": "success",
        "task_id": task_id,
        "analysis": result,
        "model": MODEL_NAME,
        "prompt_version": PROMPT_VERSION
    }

def save_to_db(task_id, result):
    """保存到数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        analysis = result.get('analysis', {})
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET analysis_status = ?,
                ntrp_level = ?,
                ntrp_confidence = ?,
                analysis_result = ?,
                finished_at = datetime('now')
            WHERE id = ?
        ''', (
            result['status'],
            analysis.get('ntrp_level'),
            analysis.get('confidence'),
            json.dumps(result, ensure_ascii=False),
            task_id
        ))
        conn.commit()
        conn.close()
        print("[DB] 已保存\n")
        return True
    except Exception as e:
        print(f"[DB] 错误: {e}\n")
        return False

# ═══════════════════════════════════════════════
# Worker 循环
# ═══════════════════════════════════════════════

def worker_loop():
    """主循环"""
    print("\n" + "="*50)
    print("🚀 Vision Worker 启动")
    print(f"   模型: {MODEL_NAME}")
    print(f"   知识库: {KNOWLEDGE_BASE_VERSION}")
    print("="*50 + "\n")
    
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, video_id FROM video_analysis_tasks 
                WHERE analysis_status = 'pending' 
                ORDER BY created_at ASC LIMIT 1
            ''')
            
            task = cursor.fetchone()
            conn.close()
            
            if task:
                task_id, video_id = task
                
                # 找视频文件
                for path in [f"/root/.openclaw/media/inbound/{video_id}.mp4",
                            f"/data/videos/{video_id}.mp4"]:
                    if os.path.exists(path):
                        result = analyze_video(path, task_id)
                        save_to_db(task_id, result)
                        break
                else:
                    print(f"✗ 找不到视频: {video_id}\n")
            else:
                time.sleep(5)
                
        except Exception as e:
            print(f"错误: {e}\n")
            traceback.print_exc()
            time.sleep(10)

if __name__ == '__main__':
    worker_loop()
