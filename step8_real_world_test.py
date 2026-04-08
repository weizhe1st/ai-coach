#!/usr/bin/env python3
"""
第八步：小范围真实使用测试框架
用于记录和评估真实视频测试结果
"""

import json
from datetime import datetime
from typing import List, Dict, Any


class RealWorldTestRecord:
    """真实使用测试记录"""
    
    def __init__(self):
        self.test_records = []
    
    def add_record(
        self,
        video_name: str,
        video_type: str,  # A:熟悉问题视频, B:标准较好, C:质量一般, D:明显不适合
        task_id: str,
        upload_time: str,
        chain_success: bool,
        delivery_success: bool,
        overall_score: int,
        subjective_score: int,  # 1-10分，你觉得分析值几分
        hit_gold_standard: bool,
        hit_knowledge_base: bool,
        key_issues: List[str],
        training_suggestions: List[str],
        your_judgment: str,  # 你自己的判断
        system_judgment_summary: str,  # 系统判断摘要
        notes: str
    ):
        """添加测试记录"""
        record = {
            "video_name": video_name,
            "video_type": video_type,
            "task_id": task_id,
            "upload_time": upload_time,
            "chain_success": chain_success,
            "delivery_success": delivery_success,
            "overall_score": overall_score,
            "subjective_score": subjective_score,
            "hit_gold_standard": hit_gold_standard,
            "hit_knowledge_base": hit_knowledge_base,
            "key_issues": key_issues,
            "training_suggestions": training_suggestions,
            "your_judgment": your_judgment,
            "system_judgment_summary": system_judgment_summary,
            "notes": notes,
            "tested_at": datetime.now().isoformat()
        }
        self.test_records.append(record)
        return record
    
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        if not self.test_records:
            return {"error": "暂无测试记录"}
        
        total = len(self.test_records)
        chain_success_count = sum(1 for r in self.test_records if r["chain_success"])
        delivery_success_count = sum(1 for r in self.test_records if r["delivery_success"])
        avg_subjective_score = sum(r["subjective_score"] for r in self.test_records) / total
        
        # 按类型统计
        type_a = [r for r in self.test_records if r["video_type"] == "A"]
        type_b = [r for r in self.test_records if r["video_type"] == "B"]
        type_c = [r for r in self.test_records if r["video_type"] == "C"]
        type_d = [r for r in self.test_records if r["video_type"] == "D"]
        
        return {
            "summary": {
                "total_videos": total,
                "chain_success_rate": f"{chain_success_count}/{total}",
                "delivery_success_rate": f"{delivery_success_count}/{total}",
                "average_subjective_score": round(avg_subjective_score, 1),
                "type_a_count": len(type_a),
                "type_b_count": len(type_b),
                "type_c_count": len(type_c),
                "type_d_count": len(type_d)
            },
            "recommendation": self._generate_recommendation(avg_subjective_score, chain_success_count, total),
            "records": self.test_records
        }
    
    def _generate_recommendation(self, avg_score: float, chain_success: int, total: int) -> str:
        """生成使用建议"""
        if avg_score >= 7 and chain_success == total:
            return "系统表现良好，建议继续小范围真实试用"
        elif avg_score >= 5 and chain_success >= total * 0.8:
            return "系统基本可用，建议针对低分项优化后继续试用"
        elif chain_success < total * 0.5:
            return "链路稳定性不足，建议先解决技术问题"
        else:
            return "结果质量需要提升，建议优化分析质量后再试用"
    
    def print_report(self):
        """打印测试报告"""
        report = self.generate_report()
        
        print("=" * 70)
        print("第八步：小范围真实使用测试报告")
        print("=" * 70)
        print()
        
        summary = report["summary"]
        print("【测试汇总】")
        print(f"  测试视频总数: {summary['total_videos']}")
        print(f"  链路成功率: {summary['chain_success_rate']}")
        print(f"  回推成功率: {summary['delivery_success_rate']}")
        print(f"  平均主观评分: {summary['average_subjective_score']}/10")
        print(f"  视频类型分布:")
        print(f"    - A类(熟悉问题视频): {summary['type_a_count']}条")
        print(f"    - B类(标准较好): {summary['type_b_count']}条")
        print(f"    - C类(质量一般): {summary['type_c_count']}条")
        print(f"    - D类(明显不适合): {summary['type_d_count']}条")
        print()
        
        print("【使用建议】")
        print(f"  {report['recommendation']}")
        print()
        
        if report["records"]:
            print("【详细记录】")
            for i, record in enumerate(report["records"], 1):
                print(f"\n  视频{i}: {record['video_name']} ({record['video_type']}类)")
                print(f"    Task ID: {record['task_id']}")
                print(f"    链路成功: {'✅' if record['chain_success'] else '❌'}")
                print(f"    回推成功: {'✅' if record['delivery_success'] else '❌'}")
                print(f"    系统评分: {record['overall_score']}")
                print(f"    你的评分: {record['subjective_score']}/10")
                print(f"    命中黄金样本: {'✅' if record['hit_gold_standard'] else '❌'}")
                print(f"    命中知识库: {'✅' if record['hit_knowledge_base'] else '❌'}")
                print(f"    关键问题: {', '.join(record['key_issues'][:3])}")
                print(f"    你的判断: {record['your_judgment'][:50]}...")
                if record['notes']:
                    print(f"    备注: {record['notes']}")
        
        print()
        print("=" * 70)
    
    def save_to_file(self, filepath: str = "step8_test_records.json"):
        """保存记录到文件"""
        report = self.generate_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"测试记录已保存到: {filepath}")


