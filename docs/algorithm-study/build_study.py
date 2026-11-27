"""Rebuild locally: Python packages markdown, weasyprint; Noto Sans CJK KR font."""
from pathlib import Path
from html import escape
import hashlib
import json
import math
import re
import random
import markdown
from weasyprint import HTML

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
BLUE, TEAL, RED, GOLD, INK = '#2563eb', '#0f8b78', '#d95757', '#d89c27', '#153047'

class SVG:
    def __init__(self):
        self.parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#60788b"/></marker></defs><rect width="900" height="300" rx="16" fill="#f3f7fb"/>']
    def text(self,x,y,s,size=18,color=INK,anchor='middle'):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Noto Sans CJK KR, sans-serif" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(str(s))}</text>')
    def rect(self,x,y,w,h,label='',fill='white',stroke='#cedbe5',size=18):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        if label: self.text(x+w/2,y+h/2+size*.35,label,size)
    def line(self,x1,y1,x2,y2,color='#60788b',width=3,arrow=False,dash=False):
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(' marker-end="url(#arrow)"' if arrow else '')+(' stroke-dasharray="7 5"' if dash else '')+'/>')
    def circle(self,x,y,r,label='',color=BLUE,fill='white'):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{color}" stroke-width="3"/>')
        if label:self.text(x,y+6,label,18,color)
    def path(self,d,color=BLUE,width=4,dash=False):
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="7 5"' if dash else '')+'/>')
    def save(self,name):
        (ASSETS / name).write_text(''.join(self.parts)+'</svg>')

s=SVG()
for x,label,sub in [(25,'작업 배정','누가 맡을까?'),(250,'SIPP 경로 계획','언제 어디로?'),(475,'허가 / 락','지금 가도 될까?'),(700,'구간 주행','어떻게 움직일까?')]:
    s.rect(x,50,175,64,label,stroke=BLUE,size=19);s.text(x+87,143,sub,17)
    if x<700:s.line(x+180,82,x+220,82,arrow=True)
s.rect(140,198,230,54,'위치 추정 · AMCL',stroke=TEAL)
s.rect(530,198,230,54,'마커 검출 · 정밀 도킹',stroke=TEAL)
s.line(255,196,540,151,color=TEAL,arrow=True);s.line(645,196,785,152,color=TEAL,arrow=True)
s.text(450,283,'기본 배정: min_cost_eta_rh  |  기본 계획: sipp  |  주행 방식에 따라 하위 계층 활성',15)
s.save('00_architecture.svg')

s=SVG();s.text(450,32,'노드 B의 예약을 빼면, 남은 연속 구간이 탐색 상태가 된다',19)
for y,name in [(75,'B 점유'),(150,'B 안전')]:s.text(90,y+24,name,18);s.line(170,y+20,830,y+20,arrow=True)
s.rect(390,72,165,42,'타 로봇 예약',fill='#ffe2df',stroke=RED)
s.rect(170,147,220,42,'안전 구간 1',fill='#d9f2eb',stroke=TEAL)
s.rect(555,147,270,42,'안전 구간 2',fill='#d9f2eb',stroke=TEAL)
for x,t in [(170,'0'),(335,'3'),(390,'4'),(555,'7'),(665,'9'),(830,'12초')]:s.text(x,220,t,16)
s.path('M335 252 L555 252 L665 252',BLUE);s.text(445,280,'A에서 대기',17,BLUE);s.text(650,280,'7초 출발 → 9초 B 도착',17,BLUE)
s.save('01_sipp.svg')

