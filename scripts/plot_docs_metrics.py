"""Rebuild additional documented figures: PYTHONNOUSERSITE=1 python3 scripts/plot_docs_metrics.py."""
from pathlib import Path
import re
from statistics import median
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from chart_style import setup, polish, BLUE, ORANGE, TEAL
setup()
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'docs'; OUT=D/'images/2026-11-19'
T=(D/'2026-11-19_REAL_TEST.md').read_text()

def table(text):
    return [[x.strip() for x in s.strip('|').split('|')] for s in text.splitlines() if s.startswith('|')]
def section(start,end=None):
    s=T.split(start,1)[1]
    return s.split(end,1)[0] if end else s

def grouped(ax,labels,series,title,unit,fmt='%.1f',headroom=1.4):
    n=len(series);width=.76/n;allvals=[]
    for j,(name,vals,color) in enumerate(series):
        allvals+=vals
        bars=ax.bar([i+(j-(n-1)/2)*width for i in range(len(labels))],vals,width*.88,color=color,label=name,zorder=3)
        ax.bar_label(bars,fmt=fmt,padding=4,fontsize=9)
    ax.set(xticks=range(len(labels)),xticklabels=labels,title=title,ylabel=unit,ylim=(0,max(allvals+[.1])*headroom))
    ax.legend(loc='upper right')

def save(fig,name,title,note):
    fig.suptitle(title,fontsize=18,fontweight='bold',x=.055,ha='left',y=.99)
    fig.text(.055,.015,note,fontsize=9,color='#61758B')
    fig.tight_layout(rect=(.02,.06,.99,.93),w_pad=3,h_pad=3)
    polish(fig);fig.savefig(OUT/name,dpi=180,bbox_inches='tight');plt.close(fig)

# Previous day's exact robot-level data, one plot per run; B5 only has first-online value and is excluded.
s=(D/'2026-11-18_REAL_TEST.md').read_text().split('### B6.',1)[1]
boot={};run=''
for c in table(s):
    if len(c)!=8:continue
    if c[0].startswith(('B2','B6-1','B6-2','B6-4')):run=c[0].split()[0]
    if c[0].startswith('B5'):run='B5'
    if c[2] in ['pinky1','pinky2','pinky3'] and run!='B5' and re.fullmatch(r'\d+(\.\d+)?',c[5]):boot.setdefault(run,[]).append(float(c[5]))
assert all(len(boot[k])==3 for k in ['B2','B6-1','B6-2','B6-4'])
fig,axs=plt.subplots(1,2,figsize=(12,4.8))
for ax,runs,title in [(axs[0],['B6-1','B6-2'],'RViz 끔 · 2회'),(axs[1],['B2','B6-4'],'RViz 켬 · 2회')]:
    grouped(ax,runs,[(f'pinky{i+1}',[boot[r][i] for r in runs],c) for i,c in enumerate([BLUE,ORANGE,TEAL])],title,'t_online (초)',headroom=1.3)
    ax.set_ylim(0,235)
save(fig,'boot_rviz_1118.png','관제 연결 시간 | RViz 켬·끔의 실행별 실측','11월 18일 · 같은 세 대 · 각 실행의 로봇별 값 · B5는 첫 대 값만 있어 그래프에서 제외 · 반복/순서 효과 통제 안 됨')

# C4 valid repeated delayed-start observations only.
rows=[c for c in table(section('## C4 재시험','### C4-2 이동')) if c[0].startswith(('C4-1b','C4-2 ' ,'C4-2b'))]
assert len(rows)==3
counts=[];longest=[]
for c in rows:
    m=re.search(r'(\d+)건.*?(\d+\.\d+)초',c[-1]);assert m;counts.append(int(m[1]));longest.append(float(m[2]))
fig,axs=plt.subplots(1,2,figsize=(11,4.8));labels=['C4-1b','C4-2','C4-2b']
grouped(axs[0],labels,[('RViz 시작 뒤 60초',counts,BLUE)],'끊김 건수','건',fmt='%.0f')
grouped(axs[1],labels,[('회차별 최장',longest,ORANGE)],'최장 끊김','초')
axs[1].axhline(2,ls='--',color='#9BA8B5',lw=1)
save(fig,'c4_delayed_start.png','지연 시작만으로는 끊김을 해결하지 못함','세 대 · 무효 C4-1a 제외 · C4-2b는 자동 홈 주행 포함 · 기본 rviz_wait=false 복귀 근거')

# C5: keep retries separate, baseline 60 s is not compared as a 30 s rate.
rows=[c for c in table(section('## C5 어느 구독','### pinky3 CPU')) if len(c)==4 and re.fullmatch(r'\d+',c[1]) and c[0].startswith('P')]
labels=['P1 TF','P2 전역','P3 지역','P4 중계','P5 RViz\n맵 표시 끔','P6 RViz\n전체','P7 중계\n+ RViz','P3 재측정','P4 재측정','P7 재측정']
assert len(rows)==10
fig,axs=plt.subplots(2,1,figsize=(13,8))
grouped(axs[0],labels,[('유효 회차',list(map(lambda c:int(c[1]),rows)),BLUE)],'관찰 30초 동안 끊김 건수','건',fmt='%.0f')
grouped(axs[1],labels,[('유효 회차',list(map(lambda c:float(c[2]),rows)),ORANGE)],'각 회차 최장 끊김','초')
axs[1].axhline(2,color='#8999AA',ls='--',lw=1)
save(fig,'c5_subscriptions.png','구독을 붙이는 순간 | 조건별 차이와 재측정 변동','세 대 · 초기 P5~P7 무효값 제외 · 비교 구간 60초는 0건 · 동일 조건의 재측정도 결과가 달라 단일 원인 확정 불가')

