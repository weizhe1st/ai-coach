#!/usr/bin/env python3
"""
网球发球分析器 - MediaPipe + 杨超教练知识点
整合姿态分析和规则库进行评分
"""

import sys
import json
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

# MediaPipe 新 API
try:
    from mediapipe.tasks.python.vision import PoseLandmarker, RunningMode
    from mediapipe.tasks.python.core.base_options import BaseOptions
except ImportError:
    # 旧版 API
    from mediapipe.tasks.python.vision import PoseLandmarker, RunningMode
    from mediapipe.tasks.python.core import base_options
    BaseOptions = base_options.BaseOptions
import mediapipe as mp

# 数据库连接
import sqlite3

DB_PATH = '/data/db/xiaolongxia_learning.db'

def get_db_connection():
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH)

def load_serve_rules():
    """加载杨超教练的发球规则（兼容旧版）"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM serve_rules WHERE enabled = 1 ORDER BY priority')
    rules = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rules

def load_coach_knowledge():
    """加载三位教练的统一知识库（Yellow、杨超、灵犀）"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT coach_name, knowledge_id, title, summary, 
               key_elements, common_errors, correction_method,
               knowledge_type, knowledge_class, phase, issue_tags
        FROM coach_knowledge_unified 
        WHERE quality_grade IN ('A', 'B') OR quality_grade IS NULL
        ORDER BY coach_name, knowledge_class
    ''')
    knowledge = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # 统计
    coach_counts = {}
    for k in knowledge:
        coach = k['coach_name']
        coach_counts[coach] = coach_counts.get(coach, 0) + 1
    
    print(f"   加载教练知识库: {coach_counts}")
    return knowledge

def analyze_video_with_mediapipe(video_path):
    """使用 MediaPipe 分析视频姿态"""
    print(f"\n🔍 使用 MediaPipe 分析视频: {video_path}")
    
    # 检查模型文件是否存在
    model_path = Path('/data/apps/xiaolongxia/pose_landmarker_lite.task')
    if not model_path.exists():
        print("⚠️  未找到 pose_landmarker_lite.task 模型文件，使用旧版 API")
        return analyze_with_legacy_mediapipe(video_path)
    
    # 初始化 PoseLandmarkerOptions
    from mediapipe.tasks.python.vision import PoseLandmarkerOptions
    base_options = BaseOptions(model_asset_path=str(model_path))
    options = PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    # 打开视频
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"   视频信息: {total_frames}帧, {fps}fps")
    
    pose_data = []
    frame_count = 0
    
    # 每5帧分析一次
    sample_interval = 5
    
    landmarker = PoseLandmarker.create_from_options(options)
    while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            if frame_count % sample_interval != 0:
                continue
            
            # 转换帧为 MediaPipe 格式
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            
            # 检测姿态
            timestamp_ms = int((frame_count / fps) * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
            
            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]
                
                # 提取关键角度
                # 肘部角度（右臂）
                right_shoulder = landmarks[12]  # RIGHT_SHOULDER
                right_elbow = landmarks[14]      # RIGHT_ELBOW
                right_wrist = landmarks[16]      # RIGHT_WRIST
                
                elbow_angle = calculate_angle(
                    (right_shoulder.x, right_shoulder.y),
                    (right_elbow.x, right_elbow.y),
                    (right_wrist.x, right_wrist.y)
                )
                
                # 膝盖角度（右腿）
                right_hip = landmarks[24]        # RIGHT_HIP
                right_knee = landmarks[26]       # RIGHT_KNEE
                right_ankle = landmarks[28]      # RIGHT_ANKLE
                
                knee_angle = calculate_angle(
                    (right_hip.x, right_hip.y),
                    (right_knee.x, right_knee.y),
                    (right_ankle.x, right_ankle.y)
                )
                
                # 肩部角度（判断 trophy 位置）
                left_shoulder = landmarks[11]    # LEFT_SHOULDER
                shoulder_angle = calculate_angle(
                    (left_shoulder.x, left_shoulder.y),
                    (right_shoulder.x, right_shoulder.y),
                    (right_elbow.x, right_elbow.y)
                )
                
                pose_data.append({
                    'frame': frame_count,
                    'timestamp': frame_count / fps,
                    'elbow_angle': elbow_angle,
                    'knee_angle': knee_angle,
                    'shoulder_angle': shoulder_angle
                })
                
                if len(pose_data) % 10 == 0:
                    print(f"   已分析 {len(pose_data)} 帧...")
    
    cap.release()
    landmarker.close()
    print(f"✅ 姿态分析完成: {len(pose_data)} 帧")
    
    return pose_data

def analyze_with_legacy_mediapipe(video_path):
    """使用旧版 MediaPipe API 分析"""
    print("   使用旧版 MediaPipe API...")
    
    # 旧版导入
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    pose_data = []
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        if frame_count % 5 != 0:
            continue
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)
        
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            
            # 提取关键点并计算角度
            right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            right_elbow = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
            right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
            
            elbow_angle = calculate_angle(
                (right_shoulder.x, right_shoulder.y),
                (right_elbow.x, right_elbow.y),
                (right_wrist.x, right_wrist.y)
            )
            
            right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
            right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
            right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
            
            knee_angle = calculate_angle(
                (right_hip.x, right_hip.y),
                (right_knee.x, right_knee.y),
                (right_ankle.x, right_ankle.y)
            )
            
            pose_data.append({
                'frame': frame_count,
                'timestamp': frame_count / fps,
                'elbow_angle': elbow_angle,
                'knee_angle': knee_angle,
                'shoulder_angle': 90  # 默认值
            })
    
    cap.release()
    pose.close()
    
    print(f"✅ 姿态分析完成: {len(pose_data)} 帧")
    return pose_data

def calculate_angle(a, b, c):
    """计算三点形成的角度"""
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    
    if angle > 180.0:
        angle = 360 - angle
    
    return angle

def evaluate_with_coach_knowledge(pose_data, knowledge_list):
    """使用三位教练（Yellow、杨超、灵犀）的知识库评估姿态数据"""
    print("\n📋 使用三位教练知识库进行评估...")
    print(f"   知识库条目: {len(knowledge_list)} 条")
    
    if not pose_data:
        return {
            'total_score': 50,
            'bucket': '2.0',
            'issues': ['未检测到姿态数据'],
            'applied_rules': []
        }
    
    # 统计数据
    elbow_angles = [d['elbow_angle'] for d in pose_data]
    knee_angles = [d['knee_angle'] for d in pose_data]
    shoulder_angles = [d.get('shoulder_angle', 90) for d in pose_data]
    
    avg_elbow = sum(elbow_angles) / len(elbow_angles)
    avg_knee = sum(knee_angles) / len(knee_angles)
    min_knee = min(knee_angles)
    max_elbow = max(elbow_angles)
    
    print(f"   平均肘部角度: {avg_elbow:.1f}°")
    print(f"   平均膝盖角度: {avg_knee:.1f}°")
    print(f"   最小膝盖角度: {min_knee:.1f}°")
    print(f"   最大肘部角度: {max_elbow:.1f}°")
    
    # 基础分数
    base_score = 70
    issues = []
    applied_rules = []
    
    # 应用三位教练的知识库进行评估
    coach_applied = {'Yellow': 0, '杨超': 0, '灵犀': 0}
    
    for knowledge in knowledge_list:
        rule_applied = False
        coach_name = knowledge.get('coach_name', 'unknown')
        phase = knowledge.get('phase', '')
        
        # 根据知识阶段和标签进行评估
        if phase == 'loading' or '蓄力' in str(knowledge.get('issue_tags', '')):
            # 蓄力阶段：检查膝盖弯曲程度
            if min_knee > 120:
                issues.append({
                    'coach': coach_name,
                    'rule': knowledge.get('title', '未知'),
                    'description': knowledge.get('summary', ''),
                    'common_errors': knowledge.get('common_errors', ''),
                    'training_advice': knowledge.get('correction_method', ''),
                    'severity': 'medium'
                })
                base_score -= 3
                rule_applied = True
                
        elif phase == 'contact' or '击球' in str(knowledge.get('issue_tags', '')):
            # 击球阶段：检查肘部伸展
            if max_elbow < 150:
                issues.append({
                    'coach': coach_name,
                    'rule': knowledge.get('title', '未知'),
                    'description': knowledge.get('summary', ''),
                    'common_errors': knowledge.get('common_errors', ''),
                    'training_advice': knowledge.get('correction_method', ''),
                    'severity': 'low'
                })
                base_score -= 3
                rule_applied = True
        
        if rule_applied:
            applied_rules.append(knowledge.get('title', '未知'))
            coach_applied[coach_name] = coach_applied.get(coach_name, 0) + 1
    
    # 计算档位
    final_score = max(0, min(100, base_score))
    if final_score >= 90:
        bucket = '5.0+'
    elif final_score >= 80:
        bucket = '4.0'
    elif final_score >= 62:
        bucket = '3.0'
    else:
        bucket = '2.0'
    
    print(f"\n📊 评分结果:")
    print(f"   总分: {final_score}")
    print(f"   档位: {bucket}")
    print(f"   发现问题: {len(issues)} 个")
    print(f"   应用规则: {len(applied_rules)} 条")
    print(f"   教练引用: Yellow({coach_applied.get('Yellow', 0)}), 杨超({coach_applied.get('杨超', 0)}), 灵犀({coach_applied.get('灵犀', 0)})")
    
    return {
        'total_score': final_score,
        'bucket': bucket,
        'issues': issues,
        'applied_rules': applied_rules,
        'statistics': {
            'avg_elbow_angle': avg_elbow,
            'avg_knee_angle': avg_knee,
            'min_knee_angle': min_knee,
            'max_elbow_angle': max_elbow,
            'frames_analyzed': len(pose_data)
        }
    }

def generate_full_report(video_path, pose_data, evaluation):
    """生成完整的分析报告"""
    report = {
        'video_path': video_path,
        'analysis_time': datetime.now().isoformat(),
        'mediapipe_version': mp.__version__,
        'frames_analyzed': len(pose_data),
        'evaluation': evaluation,
        'summary': {
            'total_score': evaluation['total_score'],
            'bucket': evaluation['bucket'],
            'main_issues': [i['rule'] for i in evaluation['issues'][:3]]
        }
    }
    
    return report

def main():
    if len(sys.argv) < 2:
        print("用法: python tennis_analyzer_v2.py <视频路径>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    print("=" * 60)
    print("🎾 网球发球分析系统")
    print("   MediaPipe + 杨超教练知识点")
    print("=" * 60)
    
    # 1. 加载规则
    print("\n📚 加载杨超教练知识点...")
    rules = load_serve_rules()
    print(f"   已加载 {len(rules)} 条规则")
    
    # 2. MediaPipe 姿态分析
    pose_data = analyze_video_with_mediapipe(video_path)
    
    # 3. 规则评估
    evaluation = evaluate_with_rules(pose_data, rules)
    
    # 4. 生成报告
    report = generate_full_report(video_path, pose_data, evaluation)
    
    # 输出结果
    print("\n" + "=" * 60)
    print("📄 分析报告")
    print("=" * 60)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    # 输出关键信息供 Node.js 调用
    print(f"\n📊 FINAL_SCORE:{evaluation['total_score']}")
    print(f"📊 BUCKET:{evaluation['bucket']}")
    print(f"📊 ISSUES_COUNT:{len(evaluation['issues'])}")
    
    return report

if __name__ == '__main__':
    main()