s=SVG();s.rect(300,20,300,55,'A와 B가 X에서 충돌',fill='#ffe2df',stroke=RED)
s.line(370,78,225,135,arrow=True);s.line(530,78,675,135,arrow=True)
s.rect(65,143,330,55,'A에게 해당 시간의 X 사용 금지',stroke=BLUE,size=18)
s.rect(505,143,330,55,'B에게 해당 시간의 X 사용 금지',stroke=TEAL,size=18)
s.text(230,230,'SIPP 재탐색 · 합계 18초',18,BLUE);s.text(670,230,'SIPP 재탐색 · 합계 17초',18,TEAL)
s.text(450,278,'비용이 작은 가지부터 검토 · 충돌이 남으면 다시 분기 (교육용 예시)',17)
s.save('02_ccbs.svg')

s=SVG();s.text(450,28,'상태 = (노드, 시간 칸) · 이동 또는 대기',19)
for r,name in enumerate(['A','B','C']):
    s.text(65,80+r*65,name)
    for k in range(10):s.rect(125+k*68,48+r*65,57,49,fill='#ffe2df' if r==1 and k in (3,4,5) else 'white',stroke=RED if r==1 and k in (3,4,5) else '#cedbe5')
for k in range(10):s.text(153+k*68,258,f'{k*.5:g}',15)
s.path('M153 72 L221 72 L289 72 L357 72 L425 72 L493 72 L561 137 L629 202',TEAL)
s.text(760,280,'시간(s) →',17);s.text(365,280,'예약 중에는 A에서 기다림',17,TEAL)
s.save('03_cooperative.svg')

s=SVG();s.line(150,145,750,145,width=14,color='#dae4ed');s.line(450,50,450,245,width=14,color='#dae4ed')
s.line(160,130,720,130,color=BLUE,width=5,arrow=True);s.line(470,235,470,68,color=TEAL,width=5,arrow=True)
s.circle(450,145,28,'X',RED);s.circle(160,145,22,'A');s.circle(450,240,22,'B',TEAL)
s.text(180,60,'A: 자기 최단 경로',19,BLUE);s.text(710,235,'B: 자기 최단 경로',19,TEAL)
s.text(450,283,'시간 협조는 없음 → 실행 중 락으로 대기·양보·재계획',18)
s.save('04_independent.svg')

s=SVG();pts={'S':(130,155),'A':(350,65),'B':(350,235),'G':(720,155)}
for a,b,w in [('S','A',2),('S','B',5),('A','B',1),('A','G',5),('B','G',2)]:
    x,y=pts[a];u,v=pts[b];s.line(x,y,u,v,color=TEAL if (a,b) in [('S','A'),('A','B'),('B','G')] else '#b4c3d0',width=5)
    s.text((x+u)/2+15,(y+v)/2-10,w,20)
for n,(x,y) in pts.items():s.circle(x,y,24,n)
s.text(730,265,'S → A → B → G = 5',20,TEAL);s.save('05_dijkstra.svg')

s=SVG();s.text(450,35,'접수 순서로 처리하고, 선택한 로봇은 후보에서 뺀다',19)
for x,t,sub in [(70,'T1','먼저 접수'),(350,'T2','다음 접수'),(630,'T3','그 다음')]:
    s.rect(x,65,200,60,t,stroke=BLUE);s.text(x+100,155,sub,17)
    if x<630:s.line(x+210,95,x+270,95,arrow=True)
s.rect(70,190,200,60,'가장 가까운 A',stroke=TEAL);s.rect(350,190,200,60,'남은 로봇 중 B',stroke=TEAL);s.rect(630,190,200,60,'남은 로봇 중 C',stroke=TEAL)
s.save('06_fifo.svg')

s=SVG();s.line(100,245,810,245,arrow=True);s.line(100,245,100,45,arrow=True)
s.text(63,40,'점수',17);s.text(807,280,'시간(s)',17)
s.line(100,215,760,65,color=BLUE,width=4);s.text(440,100,'일반 작업: 1 + 0.05 × 대기초',18,BLUE)
s.circle(650,145,7,color=RED,fill=RED);s.text(650,178,'60초에 새 긴급 작업 도착: 3점',17,RED)
s.circle(650,90,7,color=BLUE,fill=BLUE);s.text(680,56,'기존 작업: 4점',17,BLUE)
s.text(450,280,'기다리는 두 작업의 기울기는 같음 · 새 작업과 비교할 때 의미가 드러남',14)
s.save('07_aging.svg')

