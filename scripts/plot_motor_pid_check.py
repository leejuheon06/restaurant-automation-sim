"""Rebuild the 2026-11-24 motor test figures from the recorded CSVs."""
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

from chart_style import BLUE, INK, ORANGE, TEAL, polish, setup

ROOT = Path(__file__).resolve().parents[1]
MT1 = ROOT / 'runs/20261124_01_motor_check_3robots'
MT2 = ROOT / 'runs/20261124_02_motor_igain_3robots'
MT3 = ROOT / 'runs/20261124_03_motor_floor_3robots'
MT5 = ROOT / 'runs/20261124_04_cmdvel_gap_analysis'
MT6_V1 = ROOT / 'runs/20261124_05_mt6_v1_wheel_calib'
MT6_CUT = ROOT / 'runs/20261124_06_mt6_cut_t03'
OUT = ROOT / 'docs/images/2026-11-24'


def read_rows(path):
    with path.open(newline='') as source:
        yield from csv.DictReader(line for line in source if not line.startswith('#'))


def step_example(path):
    """Read the first 28 RPM forward trial and its following stop window."""
    start = None
    elapsed, left, right = [], [], []
    for row in read_rows(path):
        time = float(row['t'])
        if row['event'] == 'cmd':
            if start is None and row['seg'] == 'fwd' and float(row['target']) == 28:
                start = time
            elif start is not None:
                if row['seg'] == 'fwd_off':
                    stop = time - start
                else:
                    return elapsed, left, right, stop
        if start is not None and row['event'] == 's':
            elapsed.append(time - start)
            left.append(float(row['vel_l']) * 0.229)
            right.append(-float(row['vel_r']) * 0.229)
    raise ValueError(f'Incomplete 28 RPM trial in {path}')


def plot_steps():
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True, layout='constrained')
    for ax, robot in zip(axes, ('pinky1', 'pinky2', 'pinky3')):
        elapsed, left, right, stop = step_example(MT1 / f'steps_{robot}.csv')
        ax.step([0, stop, elapsed[-1]], [28, 0, 0], where='post',
                color=INK, linestyle='--', label='명령')
        ax.plot(elapsed, left, color=BLUE, linewidth=1, label='왼쪽')
        ax.plot(elapsed, right, color=ORANGE, linewidth=1, alpha=0.8, label='오른쪽')
        ax.set(title=robot, xlabel='명령 후 시간 (초)')
    axes[0].set_ylabel('전진 방향 속도 (RPM)')
    axes[-1].legend(loc='center right')
    fig.suptitle('MT-1 | 첫 28 RPM 전진 시험의 바퀴별 응답')
    polish(fig)
    fig.savefig(OUT / 'motor_step_response.png', dpi=180)
    plt.close(fig)


def plot_gains():
    rows = list(read_rows(MT2 / 'summary_by_gain_target.csv'))
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout='constrained')
    metrics = [('os', '오버슈트 (%)'), ('rise', '10→90% 상승 시간 (초)'),
               ('coast_mm', '0 명령 후 이동량 환산 (mm)')]
    for ax, (key, label) in zip(axes, metrics):
        ax.set(title=label, xlabel='목표 속도 (RPM)', xticks=[7, 18, 28, 48])
        for gain, color in [(1600, BLUE), (800, TEAL), (400, ORANGE)]:
            group = sorted((r for r in rows if int(r['g']) == gain), key=lambda r: int(r['t']))
            ax.plot([int(r['t']) for r in group], [float(r[key]) for r in group],
                    color=color, marker='o', label=f'I {gain}')
        ax.set_ylim(bottom=0)
    axes[-1].legend(loc='upper left')
    fig.suptitle('MT-2 | I 게인별 무부하 응답 (조건당 60개 바퀴 응답의 중앙값)')
    polish(fig)
    fig.savefig(OUT / 'motor_igain_comparison.png', dpi=180)
    plt.close(fig)


