"""HW 검증 결과 문서(2026-11-26)의 그림을 기록에서 다시 그린다."""

import csv
import json
import pathlib

import chart_style
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = ROOT / 'runs'
T0 = RUNS / '20261125_07_mt7_c2_swap'
T12 = RUNS / '20261125_08_hwfinal_t1t2_b1'
T3 = RUNS / '20261126_02_hwfinal_t3_30min'
V2 = RUNS / '20261125_02_mt6_v2_cmdvel_onboard_t05'
V3 = RUNS / '20261125_03_mt6_v3_cmdvel_t03'
OUT = ROOT / 'docs/images/2026-11-26'
ROBOTS = ('pinky1', 'pinky2', 'pinky3')
COLORS = (chart_style.BLUE, chart_style.ORANGE, chart_style.TEAL)
MARKERS = ('o', 's', '^')

# 1 m 직진의 줄자 / 오도메트리(runs/20261126_01_hwfinal_wheel_verify,
# 줄자는 사용자가 mm 로 읽음). 설계값 칸은 확정 반지름 / 0.027 로 계산.
WHEEL = {
    'pinky1': {'design': 1.0159,
               'first': (1.0026, 1.0035, 1.0064),
               'final': (0.9989, 0.9983, 0.9997)},
    'pinky2': {'design': 1.0130,
               'first': (1.0058, 1.0085, 1.0083),
               'final': (1.0019, 1.0015, 1.0011)},
    'pinky3': {'design': 1.0137,
               'first': (0.9951, 0.9951, 0.9941),
               'final': (1.0010, 1.0014, 1.0009)},
}

# (항목, 측정한 최악값, 목표 한계, 표시 문자열). 문서 7.2절과 같은 값.
SUMMARY = (
    ('속도 정상상태 오차', 3.8, 5.0, '3.8 / 5 %'),
    ('속도 오버슈트', 11.9, 15.0, '11.9 / 15 %'),
    ('속도 흔들림', 2.0, 5.0, '2.0 / 5 %'),
    ('바퀴 반지름(1 m 직진)', 0.15, 0.3, '0.15 / 0.3 %'),
    ('바퀴 간격(360° 회전)', 0.17, 0.3, '0.17 / 0.3 %'),
    ('좌우 속도 차(1 m 방향 변화)', 2.9, 5.7, '2.9 / 5.7°'),
    ('정지 거리(0.08 m/s)', 7.6, 10.0, '7.6 / 10 mm'),
    ('유격(고정 차이)', 2.2, 3.0, '2.2 / 3 mm'),
    ('명령 간격(최대)', 73.7, 100.0, '74 / 100 ms'),
    ('모터 온도(30분 뒤)', 32.0, 70.0, '32 / 70 °C'),
    ('Pi 온도(30분 최고)', 75.4, 80.0, '75.4 / 80 °C'),
    ('라이다 거리 오차', 9.3, 30.0, '9.3 / 30 mm'),
    ('라이다 흔들림', 14.1, 15.0, '14.1 / 15 mm'),
)


def read_rows(path: pathlib.Path) -> list:
    """CSV 파일을 dict 목록으로 읽는다.

    Args:
        path: CSV 파일 경로.

    Returns:
        행마다 dict 하나인 목록.
    """
    with path.open(newline='') as source:
        return list(csv.DictReader(source))


def stop_distances() -> dict:
    """0.08 m/s 0 발행 정지 거리(보간값, mm)를 로봇별로 모은다.

    Returns:
        로봇 이름 -> 정지 거리 목록.
    """
    out = {robot: [] for robot in ROBOTS}
    seen = set()
    files = [T0 / 'T0_segments.csv']
    files += [T12 / f'hw_segments_{robot}.csv' for robot in ROBOTS]
    for path in files:
        for row in read_rows(path):
            key = (row['run'], row['robot'], row['seg'])
            if key in seen:
                continue
            seen.add(key)
            if row['cond'] != 'fwd_0.08' or row['stop_kind'] != 'zero':
                continue
            out[row['robot']].append(float(row['stop_odom_interp_mm']))
    return out


