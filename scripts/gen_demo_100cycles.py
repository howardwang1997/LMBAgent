"""Generate a realistic 100-cycle PEC CSV for a lithium metal battery (LMB).

Chemistry: Li metal anode || LiPF6 in EC/DMC || NMC622 cathode
Nominal capacity: ~3.5 Ah (like a pouch cell)
C-rate: C/2 charge, C/2 discharge
Voltage window: 2.7 V – 4.2 V

Realistic degradation model:
- Capacity fade: ~0.15% per cycle (SEI growth + dead Li), accelerating slightly
- Coulombic efficiency: starts ~98.5%, improves to ~99.5% over first 20 cycles
  (SEI stabilization), then gradually drops (dendrite-driven loss)
- Impedance: grows linearly + slight acceleration (electrolyte decomposition)
- Voltage hysteresis: increases with cycle number (thickening SEI)
- Temperature: ambient 25°C, cell surface rises during charge/discharge
"""

import csv
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

OUTPUT = Path(__file__).parent.parent / "data" / "examples" / "pec_100cycles.csv"

# Battery parameters
NOMINAL_CAP_MAH = 3500.0  # mAh
C_RATE = 0.5
CURRENT_MA = NOMINAL_CAP_MAH * C_RATE  # 1750 mA
V_MIN, V_MAX = 2700.0, 4200.0  # mV
NUM_CYCLES = 100
POINTS_PER_HALF_CYCLE = 60  # data points per charge or discharge phase
REST_POINTS = 5

START_TIME = datetime(2024, 3, 15, 10, 0, 0)


_ce_history = []
_cumulative_retention = 1.0

def capacity_at_cycle(n):
    """Capacity fade driven by cumulative CE loss + noise.

    Each cycle's irreversible loss = (1 - CE) * capacity, so capacity
    tracks the product of all prior CEs, with additional calendar aging.
    Returns (capacity_mah, ce_this_cycle).
    """
    global _cumulative_retention
    ce = coulombic_efficiency(n)
    _ce_history.append(ce)
    _cumulative_retention *= ce
    calendar_fade = 0.00005 * n
    cap = NOMINAL_CAP_MAH * max(0.5, _cumulative_retention - calendar_fade)
    return cap, ce


def coulombic_efficiency(n):
    """CE with realistic noise: starts low, stabilizes, slowly degrades.

    Real LMB CE data has cycle-to-cycle scatter from side reactions,
    dendrite nucleation events, and measurement precision limits.
    """
    if n < 5:
        base = 0.970 + 0.004 * n
        noise = random.gauss(0, 0.004)
    elif n < 20:
        base = 0.988 + 0.0004 * (n - 5)
        noise = random.gauss(0, 0.002)
    else:
        base = 0.994 - 0.00015 * (n - 20)
        noise = random.gauss(0, 0.0015)
    if random.random() < 0.03:
        noise -= random.uniform(0.005, 0.015)
    return max(0.93, min(1.0, base + noise))


def impedance_mohm(n):
    """Internal resistance growth: linear + mild quadratic."""
    base = 45.0
    return base + 0.15 * n + 0.001 * n * n


def voltage_profile_charge(frac, cycle, cap_mah):
    """Voltage during CC charge as function of SOC fraction [0,1]."""
    overpotential = 20 + 0.3 * cycle  # mV, grows with degradation
    base = V_MIN + (V_MAX - V_MIN - overpotential) * (
        0.05 + 0.9 * frac + 0.05 * frac**2
    )
    noise = random.gauss(0, 0.8)
    return min(V_MAX, base + overpotential * frac + noise)


def voltage_profile_discharge(frac, cycle, cap_mah):
    """Voltage during CC discharge as function of DOD fraction [0,1]."""
    overpotential = 15 + 0.25 * cycle
    base = V_MAX - (V_MAX - V_MIN - overpotential) * (
        0.05 + 0.9 * frac + 0.05 * frac**2
    )
    noise = random.gauss(0, 0.8)
    return max(V_MIN, base - overpotential * frac + noise)