s=SVG();s.text(450,32,'개별 최선과 전체 최선은 다르다 (비용: 초)',19)
for x,label in [(235,'T1'),(435,'T2')]:s.text(x,85,label)
for y,lab,vals in [(140,'A',[4,5]),(220,'B',[6,100])]:
    s.text(110,y+8,lab)
    for j,val in enumerate(vals):s.rect(150+200*j,y-30,170,60,str(val),fill='#d9f2eb' if (lab=='A' and j==1) or (lab=='B' and j==0) else 'white',stroke=TEAL if (lab=='A' and j==1) or (lab=='B' and j==0) else '#cedbe5')
s.text(700,135,'순서대로: 4 + 100',20,RED);s.text(700,185,'전체 비교: 6 + 5',20,TEAL);s.text(700,230,'합계 104 → 11',22,TEAL)
s.save('08_assignment.svg')

s=SVG();s.text(450,30,'가까워도 예약 대기가 길면 늦는다 (설명용 초)',19)
for y,lab,move,wait in [(80,'A',10,12),(175,'B',14,1)]:
    s.text(65,y+25,lab);s.rect(120,y,move*25,48,f'이동 {move}',fill='#dce8ff',stroke=BLUE)
    s.rect(120+move*25,y,wait*25,48,str(wait),fill='#ffe2df',stroke=RED,size=17)
    s.text(155+(move+wait)*25,y+29,f'합 {move+wait}',19)
s.rect(160,253,22,22,fill='#dce8ff',stroke=BLUE);s.text(242,271,'이동',16)
s.rect(330,253,22,22,fill='#ffe2df',stroke=RED);s.text(425,271,'예약 대기',16)
s.text(680,271,'ETA 비용은 B가 유리',17,TEAL);s.save('09_eta.svg')

s=SVG();s.line(70,100,835,100,arrow=True)
for x,t in [(100,'0초'),(280,'2초'),(460,'4초'),(640,'6초'),(820,'8초')]:s.circle(x,100,7,color=BLUE,fill=BLUE);s.text(x,65,t,18)
s.rect(65,145,510,55,'배정 후 6초 안정화 · 매 2초 재평가',stroke=BLUE)
s.rect(595,145,250,55,'조건 충족 → 변경 가능',stroke=TEAL,size=17)
s.text(450,243,'이득 > 5초 · 최대 2회 · 첫 단계 · 미적재 · 로봇 정상',19)
s.text(450,280,'작은 예측 변화마다 작업이 오가는 현상을 제한',17,TEAL);s.save('10_rolling.svg')

s=SVG()
for r in range(7):
    for c in range(14):
        blocked=c in (6,7) and r in (1,2,3,4)
        near=not blocked and c in (5,6,7,8) and r in (0,1,2,3,4,5)
        s.rect(60+c*38,25+r*35,34,31,fill=INK if blocked else '#f6dca0' if near else 'white',stroke='#d5dfe6')
s.path('M115 147 L191 77 L267 42 L381 42 L495 112',BLUE,5)
s.circle(115,147,11,'',BLUE);s.circle(495,112,11,'',TEAL)
s.text(740,80,'검정: 장애물',19);s.text(740,130,'노랑: 주변 비용',19,GOLD);s.text(740,180,'파랑: 구간 경로',19,BLUE)
s.text(450,286,'교육용 격자 · 실제 Frybot 지도를 재현한 그림은 아님',16);s.save('11_navfn.svg')

