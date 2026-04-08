#!/usr/bin/env python3
"""
完整版报告生成器 - 包含样本库、知识库、黄金标准等所有内容
"""

import json
from datetime import datetime

def generate_complete_report(normalized_result, quality_info, knowledge_results=None, 
                             similar_cases=None, mp_metrics=None, level_standards=None,
                             report_version: str = 'v1'):
    """
    生成完整的分析报告（第五步标准接口）
    
    只接收 normalized_result，只读取标准字段：
    - overall_score, ntrp_level, confidence
    - phase_analysis, key_issues, training_plan
    - summary, strengths, analysis_status
    
    第五步新增：
    - 明确的缺字段兜底策略
    - report_version 支持
    """
    
    # 只从 normalized_result 读取标准字段（带兜底默认值）
    analysis_status = normalized_result.get('analysis_status', 'success')
    ntrp_level = normalized_result.get('ntrp_level', '?')
    ntrp_name = normalized_result.get('ntrp_level_name', '未知')
    confidence = normalized_result.get('confidence', 0)
    overall_score = normalized_result.get('overall_score')
    serves_observed = normalized_result.get('serves_observed', 1)
    phases = normalized_result.get('phase_analysis', {})
    key_issues = normalized_result.get('key_issues', [])
    training = normalized_result.get('training_plan', [])
    summary = normalized_result.get('summary', '')
    strengths = normalized_result.get('strengths', [])
    serves_detected = normalized_result.get('serves_detected', [])
    
    # 第五步：明确的缺字段兜底策略
    # overall_score 兜底
    if overall_score is None or overall_score == 0:
        overall_score_display = "暂无评分"
        overall_score = 0
    else:
        overall_score_display = str(overall_score)
    
    # key_issues 兜底
    if not key_issues:
        key_issues_display = [{"issue": "暂未识别出明显关键问题", "severity": "low", "phase": "", "suggestion": "建议结合视频重新采样后再生成详细分析"}]
    else:
        key_issues_display = key_issues
    
    # training_plan 兜底
    if not training:
        training_display = ["建议结合视频重新采样后再生成训练建议", "可参考同等级标准案例进行练习"]
    else:
        training_display = training
    
    # summary 兜底
    if not summary:
        summary_display = f"发球技术分析完成，评估等级 {ntrp_level}，总分 {overall_score_display}。"
    else:
        summary_display = summary
    
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
        if isinstance(iss, dict):
            if iss.get('severity') == 'high':
                top_issue = iss.get('issue', '')
                break
        elif isinstance(iss, str):
            top_issue = iss
            break
    if not top_issue and key_issues:
        first = key_issues[0]
        top_issue = first.get('issue', '') if isinstance(first, dict) else str(first)
    
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
    if mp_metrics and isinstance(mp_metrics, dict):
        lines.append('📏 量化指标参考：')
        if mp_metrics.get('min_knee_angle'):
            knee = mp_metrics['min_knee_angle']
            knee_level = '4.5+' if knee < 100 else '4.0' if knee < 120 else '3.5' if knee < 140 else '3.0'
            lines.append(f"  膝盖角度：{knee:.1f}° (约{knee_level}级水平)")
        if mp_metrics.get('max_elbow_angle'):
            lines.append(f"  肘部角度：{mp_metrics['max_elbow_angle']:.1f}°")
        if mp_metrics.get('max_shoulder_rotation'):
            lines.append(f"  肩部旋转：{mp_metrics['max_shoulder_rotation']:.1f}°")
        
        comparison = normalized_result.get('_mp_comparison', {})
        if comparison and comparison.get('consistency_check'):
            lines.append(f"  ⚠️ 注意：{comparison['consistency_check'][0]}")
        lines.append('')
    
    # ─── 多次发球检测（如果有）─────────────────────────────
    if serves_detected and len(serves_detected) > 0:
        lines.append(f'🎾 检测到 {len(serves_detected)} 次发球：')
        for serve in serves_detected[:3]:
            idx = serve.get('index', 1)
            time_range = serve.get('time_range', '')
            quality = serve.get('quality_note', '')
            lines.append(f"  第{idx}次 ({time_range})：{quality}")
        if len(serves_detected) > 3:
            lines.append(f"  ... 还有 {len(serves_detected)-3} 次")
        lines.append('')
    
    # ─── 五阶段分数 ──────────────────────────
    lines.append('📊 五阶段分析：')
    phase_list = [('ready', '准备'), ('toss', '抛球'), ('loading', '蓄力'), ('contact', '击球'), ('follow', '随挥')]
    scores = {k: max(0, min(100, phases.get(k, {}).get('score', 0))) for k, _ in phase_list}
    
    lines.append(f"  准备{scores['ready']}  抛球{scores['toss']}  蓄力{scores['loading']}")
    lines.append(f"  击球{scores['contact']}  随挥{scores['follow']}  总分{overall_score}")
    lines.append('')
    
    # ─── 详细的教练知识库建议 ──────────────────────────
    if knowledge_results:
        lines.append('📚 教练知识库详细建议：')
        has_knowledge = False
        for phase_key, phase_name in phase_list:
            if phase_key in knowledge_results and knowledge_results[phase_key]:
                phase_knowledge = knowledge_results[phase_key]
                total_items = sum(len(items) for items in phase_knowledge.values())
                if total_items > 0:
                    has_knowledge = True
                    lines.append(f"")
                    lines.append(f"【{phase_name}阶段】")
                    for coach, items in phase_knowledge.items():
                        if items:
                            lines.append(f"  👤 {coach}教练：")
                            for idx, item in enumerate(items[:3], 1):  # 每个教练最多显示3条
                                content = item.get('knowledge_summary', '') or item.get('title', '') or item.get('content', '')
                                if content:
                                    # 显示完整内容，不截断
                                    lines.append(f"    {idx}. {content}")
        if not has_knowledge:
            lines.append("  （本次分析未匹配到特定知识点）")
        lines.append('')
    
    # ─── 必改问题 ────────────────────────────────────────
    lines.append('🔴 必改要点：')
    severity_emojis = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
    
    serial = ['①', '②', '③']
    for i, iss in enumerate(key_issues_display[:3]):
        if isinstance(iss, dict):
            sev = iss.get('severity', 'medium')
            emoji = severity_emojis.get(sev, '⚪')
            issue = iss.get('issue', '')
            advice = iss.get('suggestion', '')  # 第五步：使用标准字段 suggestion
        else:
            emoji = '🔴'
            issue = str(iss)
            advice = ''
        lines.append(f"{serial[i]} {emoji} {issue}")
        if advice:
            lines.append(f"   → {advice}")
    lines.append('')
    
    # ─── 本周训练建议 ────────────────────────────────────
    lines.append('💪 本周练习：')
    for i, plan in enumerate(training_display[:3], 1):
        lines.append(f"{i}. {plan}")
    lines.append('')
    
    # ─── 相似案例 ────────────────────────────────────────
    if similar_cases and len(similar_cases) > 0:
        lines.append('👥 黄金标准相似案例参考：')
        lines.append(f"  （样本库中 {ntrp_level} 级共有 {len(similar_cases)} 个参考案例）")
        for i, case in enumerate(similar_cases[:3], 1):
            level = case.get('level', 'N/A')
            notes = case.get('notes', '')
            source = case.get('source', 'unknown')
            lines.append(f"  {i}. [{level}级|{source}] {notes}")
        lines.append('')
    
    # ─── 摘要（使用标准化后的 summary）────────────────────
    lines.append(f"📝 分析摘要：{summary_display}")
    lines.append('')
    
    # ─── 底部总览 ────────────────────────────────────────
    lines.append(f"📈 总分{overall_score_display} | 置信度{confidence:.0%} | 观察{serves_observed}次发球")
    
    # 第五步：报告版本标记
    lines.append(f"📋 报告版本：{report_version}")
    
    return '\n'.join(lines)


