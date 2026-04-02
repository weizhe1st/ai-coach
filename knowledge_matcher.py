#!/usr/bin/env python3
"""
知识库匹配模块 - 从三教练知识库匹配问题
支持：杨超(71条) + 灵犀(41条) + Yellow(57条) = 169条知识点
"""

import sqlite3
import json
from typing import List, Dict, Any

DB_PATH = '/data/db/xiaolongxia_learning.db'


class KnowledgeMatcher:
    """三教练知识库匹配器"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.coach_stats = {'杨超': 0, '灵犀': 0, 'Yellow': 0}
    
    def get_db_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def load_all_knowledge(self) -> List[Dict]:
        """加载所有三教练知识库"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT coach_name, knowledge_id, title, summary, 
                   key_elements, common_errors, correction_method,
                   knowledge_type, knowledge_class, phase, issue_tags, quality_grade
            FROM coach_knowledge_unified 
            WHERE (quality_grade IN ('A', 'B') OR quality_grade IS NULL)
              AND coach_name IN ('杨超', '灵犀', 'Yellow')
            ORDER BY coach_name, knowledge_class
        ''')
        
        knowledge = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # 统计
        stats = {}
        for k in knowledge:
            coach = k['coach_name']
            stats[coach] = stats.get(coach, 0) + 1
        
        print(f"[KnowledgeMatcher] 加载知识库: 杨超({stats.get('杨超', 0)}) + 灵犀({stats.get('灵犀', 0)}) + Yellow({stats.get('Yellow', 0)}) = {len(knowledge)}条")
        return knowledge
    
    def match_issues(self, issues: List[str], skill: str = 'serve', user_level: str = '3.0') -> List[Dict]:
        """
        根据检测到的问题匹配知识库
        
        Args:
            issues: 检测到的问题标签列表
            skill: 技能类型 (serve/forehand/backhand等)
            user_level: 用户当前水平
        
        Returns:
            匹配的知识条目列表
        """
        knowledge_list = self.load_all_knowledge()
        matches = []
        
        for issue in issues:
            issue_lower = issue.lower()
            
            for knowledge in knowledge_list:
                match_score = 0
                match_reasons = []
                
                # 1. 检查issue_tags匹配 (JSON数组格式)
                issue_tags = knowledge.get('issue_tags', '[]') or '[]'
                try:
                    issue_tags_list = json.loads(issue_tags) if isinstance(issue_tags, str) else issue_tags
                    for tag in issue_tags_list:
                        if issue_lower in tag.lower() or tag.lower() in issue_lower:
                            match_score += 0.4
                            match_reasons.append(f"issue_tag匹配:{tag}")
                            break
                except:
                    if issue_lower in str(issue_tags).lower():
                        match_score += 0.4
                        match_reasons.append(f"issue_tag匹配:{issue}")
                
                # 2. 检查common_errors匹配 (JSON数组格式)
                common_errors = knowledge.get('common_errors', '[]') or '[]'
                try:
                    common_errors_list = json.loads(common_errors) if isinstance(common_errors, str) else common_errors
                    for error in common_errors_list:
                        if issue_lower in error.lower() or error.lower() in issue_lower:
                            match_score += 0.3
                            match_reasons.append(f"common_errors匹配:{error}")
                            break
                except:
                    if issue_lower in str(common_errors).lower():
                        match_score += 0.3
                        match_reasons.append("common_errors匹配")
                
                # 3. 检查title匹配
                title = knowledge.get('title', '') or ''
                if issue_lower in title.lower():
                    match_score += 0.2
                    match_reasons.append("title匹配")
                
                # 4. 检查summary匹配
                summary = knowledge.get('summary', '') or ''
                if issue_lower in summary.lower():
                    match_score += 0.1
                    match_reasons.append("summary匹配")
                
                # 如果匹配度足够高，加入结果
                if match_score >= 0.3:
                    self.coach_stats[knowledge['coach_name']] = self.coach_stats.get(knowledge['coach_name'], 0) + 1
                    
                    matches.append({
                        'coach_name': knowledge['coach_name'],
                        'knowledge_id': knowledge['knowledge_id'],
                        'title': knowledge['title'],
                        'summary': knowledge['summary'],
                        'corrections': knowledge.get('correction_method', ''),
                        'key_elements': knowledge.get('key_elements', ''),
                        'confidence': round(match_score, 2),
                        'match_reasons': match_reasons,
                        'user_issue': issue,
                        'phase': knowledge.get('phase', ''),
                        'video_source': knowledge.get('source_video', '')
                    })
        
        # 按置信度排序
        matches.sort(key=lambda x: x['confidence'], reverse=True)
        
        print(f"[KnowledgeMatcher] 匹配结果: 共{len(matches)}条, 杨超({self.coach_stats.get('杨超', 0)}), 灵犀({self.coach_stats.get('灵犀', 0)}), Yellow({self.coach_stats.get('Yellow', 0)})")
        
        return matches[:10]  # 返回前10条最匹配的结果
    
    def get_coach_summary(self) -> Dict[str, int]:
        """获取各教练引用统计"""
        return self.coach_stats.copy()


# 测试代码
if __name__ == '__main__':
    matcher = KnowledgeMatcher()
    
    # 测试匹配
    test_issues = ['抛球高度不足', '击球点靠后', ' trophy姿势']
    matches = matcher.match_issues(test_issues)
    
    print(f"\n测试匹配 {len(test_issues)} 个问题:")
    for m in matches[:5]:
        print(f"  - [{m['coach_name']}] {m['title']} (置信度: {m['confidence']})")