# C6-A actual process percentages, compare same robot at two sampling times.
rows=[c for c in table(section('### C6-A 로봇 CPU','### C6-B 세 대 이동')) if len(c)==6 and c[1]=='pinky1']
assert len(rows)==2
names=['mobile_controll','sllidar_node','pinky_driver','joint_state_pub']
vals=[[float(re.search(r'\b'+n+r' ([\d.]+)',c[4])[1]) for n in names] for c in rows]
fig,ax=plt.subplots(figsize=(11,4.8))
grouped(ax,['mobile_controller','sllidar_node','pinky_driver','joint_state_publisher'],[('RViz 붙이기 전',vals[0],BLUE),('RViz 정상 상태',vals[1],ORANGE)],'pinky1 프로세스별 CPU','CPU % · 코어 하나 기준')
save(fig,'c6_process_cpu.png','로봇 CPU는 어디에 쓰였나','C6-A top 세 번째 화면 · 정지 상태의 시점별 값 · 전체 시스템 CPU %와 합산하지 않음 · 다른 두 대는 원본 표 참고')

# C8 attachment gaps, do not claim proven improvement when both already <2s.
rows=[c for c in table(section('### C8-B 붙는 순간','### C8-C 동작 확인')) if len(c)==7 and c[0].startswith('수정')]
assert len(rows)==12
series={}
for phase in ['수정 전','수정 뒤']:
    sub=[c for c in rows if c[0].startswith(phase)]
    series[phase]=([sum(int(c[2]) for c in sub if c[0].endswith('a'+str(i))) for i in range(1,4)], [max(float(c[3]) for c in sub if c[0].endswith('a'+str(i))) for i in range(1,4)])
fig,axs=plt.subplots(1,2,figsize=(11,4.8))
for idx,ax in enumerate(axs):
    grouped(ax,['a1','a2','a3'],[(phase,series[phase][idx],col) for phase,col in [('수정 전',BLUE),('수정 뒤',ORANGE)]],['두 대 합계 끊김 건수','두 대 중 최장 끊김'][idx],['건','초'][idx],fmt=['%.0f','%.1f'][idx])
save(fig,'c8_attach_comparison.png','T-41 | CPU는 줄었지만 끊김 개선 여부는 미확정','동일 두 대 조건 · 각 30초 × 3회 · 수정 전후 모두 2초 초과 0건 · 0.0초는 원문 반올림 값이며 건수에는 포함')

# E map quality derived only from 24 admitted measurements.
rows=[c for c in table(T) if len(c)==14 and re.fullmatch(r'M000[1-6]',c[2]) and c[1] in ['v03','v04']]
assert len(rows)==24
fig,axs=plt.subplots(1,3,figsize=(15,5))
for ax,col,title,unit,mult in [(axs[0],9,'제자리 회전 비율','%',100),(axs[1],10,'정지 비율','%',100),(axs[2],13,'도착 위치 오차','cm',1)]:
    series=[]
    for m,color in [('v03',BLUE),('v04',ORANGE)]:
        vals=[median(float(c[col].removesuffix('cm'))*mult for c in rows if c[1]==m and c[3]==dest) for dest in ['C3','A1','W1']]
        series.append((m,vals,color))
    grouped(ax,['W1→C3','C3→A1','A1→W1'],series,title+' · 중앙값',unit)
save(fig,'map_quality.png','지도 비교 | 시간 외에 확인할 주행 품질','지도별·이동별 4회 중앙값 · wobble_metrics의 spin_ratio 사용(별도 bag 분석 회전 비율과 다를 수 있음) · 시작 자세 차이 있음')

# Simulation results from W10 corrected table, never label as real robot outcomes.
s=(D/'2026-11-18_IMPROVEMENT_PLAN.md').read_text();sim={}
for c in table(s):
    if len(c)==9 and c[0] in ['normal','rush','bottleneck','moves2','moves3'] and c[1] in ['실측·흔들림0·지금 값','실측·흔들림0·보정']:
        sim[(c[0],c[1])]=[float(c[3]),float(c[4]),float(c[8])]
assert len(sim)==10
fig,axs=plt.subplots(3,1,figsize=(12,10))
labels=['normal','rush','bottleneck','moves2','moves3']
for i,ax in enumerate(axs):
    grouped(ax,labels,[(label,[sim[(w,cond)][i] for w in labels],col) for label,cond,col in [('기존 계획','실측·흔들림0·지금 값',BLUE),('보정 후보','실측·흔들림0·보정',ORANGE)]],['전체 소요 중앙값','점유 대기 중앙값','실제 소요 / 계획 ETA 중앙값'][i],['초','초','배'][i],fmt=['%.0f','%.1f','%.2f'][i])
    if i==2:ax.axhline(1,color=TEAL,ls='--',lw=1.2);ax.text(4.45,1.03,'이상적 비율 1.0',ha='right',color=TEAL,fontsize=9)