s=SVG();s.line(110,235,480,235,arrow=True);s.text(490,239,'로봇 x축',16)
s.rect(105,210,70,48,'로봇',stroke=BLUE,size=16)
s.path('M140 235 C260 235 310 100 580 82',TEAL,5)
s.circle(385,132,10,'',RED,RED);s.line(150,230,385,132,dash=True)
s.line(385,132,385,235,dash=True);s.text(265,156,'L',20);s.text(420,195,'yL',20)
s.text(710,105,'곡률 κ = 2yL / L²',23,BLUE);s.text(710,160,'각속도 ω = vκ',23,BLUE)
s.text(685,230,'RPP: 곡률·충돌·접근 감속',17)
s.text(450,285,'앞쪽 경로 목표점(carrot)을 매 제어 주기 갱신',17);s.save('12_rpp.svg')

s=SVG();rng=random.Random(7)
for x,label,tight in [(225,'관측 전: 여러 위치 가설',False),(675,'관측 후: 유력한 위치에 집중',True)]:
    s.rect(x-175,40,350,200,stroke='#94a9b9')
    for i in range(70):
        px=x+(rng.gauss(0,28) if tight else rng.uniform(-150,150));py=140+(rng.gauss(0,22) if tight else rng.uniform(-75,75))
        s.circle(round(px,1),round(py,1),2.5,color=TEAL if tight else BLUE,fill=TEAL if tight else BLUE)
    s.text(x,278,label,18)
s.line(420,140,480,140,arrow=True);s.save('13_amcl.svg')

s=SVG();s.rect(45,80,160,125,'카메라',stroke=BLUE,size=22)
s.path('M205 95 L420 60 L420 225 L205 190',BLUE,2)
s.rect(360,95,76,76,fill='white',stroke=INK)
for r in range(4):
    for c in range(4):
        if (r+c)%3!=0:s.rect(370+c*14,105+r*14,12,12,fill=INK,stroke=INK)
s.text(400,252,'알려진 크기 / 네 꼭짓점',17)
s.line(465,140,535,140,arrow=True)
for y,txt in [(40,'PnP: 카메라 → 마커 R,t'),(115,'장착 TF + 마커-도크 오프셋'),(190,'odom 기준 도킹 목표 자세')]:s.rect(550,y,320,55,txt,stroke=TEAL,size=17)
s.text(450,285,'마커 모양은 교육용 예시이며 실제 인쇄·검출용 ID가 아님',15);s.save('14_aruco.svg')

s=SVG();s.rect(735,35,40,205,fill=INK,stroke=INK);s.text(755,275,'벽 / 도크',17)
s.circle(690,145,10,color=TEAL,fill=TEAL);s.text(670,65,'목표 자세',18,TEAL)
s.path('M110 220 C320 220 350 85 540 125 S650 145 690 145',BLUE,5)
s.rect(75,197,95,48,'로봇',stroke=BLUE);s.line(600,145,690,145,color=TEAL,arrow=True)
s.line(570,50,570,240,dash=True);s.text(420,65,'자세를 정렬하며 접근',19,BLUE)
s.text(450,285,'일반 구간 이동 → 목표 검출 → 정밀 접근 → 완료 조건 확인',17)
s.save('15_docking.svg')

s=SVG();s.rect(30,100,210,75,'Frybot Python',stroke=BLUE,size=21)
s.line(250,138,325,138,arrow=True);s.rect(335,100,200,75,'C++ helper',stroke=TEAL,size=21)
s.line(545,138,615,138,arrow=True)
for y,lab in [(30,'rmf_traffic · 계획'),(110,'Negotiation · 협상'),(190,'rmf_task · 작업 대기열')]:s.rect(625,y,245,58,lab,stroke=TEAL,size=17)
s.text(450,275,'로드맵 / 상태 → 프로토콜 변환 → 라이브러리 → Step / 배정 결과',17)
s.save('16_rmf.svg')

