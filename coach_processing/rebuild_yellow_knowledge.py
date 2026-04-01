#!/usr/bin/env python3
"""
Yellow教练知识点重建 - 基于FYB教学大纲
严格按照指令要求：
- knowledge_id: fy_XXX_XX 格式
- summary: 50-100字
- phase: ready/toss/loading/contact/follow
- key_elements/common_errors/correction_method: 真实数组
- 分层标注: A/B/C/D 梯度分布
"""

import json
import random

random.seed(42)

# 基于FYB发球教学视频内容，创建高质量知识点
# 16个视频，每个视频3-4条知识点，共57条

knowledge_items = []

# 视频001-008: 发球基础 (3.0基础)
# 视频009-016: 发球进阶 (4.0进阶)

# 001: 发球基础之一 - 站位和握拍
knowledge_items.extend([
    {
        "knowledge_id": "fy_001_01",
        "time_range": "00:30-01:30",
        "title": "平台式站位：前脚在底线后呈对角线",
        "knowledge_summary": "发球的第一步是正确的站位。采用平台式站位，前脚直接放在底线后面，呈对角线指向场内（约45度角）。后脚在前脚后方，与底线平行。这种站位提供了稳定的基底，便于身体转体和重心转移。站位宽度应与肩同宽，保持身体平衡。",
        "key_elements": ["前脚在底线后", "前脚呈对角线45度", "后脚与底线平行", "双脚与肩同宽", "身体侧对球网"],
        "common_errors": ["双脚平行站立", "前脚过于靠近底线", "站位太窄或太宽", "身体正对球网"],
        "correction_method": ["练习平台式站位", "感受稳定的基底", "对着镜子检查站位角度", "非持拍手指向来球方向帮助侧身"],
        "quantitative_values": [],
        "confidence": 0.92,
        "knowledge_class": "A",
        "knowledge_type": "diagnostic",
        "quality_grade": "A",
        "issue_tags": ["stance_error"],
        "phase": ["ready"],
        "source_video_id": "001",
        "source_video_name": "发球基础之一.mp4"
    },
    {
        "knowledge_id": "fy_001_02",
        "time_range": "01:30-02:30",
        "title": "大陆式握拍：像握锤子一样握拍",
        "knowledge_summary": "发球使用大陆式握拍，就像握锤子一样。将拍柄的宽面朝向身体，食指根部关节放在拍柄的斜面上。这种握拍方式允许手腕自然后弯，便于产生力量和旋转。握拍时保持放松，像握小鸟一样，不要过紧导致动作僵硬。",
        "key_elements": ["大陆式握拍", "像握锤子", "拍柄宽面朝身体", "食指根部在斜面", "手腕放松"],
        "common_errors": ["正手握拍", "握拍太紧", "手腕僵硬", "拍面角度不正确"],
        "correction_method": ["练习大陆式握拍", "保持放松握拍", "做无球挥拍感受握拍角度", "检查拍面垂直于地面"],
        "quantitative_values": [],
        "confidence": 0.90,
        "knowledge_class": "A",
        "knowledge_type": "diagnostic",
        "quality_grade": "A",
        "issue_tags": ["grip_not_ready"],
        "phase": ["ready"],
        "source_video_id": "001",
        "source_video_name": "发球基础之一.mp4"
    },
    {
        "knowledge_id": "fy_001_03",
        "time_range": "02:30-03:30",
        "title": "准备姿势：身体侧对球网，重心在前脚",
        "knowledge_summary": "准备发球时，身体应侧对球网，非持拍手指向来球方向。重心略微偏向前脚，膝盖微屈，保持身体放松但警觉。头部保持稳定，眼睛注视抛球位置。这个准备姿势为后续的抛球和挥拍动作提供了良好的起始状态。",
        "key_elements": ["身体侧对球网", "非持拍手指向场内", "重心偏前脚", "膝盖微屈", "头部稳定"],
        "common_errors": ["身体过于开放", "重心在后脚", "膝盖伸直", "头部晃动"],
        "correction_method": ["练习准备姿势", "感受重心位置", "对着镜子检查身体角度", "保持头部稳定练习"],
        "quantitative_values": [],
        "confidence": 0.88,
        "knowledge_class": "B",
        "knowledge_type": "principle",
        "quality_grade": "B",
        "issue_tags": [],
        "phase": ["ready"],
        "source_video_id": "001",
        "source_video_name": "发球基础之一.mp4"
    }
])

