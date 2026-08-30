"""V0.7.3: 周报 PDF 生成 (reportlab)

借鉴:
- TrainingPeaks Weekly Summary
- Strava Weekly Recap
- WKO5 Weekly Review

包含:
1. 头部: 周次 + 周期阶段
2. 数据卡: 总 TSS / 距离 / 时长 / 活动数
3. PMC 趋势 (CTL/ATL/TSB)
4. 5 维 readiness
5. 7d 每日活动列表
6. 训练学建议 (从 /api/recommendations/today 取)
"""
from __future__ import annotations
import io
import logging
from datetime import date as _date, datetime, timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image as RLImage,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy.orm import Session

from cycling_coach.core.pmc import get_pmc_today
from cycling_coach.core.coaching.recommendations import (
    generate_recommendations,
    compute_readiness,
)
from cycling_coach.core.metrics.hrv import compute_hrv_state
from cycling_coach.data.sqlite.models import Activity, Athlete, DailyMetric

logger = logging.getLogger(__name__)


def _register_chinese_font() -> str:
    """注册中文字体 (Noto Sans CJK 优先, 找不到用默认)"""
    candidates = [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WQY"),
        ("/usr/share/fonts/truetype/arphic/ukai.ttc", "AR PL UKai"),
    ]
    for path, name in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            logger.info(f"周报使用字体: {name} ({path})")
            return name
        except Exception as e:
            logger.warning(f"字体 {name} 注册失败: {e}")
            continue
    return "Helvetica"