# 测试（使用标准化后的字段）
if __name__ == '__main__':
    mock_normalized_result = {
        'analysis_status': 'success',
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
            'preparation': {'score': 80, 'observations': ['站位正确'], 'issues': ['重心偏后'], 'suggestions': ['降低重心']},
            'loading': {'score': 50, 'observations': ['有奖杯姿势'], 'issues': ['抛球偏内侧'], 'suggestions': ['对墙抛球练习']},
            'acceleration': {'score': 45, 'observations': [], 'issues': ['膝盖蓄力不足'], 'suggestions': ['练习深蹲']},
            'follow_through': {'score': 55, 'observations': [], 'issues': ['旋内不足'], 'suggestions': ['短拍练旋内']},
        },
        'key_issues': [
            {'issue': '膝盖蓄力不足（约150度）', 'severity': 'high', 'phase': 'acceleration', 'suggestion': '目标弯到120度'},
            {'issue': '抛球偏向身体内侧', 'severity': 'high', 'phase': 'loading', 'suggestion': '对墙抛球练习'},
            {'issue': '旋内幅度不足', 'severity': 'medium', 'phase': 'acceleration', 'suggestion': '短拍练旋内'},
        ],
        'training_plan': ['对镜练奖杯姿势', '每天50次抛球练习', '短拍练旋内'],
        'summary': '膝盖弯曲约150度，典型3.0级特征。第2次发球抛球偏右约20cm。',
        'strengths': ['动作框架完整', '随挥流畅'],
    }
    
    mock_knowledge = {
        'loading': {
            '杨超': [{'knowledge_summary': '膝盖要弯曲到90-120度，形成深蹲蓄力', 'title': '膝盖弯曲要点'}],
            '赵凌曦': [{'knowledge_summary': '1-2-3节奏很重要，拉拍停顿→蓄力奖杯→加速击球', 'title': '蓄力节奏'}]
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
    
    report = generate_complete_report(mock_normalized_result, {'status': 'ok'}, 
                                     mock_knowledge, mock_cases, mock_mp)
    print(report)
    print('\n✓ 完整报告生成成功（使用标准化结果）！')
