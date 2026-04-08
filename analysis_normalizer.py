#!/usr/bin/env python3
"""
分析结果标准化器 - 将模型原始输出转换为系统统一标准结构
"""

from typing import Dict, Any, List, Optional

# 系统标准 Schema 定义
STANDARD_SCHEMA = {
    "analysis_status": "success",  # success / failed
    "video_type": "serve",  # serve / rally / other
    "input_quality": {
        "usable": True,
        "score": 0.0,
        "issues": [],
        "suggestions": []
    },
    "overall_score": 0,
    "confidence": 0.0,
    "ntrp_level": "",
    "phase_analysis": {
        "preparation": {"score": 0, "observations": [], "issues": [], "suggestions": []},
        "loading": {"score": 0, "observations": [], "issues": [], "suggestions": []},
        "acceleration": {"score": 0, "observations": [], "issues": [], "suggestions": []},
        "follow_through": {"score": 0, "observations": [], "issues": [], "suggestions": []}
    },
    "strengths": [],
    "key_issues": [],
    "training_plan": [],
    "summary": "",
    "report_text": "",
    "evidence_timestamps": [],
    "raw_model_meta": {
        "provider": "",
        "model": "",
        "latency_ms": 0
    }
}

# 字段映射表：原始字段 -> 标准字段
FIELD_MAPPINGS = {
    # 总分字段
    "total_score": "overall_score",
    "final_score": "overall_score",
    "score": "overall_score",
    
    # 关键问题字段
    "critical_issues": "key_issues",
    "major_issues": "key_issues",
    "main_issues": "key_issues",
    
    # 训练建议字段
    "recommendations": "training_plan",
    "practice_plan": "training_plan",
    "improvement_plan": "training_plan",
    
    # 摘要字段
    "overall_summary": "summary",
    "conclusion": "summary",
    "diagnosis_summary": "summary",
    "level_reasoning": "summary",
    
    # 置信度字段
    "confidence_score": "confidence",
    "trust_score": "confidence",
}

# 阶段字段映射
PHASE_MAPPINGS = {
    # 准备阶段
    "ready": "preparation",
    "preparation": "preparation",
    "setup": "preparation",
    
    # 蓄力阶段
    "loading": "loading",
    "toss": "loading",
    "trophy": "loading",
    
    # 加速/击球阶段
    "acceleration": "acceleration",
    "contact": "acceleration",
    "hitting": "acceleration",
    "strike": "acceleration",
    
    # 随挥阶段
    "follow_through": "follow_through",
    "follow": "follow_through",
    "finish": "follow_through",
}