def temperature_cell(is_active, frac, cycle):
    """Cell surface temp: ambient + heating during cycling."""
    ambient = 25.0 + random.gauss(0, 0.1)
    if not is_active:
        return ambient, ambient
    heat = 2.5 * math.sin(math.pi * frac) + 0.01 * cycle
    return ambient, ambient + heat + random.gauss(0, 0.15)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    header_lines = [
        "Request Year:,2024",
        "Test:,201",
        "Test Description:,",
        "TestRegime Name:,LMB NMC622 100cyc C/2",
        "TestRegime Suffix:,DEMO",
        "TestRegime CellSize:,Pouch 3.5Ah",
        "TestRegime Version:,1",
        "Project Group Name:,LMB Research",
        "Project Group Description:,Lithium Metal Battery cycling study",
        "Project Group Memo:,",
        "Project Group Storage Environment:,R.T./AMB",
        "Project Group Test Environment:,R.T./AMB",
        "Number Of Cells:,1",
        "Parameter names:,",
        "Parameter values:,",
        "Variable names",
        "LotID:,",
        "Lot Description:,",
        "Date Made:,3/01/2024 0:00",
        "Origin:,Lab",
        "Requestor:,Demo",
        "Product ID:,LMB-NMC622-Pouch",
        "Storage Temp:,R.T./AMB",
        "Storage Delay:,0 days",
        "Test Temp:,R.T./AMB",
        f"Start Time:,{START_TIME.strftime('%m/%d/%Y %H:%M:%S')}",
        "End Time:,1/1/0001 0:00",
        "Operator Instructions:,Synthetic demo data for LMBAgent",
        "#RESULTS CHECK",
        "ReqYear,Test,CellNr,Type,Value,Reason,",
        "2024,201,1,1,3500,3,",
        "#END RESULTS CHECK",
    ]

    columns = (
        "Test,Cell,Rack,Shelf,Position,Cell ID,Step,Cycle,"
        "Total Time (Seconds),Load On Time (Seconds),Step Time (Seconds),"
        "Cycle Charge Time (Seconds),Cycle Discharge Time (Seconds),"
        "Real Time,Position Start Time,"
        "Voltage (mV),Current (mA),"
        "Charge Capacity (mAh),Discharge Capacity (mAh),"
        "Charge Capacity (mWh),Discharge Capacity (mWh),"
        "ReasonCode,"
        "50% DoD (mV),PeakPower 1 (W),PeakPower 2 (W),"
        "Open Circuit Voltage 1 (V),Open Circuit Voltage 2 (V),"
        "Internal Resistance 1 (mOhm),Internal Resistance 2 (mOhm),"
        "Ambient temperature (°C),Cell surface temperature (°C),"
        "DC Internal Resistance (mOhm),AC Internal Resistance (mOhm),"
        "Station Temperature (°C),"
    )

    total_time = 0.0
    current_time = START_TIME
    rows = []

    for cycle in range(NUM_CYCLES):
        cap, ce = capacity_at_cycle(cycle)
        ir = impedance_mohm(cycle)
        charge_cap = cap
        discharge_cap = cap * ce
        charge_time_s = charge_cap / CURRENT_MA * 3600
        discharge_time_s = discharge_cap / CURRENT_MA * 3600
        dt_charge = charge_time_s / POINTS_PER_HALF_CYCLE
        dt_discharge = discharge_time_s / POINTS_PER_HALF_CYCLE

        cycle_charge_time = 0.0
        cycle_discharge_time = 0.0

        # --- REST before charge ---
        step = cycle * 4
        for j in range(REST_POINTS):
            step_time = j * 20.0
            total_time += 20.0
            t_amb, t_cell = temperature_cell(False, 0, cycle)
            ocv = V_MIN + 200 + random.gauss(0, 2) + 5 * cycle * 0.01
            row = _make_row(
                step=step, cycle=cycle, total_time=total_time,
                load_on=0, step_time=step_time,
                cycle_charge_time=0, cycle_discharge_time=0,
                real_time=current_time, start_time=START_TIME,
                voltage=ocv, current=0,
                charge_cap=0, discharge_cap=0,
                charge_energy=0, discharge_energy=0,
                reason=30 if j % 3 == 0 else 2,
                ir=ir, t_amb=t_amb, t_cell=t_cell,
            )
            rows.append(row)
            current_time += timedelta(seconds=20)

        # --- CC CHARGE ---
        step += 1
        cum_charge = 0.0
        cum_charge_energy = 0.0
        for j in range(POINTS_PER_HALF_CYCLE):
            frac = j / (POINTS_PER_HALF_CYCLE - 1)
            v = voltage_profile_charge(frac, cycle, cap)
            dt = dt_charge
            total_time += dt
            cycle_charge_time += dt
            delta_cap = CURRENT_MA * (dt / 3600)
            cum_charge += delta_cap
            cum_charge_energy += delta_cap * v / 1000.0
            t_amb, t_cell = temperature_cell(True, frac, cycle)
            row = _make_row(
                step=step, cycle=cycle, total_time=total_time,
                load_on=cycle_charge_time, step_time=cycle_charge_time,
                cycle_charge_time=cycle_charge_time, cycle_discharge_time=0,
                real_time=current_time, start_time=START_TIME,
                voltage=v, current=CURRENT_MA,
                charge_cap=cum_charge, discharge_cap=0,
                charge_energy=cum_charge_energy, discharge_energy=0,
                reason=30 if j % 10 == 0 else 2,
                ir=ir, t_amb=t_amb, t_cell=t_cell,
            )
            rows.append(row)
            current_time += timedelta(seconds=dt)

        # --- REST after charge ---
        step += 1
        for j in range(REST_POINTS):
            step_time = j * 30.0
            total_time += 30.0
            t_amb, t_cell = temperature_cell(False, 0, cycle)
            row = _make_row(
                step=step, cycle=cycle, total_time=total_time,
                load_on=0, step_time=step_time,
                cycle_charge_time=cycle_charge_time, cycle_discharge_time=0,
                real_time=current_time, start_time=START_TIME,
                voltage=V_MAX - 10 + random.gauss(0, 2), current=0,
                charge_cap=cum_charge, discharge_cap=0,
                charge_energy=cum_charge_energy, discharge_energy=0,
                reason=30 if j % 3 == 0 else 2,
                ir=ir, t_amb=t_amb, t_cell=t_cell,
            )
            rows.append(row)
            current_time += timedelta(seconds=30)

        # --- CC DISCHARGE ---
        step += 1
        cum_discharge = 0.0
        cum_discharge_energy = 0.0
        for j in range(POINTS_PER_HALF_CYCLE):
            frac = j / (POINTS_PER_HALF_CYCLE - 1)
            v = voltage_profile_discharge(frac, cycle, cap)
            dt = dt_discharge
            total_time += dt
            cycle_discharge_time += dt
            delta_cap = CURRENT_MA * (dt / 3600)
            cum_discharge += delta_cap
            cum_discharge_energy += delta_cap * v / 1000.0
            t_amb, t_cell = temperature_cell(True, frac, cycle)
            row = _make_row(
                step=step, cycle=cycle, total_time=total_time,
                load_on=cycle_discharge_time, step_time=cycle_discharge_time,
                cycle_charge_time=cycle_charge_time,
                cycle_discharge_time=cycle_discharge_time,
                real_time=current_time, start_time=START_TIME,
                voltage=v, current=-CURRENT_MA,
                charge_cap=cum_charge, discharge_cap=cum_discharge,
                charge_energy=cum_charge_energy, discharge_energy=cum_discharge_energy,
                reason=30 if j % 10 == 0 else 2,
                ir=ir, t_amb=t_amb, t_cell=t_cell,
            )
            rows.append(row)
            current_time += timedelta(seconds=dt)

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line + "\n")
        f.write(columns + "\n")
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)

    print(f"Generated {len(rows)} data points over {NUM_CYCLES} cycles → {OUTPUT}")


def _make_row(
    step, cycle, total_time, load_on, step_time,
    cycle_charge_time, cycle_discharge_time,
    real_time, start_time,
    voltage, current,
    charge_cap, discharge_cap,
    charge_energy, discharge_energy,
    reason, ir, t_amb, t_cell,
):
    return [
        201, 1, "LAB01", "001", 1, "",
        step, cycle,
        f"{total_time:.3f}",
        f"{load_on:.0f}",
        f"{step_time:.0f}",
        f"{cycle_charge_time:.0f}",
        f"{cycle_discharge_time:.0f}",
        real_time.strftime("%m/%d/%Y %H:%M:%S"),
        start_time.strftime("%m/%d/%Y %H:%M:%S"),
        f"{voltage:.4f}",
        f"{current:.1f}",
        f"{charge_cap:.3f}",
        f"{discharge_cap:.3f}",
        f"{charge_energy:.3f}",
        f"{discharge_energy:.3f}",
        reason,
        0, 0, 0, 0, 0,
        f"{ir:.1f}", 0,
        f"{t_amb:.2f}", f"{t_cell:.2f}",
        "", "", "", "",
    ]


if __name__ == "__main__":
    main()