s=SVG();s.line(100,140,825,140,arrow=True,width=4)
s.rect(100,175,580,45,'UNDERCOOKED',fill='#ffe2df',stroke=RED)
s.rect(680,175,140,45,'DONE',fill='#d9f2eb',stroke=TEAL)
s.line(680,65,680,225,color=BLUE,width=3);s.text(680,48,'임계값 0.9',20,BLUE)
s.text(100,115,'0',18);s.text(820,115,'1.0',18)
s.circle(666,140,7,color=RED,fill=RED);s.circle(695,140,7,color=TEAL,fill=TEAL)
s.text(440,265,'입력은 모의 golden_ratio · 영상 인식 네트워크가 아님',19)
s.save('17_threshold.svg')

md = (ROOT/'study.md').read_text().replace('時間格子','시간 격자').replace('時刻なし','시각 없음')
(ROOT/'study.md').write_text(md)
chunks = [c.strip() for c in md.split('<!-- PAGE -->') if c.strip()]
css='''
@font-face {font-family: Study; src: local("Noto Sans CJK KR");}
@page {size:A4; margin:17mm 17mm 18mm; @top-left{content:"FRYBOT  /  ALGORITHM STUDY";font-family:Study,sans-serif;font-size:8pt;color:#718399;} @bottom-left{content:"코드·문헌 기준 2026-11-19  |  교육용 도식";font-family:Study,sans-serif;font-size:7.5pt;color:#718399;} @bottom-right{content:counter(page);font-family:Study,sans-serif;font-size:9pt;color:#153047;}}
*{box-sizing:border-box}body{font-family:Study,"Noto Sans CJK KR",sans-serif;color:#23374b;font-size:10pt;line-height:1.66;margin:0} .sheet{break-before:page;} .sheet:first-child{break-before:auto}h1{font-size:23pt;line-height:1.3;color:#153047;margin:0 0 5mm;letter-spacing:-.6pt;bookmark-level:1}h2{font-size:14pt;line-height:1.4;font-weight:500;color:#0f8b78;margin:0 0 6mm;bookmark-level:2}p{margin:0 0 3.5mm}strong{font-weight:700;color:#153047}a{color:#2563eb;text-decoration:none;overflow-wrap:anywhere}blockquote{border-left:3px solid #0f8b78;background:#f0f7f6;padding:3mm 4mm;margin:4mm 0;font-size:9.3pt}blockquote p:last-child{margin:0}table{border-collapse:collapse;width:100%;margin:4mm 0;font-size:8.4pt;line-height:1.5;table-layout:auto}th{background:#153047;color:white;text-align:left;font-weight:500}th,td{padding:2mm 2.2mm;border-bottom:1px solid #d8e1e9;vertical-align:top;overflow-wrap:anywhere}tr:nth-child(even) td{background:#f3f7fb}tr{break-inside:avoid}thead{display:table-header-group}code{font-family:Study,sans-serif;font-size:.92em;background:#edf2f7;padding:0 .12em;overflow-wrap:anywhere}img{width:100%;height:auto;display:block;margin:4mm 0 2mm}ul,ol{padding-left:5mm;margin:3mm 0}li{margin-bottom:2.6mm}h1,h2{break-after:avoid} .figcaption{text-align:center;color:#6c7e90;font-size:8pt;margin-top:-1mm;margin-bottom:4mm} .reference{font-size:9pt;line-height:1.55}.reference li{margin-bottom:3mm}.codeindex table{font-size:7.3pt} .cover h1{font-size:31pt;margin-top:14mm}.cover h2{font-size:20pt;margin-bottom:10mm}.toc table{font-size:8.1pt} .sheet{position:relative}
@media screen {body{background:#e8edf2}.sheet{background:white;width:210mm;min-height:297mm;padding:17mm;margin:22px auto;box-shadow:0 8px 30px #15304720} } 
'''
sections=[]
figure_no=0
for i,c in enumerate(chunks):
    content=markdown.markdown(c,extensions=['tables','fenced_code'])
    content=re.sub(r'<h1>(.*?)</h1>',lambda m:f'<h1 id="page-{i+1}">{m[1]}</h1>',content,count=1)
    def embed(m):
        global figure_no
        figure_no += 1
        src=m[1];alt=m[2]
        data=(ROOT/src).read_bytes()
        import base64
        return '<img alt="'+escape(alt)+'" src="data:image/svg+xml;base64,'+base64.b64encode(data).decode()+'"/><p class="figcaption">그림 '+str(figure_no)+'. '+escape(alt)+' · 자체 제작 교육용 도식</p>'
    content=re.sub(r'<img alt="([^"]*)" src="([^"]*)"\s*/?>',lambda m:embed([None,m[2],m[1]]),content)
    # Link the table of contents to the chapter's first page.
    if i==1:
        for n in range(1,18):content=content.replace(f'<td>{n:02}</td>',f'<td><a href="#page-{4+(n-1)*2}">{n:02}</a></td>',1)
    klass='cover' if i==0 else 'toc' if i==1 else 'reference' if c.startswith('# 참고문헌') else 'codeindex' if c.startswith('# 코드 근거') else ''
    sections.append(f'<section class="sheet {klass}" data-sheet="{i+1}">{content}</section>')
