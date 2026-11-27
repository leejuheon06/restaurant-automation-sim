"""Plot inference times reported in the 2026-11-24 YOLO planning document."""
from pathlib import Path

import matplotlib.pyplot as plt

from chart_style import BLUE, ORANGE, polish, setup

# Reported summary statistics, in model order. These are inference-only times.
MODELS = ('YOLOv8s', 'YOLO11s', 'YOLO26s')
GPU = ((8.7, 8.0, 8.2), (15.5, 10.1, 11.1))
CPU = ((96, 87, 93), (119, 104, 104))


def main():
    setup()
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), layout='constrained')
    for ax, values, title in zip(axes, (GPU, CPU),
                                  ('GPU · 1,907프레임', 'CPU · 60프레임')):
        for series, label, color, offset in zip(
                values, ('p50', 'p95'), (BLUE, ORANGE), (-0.18, 0.18)):
            bars = ax.bar([i + offset for i in range(len(MODELS))], series,
                          width=0.34, label=label, color=color)
            ax.bar_label(bars, fmt='%g', padding=3)
        ax.set_xticks(range(len(MODELS)), MODELS)
        ax.set(title=title, ylabel='프레임당 추론 시간 (ms)')
        ax.margins(y=0.27)
        ax.legend(loc='upper center', ncol=2)
    fig.suptitle('YOLO 모델별 정지 영상 사전 측정')
    polish(fig)
    out = Path(__file__).resolve().parents[1] / 'docs/images/2026-11-24'
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / 'guest_tracker_inference.png', dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.6), layout='constrained')
    for ax, values, title in zip(axes, ((667, 38), (135, 28)),
                                 ('송신 대기 (KB)', 'TCP RTT (ms)')):
        bars = ax.bar(['30 fps / 품질 93', '15 fps / 품질 70'],
                      values, color=[BLUE, ORANGE], width=0.55)
        ax.bar_label(bars, fmt='약 %g', padding=3)
        ax.set_title(title)
        ax.margins(y=0.17)
    fig.suptitle('카메라 3대 동시 송신 시 pinky2 링크 관측값')
    polish(fig)
    fig.savefig(out / 'guest_tracker_stream_link.png', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    main()
