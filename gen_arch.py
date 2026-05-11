#!/usr/bin/env python3
"""Generate architecture framework diagram."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
_font_path = "/root/.fonts/NotoSansSC.ttf"
fm.fontManager.addfont(_font_path)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

plt.rcParams.update({
    "figure.dpi": 200,
    "font.family": "Noto Sans SC",
})

OUT = Path("ppt_assets")

fig, ax = plt.subplots(figsize=(14, 7.5))
ax.set_xlim(0, 14)
ax.set_ylim(0, 7.5)
ax.axis("off")
fig.patch.set_facecolor("#0F1628")

def _box(x, y, w, h, text, color, fontsize=11, textcolor="white", alpha=0.85):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                         facecolor=color, edgecolor=color, alpha=alpha, linewidth=1.5)
    ax.add_patch(box)
    ax.text(x + w/2, y + h/2, text, ha="center", va="center",
            fontsize=fontsize, color=textcolor, fontweight="bold", zorder=10)

def _arrow(x1, y1, x2, y2, color="#4DA6FF"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=2, alpha=0.6))

# ── Title ──
ax.text(7, 7.1, "LMBAgent 系统架构", ha="center", va="center",
        fontsize=20, color="white", fontweight="bold")

# ── Layer 1: Data Sources (top) ──
sources = [
    (0.3, 5.8, 2.2, 0.7, "NEWAREA xlsx\n(record sheet)", "#1E3A5F"),
    (2.7, 5.8, 2.2, 0.7, "NEWAREB xlsx\n(Detail sheet)", "#1E3A5F"),
    (5.1, 5.8, 2.2, 0.7, "TVC 报告\n(CD_Capacity)", "#1E3A5F"),
    (7.5, 5.8, 2.0, 0.7, "PEC CSV", "#1E3A5F"),
    (9.7, 5.8, 2.0, 0.7, "Arbin CSV", "#1E3A5F"),
    (11.9, 5.8, 1.8, 0.7, "通用CSV", "#1E3A5F"),
]
for args in sources:
    _box(*args)

ax.text(0.2, 6.65, "数据源", fontsize=13, color="#4DA6FF", fontweight="bold")

# ── Layer 2: Data Ingestion ──
_box(0.3, 4.3, 5.5, 1.2, "AI 智能加载器\n自动格式检测 | LLM列名分析\n电流方向容量拆分", "#0D47A1", fontsize=11)
_box(6.0, 4.3, 3.8, 1.2, "实验设计元数据\nYAML Schema | 自动发现\nPydantic 校验", "#1B5E20", fontsize=11)
_box(10.0, 4.3, 3.7, 1.2, "SQLite 持久化\n4表 | 内存缓存\n跨会话", "#4A148C", fontsize=11)

ax.text(0.2, 5.7, "数据基础层", fontsize=13, color="#00D68F", fontweight="bold")

# ── Layer 3: Analysis Engine ──
_box(0.3, 2.6, 3.3, 1.3, "多实验对比\n叠加 / 差异 / 排名", "#B71C1C", fontsize=10)
_box(3.8, 2.6, 3.3, 1.3, "退化模式分解\n7模式 | NNLS", "#E65100", fontsize=10)
_box(7.3, 2.6, 3.3, 1.3, "DOE 智能诊断\n覆盖度评分\n缺失组合推荐", "#006064", fontsize=10)
_box(10.8, 2.6, 2.9, 1.3, "历史检索\n相似 / 对比度\n向量索引", "#1A237E", fontsize=10)

ax.text(0.2, 4.1, "分析引擎", fontsize=13, color="#FFB800", fontweight="bold")

# ── Layer 4: Agent + UI (bottom) ──
_box(0.3, 0.8, 6.5, 1.4, "LLM 智能体 (18个工具)\nminimax-m2.7 | 函数调用\n加载→对比→分解→验证", "#00695C", fontsize=12)
_box(7.0, 0.8, 3.2, 1.4, "结论管理\n5状态生命周期\n新数据自动验证", "#880E4F", fontsize=10)
_box(10.4, 0.8, 3.3, 1.4, "Web界面 (Streamlit)\n10个页面 | 直接调用\n上传→可视化→报告", "#1565C0", fontsize=10)

ax.text(0.2, 2.35, "智能交互层", fontsize=13, color="#C084FC", fontweight="bold")

# ── Arrows ──
for sx in [1.4, 3.8, 6.2, 8.5, 10.7, 12.8]:
    _arrow(sx, 5.8, sx, 5.55)

for sx in [3.0, 7.9, 11.8]:
    _arrow(sx, 4.3, sx, 4.0)

for sx in [2.0, 5.4, 9.0, 12.2]:
    _arrow(sx, 2.6, sx, 2.3)

for sx in [3.5, 8.6, 12.0]:
    _arrow(sx, 0.8, sx, 0.55)

fig.tight_layout()
fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close()
print("Saved architecture.png")
