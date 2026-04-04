#!/usr/bin/env python3
"""
OpenCloud Coach 系统统计脚本

用法：
    python3 stats.py [--days N] [--full]

参数：
    --days N    只统计最近N天的数据（默认全部）
    --full      显示完整详情（默认只显示摘要）
"""

import sqlite3
import json
import argparse
from datetime import datetime, timedelta
from collections import Counter

DB_PATH = '/data/db/xiaolongxia_learning.db'

# ─── 工具函数 ────────────────────────────────────────────────
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def section(title):
    width = 25
    print(f"\n{'━' * width}")
    print(f"  {title}")
    print(f"{'━' * width}")

def bar(value, total, width=20):
    """文字进度条"""
    if total == 0:
        return '─' * width + ' 0%'
    filled = int(value / total * width)
    pct = value / total * 100
    return '█' * filled + '░' * (width - filled) + f' {pct:.1f}%'

def date_filter(days):
    """返回 WHERE 子句片段和参数"""
    if days is None:
        return '', []
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    return 'AND created_at >= ?', [cutoff]

# ─── 各统计模块 ──────────────────────────────────────────────
def stats_overview(conn, days, full):
    """总览：分析量、成功率、失败原因分布"""
    section("总览")
    where, params = date_filter(days)
    
    # vision_analysis_direct 表
    rows = conn.execute(f"""
        SELECT status, COUNT(*) as cnt
        FROM vision_analysis_direct
        WHERE 1=1 {where}
        GROUP BY status
        ORDER BY cnt DESC
    """, params).fetchall()
    
    total = sum(r['cnt'] for r in rows)
    success = next((r['cnt'] for r in rows if r['status'] == 'success'), 0)
    failed = next((r['cnt'] for r in rows if r['status'] == 'failed'), 0)
    low_q = next((r['cnt'] for r in rows if r['status'] == 'low_quality'), 0)
    
    print(f"\n  分析总量 {total} 次")
    print(f"  成功 {success} 次 {bar(success, total)}")
    print(f"  质检未通过 {low_q} 次 {bar(low_q, total)}")
    print(f"  API失败 {failed} 次 {bar(failed, total)}")
    
    # 成功率趋势（按天）
    if full and total > 0:
        print("\n  按日成功率：")
        daily = conn.execute(f"""
            SELECT DATE(created_at) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as ok
            FROM vision_analysis_direct
            WHERE 1=1 {where}
            GROUP BY day
            ORDER BY day DESC
            LIMIT 14
        """, params).fetchall()
        for r in daily:
            rate = r['ok'] / r['total'] * 100 if r['total'] > 0 else 0
            print(f"  {r['day']} {r['ok']}/{r['total']} {rate:.0f}%")

def stats_ntrp(conn, days, full):
    """NTRP 等级分布"""
    section("NTRP 等级分布")
    where, params = date_filter(days)
    
    rows = conn.execute(f"""
        SELECT ntrp_level, COUNT(*) as cnt
        FROM vision_analysis_direct
        WHERE status = 'success'
          AND ntrp_level IS NOT NULL
          {where}
        GROUP BY ntrp_level
        ORDER BY ntrp_level
    """, params).fetchall()
    
    if not rows:
        print("\n  暂无数据")
        return
    
    total = sum(r['cnt'] for r in rows)
    level_order = ['2.0','2.5','3.0','3.5','4.0','4.5','5.0','5.0+']
    level_map = {r['ntrp_level']: r['cnt'] for r in rows}
    
    print(f"\n  {'等级':<8} {'人次':<6} {'占比'}")
    for lv in level_order:
        cnt = level_map.get(lv, 0)
        if cnt == 0 and not full:
            continue
        print(f"  {lv:<8} {cnt:<6} {bar(cnt, total, 15)}")
    
    # 平均等级（数值化）
    level_num = {'2.0':2.0,'2.5':2.5,'3.0':3.0,'3.5':3.5,
                 '4.0':4.0,'4.5':4.5,'5.0':5.0,'5.0+':5.5}
    weighted = sum(level_num.get(r['ntrp_level'], 0) * r['cnt'] for r in rows)
    avg = weighted / total if total > 0 else 0
    print(f"\n  内测用户平均等级：{avg:.2f}")