def pi_temperature(robot: str) -> tuple:
    """30분 운전 중 1분마다 기록한 Pi 온도를 읽는다.

    Args:
        robot: 로봇 이름.

    Returns:
        (시작 뒤 경과 분 목록, 온도 목록).
    """
    stamps, temps = [], []
    path = T3 / 'logs' / f'{robot}_mon.log'
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[1].startswith('temp='):
            continue
        stamps.append(float(parts[0]))
        temps.append(float(parts[1][5:].rstrip("'C")))
    minutes = [(stamp - stamps[0]) / 60 for stamp in stamps]
    return minutes, temps


def plot_wheel() -> None:
    """바퀴 값 단계별 1 m 직진 오차를 그린다."""
    fig, ax = plt.subplots(figsize=(8.4, 4.4), layout='constrained')
    ax.axhspan(-0.3, 0.3, color=chart_style.TEAL, alpha=0.13)
    ax.axhline(0, color=chart_style.INK, linewidth=0.8)
    stages = (('design', '설계값 (계산)', chart_style.INK, 'D', -0.25),
              ('first', '11-25 보정값 (측정 3회)', chart_style.ORANGE,
               's', 0.0),
              ('final', '확정값 (측정 3회)', chart_style.BLUE, 'o', 0.25))
    for index, robot in enumerate(ROBOTS):
        for key, label, color, marker, offset in stages:
            value = WHEEL[robot][key]
            values = (value,) if isinstance(value, float) else value
            ax.scatter([index + offset] * len(values),
                       [(ratio - 1) * 100 for ratio in values],
                       color=color, marker=marker, s=46, zorder=3,
                       label=label if index == 0 else None)
    ax.text(2.42, 0.33, '목표 ±0.3 %', ha='right', va='bottom',
            fontsize=9, color=chart_style.INK)
    ax.set(xticks=range(len(ROBOTS)), xticklabels=ROBOTS,
           xlim=(-0.5, 2.5), ylim=(-0.9, 1.9),
           ylabel='실제 거리 ÷ 오도메트리의 1 대비 오차 (%)',
           title='바퀴 값 단계별 1 m 직진 오차 (줄자 기준)')
    ax.legend(loc='upper right')
    chart_style.polish(fig)
    fig.savefig(OUT / 'hw_wheel_calibration.png', dpi=180)
    plt.close(fig)


def plot_stop() -> None:
    """로봇별 정지 거리 분포를 그린다."""
    data = stop_distances()
    fig, ax = plt.subplots(figsize=(8.4, 4.2), layout='constrained')
    for index, robot in enumerate(ROBOTS):
        values = data[robot]
        step = 0.56 / max(len(values) - 1, 1)
        spread = [index - 0.28 + k * step for k in range(len(values))]
        ax.scatter(spread, values, color=COLORS[index],
                   marker=MARKERS[index], s=22, zorder=3)
        ax.text(index, max(values) + 0.35,
                f'{len(values)}회, 최악 {max(values):.1f} mm',
                ha='center', va='bottom', fontsize=9, color=chart_style.INK)
    ax.axhline(10, color=chart_style.INK, linestyle='--', linewidth=1)
    ax.text(2.45, 10.15, '목표 10 mm', ha='right', va='bottom',
            fontsize=9, color=chart_style.INK)
    ax.set(xticks=range(len(ROBOTS)), xticklabels=ROBOTS,
           xlim=(-0.5, 2.5), ylim=(0, 11.5),
           ylabel='0 명령 뒤 더 간 거리 (mm)',
           title='정지 거리 (0.08 m/s, 회차별)')
    chart_style.polish(fig)
    fig.savefig(OUT / 'hw_stop_distance.png', dpi=180)
    plt.close(fig)