# 使用示例和测试模板
TEST_TEMPLATE = """
【第八步真实使用测试模板】

请准备3-5条真实视频，按以下格式记录：

=== 视频1 (A类: 你熟悉的问题视频) ===
视频名称: ________________
Task ID: ________________
上传时间: ________________

链路运行:
  - 是否跑通: ____
  - 是否成功回推: ____
  - overall_score: ____

结果评估:
  - 你的主观评分(1-10): ____
  - 是否命中黄金样本: ____
  - 是否命中知识库: ____
  
关键问题(系统指出):
  1. ________________
  2. ________________
  
训练建议(系统给出):
  1. ________________
  2. ________________

对比判断:
  - 你自己的判断: ________________
  - 系统判断摘要: ________________
  - 是否大体一致: ____

备注: ________________


=== 视频2 (B类: 标准较好视频) ===
[同上格式]


=== 视频3 (C类: 质量一般视频) ===
[同上格式]


=== 评估总结 ===
1. 哪几条结果最像真实教练判断? ________________
2. 哪几条结果明显还不够好? ________________
3. 总分有没有明显偏高或偏低? ________________
4. 关键问题是否抓住了主要矛盾? ________________
5. 建议是不是能马上拿去练? ________________
6. 教练知识库风格有没有体现? ________________
7. 上传、等待、回推体验能不能接受? ________________
8. 当前系统是否值得继续小范围试用? ________________
"""


if __name__ == '__main__':
    print(TEST_TEMPLATE)
    print("\n" + "=" * 70)
    print("示例：如何创建测试记录")
    print("=" * 70)
    
    # 创建示例记录
    tester = RealWorldTestRecord()
    
    # 示例记录1
    tester.add_record(
        video_name="test_serve_01.mp4",
        video_type="A",
        task_id="task_20260408_001",
        upload_time="2026-04-08 15:00:00",
        chain_success=True,
        delivery_success=True,
        overall_score=78,
        subjective_score=7,
        hit_gold_standard=True,
        hit_knowledge_base=True,
        key_issues=["抛球偏右约15cm", "膝盖蓄力角度约140度"],
        training_suggestions=["对墙抛球练习", "深蹲练习"],
        your_judgment="抛球确实偏右，膝盖弯曲不足",
        system_judgment_summary="指出抛球和膝盖问题，建议合理",
        notes="结果基本符合预期"
    )
    
    # 示例记录2
    tester.add_record(
        video_name="test_serve_02.mp4",
        video_type="B",
        task_id="task_20260408_002",
        upload_time="2026-04-08 15:05:00",
        chain_success=True,
        delivery_success=True,
        overall_score=85,
        subjective_score=8,
        hit_gold_standard=True,
        hit_knowledge_base=False,
        key_issues=["随挥可以更完整"],
        training_suggestions=["注意收拍动作"],
        your_judgment="动作比较标准，小建议合理",
        system_judgment_summary="评分合理，建议有针对性",
        notes="标准视频处理得当"
    )
    
    # 打印报告
    tester.print_report()
    
    # 保存到文件
    tester.save_to_file("/data/apps/xiaolongxia/step8_test_records_example.json")
