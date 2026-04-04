#!/usr/bin/env python3
"""
分析Worker - 带完整MediaPipe分析
"""

import sqlite3
import time
import json
import os
import sys
from datetime import datetime
from uuid import uuid4

# 添加路径
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')
sys.path.insert(0, '/usr/lib/python3/dist-packages')

# 导入MediaPipe
try:
    import mediapipe as mp
    import cv2
    import numpy as np
    MEDIAPIPE_AVAILABLE = True
except ImportError as e:
    print(f"[Worker] MediaPipe导入错误: {e}")
    MEDIAPIPE_AVAILABLE = False

# 导入COS
try:
    from qcloud_cos import CosConfig, CosS3Client
    COS_AVAILABLE = True
except ImportError:
    print("[Worker] COS SDK未安装")
    COS_AVAILABLE = False

# 配置
DB_PATH = '/data/db/xiaolongxia_learning.db'
COS_SECRET_ID = os.environ.get('COS_SECRET_ID', '')
COS_SECRET_KEY = os.environ.get('COS_SECRET_KEY', '')
COS_BUCKET = os.environ.get('COS_BUCKET', 'tennis-ai-1411340868')
COS_REGION = os.environ.get('COS_REGION', 'ap-shanghai')

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_pending_task():
    """获取一个pending状态的任务"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.id, t.video_id, v.cos_url, v.file_name, v.cos_key
            FROM video_analysis_tasks t
            JOIN videos v ON t.video_id = v.id
            WHERE t.analysis_status = 'pending'
            ORDER BY t.created_at ASC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row['id'],
                'video_id': row['video_id'],
                'cos_url': row['cos_url'],
                'file_name': row['file_name'],
                'cos_key': row['cos_key']
            }
        return None
        
    except Exception as e:
        print(f"[Worker] 获取任务错误: {e}")
        return None

def download_video(cos_key, local_path):
    """从COS下载视频"""
    if not COS_AVAILABLE:
        return False
    
    try:
        config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
        client = CosS3Client(config)
        
        client.download_file(
            Bucket=COS_BUCKET,
            Key=cos_key,
            DestFilePath=local_path
        )
        return True
    except Exception as e:
        print(f"[Worker] 下载视频失败: {e}")
        return False

def analyze_video_with_mediapipe(video_path):
    """使用MediaPipe分析视频 - 强制使用MediaPipe，不使用模拟数据"""
    if not MEDIAPIPE_AVAILABLE:
        raise Exception("MediaPipe不可用，无法进行分析")
    
    print(f"[Worker] 使用MediaPipe分析: {video_path}")
    
    # 调用真正的MediaPipe分析
    import cv2
    import numpy as np
    
    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"无法打开视频: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"   视频信息: {total_frames}帧, {fps}fps")
    
    # 使用MediaPipe Tasks API
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
    from mediapipe.tasks.python.core.base_options import BaseOptions
    from pathlib import Path
    
    # 检查模型文件
    model_path = Path('/data/apps/xiaolongxia/pose_landmarker_lite.task')
    if not model_path.exists():
        raise Exception("MediaPipe模型文件不存在")
    
    # 配置选项
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    pose_data = []
    frame_count = 0
    
    with PoseLandmarker.create_from_options(options) as landmarker:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 每5帧分析一次
            if frame_count % 5 != 0:
                continue
            
            # 转换帧格式
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            
            # 检测姿态
            timestamp_ms = int((frame_count / fps) * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
            
            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]
                
                # 提取关键点（右臂）
                right_shoulder = landmarks[12]  # RIGHT_SHOULDER
                right_elbow = landmarks[14]     # RIGHT_ELBOW
                right_wrist = landmarks[16]     # RIGHT_WRIST
                right_hip = landmarks[24]       # RIGHT_HIP
                right_knee = landmarks[26]      # RIGHT_KNEE
                right_ankle = landmarks[28]     # RIGHT_ANKLE
                
                # 计算角度
                def calculate_angle(a, b, c):
                    import math
                    a = np.array([a.x, a.y])
                    b = np.array([b.x, b.y])
                    c = np.array([c.x, c.y])
                    
                    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
                    angle = np.abs(radians * 180.0 / np.pi)
                    
                    if angle > 180.0:
                        angle = 360 - angle
                    
                    return angle
                
                elbow_angle = calculate_angle(right_shoulder, right_elbow, right_wrist)
                knee_angle = calculate_angle(right_hip, right_knee, right_ankle)
                
                pose_data.append({
                    'frame': frame_count,
                    'timestamp': frame_count / fps,
                    'elbow_angle': elbow_angle,
                    'knee_angle': knee_angle,
                    'shoulder_angle': 90
                })
                
                if len(pose_data) % 10 == 0:
                    print(f"   已分析 {len(pose_data)} 帧...")
    
    cap.release()
    print(f"✅ MediaPipe分析完成: {len(pose_data)} 帧")
    
    if not pose_data:
        raise Exception("MediaPipe未检测到姿态数据")
    
    # 基于姿态数据分析
    return analyze_pose_data(pose_data)


def analyze_pose_data(pose_data):
    """基于MediaPipe姿态数据分析"""
    if not pose_data:
        raise Exception("无姿态数据")
    
    # 统计数据
    elbow_angles = [d['elbow_angle'] for d in pose_data]
    knee_angles = [d['knee_angle'] for d in pose_data]
    
    avg_elbow = sum(elbow_angles) / len(elbow_angles)
    avg_knee = sum(knee_angles) / len(knee_angles)
    min_knee = min(knee_angles)
    max_elbow = max(elbow_angles)
    
    print(f"   平均肘部角度: {avg_elbow:.1f}°")
    print(f"   平均膝盖角度: {avg_knee:.1f}°")
    print(f"   最小膝盖角度: {min_knee:.1f}°")
    print(f"   最大肘部角度: {max_elbow:.1f}°")
    
    # 计算评分
    base_score = 70
    problems = []
    
    # 根据角度判断问题
    if min_knee > 120:
        problems.append({"phase": "loading", "problem_code": "knee_bend", "description": "蓄力不足，膝盖弯曲不够"})
        base_score -= 5
    
    if max_elbow < 150:
        problems.append({"phase": "contact", "problem_code": "elbow_extension", "description": "肘部伸展不足，击球点偏低"})
        base_score -= 5
    
    if avg_knee > 130:
        problems.append({"phase": "loading", "problem_code": "loading_weak", "description": "蓄力可加强"})
        base_score -= 3
    
    # 计算档位
    final_score = max(0, min(100, base_score))
    if final_score >= 95:
        bucket = '5.5+'
    elif final_score >= 90:
        bucket = '5.0'
    elif final_score >= 85:
        bucket = '4.5'
    elif final_score >= 80:
        bucket = '4.0'
    elif final_score >= 72:
        bucket = '3.5'
    elif final_score >= 65:
        bucket = '3.0'
    elif final_score >= 58:
        bucket = '2.5'
    elif final_score >= 50:
        bucket = '2.0'
    elif final_score >= 40:
        bucket = '1.5'
    else:
        bucket = '1.0'
    
    return {
        "total_score": final_score,
        "bucket": bucket,
        "problems": problems if problems else [{"phase": "general", "problem_code": "good_form", "description": "动作良好，继续保持"}],
        "recommendations": ["继续练习，保持动作稳定性"],
        "phase_analysis": {
            "ready": {"score": min(85, final_score + 5), "issues": []},
            "toss": {"score": min(80, final_score), "issues": []},
            "loading": {"score": min(85, final_score + 5) if min_knee < 120 else min(70, final_score), "issues": ["蓄力不足"] if min_knee > 120 else []},
            "contact": {"score": min(80, final_score) if max_elbow > 150 else min(65, final_score), "issues": ["肘部伸展不足"] if max_elbow < 150 else []},
            "follow": {"score": min(82, final_score + 3), "issues": []}
        },
        "statistics": {
            "avg_elbow_angle": avg_elbow,
            "avg_knee_angle": avg_knee,
            "min_knee_angle": min_knee,
            "max_elbow_angle": max_elbow,
            "frames_analyzed": len(pose_data)
        }
    }

def simulate_analysis():
    """模拟分析结果（当MediaPipe不可用时）"""
    return {
        "total_score": 72.5,
        "bucket": "4.0",
        "problems": [
            {"phase": "toss", "problem_code": "toss_height", "description": "抛球高度偏低，导致准备时间不足"},
            {"phase": "contact", "problem_code": "contact_point", "description": "击球点过于靠后，影响发力"}
        ],
        "recommendations": [
            "增加抛球高度，确保充分准备时间",
            "调整击球点位置，在身体前方击球"
        ],
        "phase_analysis": {
            "ready": {"score": 75, "issues": []},
            "toss": {"score": 65, "issues": ["抛球高度不足"]},
            "loading": {"score": 70, "issues": []},
            "contact": {"score": 68, "issues": ["击球点靠后"]},
            "follow": {"score": 72, "issues": []}
        }
    }

def recall_knowledge(problems):
    """从知识库召回相关知识点"""
    # 简化版：返回固定的知识召回
    return [
        {
            "coach": "杨超",
            "title": "抛球高度决定准备时间",
            "content": "抛球的高度直接影响发球前的准备时间...",
            "match_score": 0.92
        },
        {
            "coach": "灵犀",
            "title": "击球点位置控制",
            "content": "击球点应该在身体前方，便于向前发力...",
            "match_score": 0.88
        }
    ]

def process_task(task):
    """处理任务"""
    print(f"[Worker] 处理任务: {task['id']}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 更新状态为processing
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET analysis_status = 'running', started_at = datetime('now')
            WHERE id = ?
        ''', (task['id'],))
        conn.commit()
        
        # 下载视频
        local_path = f"/tmp/{task['video_id']}.mp4"
        if task.get('cos_key'):
            download_video(task['cos_key'], local_path)
        
        # 分析视频
        print(f"[Worker] 分析视频: {task['file_name']}")
        analysis_result = analyze_video_with_mediapipe(local_path)
        
        # 知识召回
        knowledge_recall = recall_knowledge(analysis_result.get('problems', []))
        
        # 更新结果
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET analysis_status = 'success',
                ntrp_level = ?,
                ntrp_confidence = ?,
                knowledge_recall_count = ?,
                sample_saved = 1,
                analysis_result = ?,
                phase_marks = ?,
                finished_at = datetime('now')
            WHERE id = ?
        ''', (
            analysis_result.get('bucket', '4.0'),
            0.82,
            len(knowledge_recall),
            json.dumps(analysis_result),
            json.dumps(analysis_result.get('phase_analysis', {})),
            task['id']
        ))
        
        conn.commit()
        conn.close()
        
        # 清理临时文件
        if os.path.exists(local_path):
            os.remove(local_path)
        
        print(f"[Worker] 任务完成: {task['id']}")
        
    except Exception as e:
        print(f"[Worker] 处理任务错误: {e}")
        import traceback
        traceback.print_exc()

def main_loop():
    """主循环"""
    print("[Worker] 启动分析worker（带MediaPipe）...")
    print(f"[Worker] MediaPipe可用: {MEDIAPIPE_AVAILABLE}")
    print(f"[Worker] COS可用: {COS_AVAILABLE}")
    
    while True:
        try:
            task = get_pending_task()
            
            if task:
                print(f"[Worker] 获取任务: {task['id']}")
                process_task(task)
            else:
                print("[Worker] 无pending任务，等待5秒...")
                time.sleep(5)
                
        except Exception as e:
            print(f"[Worker] 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)

if __name__ == '__main__':
    main_loop()
