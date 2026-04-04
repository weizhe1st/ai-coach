#!/usr/bin/env python3
"""
完整版报告生成器 - 包含样本库、知识库、黄金标准等所有内容
"""

import json
from datetime import datetime

def generate_complete_report(result, quality_info, knowledge_results=None, 
                             similar_cases=None, mp_metrics=None, level_standards=None):
    """
    生成完整的分析报告，包含所有内容：
    - 样本库引用
    - 教练知识库详细引用
    - 黄金标准对比
    - MediaPipe量化指标
    - 一致性检查
    """
    
    ntrp_level = result.get('ntrp_level', '?')
    ntrp_name = result.get('ntrp_level_name', '未知')
    confidence = result.get('confidence', 0)
    overall_score = result.get('overall_score', 0)
    serves_observed = result.get('serves_observed', 1)
    phases = result.get('phase_analysis', {})
    key_issues = result.get('key_issues', [])
    training = result.get('training_plan', [])
    reasoning = result.get('level_reasoning', '')
    consistency = result.get('consistency_note', '')
    serves_detected = result.get('serves_detected', [])
    
    # 默认等级描述
    default_standards = {
        '2.0': '入门：动作不完整，无背挠，抛球不稳',
        '2.5': '初级：动作基本完整，但质量一般',
        '3.0': '基础：框架完整但执行质量一般',
        '3.5': '进阶：框架完整有流畅性',
        '4.0': '熟练：流畅连贯，膝盖深蹲',
        '4.5': '高级：高度流畅，明确旋转意图',
        '5.0': '精通：教科书标准，完整动力链',
        '5.0+': '专业：职业水平，完美动力链'
    }
    
    level_desc = level_standards.get('description', default_standards.get(ntrp_level, '未知等级')) if level_standards else default_standards.get(ntrp_level, '未知等级')
    
    lines = []
    
    # ─── 第一行：等级 + 核心短板 ──────────────────────────
    top_issue = ''
    for iss in key_issues:
        if iss.get('severity') == 'high':
            top_issue = iss.get('issue', '')
            break
    if not top_issue and key_issues:
        top_issue = key_issues[0].get('issue', '')
    
    level_emoji = {'2.0': '🌱', '2.5': '🌿', '3.0': '🌳', '3.5': '🌲', '4.0': '🏆', '4.5': '🥈', '5.0': '🥇', '5.0+': '👑'}.get(ntrp_level, '🎯')
    
    if top_issue:
        lines.append(f"{level_emoji} {ntrp_level}级 核心短板：{top_issue}")
    else:
        lines.append(f"{level_emoji} {ntrp_level}级（{ntrp_name}） 置信度{confidence:.0%}")
    lines.append('')
    
    # ─── 等级标准说明 ────────────────────────────────────
    lines.append(f"📚 {ntrp_level}级标准：{level_desc}")
    lines.append('')
    
    # ─── MediaPipe量化指标（如果有）────────────────────────
    if mp_metrics:
        lines.append('📏 量化指标参考：')
        if mp_metrics.get('min_knee_angle'):
            knee = mp_metrics['min_knee_angle']
            knee_level = '4.5+' if knee < 100 else '4.0' if knee < 120 else '3.5' if knee < 140 else '3.0'
            lines.append(f"  膝盖角度：{knee:.1f}° (约{knee_level}级水平)")
        if mp_metrics.get('max_elbow_angle'):
            lines.append(f"  肘部角度：{mp_metrics['max_elbow_angle']:.1f}°")
        if mp_metrics.get('max_shoulder_rotation'):
            lines.append(f"  肩部旋转：{mp_metrics['max_shoulder_rotation']:.1f}°")
        
        # 一致性检查
        comparison = result.get('_mp_comparison', {})
        if comparison and comparison.get('consistency_check'):
            lines.append(f"  ⚠️ 注意：{comparison['consistency_check'][0]}")
        lines.append('')
    
    # ─── 多次发球检测（如果有）─────────────────────────────
    if serves_detected and len(serves_detected) > 0:
        lines.append(f'🎾 检测到 {len(serves_detected)} 次发球：')
        for serve in serves_detected[:3]:  # 最多显示3次
            idx = serve.get('index', 1)
            time_range = serve.get('time_range', '')
            quality = serve.get('quality_note', '')
            lines.append(f"  第{idx}次 ({time_range})：{quality}")
        if len(serves_detected) > 3:
            lines.append(f"  ... 还有 {len(serves_detected)-3} 次")
        lines.append('')
    
    # ─── 五阶段分数 + 知识库引用 ──────────────────────────
    lines.append('📊 五阶段分析：')
    phase_list = [('ready', '准备'), ('toss', '抛球'), ('loading', '蓄力'), ('contact', '击球'), ('follow', '随挥')]
    scores = {k: max(0, min(100, phases.get(k, {}).get('score', 0))) for k, _ in phase_list}
    
    # 显示分数
    lines.append(f"  准备{scores['ready']}  抛球{scores['toss']}  蓄力{scores['loading']}")
    lines.append(f"  击球{scores['contact']}  随挥{scores['follow']}  总分{overall_score}")
    lines.append('')
    
    # 显示每个阶段的知识库建议
    if knowledge_results:
        lines.append('💡 教练知识库建议（已召回知识点）：')
        has_knowledge = False
        for phase_key, phase_name in phase_list:
            if phase_key in knowledge_results and knowledge_results[phase_key]:
                phase_knowledge = knowledge_results[phase_key]
                # 检查是否有实际内容
                total_items = sum(len(items) for items in phase_knowledge.values())
                if total_items > 0:
                    has_knowledge = True
                    lines.append(f"  【{phase_name}】")
                    for coach, items in phase_knowledge.items():
                        if items:
                            content = items[0].get('knowledge_summary', '') or items[0].get('title', '')
                            lines.append(f"    • {coach}：{content[:50]}...")
        if not has_knowledge:
            lines.append("  （本次分析未匹配到特定知识点）")
        lines.append('')
    
    # ─── 必改问题 ────────────────────────────────────────
    if key_issues:
        lines.append('🔴 必改要点：')
        severity_emojis = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        sorted_issues = sorted(key_issues, key=lambda x: severity_order.get(x.get('severity', 'medium'), 1))
        
        serial = ['①', '②', '③']
        for i, iss in enumerate(sorted_issues[:3]):
            sev = iss.get('severity', 'medium')
            emoji = severity_emojis.get(sev, '⚪')
            issue = iss.get('issue', '')
            advice = iss.get('coach_advice', '')
            lines.append(f"{serial[i]} {emoji} {issue}")
            if advice:
                lines.append(f"   → {advice}")
        lines.append('')
    
    # ─── 本周训练建议 ────────────────────────────────────
    if training:
        lines.append('💪 本周练习：')
        for i, plan in enumerate(training[:3], 1):
            lines.append(f"{i}. {plan}")
        lines.append('')
    
    # ─── 相似案例 ────────────────────────────────────────
    if similar_cases and len(similar_cases) > 0:
        lines.append('👥 黄金标准相似案例参考：')
        lines.append(f"  （样本库中 {ntrp_level} 级共有 {len(similar_cases)} 个参考案例）")
        for i, case in enumerate(similar_cases[:3], 1):
            level = case.get('level', 'N/A')
            notes = case.get('notes', '')[:30]
            source = case.get('source', 'unknown')
            lines.append(f"  {i}. [{level}级|{source}] {notes}...")
        lines.append('')
    
    # ─── 一致性备注 ──────────────────────────────────────
    if consistency:
        lines.append(f"📝 备注：{consistency}")
        lines.append('')
    
    # ─── 底部总览 ────────────────────────────────────────
    lines.append(f"📈 总分{overall_score} | 置信度{confidence:.0%} | 观察{serves_observed}次发球")
    
    # ─── 等级推理 ────────────────────────────────────────
    if reasoning:
        short = reasoning[:80] + '…' if len(reasoning) > 80 else reasoning
        lines.append(f"🎯 判定：{short}")
    
    return '\n'.join(lines)


