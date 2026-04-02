#!/usr/bin/env python3
"""
vision_analysis_worker.py
Kimi K2.5 视觉分析 — 抽帧图片版
Moonshot不支持直接传视频，改为抽取关键帧上传图片
"""

import os
import json
import time
import sqlite3
import traceback
import subprocess
from openai import OpenAI

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', 'sk-LsZC9HAarYmH6oH4EkOzCEhIIUZ02yvsU6J7xr1u26iifksq')
DB_PATH = '/data/db/xiaolongxia_learning.db'
FRAMES_DIR = '/data/tmp/vision_frames'
PROMPT_VERSION = 'v4.0_frames'
MODEL_NAME = 'kimi-k2.5'

client = OpenAI(
    api_key=MOONSHOT_API_KEY,
    base_url="https://api.moonshot.cn/v1"
)

# ═══════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════
SYSTEM_PROMPT = """你是一个专业的网球发球分析系统。你将收到网球发球视频的关键帧图片（按时间顺序排列），需要分析发球技术并给出NTRP等级评估。

## 三位教练的评估标准（169条知识点）

### 杨超教练（71条）— 分级标准权威
- 3.0级：成功率70%+，动作基本规范，能控制落点
- 4.0级：能控制旋转方向和量，一发成功率65%+
- 5.0级：完整动力链，腿部40%+核心30%+手臂20%+手腕10%

关键技术：大陆式握拍、抛球稳定、奖杯姿势、完整旋内

### 赵凌曦教练（41条）— 节奏与纠错
- 发球节奏1-2-3：拉拍停顿→蓄力奖杯→加速击球
- 顶髋是重心前倾，不是后仰
- 抛球方向必须与发球方向一致

### Yellow教练（57条）— 动作细节
- 完整动作链条和各阶段要点

## NTRP 等级标准
2.0级（入门）：动作不完整，无蓄力
3.0级（基础）：有框架但执行一般
4.0级（熟练）：流畅连贯，深蹲蓄力
5.0级（精通）：教科书标准，完整动力链

## 评分红线
1. 看"质"不看"形"
2. 膝盖蓄力是分水岭
3. 短板决定上限
4. 看不清就说看不清

## 输出格式（只输出JSON）
{
  "ntrp_level": "4.0",
  "ntrp_level_name": "熟练级",
  "confidence": 0.8,
  "overall_score": 75,
  "serves_observed": 3,
  "phase_analysis": {
    "ready": {"score": 70, "observations": [], "issues": []},
    "toss": {"score": 75, "observations": [], "issues": []},
    "loading": {"score": 80, "observations": [], "issues": []},
    "contact": {"score": 75, "observations": [], "issues": []},
    "follow": {"score": 70, "observations": [], "issues": []}
  },
  "key_strengths": ["优点1", "优点2"],
  "key_issues": [{"issue": "", "severity": "", "phase": "", "coach_advice": ""}],
  "training_plan": ["建议1", "建议2"],
  "detection_quality": "reliable",
  "level_reasoning": "等级推理过程"
}"""

# ═══════════════════════════════════════════════
# 抽帧
# ═══════════════════════════════════════════════

