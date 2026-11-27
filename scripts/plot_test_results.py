"""Render documented C6/C8 measurements. Run: PYTHONNOUSERSITE=1 python3 scripts/plot_test_results.py."""
from pathlib import Path
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/2026-11-19_REAL_TEST.md'
OUT = ROOT / 'docs/images/2026-11-19'
font = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family': font.get_name(), 'axes.unicode_minus': False, 'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
from chart_style import setup, polish
setup()
text = DOC.read_text()
OUT.mkdir(parents=True, exist_ok=True)
blue, orange = '#277DA1', '#E88D34'

def finish(fig, name):
    polish(fig)
    fig.savefig(OUT / name, dpi=180, facecolor='#F5F8FB', bbox_inches='tight')
    plt.close(fig)

rows = []
for line in text.splitlines():
    c = [v.strip() for v in line.strip('|').split('|')]
    if len(c) == 9 and re.fullmatch(r'[1-6]_(on|off)', c[0]):
        rows.append((c[0], c[1], int(c[2]), float(c[3]), int(c[4])))
assert len(rows) == 18
fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
for offset, state, color in [(-.18, 'on', blue), (.18, 'off', orange)]:
    subset = [r for r in rows if r[0].endswith('_' + state)]
    vals = [sum(r[2] for r in subset), sum(r[4] for r in subset)]
    bars = axs[0].bar([offset, 1+offset], vals, width=.34, color=color, label='켬' if state=='on' else '끔')
    axs[0].bar_label(bars, padding=3)
axs[0].set(xticks=[0,1], xticklabels=['전체 끊김', '2초 초과 끊김'], ylabel='건수 (조건별 3회 × 로봇 3대)', ylim=(0,24), title='C6-C 전역 코스트맵 표시 비교')
axs[0].legend(frameon=False)
trials = ['1_on','2_off','3_off','4_on','5_on','6_off']
values = [max(r[3] for r in rows if r[0] == t) for t in trials]
bars = axs[1].bar(range(6), values, color=[blue if t.endswith('_on') else orange for t in trials])
axs[1].bar_label(bars, fmt='%.1f', padding=3)
axs[1].axhline(2, color='#888', linestyle='--', label='2초 기준')
axs[1].set(xticks=range(6), xticklabels=['1 켬','2 끔','3 끔','4 켬','5 켬','6 끔'], ylabel='초', ylim=(0,7.4), title='실제 시험 순서별 최장 끊김')
handles, labels = axs[1].get_legend_handles_labels()
axs[1].legend(handles=[Patch(facecolor=blue, label='켬'), Patch(facecolor=orange, label='끔'), *handles], frameon=False)
fig.text(.5, -.02, '각 회차 30초 관찰 · 기동 시간 비교 미실시 · 소표본이며 조건의 동등성을 입증한 결과는 아님', ha='center', fontsize=10)
fig.tight_layout()
finish(fig, 'c6_costmap_comparison.png')

# C6-B rows preserve the actual test context and extract both latencies.
section = text.split('### C6-B 세 대 이동',1)[1].split('### C6-C',1)[0]
latencies=[]
for line in section.splitlines():
    if 'odom 정지' in line:
        m = re.search(r'`cmd_vel` 0까지 \+(\d+\.\d+)초, odom 정지 \+(\d+\.\d+)초', line)
        assert m, line
        latencies.append(tuple(map(float,m.groups())))
assert len(latencies)==3
fig, ax = plt.subplots(figsize=(9,4.3))
for j, label, color in [(0,'cmd_vel 0까지',blue),(1,'odom 정지까지',orange)]:
    bars=ax.bar([i+(-.18 if j==0 else .18) for i in range(3)], [v[j] for v in latencies], width=.34, label=label,color=color)
    ax.bar_label(bars, fmt='%.2f', padding=3)
ax.set(xticks=range(3),xticklabels=['pinky2 단독 주행','pinky3 단독 주행','동시 주행 중 pinky2'],ylabel='비상 정지 명령 후 시간 (초)',ylim=(0,.52),title='C6-B 비상 정지 응답 실측')
ax.legend(frameon=False)
fig.text(.5,-.01,'서로 다른 주행 조건의 단일 측정값 · 모든 조건에서의 정지 시간 상한을 뜻하지 않음',ha='center',fontsize=10)
fig.tight_layout(); finish(fig,'c6_estop_latency.png')

section=text.split('### C8-A CPU 재측정',1)[1].split('### C8-B',1)[0]
data={}
for line in section.splitlines():
    c=[v.strip() for v in line.strip('|').split('|')]
    if c and re.fullmatch(r'C[78] r[12] pinky[12]',c[0]):
        data[c[0]]=tuple(map(float,c[1].split('/')))
assert len(data)==8
fig,ax=plt.subplots(figsize=(10,4.5))
labels=['r1 pinky1','r1 pinky2','r2 pinky1','r2 pinky2']
for phase,offset,color in [('C7',-.18,blue),('C8',.18,orange)]:
    values=[data[phase+' '+s] for s in labels]
    means=[sum(v)/len(v) for v in values]
    bars=ax.bar([i+offset for i in range(4)],means,width=.34,color=color,label=phase+(' 수정 전' if phase=='C7' else ' 수정 후'))
    ax.bar_label(bars,fmt='%.1f',padding=4)
ax.set(xticks=range(4),xticklabels=labels,ylabel='메인 스레드 CPU (%) · 코어 하나 기준',ylim=(0,70),title='T-41 수정 전후 mobile_controller 메인 스레드')
ax.legend(frameon=False)
fig.text(.5,-.02,'막대: 5초 간격 두 측정값의 산술평균 · 두 대 충전 중 정지 · 측정 시각·온도 차이 있음',ha='center',fontsize=10)
fig.tight_layout();finish(fig,'c8_cpu_before_after.png')
print('Rendered 3 figures from Markdown measurements.')
