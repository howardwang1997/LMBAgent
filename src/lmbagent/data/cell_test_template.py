"""电芯挂测表模板 parser.

Reads the '电芯挂测表模板_final.xlsx' format used in LMB testing.
Maps each row (one cell test) to a structured dict of DOE design factors.

The template has 45 columns in the '挂测表' sheet, plus reference sheets
for valid values (cathode, anode, electrolyte, separator, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, Field


TEMPLATE_COLUMNS = [
    "挂测地点", "通道", "挂测时间", "电芯编号", "cell_type",
    "阴极", "阴极PN", "其它阴极", "阳极", "阳极PN", "其它阳极",
    "极片容量_Ah", "四边绝缘", "四边绝缘备注",
    "电解液", "注液系数_g_Ah",
    "隔膜", "隔膜PN",
    "阻抗_ohm", "归一化阻抗_ohm_cm2",
    "测试温度_C", "充电电流_C", "放电电流_C",
    "上限电压_V", "下限电压_V", "SOC_pct", "DOD_pct",
    "夹具", "预紧力_MPa", "缓冲垫", "缓冲垫厚度_mm",
    "是否反向", "重注液", "重注液日期", "重注液电芯编号", "重注液注液量",
    "阴极反向", "阴极反向挂测时间", "阴极反向电芯编号",
    "阳极反向", "阳极反向挂测时间", "阳极反向电芯编号",
    "是否拆解", "拆解图片路径", "备注",
]

RAW_HEADER_MAP = {
    "挂测地点": "挂测地点",
    "通道": "通道",
    "挂测时间": "挂测时间",
    "电芯编号": "电芯编号",
    "cell type": "cell_type",
    "阴极": "阴极",
    "阴极PN": "阴极PN",
    "其它阴极": "其它阴极",
    "阳极": "阳极",
    "阳极PN": "阳极PN",
    "其它阳极": "其它阳极",
    "极片容量 (Ah)": "极片容量_Ah",
    "四边绝缘": "四边绝缘",
    "四边绝缘备注": "四边绝缘备注",
    "电解液": "电解液",
    "注液系数 (g/Ah)": "注液系数_g_Ah",
    "隔膜": "隔膜",
    "隔膜PN": "隔膜PN",
    "阻抗 (RT, Ω)": "阻抗_ohm",
    "归一化阻抗 (RT, Ω·cm2)": "归一化阻抗_ohm_cm2",
    "测试温度 (℃)": "测试温度_C",
    "充电电流 (C)": "充电电流_C",
    "放电电流 (C)": "放电电流_C",
    "上限电压 (V)": "上限电压_V",
    "下限电压 (V)": "下限电压_V",
    "SOC (%)": "SOC_pct",
    "DOD (%)": "DOD_pct",
    "夹具": "夹具",
    "预紧力 (MPa)": "预紧力_MPa",
    "缓冲垫": "缓冲垫",
    "缓冲垫厚度 (mm)": "缓冲垫厚度_mm",
    "是否反向": "是否反向",
    "重注液": "重注液",
    "重注液日期": "重注液日期",
    "重注液电芯编号": "重注液电芯编号",
    "重注液注液量": "重注液注液量",
    "阴极反向": "阴极反向",
    "阴极反向挂测时间": "阴极反向挂测时间",
    "阴极反向电芯编号": "阴极反向电芯编号",
    "阳极反向": "阳极反向",
    "阳极反向挂测时间": "阳极反向挂测时间",
    "阳极反向电芯编号": "阳极反向电芯编号",
    "是否拆解": "是否拆解",
    "拆解图片路径": "拆解图片路径",
    "备注": "备注",
}

DOE_CATEGORICAL_FACTORS = [
    "挂测地点",
    "cell_type",
    "阴极",
    "阳极",
    "电解液",
    "隔膜",
    "夹具",
    "缓冲垫",
]

DOE_NUMERIC_FACTORS = [
    "测试温度_C",
    "充电电流_C",
    "放电电流_C",
    "上限电压_V",
    "下限电压_V",
    "注液系数_g_Ah",
    "极片容量_Ah",
    "预紧力_MPa",
    "缓冲垫厚度_mm",
    "SOC_pct",
    "DOD_pct",
]

DOE_ALL_FACTORS = DOE_CATEGORICAL_FACTORS + DOE_NUMERIC_FACTORS


class CellTestRecord(BaseModel):
    cell_id: str
    location: str = ""
    test_date: str = ""
    cell_type: str = ""
    cathode: str = ""
    cathode_pn: str = ""
    anode: str = ""
    anode_pn: str = ""
    electrode_capacity_ah: float | None = None
    electrolyte: str = ""
    filling_coefficient_g_ah: float | None = None
    separator: str = ""
    separator_pn: str = ""
    impedance_ohm: float | None = None
    normalized_impedance_ohm_cm2: float | None = None
    test_temperature_c: float | None = None
    charge_rate_c: float | None = None
    discharge_rate_c: float | None = None
    upper_voltage_v: float | None = None
    lower_voltage_v: float | None = None
    soc_pct: float | None = None
    dod_pct: float | None = None
    fixture: str = ""
    preload_mpa: float | None = None
    buffer_pad: str = ""
    buffer_pad_thickness_mm: float | None = None
    is_reversed: str = ""
    notes: str = ""
    raw_row: dict[str, Any] = Field(default_factory=dict)

    def to_doe_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "挂测地点": self.location,
            "cell_type": self.cell_type,
            "阴极": self.cathode,
            "阳极": self.anode,
            "电解液": self.electrolyte,
            "隔膜": self.separator,
            "夹具": self.fixture,
            "缓冲垫": self.buffer_pad,
            "测试温度_C": self.test_temperature_c,
            "充电电流_C": self.charge_rate_c,
            "放电电流_C": self.discharge_rate_c,
            "上限电压_V": self.upper_voltage_v,
            "下限电压_V": self.lower_voltage_v,
            "注液系数_g_Ah": self.filling_coefficient_g_ah,
            "极片容量_Ah": self.electrode_capacity_ah,
            "预紧力_MPa": self.preload_mpa,
            "缓冲垫厚度_mm": self.buffer_pad_thickness_mm,
            "SOC_pct": self.soc_pct,
            "DOD_pct": self.dod_pct,
        }


def load_cell_test_template(xlsx_path: str | Path) -> list[CellTestRecord]:
    """Parse a 电芯挂测表 template xlsx into a list of CellTestRecord.

    Reads the '挂测表' sheet, maps raw Chinese headers to standardized names.
    Skips empty rows.
    """
    import openpyxl

    xlsx_path = Path(xlsx_path)
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)

    sheet_name = None
    for sn in wb.sheetnames:
        if "挂测" in sn:
            sheet_name = sn
            break
    if sheet_name is None:
        sheet_name = wb.sheetnames[0]

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    raw_header = [str(v).strip() if v is not None else "" for v in rows[0]]

    header_map = {}
    for i, h in enumerate(raw_header):
        if h in RAW_HEADER_MAP:
            header_map[i] = RAW_HEADER_MAP[h]

    records = []
    for row in rows[1:]:
        if row is None:
            continue

        vals = {}
        for col_idx, std_name in header_map.items():
            if col_idx < len(row) and row[col_idx] is not None:
                vals[std_name] = row[col_idx]

        cell_id = str(vals.get("电芯编号", "")).strip()
        if not cell_id:
            continue

        def _float(key):
            v = vals.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        record = CellTestRecord(
            cell_id=cell_id,
            location=str(vals.get("挂测地点", "")),
            test_date=str(vals.get("挂测时间", "")),
            cell_type=str(vals.get("cell_type", "")),
            cathode=str(vals.get("阴极", "")),
            cathode_pn=str(vals.get("阴极PN", "")),
            anode=str(vals.get("阳极", "")),
            anode_pn=str(vals.get("阳极PN", "")),
            electrode_capacity_ah=_float("极片容量_Ah"),
            electrolyte=str(vals.get("电解液", "")),
            filling_coefficient_g_ah=_float("注液系数_g_Ah"),
            separator=str(vals.get("隔膜", "")),
            separator_pn=str(vals.get("隔膜PN", "")),
            impedance_ohm=_float("阻抗_ohm"),
            normalized_impedance_ohm_cm2=_float("归一化阻抗_ohm_cm2"),
            test_temperature_c=_float("测试温度_C"),
            charge_rate_c=_float("充电电流_C"),
            discharge_rate_c=_float("放电电流_C"),
            upper_voltage_v=_float("上限电压_V"),
            lower_voltage_v=_float("下限电压_V"),
            soc_pct=_float("SOC_pct"),
            dod_pct=_float("DOD_pct"),
            fixture=str(vals.get("夹具", "")),
            preload_mpa=_float("预紧力_MPa"),
            buffer_pad=str(vals.get("缓冲垫", "")),
            buffer_pad_thickness_mm=_float("缓冲垫厚度_mm"),
            is_reversed=str(vals.get("是否反向", "")),
            notes=str(vals.get("备注", "")),
            raw_row=vals,
        )
        records.append(record)

    return records


def load_template_reference_sheets(xlsx_path: str | Path) -> dict[str, list[str]]:
    """Load reference value lists from template xlsx (cathode, anode, electrolyte, etc.)."""
    import openpyxl

    xlsx_path = Path(xlsx_path)
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)

    refs = {}

    ref_configs = {
        "electrolyte": ("electrolyte", 0),
        "temperature": ("testting temperature", 0),
        "cell_type": ("cell type", 0),
        "fixture": ("fixture", 0),
    }

    for key, (sheet_name, col) in ref_configs.items():
        if sheet_name in [s.lower() for s in wb.sheetnames]:
            sn = [s for s in wb.sheetnames if s.lower() == sheet_name][0]
            ws = wb[sn]
            vals = []
            for row in ws.iter_rows(values_only=True):
                if row[col] is not None and str(row[col]).strip():
                    vals.append(str(row[col]).strip())
            refs[key] = vals

    if "注液量" in wb.sheetnames:
        ws = wb["注液量"]
        vals = []
        for row in ws.iter_rows(values_only=True):
            if row[0] is not None and str(row[0]).strip():
                vals.append(str(row[0]).strip())
        refs["filling_coefficient"] = vals

    if "隔膜" in wb.sheetnames:
        ws = wb["隔膜"]
        vals = []
        for row in ws.iter_rows(values_only=True):
            if row[0] is not None and str(row[0]).strip():
                vals.append(str(row[0]).strip())
        refs["separator"] = vals

    wb.close()
    return refs


def match_cycling_data_to_template(
    template_records: list[CellTestRecord],
    data_dir: str | Path,
) -> dict[str, CellTestRecord]:
    """Match cycling xlsx files to template records by cell ID.

    Scans data_dir recursively for xlsx files, matches filename stems
    to cell_id in template records.

    Returns:
        Dict mapping xlsx file path → CellTestRecord.
    """
    data_dir = Path(data_dir)
    cell_id_map = {r.cell_id: r for r in template_records}

    matches = {}
    for xlsx_file in data_dir.rglob("*.xlsx"):
        stem = xlsx_file.stem
        if "挂测表" in stem or "模板" in stem:
            continue
        if stem in cell_id_map:
            matches[str(xlsx_file)] = cell_id_map[stem]

    return matches


def template_records_to_yaml(
    records: list[CellTestRecord],
    output_dir: str | Path,
) -> list[Path]:
    """Write each CellTestRecord as a YAML design file for auto-loading."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for rec in records:
        data = {
            "cell_id": rec.cell_id,
            "chemistry": "LMB",
            "form_factor": rec.cell_type,
            "design_capacity_ah": rec.electrode_capacity_ah,
            "voltage_range": (
                [rec.lower_voltage_v, rec.upper_voltage_v]
                if rec.lower_voltage_v and rec.upper_voltage_v
                else None
            ),
            "positive_electrode": {
                "active_material": rec.cathode,
                "type": rec.cathode_pn,
            },
            "negative_electrode": {
                "type": rec.anode,
            },
            "electrolyte": {
                "solvent": rec.electrolyte,
                "additives": None,
            },
            "separator": {
                "type": rec.separator,
            },
            "test": {
                "temperature_c": rec.test_temperature_c,
                "c_rates": (
                    [rec.charge_rate_c, rec.discharge_rate_c]
                    if rec.charge_rate_c and rec.discharge_rate_c
                    else None
                ),
            },
            "custom": {
                "挂测地点": rec.location,
                "注液系数_g_Ah": rec.filling_coefficient_g_ah,
                "预紧力_MPa": rec.preload_mpa,
                "缓冲垫": rec.buffer_pad,
                "缓冲垫厚度_mm": rec.buffer_pad_thickness_mm,
                "SOC_pct": rec.soc_pct,
                "DOD_pct": rec.dod_pct,
                "阻抗_ohm": rec.impedance_ohm,
                "归一化阻抗_ohm_cm2": rec.normalized_impedance_ohm_cm2,
            },
            "notes": rec.notes,
        }
        out = output_dir / f"{rec.cell_id}_design.yaml"
        clean = {k: v for k, v in data.items() if v is not None}
        with open(out, "w", encoding="utf-8") as f:
            yaml.dump(clean, f, allow_unicode=True, default_flow_style=False)
        paths.append(out)
    return paths