save(fig,'simulation_calibration.png','모의 실험 | ETA 보정이 전체 속도 개선을 보장하지는 않음','W10 정정 표 · 실측 시간 모델 / 흔들림 0 / 조건별 씨앗 30개 · 보정 0.135m/s + 구간당 2.27초 · 실기기 결과 아님')
print('Generated 7 additional figures from source Markdown tables.')
# PC reproduction min/max ranges: do not invent means or standard deviations.
s=(D/'2026-11-19_BRINGUP_RVIZ_PLAN.md').read_text().split('### 4.11',1)[1].split('### 4.12',1)[0]
rows=[c for c in table(s) if len(c)==3 and c[0].startswith(('지금 코드','기본 QoS','위 +'))]
assert len(rows)==3
labels=['기존 코드 · 5회','QoS 이벤트 끔 · 3회','추가 노드 분리 · 1회']
fig,axs=plt.subplots(1,2,figsize=(12,5))
for ax,col,title in [(axs[0],1,'메인 스레드'),(axs[1],2,'프로세스 합')]:
    for i,c in enumerate(rows):
        nums=[float(x) for x in re.findall(r'\d+\.\d+',c[col])];lo,hi=min(nums),max(nums)
        if lo==hi:ax.vlines(lo,i-.18,i+.18,color=TEAL,lw=4)
        else:ax.barh(i,hi-lo,left=lo,height=.4,color=[BLUE,ORANGE,TEAL][i])
        label=f'{lo:.1f}–{hi:.1f}%' if lo!=hi else f'{lo:.1f}%'
        ax.text(hi+.5,i,label,va='center',fontsize=10)
    ax.set(yticks=range(3),yticklabels=labels,xlim=(0,43),title=title,xlabel='CPU % · 코어 하나 기준')
    ax.invert_yaxis()
    ax.legend(handles=[Patch(color=BLUE,label='기존 코드'),Patch(color=ORANGE,label='QoS 끔'),Patch(color=TEAL,label='추가 분리')],loc='lower right',fontsize=8)
save(fig,'pc_qos_ranges.png','PC 재현 | QoS 이벤트 처리 비용을 분리해서 확인','도메인 75 · 가짜 입력 · 띠는 관찰 최솟값–최댓값(평균·신뢰구간 아님) · 1회 조건은 세로선 · Pi 실측과 직접 비교 금지')

# Historical logic simulation: distances do not prove real-world travel times.
s=(D/'2026-11-16_CHANGES.md').read_text()
rows=[c for c in table(s) if len(c)==3 and c[0].startswith(('pinky2(B6','pinky2(A8','pinky1(B1'))]
assert len(rows)==3
pairs=[]
for c in rows:
    a=re.findall(r'(\d+\.\d+) m',c[1]);b=re.findall(r'(\d+\.\d+) m',c[2]);assert a and b;pairs.append((float(a[0]),float(b[0])))
fig,ax=plt.subplots(figsize=(11,5))
grouped(ax,['정지 로봇 비켜주기\nB6→B1','정지 로봇 비켜주기\nA8→A1','마주 오는 로봇 대기\nB1→B7'],[('수정 전',[v[0] for v in pairs],BLUE),('수정 후',[v[1] for v in pairs],ORANGE)],'계획 경로 길이','m',fmt='%.2f')
save(fig,'yield_paths_1116.png','양보 로직 | 돌아가는 거리 감소를 모의로 확인','11월 16일 · test_map_v001 / 두 대 모의 시험 · 세 번째 경우 도착은 5.7초 늦음 · 짧은 경로가 빠른 도착을 뜻하지 않음')
print('Generated PC range and historical path figures.')
# Final post-change E-stop measurements, separated from earlier conditions.
s=section('### C8-C 동작 확인','### 판정')
values=[]
for line in s.splitlines():
    if '`cmd_vel` 0까지' in line:
        m=re.search(r'`cmd_vel` 0까지 \+([\d.]+)초, odom 정지 \+([\d.]+)초',line);assert m;values.append(tuple(map(float,m.groups())))
assert len(values)==2
fig,ax=plt.subplots(figsize=(10,5))
grouped(ax,['pinky2 · 제자리 회전 중','pinky1 · 동시 주행 중'],[('cmd_vel 0까지',[v[0] for v in values],BLUE),('odom 정지까지',[v[1] for v in values],ORANGE)],'수정 후 비상 정지 응답','초',fmt='%.3f')
save(fig,'c8_estop_latency.png','최종 동작 확인 | 대상 로봇 정지와 다른 로봇 주행 지속','C8-C · 단일 실측 · 회전 / 0.08m/s 주행의 서로 다른 조건 · 모든 환경의 정지 시간 상한을 뜻하지 않음')
