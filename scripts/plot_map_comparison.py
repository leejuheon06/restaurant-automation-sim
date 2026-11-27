"""Plot measured v03/v04 comparison: PYTHONNOUSERSITE=1 python3 scripts/plot_map_comparison.py."""
from pathlib import Path
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/2026-11-19_MAP_COMPARE_PLAN.md'
OUT=ROOT/'docs/images/2026-11-19'
text=DOC.read_text().split('## 4.5 결과',1)[1]
font=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
from chart_style import setup, polish
setup()
colors=['#277DA1','#E88D34']
rows={}
for line in text.splitlines():
    c=[x.strip() for x in line.strip('|').split('|')]
    if len(c)==10 and c[1] in ('v03','v04'):
        rows[(c[0],c[1])]=[float(x.replace(',','')) for x in c[2:]]
assert len(rows)==6
routes=['W1 → C3','C3 → A1','A1 → W1']

def bars(ax,labels,a,b,title,unit,fmt='%.1f'):
    for shift,values,color,label in [(-.18,a,colors[0],'v03 · 노드 40개'),(.18,b,colors[1],'v04 · 노드 20개')]:
        rect=ax.bar([i+shift for i in range(len(labels))],values,.34,color=color,label=label)
        ax.bar_label(rect,fmt=fmt,padding=3,fontsize=10)
    ax.set(xticks=range(len(labels)),xticklabels=labels,title=title,ylabel=unit,ylim=(0,max(a+b)*1.45))
    ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    ax.legend(loc='upper right',frameon=False,fontsize=9)

def save(fig,name):
    OUT.mkdir(parents=True,exist_ok=True)
    polish(fig)
    fig.savefig(OUT/name,dpi=180,bbox_inches='tight',facecolor='#F5F8FB');plt.close(fig)

# Read whole-lap means explicitly: do not sum route medians.
match=re.search(r'한 바퀴\(세 이동의 합\) 평균: 소요 ([\d.]+)초 → ([\d.]+)초.*?제자리 회전 ([\d.]+)회 → ([\d.]+)회.*?회전 시간 ([\d.]+)초 → ([\d.]+)초.*?남는 회전량 ([\d,]+)도 → ([\d,]+)도',text)
assert match
vals=[float(x.replace(',','')) for x in match.groups()]
fig,axes=plt.subplots(2,2,figsize=(11,8))
for i,(ax,label,unit) in enumerate(zip(axes.flat,['한 바퀴 소요 시간','제자리 회전 횟수','제자리 회전 시간','남는 회전량'],['초','회','초','도'])):
    a,b=vals[i*2:i*2+2]; reduction=(a-b)/a*100
    bars(ax,['한 바퀴 평균'],[a],[b],f'{label} · v04 {reduction:.0f}% 감소',unit,'%.0f' if i==3 else '%.1f')
fig.suptitle('실측 종합: v04가 더 빠르고 제자리 회전이 적음',fontsize=17)
fig.text(.5,.015,'지도별 4바퀴 평균 · 모든 패널은 낮을수록 좋음 · 실행별 초기 방향·자세 지정 차이 있음',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.04,1,.95)); save(fig,'map_compare_lap.png')

fig,axes=plt.subplots(2,2,figsize=(12,8))
for ax,idx,title,unit in [(axes[0,0],0,'이동별 소요 시간','초'),(axes[0,1],1,'이동별 제자리 회전 횟수','회'),(axes[1,0],6,'노드 근처 조향 뒤집힘','회'),(axes[1,1],7,'통로 중간 조향 뒤집힘','회')]:
    a=[rows[(r,'v03')][idx] for r in routes];b=[rows[(r,'v04')][idx] for r in routes]
    bars(ax,routes,a,b,title+' (중앙값)',unit)
fig.suptitle('구간별 비교: 속도·회전은 개선, 통로 중간 뒤집힘은 증가',fontsize=16)
fig.text(.5,.015,'이동별 각 4회 중앙값 · 개별 측정점 생략 · 뒤집힘 위치 구분은 노드 밀도의 영향도 받음',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.04,1,.95));save(fig,'map_compare_routes.png')
print('2 figures rendered from section 4.5 measured values.')