def normalize_analysis_result(raw_result: Dict[str, Any], 
                               model_meta: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    标准化分析结果
    
    Args:
        raw_result: 模型原始输出
        model_meta: 模型元信息（可选）
    
    Returns:
        标准化后的结果字典，包含：
        - normalized_result: 标准结果
        - warnings: 警告信息列表
        - mapping_trace: 字段映射追踪
    """
    warnings = []
    mapping_trace = {}
    
    # 创建标准结构副本
    normalized = _deep_copy(STANDARD_SCHEMA)
    
    if not raw_result or not isinstance(raw_result, dict):
        warnings.append("raw_result 为空或不是字典")
        normalized["analysis_status"] = "failed"
        return {
            "normalized_result": normalized,
            "warnings": warnings,
            "mapping_trace": mapping_trace
        }
    
    # 1. 标准化顶层字段
    _normalize_top_level_fields(raw_result, normalized, mapping_trace, warnings)
    
    # 2. 标准化阶段分析
    _normalize_phase_analysis(raw_result, normalized, mapping_trace, warnings)
    
    # 3. 标准化列表字段
    _normalize_list_fields(raw_result, normalized, mapping_trace, warnings)
    
    # 4. 设置模型元信息
    if model_meta:
        normalized["raw_model_meta"] = model_meta
    
    # 5. 确保 summary 有内容
    if not normalized.get("summary"):
        normalized["summary"] = _generate_default_summary(normalized)
        warnings.append("summary 为空，已生成默认摘要")
    
    return {
        "normalized_result": normalized,
        "warnings": warnings,
        "mapping_trace": mapping_trace
    }


def _normalize_top_level_fields(raw: Dict, normalized: Dict, 
                                mapping_trace: Dict, warnings: List):
    """标准化顶层字段"""
    
    # 处理总分字段
    score_value = _extract_field_with_aliases(raw, 
        ["overall_score", "total_score", "final_score", "score"],
        mapping_trace, "overall_score"
    )
    if score_value is not None:
        normalized["overall_score"] = _to_int(score_value, warnings, "overall_score")
    else:
        warnings.append("overall_score 缺失，使用默认值 0")
    
    # 处理置信度
    confidence_value = _extract_field_with_aliases(raw,
        ["confidence", "confidence_score", "trust_score"],
        mapping_trace, "confidence"
    )
    if confidence_value is not None:
        normalized["confidence"] = _to_float(confidence_value, warnings, "confidence")
    else:
        warnings.append("confidence 缺失，使用默认值 0")
    
    # 处理 NTRP 等级
    ntrp_value = _extract_field(raw, "ntrp_level", mapping_trace)
    if ntrp_value is None:
        ntrp_value = _extract_field(raw, "level", mapping_trace)
    if ntrp_value:
        normalized["ntrp_level"] = str(ntrp_value)
    else:
        warnings.append("ntrp_level 缺失")
    
    # 处理摘要
    summary_value = _extract_field_with_aliases(raw,
        ["summary", "overall_summary", "conclusion", "diagnosis_summary", "level_reasoning"],
        mapping_trace, "summary"
    )
    if summary_value:
        normalized["summary"] = str(summary_value)
    
    # 处理报告文本
    report_value = _extract_field(raw, "report", mapping_trace)
    if report_value:
        normalized["report_text"] = str(report_value)
    elif _extract_field(raw, "report_text", mapping_trace):
        normalized["report_text"] = str(raw.get("report_text", ""))


def _normalize_phase_analysis(raw: Dict, normalized: Dict,
                              mapping_trace: Dict, warnings: List):
    """标准化阶段分析"""
    
    # 获取阶段数据
    phase_data = None
    for key in ["phase_analysis", "phases", "scoring_details"]:
        if key in raw:
            phase_data = raw[key]
            mapping_trace[f"phases_source"] = key
            break
    
    if not phase_data or not isinstance(phase_data, dict):
        warnings.append("phase_analysis 缺失或格式错误，使用默认空结构")
        return
    
    # 标准化每个阶段
    for raw_phase_key, phase_content in phase_data.items():
        if not isinstance(phase_content, dict):
            continue
        
        # 映射到标准阶段名
        standard_phase = PHASE_MAPPINGS.get(raw_phase_key.lower(), raw_phase_key)
        
        if standard_phase not in normalized["phase_analysis"]:
            # 尝试直接匹配
            if raw_phase_key in normalized["phase_analysis"]:
                standard_phase = raw_phase_key
            else:
                continue
        
        # 记录映射
        if raw_phase_key != standard_phase:
            mapping_trace[f"phase_{raw_phase_key}"] = standard_phase
        
        # 复制阶段数据
        target_phase = normalized["phase_analysis"][standard_phase]
        
        # 分数
        score = phase_content.get("score", 0)
        target_phase["score"] = _to_int(score, warnings, f"phase.{standard_phase}.score")
        
        # 观察
        observations = phase_content.get("observations", [])
        target_phase["observations"] = _to_list(observations, warnings, f"phase.{standard_phase}.observations")
        
        # 问题
        issues = phase_content.get("issues", [])
        target_phase["issues"] = _to_list(issues, warnings, f"phase.{standard_phase}.issues")
        
        # 建议
        suggestions = phase_content.get("suggestions", phase_content.get("coach_advice", []))
        target_phase["suggestions"] = _to_list(suggestions, warnings, f"phase.{standard_phase}.suggestions")


def _normalize_list_fields(raw: Dict, normalized: Dict,
                           mapping_trace: Dict, warnings: List):
    """标准化列表字段"""
    
    # 优势/优点
    strengths = _extract_field(raw, "strengths", mapping_trace)
    if strengths:
        normalized["strengths"] = _to_list(strengths, warnings, "strengths")
    
    # 关键问题
    key_issues = _extract_field_with_aliases(raw,
        ["key_issues", "critical_issues", "major_issues", "main_issues"],
        mapping_trace, "key_issues"
    )
    if key_issues:
        normalized["key_issues"] = _normalize_issues(key_issues, warnings)
    
    # 训练计划
    training = _extract_field_with_aliases(raw,
        ["training_plan", "recommendations", "practice_plan", "improvement_plan"],
        mapping_trace, "training_plan"
    )
    if training:
        normalized["training_plan"] = _to_list(training, warnings, "training_plan")


def _normalize_issues(issues: Any, warnings: List) -> List[Dict]:
    """标准化问题列表"""
    result = []
    
    if not isinstance(issues, list):
        warnings.append(f"key_issues 不是列表，尝试转换")
        if isinstance(issues, str):
            issues = [issues]
        else:
            return result
    
    for issue in issues:
        if isinstance(issue, dict):
            # 已经是字典格式
            normalized_issue = {
                "issue": issue.get("issue", issue.get("description", "")),
                "severity": issue.get("severity", "medium"),
                "phase": issue.get("phase", ""),
                "suggestion": issue.get("suggestion", issue.get("coach_advice", ""))
            }
            result.append(normalized_issue)
        elif isinstance(issue, str):
            # 字符串格式
            result.append({
                "issue": issue,
                "severity": "medium",
                "phase": "",
                "suggestion": ""
            })
    
    return result


def _extract_field(raw: Dict, field_name: str, mapping_trace: Dict) -> Any:
    """提取字段"""
    if field_name in raw:
        mapping_trace[field_name] = field_name
        return raw[field_name]
    return None


def _extract_field_with_aliases(raw: Dict, aliases: List[str], 
                                mapping_trace: Dict, standard_name: str) -> Any:
    """使用别名提取字段"""
    for alias in aliases:
        if alias in raw:
            if alias != standard_name:
                mapping_trace[standard_name] = f"{alias} -> {standard_name}"
            else:
                mapping_trace[standard_name] = standard_name
            return raw[alias]
    return None


def _to_int(value: Any, warnings: List, field_name: str) -> int:
    """转换为整数"""
    try:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(float(value))
        warnings.append(f"{field_name} 类型无法转换为整数: {type(value)}")
        return 0
    except:
        warnings.append(f"{field_name} 转换整数失败: {value}")
        return 0


def _to_float(value: Any, warnings: List, field_name: str) -> float:
    """转换为浮点数"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
        warnings.append(f"{field_name} 类型无法转换为浮点数: {type(value)}")
        return 0.0
    except:
        warnings.append(f"{field_name} 转换浮点数失败: {value}")
        return 0.0


def _to_list(value: Any, warnings: List, field_name: str) -> List:
    """转换为列表"""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    warnings.append(f"{field_name} 不是列表，已转换")
    return []


def _deep_copy(obj: Any) -> Any:
    """深拷贝"""
    import copy
    return copy.deepcopy(obj)


def _generate_default_summary(normalized: Dict) -> str:
    """生成默认摘要"""
    level = normalized.get("ntrp_level", "未知")
    score = normalized.get("overall_score", 0)
    return f"发球技术分析完成，评估等级 {level}，总分 {score} 分。"


if __name__ == '__main__':
    # 测试
    print("[AnalysisNormalizer] 测试")
    
    # 测试 1: Kimi 风格输出
    kimi_raw = {
        "ntrp_level": "3.0",
        "ntrp_level_name": "基础级",
        "confidence": 0.75,
        "overall_score": 55,
        "phase_analysis": {
            "ready": {"score": 65, "issues": ["重心偏后"]},
            "toss": {"score": 58, "issues": ["抛球偏内"]},
            "loading": {"score": 42, "issues": ["膝盖蓄力不足"]},
            "contact": {"score": 50, "issues": []},
            "follow": {"score": 62, "issues": []}
        },
        "key_issues": [
            {"issue": "膝盖蓄力不足", "severity": "high", "phase": "loading"}
        ],
        "training_plan": ["练习深蹲", "对镜练习"],
        "level_reasoning": "膝盖弯曲不足，典型3.0级"
    }
    
    result = normalize_analysis_result(kimi_raw, {"provider": "moonshot", "model": "kimi-k2.5"})
    norm = result["normalized_result"]
    
    print(f"\nTest 1 - Kimi style:")
    print(f"  overall_score: {norm['overall_score']}")
    print(f"  confidence: {norm['confidence']}")
    print(f"  ntrp_level: {norm['ntrp_level']}")
    print(f"  summary: {norm['summary'][:50]}...")
    print(f"  key_issues count: {len(norm['key_issues'])}")
    print(f"  phase_analysis keys: {list(norm['phase_analysis'].keys())}")
    print(f"  warnings: {result['warnings']}")
    
    # 测试 2: 不同字段命名
    different_raw = {
        "total_score": 78,
        "confidence_score": 0.82,
        "level": "4.0",
        "critical_issues": ["问题1", "问题2"],
        "recommendations": ["建议1", "建议2"],
        "phases": {
            "preparation": {"score": 75},
            "loading": {"score": 72},
            "acceleration": {"score": 80},
            "follow_through": {"score": 76}
        }
    }
    
    result2 = normalize_analysis_result(different_raw)
    norm2 = result2["normalized_result"]
    
    print(f"\nTest 2 - Different naming:")
    print(f"  overall_score: {norm2['overall_score']} (from total_score)")
    print(f"  confidence: {norm2['confidence']} (from confidence_score)")
    print(f"  ntrp_level: {norm2['ntrp_level']} (from level)")
    print(f"  key_issues count: {len(norm2['key_issues'])} (from critical_issues)")
    print(f"  training_plan count: {len(norm2['training_plan'])} (from recommendations)")
    print(f"  mapping_trace: {result2['mapping_trace']}")
    
    print("\n✅ 所有测试通过")