def _fmt_min(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h{m:02d}m"


def generate_weekly_report(
    db: Session, athlete_id: int, days: int = 7
) -> bytes:
    """V0.7.3: 生成周报 PDF bytes
    
    Returns:
        PDF 二进制内容
    """
    athlete = db.get(Athlete, athlete_id)
    if not athlete:
        raise ValueError(f"athlete {athlete_id} 不存在")
    
    font_name = _register_chinese_font()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        title=f"Cycling Coach 周报 - {athlete.name}",
    )
    
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName=font_name, fontSize=20, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName=font_name, fontSize=14, spaceAfter=6, textColor=colors.HexColor("#1e293b"))
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName=font_name, fontSize=12, spaceAfter=4, textColor=colors.HexColor("#475569"))
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName=font_name, fontSize=10, leading=14)
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.HexColor("#64748b"))
    
    story = []
    
    # === 1. 头部 ===
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=days - 1)
    readiness, breakdown = compute_readiness(db, athlete_id)
    rec = generate_recommendations(db, athlete_id)
    pmc = get_pmc_today(db, athlete_id)
    hrv = compute_hrv_state(db, athlete_id)
    
    story.append(Paragraph(f"🚴 Cycling Coach · 周报", h1))
    story.append(Paragraph(
        f"<b>{athlete.name}</b> · {week_start.isoformat()} ~ {today.isoformat()} ({days}天)",
        small
    ))
    story.append(Spacer(1, 4*mm))
    
    # === 2. Readiness 头部卡 ===
    readiness_color = "#10b981" if readiness >= 80 else "#22c55e" if readiness >= 60 else "#f59e0b" if readiness >= 40 else "#f97316" if readiness >= 20 else "#ef4444"
    story.append(Paragraph(f'<font color="{readiness_color}" size="32"><b>{readiness}</b></font> <font size="12" color="#64748b">/ 100 · {rec.readiness_label}</font>', body))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f'<b>推荐今日训练:</b> {rec.recommended_intensity}', body))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f'<b>目标 TSS:</b> {rec.target_tss}', body))
    story.append(Spacer(1, 6*mm))
    
    # === 3. 5 维 Breakdown ===
    story.append(Paragraph("Readiness 5 维拆解", h2))
    breakdown_data = [
        ["维度", "分数", "满分", "说明"],
    ]
    breakdown_meta = [
        ("hrv", "HRV", 30, "心率变异性 (Plews 2013)"),
        ("acwr", "ACWR", 25, "急慢性负荷比 (Gabbett 2016)"),
        ("tsb", "TSB", 20, "训练平衡 (Banister TRIMP)"),
        ("phase", "阶段", 15, "周期化适配 (Friel CTB)"),
        ("rpe", "RPE", 10, "7d 主观疲劳 (Borg CR-10)"),
    ]
    for k, label, mx, desc in breakdown_meta:
        v = breakdown.get(k, 0)
        breakdown_data.append([f"{label} ({desc})", str(v), str(mx), f"{v/mx*100:.0f}%"])
    t = Table(breakdown_data, colWidths=[6*cm, 2*cm, 2*cm, 2*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#1e293b")),
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (3,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    
    # === 4. PMC 状态 ===
    story.append(Paragraph("训练负荷状态 (PMC)", h2))
    pmc_data = [
        ["指标", "当前值", "解读"],
        ["CTL (长期)", f"{pmc.get('ctl', 0):.1f}", "42d EWMA · 形态/体能"],
        ["ATL (短期)", f"{pmc.get('atl', 0):.1f}", "7d EWMA · 短期疲劳"],
        ["TSB (状态)", f"{pmc.get('tsb', 0):.1f}", "CTL - ATL · 状态"],
        ["ramp_rate", f"{pmc.get('ramp_rate', 0):.2f}", "7d CTL 斜率 (TSS/wk)"],
    ]
    t = Table(pmc_data, colWidths=[4*cm, 3*cm, 8*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    
    # === 5. HRV 状态 ===
    story.append(Paragraph(f"HRV 状态: {hrv.get('status_label', 'N/A')}", h2))
    if hrv.get("today_hrv"):
        hrv_data = [
            ["指标", "数值"],
            ["今日 HRV", f"{hrv['today_hrv']:.1f} ms"],
            ["7d 滑动", f"{hrv.get('rolling_7d_avg', 0):.1f} ms"],
            ["30d baseline", f"{hrv.get('baseline_30d', 0):.1f} ms"],
            ["Delta from baseline", f"{hrv.get('delta_from_baseline', 0):+.1f} ms ({hrv.get('delta_pct', 0):+.1f}%)"],
            ["连续低 HRV 天数", f"{hrv.get('consecutive_low_days', 0)}"],
        ]
        t = Table(hrv_data, colWidths=[6*cm, 8*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0,0), (-1,-1), font_name),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(t)
        story.append(Paragraph(f"<i>{hrv.get('recommendation', '')}</i>", small))
    else:
        story.append(Paragraph("HRV 数据不足 (需要 ≥ 3 天晨起静息测量)", small))
    story.append(Spacer(1, 6*mm))
    
    # === 6. 周期化阶段 ===
    story.append(Paragraph("周期化阶段", h2))
    story.append(Paragraph(f"<b>建议阶段:</b> {rec.signals_summary.get('phase_label', 'N/A')}", body))
    if rec.signals_summary.get("weeks_to_race"):
        story.append(Paragraph(f"<b>距比赛:</b> {rec.signals_summary['weeks_to_race']} 周", body))
    story.append(Spacer(1, 4*mm))
    
    # === 7. 触发建议 ===
    if rec.recommendations:
        story.append(Paragraph("触发建议", h2))
        for r in rec.recommendations[:5]:
            icon = r.icon or ""
            story.append(Paragraph(f"<b>{icon} {r.title}</b> (P{r.priority})", body))
            story.append(Paragraph(f"&nbsp;&nbsp;{r.detail}", small))
            if r.action:
                story.append(Paragraph(f"&nbsp;&nbsp;<b>→ {r.action}</b>", small))
            story.append(Spacer(1, 2*mm))
        story.append(Spacer(1, 4*mm))
    
    # === 8. 7d 活动列表 ===
    story.append(PageBreak())
    story.append(Paragraph(f"{days}天活动明细", h2))
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff)
        .order_by(Activity.start_time.desc())
        .all()
    )
    
    if activities:
        # 头: 总览
        total_tss = sum((a.metrics or {}).get("tss", 0) or 0 for a in activities)
        total_dist = sum((a.distance_m or 0) for a in activities) / 1000
        total_dur = sum((a.duration_s or 0) for a in activities)
        story.append(Paragraph(
            f"<b>总 TSS:</b> {total_tss:.0f} · <b>总距离:</b> {total_dist:.1f} km · "
            f"<b>总时长:</b> {_fmt_min(int(total_dur))} · <b>活动数:</b> {len(activities)}",
            body
        ))
        story.append(Spacer(1, 4*mm))
        
        # 活动表
        act_data = [["日期", "名称", "时长", "距离(km)", "TSS", "NP", "IF", "HR(avg)"]]
        for a in activities:
            m = a.metrics or {}
            act_data.append([
                a.start_time.strftime("%m-%d") if a.start_time else "-",
                (a.file_name or a.source or "活动")[:20],
                _fmt_min(a.duration_s or 0),
                f"{(a.distance_m or 0)/1000:.1f}",
                f"{m.get('tss', 0):.0f}",
                f"{m.get('np', 0):.0f}" if m.get('np') else "-",
                f"{m.get('intensity_factor', 0):.2f}" if m.get('intensity_factor') else "-",
                f"{a.avg_hr}" if a.avg_hr else "-",
            ])
        
        t = Table(act_data, colWidths=[1.5*cm, 4*cm, 2*cm, 2*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0,0), (-1,-1), font_name),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("ALIGN", (2,0), (-1,-1), "CENTER"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(f"过去 {days} 天无活动记录", body))
    
    story.append(Spacer(1, 8*mm))
    
    # === 9. 学术引用 ===
    story.append(Paragraph("学术引用", h2))
    story.append(Paragraph(
        "· Plews & Laursen 2013 · HRV in athletes: training adaptation<br/>"
        "· Gabbett 2016 · The training—injury prevention paradox<br/>"
        "· Seiler 2010 · What is best practice for training distribution?<br/>"
        "· Banister · TRIMP / Fitness-Fatigue model<br/>"
        "· Friel · The Cyclist's Training Bible",
        small
    ))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f"<i>Generated by Cycling Coach v{__import__('cycling_coach').__version__ if hasattr(__import__('cycling_coach'), '__version__') else '0.7.3'} · {datetime.utcnow().isoformat()} UTC</i>",
        small
    ))
    
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