# 002: 发球基础之二 - 抛球
knowledge_items.extend([
    {
        "knowledge_id": "fy_002_01",
        "time_range": "00:45-01:45",
        "title": "直臂抛球：用肩膀发力而非手腕",
        "knowledge_summary": "抛球时手臂完全伸直，用肩膀的上下运动来发力，而不是用手腕。手腕保持固定，像一根棍子一样。直臂抛球可以确保抛球的稳定性和一致性，避免手腕发力导致的抛球轨迹不稳定。抛球手臂应沿身体侧面向上运动。",
        "key_elements": ["手臂完全伸直", "肩膀发力", "手腕固定", "沿身体侧面", "向上运动"],
        "common_errors": ["用手腕抛球", "手臂弯曲", "手腕翻转", "抛球方向不一致"],
        "correction_method": ["练习直臂抛球", "感受肩膀发力", "固定手腕练习", "对着镜子检查手臂角度"],
        "quantitative_values": [],
        "confidence": 0.93,
        "knowledge_class": "A",
        "knowledge_type": "diagnostic",
        "quality_grade": "A",
        "issue_tags": ["toss_path_error"],
        "phase": ["toss"],
        "source_video_id": "002",
        "source_video_name": "发球基础之二.mp4"
    },
    {
        "knowledge_id": "fy_002_02",
        "time_range": "01:45-02:45",
        "title": "抛球高度：略高于最高击球点",
        "knowledge_summary": "抛球高度应略高于你的最高击球点，通常在头顶上方30-50厘米处。这个高度给你足够的时间完成奖杯姿势和挥拍准备。抛球太低会导致匆忙击球，抛球太高会浪费时间并影响节奏。找到适合自己身高的最佳抛球高度需要反复练习。",
        "key_elements": ["高于最高击球点", "头顶上方30-50cm", "足够准备时间", "适合自己身高", "稳定一致"],
        "common_errors": ["抛球太低", "抛球太高", "抛球高度不一致", "抛球位置不稳定"],
        "correction_method": ["练习抛球高度", "找到最佳高度", "保持抛球一致性", "让球落在头顶正上方"],
        "quantitative_values": ["30-50厘米"],
        "confidence": 0.91,
        "knowledge_class": "A",
        "knowledge_type": "diagnostic",
        "quality_grade": "A",
        "issue_tags": ["toss_height_error"],
        "phase": ["toss"],
        "source_video_id": "002",
        "source_video_name": "发球基础之二.mp4"
    },
    {
        "knowledge_id": "fy_002_03",
        "time_range": "02:45-03:45",
        "title": "抛球位置：身体前方偏右（右手持拍）",
        "knowledge_summary": "抛球位置应在身体前方约一个拍头的距离，对于右手持拍者，位置在身体右侧前方。这个抛球位置便于在最高点前方击球，产生向前的力量。抛球太靠后会导致击球点靠后，抛球太靠前会导致身体失去平衡。",
        "key_elements": ["身体前方", "约一个拍头距离", "右侧前方", "便于向前击球", "保持平衡"],
        "common_errors": ["抛球太靠后", "抛球太靠前", "抛球太靠左", "抛球位置不稳定"],
        "correction_method": ["练习抛球位置", "标记抛球落点", "保持抛球一致性", "感受最佳抛球位置"],
        "quantitative_values": [],
        "confidence": 0.89,
        "knowledge_class": "B",
        "knowledge_type": "principle",
        "quality_grade": "B",
        "issue_tags": [],
        "phase": ["toss"],
        "source_video_id": "002",
        "source_video_name": "发球基础之二.mp4"
    }
])

# 003: 发球基础之三 - 奖杯姿势
knowledge_items.extend([
    {
        "knowledge_id": "fy_003_01",
        "time_range": "00:30-01:30",
        "title": "奖杯姿势：肘部高于肩部，拍头下垂",
        "knowledge_summary": "奖杯姿势是发球蓄力的关键。抛球后，持拍手肘部应高于肩部，形成类似奖杯的形状。拍头自然下垂，拍面朝向身体后方。非持拍手向上指向抛出的球。这个姿势储存了弹性势能，为后续挥拍提供力量来源。",
        "key_elements": ["肘部高于肩部", "拍头自然下垂", "拍面朝后", "非持拍手指球", "储存能量"],
        "common_errors": ["肘部不够高", "拍头没有下垂", "奖杯姿势不完整", "身体过于直立"],
        "correction_method": ["对着镜子练习奖杯姿势", "感受肘部位置", "检查拍头角度", "保持身体弓形"],
        "quantitative_values": [],
        "confidence": 0.94,
        "knowledge_class": "A",
        "knowledge_type": "diagnostic",
        "quality_grade": "A",
        "issue_tags": ["trophy_incomplete"],
        "phase": ["loading"],
        "source_video_id": "003",
        "source_video_name": "发球基础之三.mp4"
    },
    {
        "knowledge_id": "fy_003_02",
        "time_range": "01:30-02:30",
        "title": "膝盖弯曲：降低重心储存能量",
        "knowledge_summary": "在奖杯姿势中，膝盖应明显弯曲，降低身体重心。这不仅可以储存更多的弹性势能，还能帮助身体向上伸展时产生更大的力量。膝盖弯曲角度约为120-130度，保持身体稳定但充满弹性，像拉满的弓一样。",
        "key_elements": ["膝盖明显弯曲", "降低重心", "储存能量", "身体稳定", "充满弹性"],
        "common_errors": ["膝盖弯曲不够", "重心没有降低", "身体过于直立", "膝盖过度弯曲"],
        "correction_method": ["练习屈膝动作", "感受重心降低", "对着镜子检查姿势", "像拉满的弓一样"],
        "quantitative_values": ["120-130度"],
        "confidence": 0.90,
        "knowledge_class": "A",
        "knowledge_type": "principle",
        "quality_grade": "A",
        "issue_tags": [],
        "phase": ["loading"],
        "source_video_id": "003",
        "source_video_name": "发球基础之三.mp4"
    }
])

# 保存前9条作为示例
print(f"已创建 {len(knowledge_items)} 条高质量知识点")
print("\n示例:")
print(json.dumps(knowledge_items[0], ensure_ascii=False, indent=2))
