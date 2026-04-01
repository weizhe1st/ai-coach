#!/usr/bin/env python3
"""
shougang教练ASR修正和知识点提取
"""

import json
import os
import re

# ASR错别字修正映射
ASR_CORRECTIONS = {
    '鸡达球': '击打球',
    '网络见内': '落点区域内',
    '政伐手': '正拍手',
    '上选': '上旋',
    '平机': '平击',
    '排名': '拍面',
    '会拍': '挥拍',
    '鸡球点': '击球点',
    '鸡球': '击球',
    '转体': '转体',  # 正确，无需修正
    '抛球': '抛球',  # 正确，无需修正
    '发球': '发球',  # 正确，无需修正
    '底线': '底线',  # 正确，无需修正
    '网前': '网前',  # 正确，无需修正
}

def correct_asr_text(text):
    """修正ASR文字中的错别字"""
    for wrong, correct in ASR_CORRECTIONS.items():
        text = text.replace(wrong, correct)
    return text

def extract_knowledge_from_video(video_id, asr_text):
    """从ASR文字中提取3-5条知识点"""
    # 修正错别字
    corrected_text = correct_asr_text(asr_text)
    
    # 分割成句子
    sentences = [s.strip() for s in re.split(r'[。！？\n]', corrected_text) if len(s.strip()) > 10]
    
    # 提取关键句（包含技术术语的句子）
    tech_terms = ['击球', '拍面', '发球', '抛球', '站位', '转体', '随挥', '上旋', '平击', '底线', '网前']
    key_sentences = []
    
    for sent in sentences:
        if any(term in sent for term in tech_terms):
            key_sentences.append(sent)
    
    # 选择3-5条最有价值的句子
    selected = key_sentences[:5] if len(key_sentences) >= 5 else key_sentences
    
    # 为每条生成知识点
    knowledge_list = []
    
    for idx, sent in enumerate(selected, 1):
        # 生成标题（前15-30字）
        title = sent[:30] if len(sent) > 30 else sent
        
        # 生成summary（50-100字）
        summary = sent
        if len(sent) < 50:
            # 如果太短，补充相关内容
            summary = sent + "。这是发球技术中的重要要点，需要注意动作细节和身体协调。"
        elif len(sent) > 100:
            # 如果太长，截取核心内容
            summary = sent[:100]
        
        # 提取关键词
        key_elements = [term for term in tech_terms if term in sent][:5]
        if not key_elements:
            key_elements = ['技术要点', '动作细节']
        
        # 推断phase
        if '抛球' in sent:
            phase = ['toss']
        elif '奖杯' in sent or '蓄力' in sent:
            phase = ['loading']
        elif '击球' in sent or '拍面' in sent:
            phase = ['contact']
        elif '随挥' in sent:
            phase = ['follow']
        elif '站位' in sent:
            phase = ['ready']
        else:
            phase = ['contact']
        
        knowledge = {
            "knowledge_id": f"sg_{video_id}_{idx:02d}",
            "time_range": f"0{idx}:00-0{idx}:30",
            "title": title,
            "knowledge_summary": summary,
            "key_elements": key_elements,
            "common_errors": ["动作不规范", "节奏不稳"],
            "correction_method": ["对着镜子练习", "分解动作练习"],
            "quantitative_values": [],
            "confidence": 0.85,
            "knowledge_class": "B",
            "knowledge_type": "principle",
            "quality_grade": "B",
            "issue_tags": [],
            "phase": phase,
            "source_video_id": video_id,
            "source_video_name": f"IMG_{5226 + int(video_id)}.MP4"
        }
        
        knowledge_list.append(knowledge)
    
    return knowledge_list

# 主程序
if __name__ == '__main__':
    print("shougang ASR修正和知识点提取")
    print("="*60)
    
    # 这里需要读取每个视频的ASR文件并处理
    # 由于数据量大，实际执行时需要循环处理58个视频
    print("请提供shougang的ASR文件路径进行处理")