# 测试
if __name__ == '__main__':
    mock_result = {
        'ntrp_level': '3.0',
        'ntrp_level_name': '基础级',
        'confidence': 0.75,
        'overall_score': 55,
        'serves_observed': 2,
        'serves_detected': [
            {'index': 1, 'time_range': '0s-8s', 'quality_note': '动作完整'},
            {'index': 2, 'time_range': '12s-20s', 'quality_note': '抛球偏右'}
        ],
        'phase_analysis': {
            'ready': {'score': 80, 'issues': ['重心偏后']},
            'toss': {'score': 50, 'issues': ['抛球偏内侧']},
            'loading': {'score': 45, 'issues': ['膝盖蓄力不足']},
            'contact': {'score': 55, 'issues': ['旋内不足']},
            'follow': {'score': 60, 'issues': []},
        },
        'key_issues': [
            {'issue': '膝盖蓄力不足（约150度）', 'severity': 'high', 'coach_advice': '目标弯到120度'},
            {'issue': '抛球偏向身体内侧', 'severity': 'high', 'coach_advice': '对墙抛球练习'},
            {'issue': '旋内幅度不足', 'severity': 'medium', 'coach_advice': '短拍练旋内'},
        ],
        'training_plan': ['对镜练奖杯姿势', '每天50次抛球练习', '短拍练旋内'],
        'consistency_note': '第2次发球抛球偏右约20cm',
        'level_reasoning': '膝盖弯曲约150度，典型3.0级特征。',
    }
    
    mock_knowledge = {
        'loading': {
            '杨超': [{'knowledge_summary': '膝盖要弯曲到90度', 'title': '膝盖弯曲要点'}],
            '赵凌曦': [{'knowledge_summary': '1-2-3节奏很重要', 'title': '蓄力节奏'}]
        }
    }
    
    mock_cases = [
        {'level': '3.0', 'notes': 'NTRP 3.0发球案例'},
        {'level': '3.0', 'notes': '室内双打3.0'},
    ]
    
    mock_mp = {
        'min_knee_angle': 150.5,
        'max_elbow_angle': 165.2
    }
    
    report = generate_complete_report(mock_result, {'status': 'ok'}, 
                                     mock_knowledge, mock_cases, mock_mp)
    print(report)
    
    # 验证
    assert '█' not in report and '░' not in report
    assert '膝盖蓄力不足' in report
    assert '杨超' in report
    assert '相似案例' in report
    print('\n✓ 完整报告生成成功！')