def stats_confidence(conn, days, full):
    """置信度与评分质量"""
    section("分析质量")
    where, params = date_filter(days)
    
    row = conn.execute(f"""
        SELECT ROUND(AVG(confidence), 3) as avg_conf,
               ROUND(MIN(confidence), 3) as min_conf,
               ROUND(AVG(overall_score), 1) as avg_score,
               COUNT(*) as cnt
        FROM vision_analysis_direct
        WHERE status = 'success' {where}
    """, params).fetchone()
    
    if not row or row['cnt'] == 0:
        print("\n  暂无数据")
        return
    
    print(f"\n  成功分析量 {row['cnt']} 次")
    print(f"  平均置信度 {row['avg_conf']:.1%}")
    print(f"  最低置信度 {row['min_conf']:.1%}")
    print(f"  平均总分 {row['avg_score']:.1f} / 100")
    
    # 五阶段平均分
    print("\n  五阶段平均分：")
    phase_keys = ['ready', 'toss', 'loading', 'contact', 'follow']
    phase_names = {'ready':'准备','toss':'抛球','loading':'蓄力',
                   'contact':'击球','follow':'随挥'}
    phase_scores = {k: [] for k in phase_keys}
    
    records = conn.execute(f"""
        SELECT phase_analysis
        FROM vision_analysis_direct
        WHERE status = 'success' AND phase_analysis IS NOT NULL {where}
    """, params).fetchall()
    
    for rec in records:
        try:
            pa = json.loads(rec['phase_analysis'])
            for k in phase_keys:
                if k in pa and 'score' in pa[k]:
                    phase_scores[k].append(pa[k]['score'])
        except:
            continue
    
    for k in phase_keys:
        scores = phase_scores[k]
        if scores:
            avg = sum(scores) / len(scores)
            print(f"    {phase_names[k]}: {avg:.1f}")

def stats_sample_library(conn, days, full):
    """样本库统计"""
    section("样本库")
    
    # gold_standard_samples 表
    rows = conn.execute("""
        SELECT level, COUNT(*) as cnt
        FROM gold_standard_samples
        GROUP BY level
        ORDER BY level
    """).fetchall()
    
    if not rows:
        print("\n  暂无样本")
        return
    
    total = sum(r['cnt'] for r in rows)
    print(f"\n  样本总数 {total} 个")
    
    for r in rows:
        print(f"  {r['level']}级: {r['cnt']}个")
    
    # 最近入库
    recent = conn.execute("""
        SELECT level, video_path, created_at
        FROM gold_standard_samples
        ORDER BY created_at DESC
        LIMIT 5
    """).fetchall()
    
    if recent:
        print("\n  最近入库：")
        for r in recent:
            print(f"  [{r['level']}级] {r['created_at'][:10]} {r['video_path'][:30]}...")

def stats_errors(conn, days, full):
    """错误分析"""
    section("错误分析")
    where, params = date_filter(days)
    
    # 失败原因分布
    errors = conn.execute(f"""
        SELECT error_message, COUNT(*) as cnt
        FROM vision_analysis_direct
        WHERE status = 'failed'
          AND error_message IS NOT NULL
          {where}
        GROUP BY error_message
        ORDER BY cnt DESC
        LIMIT 10
    """, params).fetchall()
    
    if not errors:
        print("\n  无失败记录")
        return
    
    print(f"\n  失败原因 TOP{len(errors)}：")
    for e in errors:
        msg = e['error_message'][:40] + '...' if len(e['error_message']) > 40 else e['error_message']
        print(f"  {e['cnt']}次: {msg}")

# ─── 主函数 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='OpenCloud Coach 系统统计')
    parser.add_argument('--days', type=int, help='统计最近N天')
    parser.add_argument('--full', action='store_true', help='显示完整详情')
    args = parser.parse_args()
    
    print(f"\n{'='*50}")
    print(f"  OpenCloud Coach 系统统计")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.days:
        print(f"  范围: 最近{args.days}天")
    else:
        print(f"  范围: 全部历史数据")
    print(f"{'='*50}")
    
    conn = connect()
    
    try:
        stats_overview(conn, args.days, args.full)
        stats_ntrp(conn, args.days, args.full)
        stats_confidence(conn, args.days, args.full)
        stats_sample_library(conn, args.days, args.full)
        if args.full:
            stats_errors(conn, args.days, args.full)
    finally:
        conn.close()
    
    print(f"\n{'='*50}")
    print("  统计完成")
    print(f"{'='*50}\n")

if __name__ == '__main__':
    main()