def plot_temperature() -> None:
    """30분 운전 중 Pi 온도를 그린다."""
    fig, ax = plt.subplots(figsize=(8.4, 4.2), layout='constrained')
    for robot, color, marker in zip(ROBOTS, COLORS, MARKERS, strict=True):
        minutes, temps = pi_temperature(robot)
        ax.plot(minutes, temps, color=color, linewidth=2, marker=marker,
                markersize=4, label=robot)
    ax.axhline(80, color=chart_style.INK, linestyle='--', linewidth=1)
    ax.text(0.2, 80.4, '목표 80 °C 미만 (이 온도부터 성능을 낮춤)',
            ha='left', va='bottom', fontsize=9, color=chart_style.INK)
    peak_minutes, peak_temps = pi_temperature('pinky3')
    top = max(peak_temps)
    ax.annotate(f'pinky3 최고 {top:.1f} °C',
                xy=(peak_minutes[peak_temps.index(top)], top),
                xytext=(-8, 8), textcoords='offset points', ha='right',
                fontsize=9, color=chart_style.INK)
    ax.set(xlabel='기록 시작 뒤 시간 (분)', ylabel='Pi 온도 (°C)',
           ylim=(50, 84), xlim=(0, 41),
           title='세 대 동시 30분 운전 중 Pi 온도 (1분 간격)')
    ax.legend(loc='lower right')
    chart_style.polish(fig)
    fig.savefig(OUT / 'hw_pi_temperature.png', dpi=180)
    plt.close(fig)


def plot_interval() -> None:
    """시험별 로봇 안 명령 간격을 그린다."""
    tests = (('20회 왕복\n(감시 0.5초)', V2), ('20회 왕복\n(감시 0.3초)', V3),
             ('30분 왕복', T3))
    fig, ax = plt.subplots(figsize=(8.4, 4.2), layout='constrained')
    for index, (_, folder) in enumerate(tests):
        total = json.loads((folder / 'gaps_total.json').read_text())['ALL']
        bar = ax.bar(index, total['max_ms'], width=0.5,
                     color=chart_style.BLUE,
                     label='최대 간격' if index == 0 else None)
        ax.bar_label(bar, labels=[f"{total['max_ms']:.1f} ms"], padding=3)
        ax.scatter(index, total['median_ms'], color=chart_style.INK,
                   marker='D', s=36, zorder=3,
                   label='중앙값' if index == 0 else None)
    ax.axhline(100, color=chart_style.INK, linestyle='--', linewidth=1)
    ax.text(2.45, 102, '목표 100 ms (명령 한 번이 빠진 간격)',
            ha='right', va='bottom', fontsize=9, color=chart_style.INK)
    ax.set(xticks=range(len(tests)), xticklabels=[t[0] for t in tests],
           xlim=(-0.5, 2.5), ylim=(0, 125),
           ylabel='로봇 안 명령 도착 간격 (ms)',
           title='로봇 안 명령 간격 (약 13만 개)')
    ax.legend(loc='upper left')
    chart_style.polish(fig)
    fig.savefig(OUT / 'hw_cmd_interval.png', dpi=180)
    plt.close(fig)


def plot_summary() -> None:
    """항목별 측정값을 목표 한계 대비 비율로 그린다."""
    fig, ax = plt.subplots(figsize=(8.8, 5.6), layout='constrained')
    names = [row[0] for row in SUMMARY][::-1]
    ratios = [100 * row[1] / row[2] for row in SUMMARY][::-1]
    labels = [row[3] for row in SUMMARY][::-1]
    bars = ax.barh(names, ratios, height=0.6, color=chart_style.BLUE)
    for bar, label in zip(bars, labels, strict=True):
        ax.text(bar.get_width() - 1.2, bar.get_y() + bar.get_height() / 2,
                label, ha='right', va='center', fontsize=9, color='white')
    ax.axvline(100, color=chart_style.INK, linestyle='--', linewidth=1)
    ax.text(101.5, len(names) - 1, '목표 한계', ha='left', va='center',
            fontsize=9, color=chart_style.INK)
    ax.set(xlim=(0, 118), xlabel='목표 한계 대비 측정값 (%)',
           title='항목별 측정값 (세 대 중 최악값) / 목표 한계')
    chart_style.polish(fig)
    ax.grid(axis='y', visible=False)
    ax.grid(axis='x', color='#E7EDF3', linewidth=0.7)
    fig.savefig(OUT / 'hw_target_summary.png', dpi=180)
    plt.close(fig)


def main() -> None:
    """그림 다섯 장을 만든다."""
    chart_style.setup()
    OUT.mkdir(parents=True, exist_ok=True)
    plot_wheel()
    plot_stop()
    plot_temperature()
    plot_interval()
    plot_summary()


if __name__ == '__main__':
    main()