def plot_floor():
    rows = [r for r in read_rows(MT3 / 'compare_floor_vs_noload.csv') if r['v'] == '0.08']
    stops = list(read_rows(MT3 / 'summary_C_stop.csv'))
    robots = [r['r'] for r in rows]
    x = range(len(robots))
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout='constrained')
    for ax, key, title in zip(axes, ('rise', 'cur0'),
                              ('10→90% 상승 시간 (초)', '출발 전류 (mA)')):
        for condition, label, color, offset in [
                ('nl', '무부하', BLUE, -0.19), ('floor', '바닥', TEAL, 0.19)]:
            ax.bar([i + offset for i in x],
                   [float(r[f'{key}_{condition}']) for r in rows],
                   width=0.36, label=label, color=color)
        ax.set_title(title)
    axes[0].legend()
    for mode, label, color, offset in [
            ('zero', '0 발행', TEAL, -0.19), ('cut', '발행 끊김', ORANGE, 0.19)]:
        by_robot = {r['r']: r for r in stops if r['mode'] == mode}
        axes[2].bar([i + offset for i in x],
                    [float(by_robot[robot]['odom_stop_mm']) for robot in robots],
                    width=0.36, label=label, color=color)
    axes[2].set_title('오도메트리 정지 거리 (mm)')
    axes[2].legend()
    for ax in axes:
        ax.set_xticks(list(x), robots)
        ax.margins(y=0.22)
    fig.suptitle('MT-3 | 0.08 m/s 응답과 정지 거리 비교 (중앙값)')
    polish(fig)
    fig.savefig(OUT / 'motor_floor_comparison.png', dpi=180)
    plt.close(fig)


def plot_cmdvel_gaps():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained', sharey=True)
    metrics = ('median_ms', 'p99_ms', 'p999_ms', 'max_ms')
    for ax, folder, title, color in zip(
            axes, ('pc_bags', 'robot_bags'),
            ('관제 PC 수신 기록', '로봇 내부 · 20 Hz 시험 스크립트'), (BLUE, TEAL)):
        summary = json.loads((MT5 / folder / 'gaps_total.json').read_text())['ALL']
        bars = ax.bar(['중앙값', 'p99', 'p99.9', '최대'],
                      [summary[key] for key in metrics], color=color)
        ax.bar_label(bars, fmt='%g', padding=3)
        ax.axhline(300, color=ORANGE, linestyle='--', label='시험 후보 300 ms')
        ax.axhline(500, color=INK, linestyle=':', label='현재 500 ms')
        ax.set(title=title, ylim=(0, 860))
    axes[0].set_ylabel('기록된 명령 간격 (ms)')
    axes[1].legend(loc='upper right')
    fig.suptitle('MT-5 | 기록 위치와 발행 조건별 명령 간격')
    polish(fig)
    fig.savefig(OUT / 'motor_cmdvel_gaps.png', dpi=180)
    plt.close(fig)


def plot_mt6():
    fig, (cal, cut) = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
    cal.axhspan(-0.3, 0.3, color=TEAL, alpha=0.13)
    cal.axhline(0, color=INK, linewidth=0.8)
    baseline = {r['r']: r for r in read_rows(MT3 / 'summary_C_stop.csv')
                if r['mode'] == 'cut'}
    for offset, robot, color in [(-0.12, 'pinky2', BLUE), (0.12, 'pinky3', ORANGE)]:
        trials = list(read_rows(MT6_V1 / f'V1_{robot}_v1.csv'))
        cal.scatter([i + offset for i in range(len(trials))],
                    [(float(r['ratio']) - 1) * 100 for r in trials],
                    color=color, label=robot)
        rows = read_rows(MT6_CUT / f'CUT_{robot}_C_segments.csv')
        values = [100 * float(r['lidar_stop_dist_m']) for r in rows if r['mode'] == 'cut']
        cut.scatter([offset + (j - 1) * 0.023 for j in range(len(values))],
                    values, color=color)
        median = float(baseline[robot]['lidar_stop_mm']) / 10
        maximum = float(baseline[robot]['lidar_stop_w']) / 10
        cut.errorbar(1 + offset, median, yerr=[[0], [maximum - median]],
                     fmt='D', capsize=4, color=color)
    cal.set(title='V1 · 보정 후 검증', ylabel='ICP ÷ odom의 1 대비 오차 (%)',
            xticks=range(7), xticklabels=['직진 1', '직진 2', '직진 3',
                                          '회전 1', '회전 2', '회전 3', '회전 4'],
            ylim=(-0.82, 0.52))
    cal.legend(loc='lower right')
    cut.set(title='발행 끊김 · 0.08 m/s', ylabel='라이다 환산 정지 거리 (cm)',
            xticks=[0, 1], xticklabels=['MT-6 · 0.3초', 'MT-3 · 0.5초'],
            xlim=(-0.4, 1.4), ylim=(0, 5.8))
    fig.suptitle('MT-6 1차 | pinky2·pinky3 보정 검증과 정지 거리')
    polish(fig)
    fig.savefig(OUT / 'motor_mt6_interim.png', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    setup()
    OUT.mkdir(parents=True, exist_ok=True)
    plot_steps()
    plot_gains()
    plot_floor()
    plot_cmdvel_gaps()
    plot_mt6()