def extract_frames(video_path, output_dir, num_frames=8):
    """抽取关键帧"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 清空旧帧
    for f in os.listdir(output_dir):
        if f.endswith('.jpg'):
            os.remove(os.path.join(output_dir, f))
    
    # 使用ffmpeg抽帧
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f'fps=1/2,scale=640:360',
        '-vframes', str(num_frames),
        os.path.join(output_dir, 'frame_%02d.jpg')
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        frames = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
        return len(frames) >= 3, sorted(frames)
    except Exception as e:
        print(f"[FFmpeg] 错误: {e}")
        return False, []

# ═══════════════════════════════════════════════
# 检查
# ═══════════════════════════════════════════════

def check_input(video_path):
    """检查输入"""
    if not os.path.exists(video_path):
        return False, "文件不存在"
    
    size = os.path.getsize(video_path) / 1024 / 1024
    if size < 0.1:
        return False, "文件过小"
    if size > 100:
        return False, f"文件过大({size:.0f}MB)"
    
    return True, f"{size:.1f}MB"

# ═══════════════════════════════════════════════
# Kimi 分析
# ═══════════════════════════════════════════════

import base64

def analyze_frames(frame_dir, frame_files):
    """上传图片给Kimi分析（使用base64编码）"""
    try:
        print(f"[Kimi] 分析 {len(frame_files)} 帧...")
        
        # 构建消息
        content = [{"type": "text", "text": "请按时间顺序观察这些网球发球关键帧，分析完整发球动作，给出NTRP等级评估。"}]
        
        # 读取图片并转为base64（最多6张）
        for fname in frame_files[:6]:
            img_path = os.path.join(frame_dir, fname)
            with open(img_path, 'rb') as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                })
        
        # 调用API
        response = client.chat.completions.create(
            model="kimi-k2.5",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ],
            temperature=1,
            max_tokens=2000
        )
        
        # 解析JSON
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
# 校验
# ═══════════════════════════════════════════════

def validate(result):
    """校验结果"""
    required = ['ntrp_level', 'confidence', 'phase_analysis']
    errors = [f"缺少:{f}" for f in required if f not in result]
    
    valid_levels = ['2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.0+']
    if result.get('ntrp_level') not in valid_levels:
        errors.append(f"无效等级:{result.get('ntrp_level')}")
    
    return len(errors) == 0, errors

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
    print("[1] 检查...")
    ok, info = check_input(video_path)
    if not ok:
        print(f"  ✗ {info}")
        return {"status": "low_quality", "reason": info}
    print(f"  ✓ {info}")
    
    # 2. 抽帧
    print("[2] 抽帧...")
    frame_dir = os.path.join(FRAMES_DIR, task_id)
    success, frames = extract_frames(video_path, frame_dir)
    if not success:
        print(f"  ✗ 抽帧失败")
        return {"status": "failed", "reason": "抽帧失败"}
    print(f"  ✓ {len(frames)}帧")
    
    # 3. 分析
    print("[3] Kimi分析...")
    success, result = analyze_frames(frame_dir, frames)
    if not success:
        print(f"  ✗ {result.get('error')}")
        return {"status": "failed", "reason": result.get('error')}
    print(f"  ✓ 完成")
    
    # 4. 校验
    print("[4] 校验...")
    valid, errors = validate(result)
    if not valid:
        print(f"  ✗ {errors}")
        return {"status": "failed", "reason": "校验失败", "errors": errors}
    print(f"  ✓ 通过")
    
    print(f"\n{'='*50}")
    print(f"等级: {result.get('ntrp_level')}")
    print(f"置信度: {result.get('confidence')}")
    print(f"{'='*50}\n")
    
    return {
        "status": "success",
        "task_id": task_id,
        "analysis": result,
        "model": MODEL_NAME
    }

# ═══════════════════════════════════════════════
# Worker循环
# ═══════════════════════════════════════════════

def worker_loop():
    """主循环"""
    print("\n" + "="*50)
    print("🚀 Vision Worker")
    print(f"   模型: {MODEL_NAME}")
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
                
                for path in [f"/root/.openclaw/media/inbound/{video_id}.mp4",
                            f"/data/videos/{video_id}.mp4"]:
                    if os.path.exists(path):
                        result = analyze_video(path, task_id)
                        
                        # 保存到数据库
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        analysis = result.get('analysis', {})
                        cursor.execute('''
                            UPDATE video_analysis_tasks 
                            SET analysis_status = ?, ntrp_level = ?, 
                                ntrp_confidence = ?, analysis_result = ?
                            WHERE id = ?
                        ''', (result['status'], analysis.get('ntrp_level'),
                              analysis.get('confidence'), 
                              json.dumps(result), task_id))
                        conn.commit()
                        conn.close()
                        break
                else:
                    print(f"✗ 找不到视频: {video_id}")
            else:
                time.sleep(5)
                
        except Exception as e:
            print(f"错误: {e}")
            traceback.print_exc()
            time.sleep(10)

if __name__ == '__main__':
    worker_loop()
