"""Rebuild J5 hold-temperature chart from original logs; no measurement edits."""
from pathlib import Path
import ast
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from chart_style import setup, polish

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'runs/20261120_10_serving_arm_rest_pose'
OUT = ROOT / 'docs/images/2026-11-20/serving_arm_j5_temperature.png'
rows = {}
for name in ['j5_hold_74.log', 'j5_hold_candidates.log']:
    for line in (DATA / name).read_text().splitlines():
        m = re.match(r'HOLD j5=(-?\d+) t=(\d+) temps=(\[[^]]+\])', line)
        if m:
            angle, second = int(m[1]), int(m[2])
            rows.setdefault(angle, []).append((second, ast.literal_eval(m[3])[4]))
expected = {74:(255,61,68),45:(300,53,57),0:(300,50,41),-45:(300,42,53),-90:(300,50,53)}
for a,(end,start_temp,end_temp) in expected.items():
    assert rows[a][0] == (0,start_temp) and rows[a][-1] == (end,end_temp)
setup()
fig,(ax,bx) = plt.subplots(1,2,figsize=(13,6),gridspec_kw={'width_ratios':[1.6,1]})
colors = {74:'#D95A4E',45:'#E5A13B',0:'#2C9B8F',-45:'#7C6BB2',-90:'#287DAB'}
for a in expected:
    pts=rows[a]
    ax.plot([t/60 for t,v in pts],[v for t,v in pts],lw=2.5,color=colors[a],label=f'J5 {a}° · {pts[0][1]} → {pts[-1][1]}°C')
ax.axhline(68,color='#D95A4E',lw=1,ls='--')
ax.text(.12,68.6,'試験'.replace('試験','시험 중단 기준 68°C'),color=colors[74],fontsize=9)
ax.annotate('74°: 4분 15초에 중단',xy=(4.25,68),xytext=(2.4,64),fontsize=10,color=colors[74],arrowprops={'arrowstyle':'->','color':colors[74]})
ax.set(xlim=(0,5.25),ylim=(38,72),xlabel='유지 시간 (분)',ylabel='J5 서보 보고 온도 (°C)',title='각도별 J5 온도 변화 · 15초 간격 실측')
ax.legend(loc='lower left',ncol=2,fontsize=9)
angles=[74,45,0,-45,-90]
changes=[rows[a][-1][1]-rows[a][0][1] for a in angles]
bars=bx.bar(range(5),changes,color=[colors[a] for a in angles],width=.62)
bx.axhline(0,color='#8895A7',lw=1)
for i,(bar,delta) in enumerate(zip(bars,changes)):
    bx.text(i,delta+(0.6 if delta>=0 else -0.6),f'{delta:+d}°C',ha='center',va='bottom' if delta>=0 else 'top',fontweight='bold',fontsize=12)
bx.set(xticks=range(5),xticklabels=[f'{a}°' for a in angles],ylim=(-13,15),xlabel='J5 목표 각도',ylabel='종료 − 시작 온도 (°C)',title='각 시험의 온도 변화량')
fig.suptitle('서빙 팔 접은 자세 | J5 각도별 유지 발열',x=.055,ha='left',fontsize=19,fontweight='bold')
fig.text(.055,.045,'시작 온도·시험 순서가 다름: 각도만의 효과로 단정하지 않음 · 74°는 255초, 나머지는 300초 · 평균값 아님',fontsize=10)
fig.text(.055,.012,'원자료: j5_hold_74.log / j5_hold_candidates.log · J1~J4·J6 목표 고정 · 빈손·평평한 테이블 위의 실물 팔',fontsize=9,color='#61758B')
fig.tight_layout(rect=(.02,.09,.99,.92),w_pad=3)
polish(fig)
OUT.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(OUT,dpi=180,bbox_inches='tight')
print(OUT)