html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Frybot 알고리즘 학습 노트</title><style>'+css+'</style></head><body>'+''.join(sections)+'</body></html>'
(ROOT/'Frybot_Algorithms_Study.html').write_text(html)
doc=HTML(string=html,base_url=str(ROOT)).render()
out=ROOT/'output/pdf/Frybot_Algorithms_Study.pdf'
out.parent.mkdir(parents=True,exist_ok=True)
doc.write_pdf(out)
page_sheets=[]
for p in doc.pages:
    found=set()
    for b in p._page_box.descendants():
        if b.element is not None and b.element.get('data-sheet'):found.add(int(b.element.get('data-sheet')))
    page_sheets.append(sorted(found))
(ROOT/'layout_check.json').write_text(json.dumps({'source_sheets':len(chunks),'pdf_pages':len(doc.pages),'page_sheets':page_sheets},indent=2))

base=ROOT.parents[1]/'src/frybot'
files=['frybot_control/frybot_control/fleet_core.py','frybot_bringup/launch/sim.launch.py','frybot_bringup/launch/real.launch.py','frybot_control/frybot_control/planners/__init__.py','frybot_control/frybot_control/planners/sipp.py','frybot_control/frybot_control/planners/base.py','frybot_control/frybot_control/layout.py','frybot_control/frybot_control/planners/cbs.py','frybot_control/frybot_control/planners/cooperative_astar.py','frybot_control/frybot_control/planners/independent_astar.py','frybot_mobile/frybot_mobile/navigator.py','frybot_control/frybot_control/schedulers/__init__.py','frybot_mobile/config/nav2_store.yaml','frybot_mobile/frybot_mobile/mobile_controller.py','frybot_mobile/frybot_mobile/aruco_dock_detector.py','frybot_control/frybot_control/planners/rmf.py','frybot_control/frybot_control/schedulers/rmf_task.py','frybot_control/rmf_bridge/rmf_plan_server.cpp','frybot_sim/frybot_sim/ai_server.py']
snapshot={'date':'2026-11-19','git_head':'4ab5d33','worktree':'dirty; existing changes retained','files':[]}
for f in files:
    p=base/f;data=p.read_bytes();symbols=[]
    for n,l in enumerate(data.decode().splitlines(),1):
        if re.match(r'\s*(class |def )',l):symbols.append({'line':n,'symbol':l.strip()})
    snapshot['files'].append({'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'symbols':symbols})
(ROOT/'source_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
print(json.dumps({'sheets':len(chunks),'pdf_pages':len(doc.pages),'pdf':str(out),'page_sheets':page_sheets},ensure_ascii=False))
