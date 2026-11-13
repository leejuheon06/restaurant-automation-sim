// Shared helpers + store map drawing for all FryBot pages.
const API = window.FRYBOT_API || '';
async function getJSON(p){const r=await fetch(API+p);return r.json()}
async function postJSON(p,b){const r=await fetch(p.startsWith('http')?p:API+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()}
const TAG={AVAILABLE:'t-ok',IDLE:'t-ok',STANDBY:'t-ok',CHARGING:'t-ok',DONE:'t-ok',COMPLETED:'t-ok',DELIVERED:'t-ok',SEATED:'t-blue',IN_USE:'t-blue',IN_PROGRESS:'t-blue',
 ASSIGNED:'t-warn',PENDING:'t-warn',COLLECTING:'t-warn',VACANT_CHECK:'t-warn',ON_HOLD:'t-bad',SUSPENDED:'t-bad',E_STOP:'t-bad',GUIDE_FAILED:'t-bad',REJECTED:'t-bad',CANCELED:'t-bad'};
const tag=s=>`<span class="tag ${TAG[s]||'t-blue'}">${s}</span>`;
const KO={ASSIGNED:'테이블 배정',GUIDING:'안내 중',SEATED:'착석',LEFT:'이용 종료',REJECTED:'안내 불가',GUIDE_FAILED:'동행 실패',CANCELED:'취소',
 QUEUED:'조리 대기',COOKING:'조리 중',READY:'서빙 대기',SERVING:'서빙 중',DELIVERED:'전달 완료',ON_HOLD:'보류',ORDERED:'접수',COMPLETED:'전달 완료',
 AVAILABLE:'이용 가능',IN_USE:'이용 중',COLLECTING:'식기 회수 중',VACANT_CHECK:'빈자리 확인 중'};
const ko=s=>KO[s]||s;
const RCB=['#16a34a','#ea580c','#9333ea','#0284c7','#db2777','#ca8a04','#0d9488'];
const RC=new Proxy({},{get:(_,id)=>{const n=parseInt(String(id).replace(/\D/g,''))||1;return RCB[(n-1)%RCB.length];}});
const GC=['#dc2626','#2563eb','#16a34a','#d97706','#7c3aed','#0891b2'];
function drawMap(cv,L,S){
  if(!L)return;const W=2.34,H=1.22,pad=0.08;const k=cv.width/(W+pad*2);cv.height=Math.round((H+pad*2)*k);
  const c=cv.getContext('2d');const X=x=>(x+pad)*k,Y=y=>(1.0-y+pad+0.12)*k;
  const rect=(r,fill,stroke)=>{c.beginPath();c.rect(X(r[0]),Y(r[3]),(r[2]-r[0])*k,(r[3]-r[1])*k);if(fill){c.fillStyle=fill;c.fill()}if(stroke){c.strokeStyle=stroke;c.lineWidth=1;c.stroke()}};
  const text=(t,x,y,size,col,al)=>{c.fillStyle=col||'#333';c.font=`${size||11}px sans-serif`;c.textAlign=al||'center';c.fillText(t,X(x),Y(y))};
  c.clearRect(0,0,cv.width,cv.height);
  rect([0,0,2,1],'#fff','#111');rect(L.zones.charge,'#e0ecff');rect(L.zones.cook_zone,'#fdeede');rect(L.zones.wall,'#222');
  rect([2.045,0.08,2.11,0.92],'#ddd','#aaa');text('조리대',2.078,0.5,10,'#555');
  rect(L.zones.fry_pickup,null,'#e9b98a');rect(L.zones.wok_pickup,null,'#e9b98a');
  text('튀김 받는 곳',1.83,0.88,10,'#b45309');text('볶음밥 받는 곳',1.83,0.13,10,'#b45309');text('퇴식구',L.dish_return[0],L.dish_return[1]+0.07,10,'#b45309');
  text('▼ 입구',L.door[0],1.03,12,'#6d28d9');
  for(const r of Object.values(L.bays||{})){rect(r,'#e3f4e3','#6bb36b');text('비켜 서는 곳',(r[0]+r[2])/2,(r[1]+r[3])/2-0.012,10,'#2f7d32')}
  for(const r of Object.values(L.standby||{})){rect(r,'#d3efd6','#4c9a52');text('대기',(r[0]+r[2])/2,(r[1]+r[3])/2-0.012,10,'#2f7d32')}
  for(const [n,r] of Object.entries(L.chargers)){rect(r,'#bfd6ff','#1d4ed8');text(n,(r[0]+r[2])/2,(r[1]+r[3])/2-0.012,9,'#1d4ed8')}
  c.strokeStyle='#c7d2fe';c.lineWidth=1;for(const [a,b] of L.edges){c.beginPath();c.moveTo(X(L.nodes[a][0]),Y(L.nodes[a][1]));c.lineTo(X(L.nodes[b][0]),Y(L.nodes[b][1]));c.stroke()}
  const locks=(S.fms&&S.fms.locks)||{};
  for(const [n,p] of Object.entries(L.nodes)){c.beginPath();c.arc(X(p[0]),Y(p[1]),locks[n]?5:2,0,7);c.fillStyle=locks[n]?(RC[locks[n]]||'#888')+'88':'#a5b4fc';c.fill()}
  const ts={};((S.rest&&S.rest.tables)||[]).forEach(t=>ts[t.id]=t);
  const chairs=(S.world&&S.world.chairs)||{};
  const tcol={AVAILABLE:'#8b6a55',ASSIGNED:'#d97706',IN_USE:'#1d4ed8',VACANT_CHECK:'#ea580c',COLLECTING:'#b91c1c'};
  for(const [id,t] of Object.entries(L.tables)){const st=(ts[id]||{}).state||'AVAILABLE';const free=chairs[id]===undefined?t.seats:chairs[id];
    t.chairs.forEach((ch,j)=>rect(ch,j<free?'#fff':'#9ca3af','#888'));rect(t.table,tcol[st]||'#8b6a55');
    text(`T${id}`,(t.table[0]+t.table[2])/2,(t.table[1]+t.table[3])/2+0.0,12,'#fff');text(ko(st),(t.table[0]+t.table[2])/2,(t.table[1]+t.table[3])/2-0.04,9,'#fff')}
  const fms=S.fms||{};const slots=(fms.cooking||{}).slots||{};
  [['FRY_PICKUP',0.76],['WOK_PICKUP',0.24]].forEach(([n,y])=>{for(let j=0;j<(slots[n]||0);j++){c.beginPath();c.arc(X(1.96),Y(y-0.05+0.05*j),5,0,7);c.fillStyle='#f59e0b';c.fill()}});
  const res=(fms.cooking||{}).resources||{};const jobs={};((fms.cooking||{}).jobs||[]).forEach(j=>jobs[j.task]=j);
  [['cook_arm_a','ARM_A'],['cook_arm_b','ARM_B']].forEach(([a,r])=>{const p=L.cook_arms[a].pos;c.beginPath();c.arc(X(p[0]),Y(p[1]),14,0,7);c.fillStyle=res[r]?'#fb923c':'#e5e7eb';c.fill();c.strokeStyle='#c2410c';c.stroke();
    text(a.endsWith('a')?'팔A':'팔B',p[0],p[1]-0.012,10,'#7c2d12');const j=jobs[res[r]];text(j?j.step:'IDLE',p[0],p[1]-0.11,9,'#7c2d12')});
  for(const r of (fms.robots||[])){const col=RC[r.id]||'#555';
    if(r.route&&r.route.length){c.beginPath();c.moveTo(X(r.x),Y(r.y));r.route.forEach(n=>c.lineTo(X(L.nodes[n][0]),Y(L.nodes[n][1])));c.strokeStyle=col;c.lineWidth=3;c.globalAlpha=.45;c.stroke();c.globalAlpha=1}
    c.save();c.translate(X(r.x),Y(r.y));c.rotate(-r.yaw);c.fillStyle=r.state==='E_STOP'||r.state==='SUSPENDED'?'#b91c1c':col;c.fillRect(-0.06*k,-0.055*k,0.12*k,0.11*k);
    c.fillStyle='#fff';c.beginPath();c.moveTo(0.06*k,0);c.lineTo(0.02*k,-0.03*k);c.lineTo(0.02*k,0.03*k);c.fill();c.restore();
    if(r.carrying){c.beginPath();c.arc(X(r.x),Y(r.y),5,0,7);c.fillStyle='#fbbf24';c.fill();c.strokeStyle='#000';c.lineWidth=1;c.stroke()}
    text(`${r.id.replace('pinky','P')} ${r.state}`,r.x,r.y+0.085,10,col)}
  const guests=(S.world&&S.world.guests)||{};
  for(const [vid,g] of Object.entries(guests)){if(g.phase==='GONE')continue;const col=GC[vid%GC.length];
    for(let j=0;j<g.party;j++){c.beginPath();c.arc(X(g.x+0.035*(j%2)-0.017),Y(g.y+0.035*Math.floor(j/2)-0.017),6,0,7);c.fillStyle=col;c.fill();c.strokeStyle='#fff';c.lineWidth=1;c.stroke()}
    text(`손님${vid}`+(g.straggle?' (멈춤)':''),g.x,g.y+0.06,10,col)}
}
