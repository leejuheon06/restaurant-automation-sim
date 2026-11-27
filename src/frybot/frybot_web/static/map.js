// Shared helpers + measured map drawing for all FryBot pages.
// 매장(proto) 지도는 ui.js 의 drawStore 가 그리고 여기는 실측 지도
// (drawMeasuredMap)만 그림
// API 주소 앞부분. 페이지가 window.FRYBOT_API 를 먼저 정하면 그 값,
// 없으면 '' (같은 출처의 /api/...)
const API = window.FRYBOT_API || '';
// GET API+p 의 응답을 JSON 으로 읽음(HTTP 오류 상태도 그대로 읽음)
async function getJSON(p){const r=await fetch(API+p);return r.json()}
// b 를 JSON 으로 POST. p 가 http 로 시작하면 그 주소 그대로, 아니면 API+p
async function postJSON(p,b){const r=await fetch(p.startsWith('http')?p:API+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()}
// 상태 이름 -> 꼬리표 CSS 클래스(app.css). 목록에 없으면 t-blue
const TAG={AVAILABLE:'t-ok',IDLE:'t-ok',STANDBY:'t-ok',CHARGING:'t-ok',DONE:'t-ok',COMPLETED:'t-ok',DELIVERED:'t-ok',SEATED:'t-blue',IN_USE:'t-blue',IN_PROGRESS:'t-blue',
 ASSIGNED:'t-warn',PENDING:'t-warn',COLLECTING:'t-warn',VACANT_CHECK:'t-warn',ON_HOLD:'t-bad',SUSPENDED:'t-bad',E_STOP:'t-bad',GUIDE_FAILED:'t-bad',REJECTED:'t-bad',CANCELED:'t-bad'};
// tag(s): 상태 s 를 색 꼬리표 <span> HTML 로 만듦
const tag=s=>`<span class="tag ${TAG[s]||'t-blue'}">${s}</span>`;
// 상태 이름 -> 화면에 보일 한국어. ko(s) 는 목록에 없으면 s 그대로
const KO={ASSIGNED:'테이블 배정',GUIDING:'안내 중',SEATED:'착석',LEFT:'이용 종료',REJECTED:'안내 불가',GUIDE_FAILED:'동행 실패',CANCELED:'취소',
 QUEUED:'조리 대기',COOKING:'조리 중',READY:'서빙 대기',LOADED:'적재 완료',SERVING:'서빙 중',DELIVERED:'전달 완료',ON_HOLD:'보류',ORDERED:'접수',COMPLETED:'전달 완료',
 AVAILABLE:'이용 가능',IN_USE:'이용 중',COLLECTING:'식기 회수 중',VACANT_CHECK:'빈자리 확인 중'};
const ko=s=>KO[s]||s;
// 로봇 색: RC[로봇 id] 는 이름 속 숫자(pinky3 -> 3)로 RCB 를 돌려 씀.
// 숫자가 없으면 1번 색
const RCB=['#16a34a','#ea580c','#9333ea','#0284c7','#db2777','#ca8a04','#0d9488'];
const RC=new Proxy({},{get:(_,id)=>{const n=parseInt(String(id).replace(/\D/g,''))||1;return RCB[(n-1)%RCB.length];}});
// 손님 그룹 색(ui.js 가 방문 번호 % GC.length 로 고름)
const GC=['#dc2626','#2563eb','#16a34a','#d97706','#7c3aed','#0891b2'];

// 실측 지도 운영 지점(stations-<map_id>.json 의 role)별 색과,
// 모르는 role 이면 회색을 돌려주는 stationColor
const STATION_COLORS={
  dock:'#4338ca', waiting:'#116644', entrance:'#0f766e', table:'#9a3412', pickup:'#a21caf', dish_return:'#0e7490'
};
const stationColor=role=>STATION_COLORS[role]||'#334155';

// 실측 지도(관리자 화면)를 canvas 에 그림. 관리자 화면 showMap 이 부름.
//   map: /api/map 응답 + bitmap(디코딩한 지도 그림), stations(운영 지점)
//   state: /api/state 응답(state.fms 의 robots, locks). 미리보기는 {}
//   opt: showNodes(false 면 지점·락 없는 노드 숨김), showRoute(false 면
//        경로 선 숨김), selected(강조할 로봇 id). theme 은 여기서 안 씀
// [수정 2026-11-17] opt 추가(GUI 구성도 A1: 경로·노드 표시 전환, 선택한 로봇 강조).
// opt 를 주지 않으면 이전과 똑같이 그린다
function drawMeasuredMap(canvas,map,state,opt){
  opt=opt||{};
  // 캔버스 폭에 지도 그림 폭을 맞추고, 높이는 그 비율대로 캔버스를 바꿈
  const padding=25;
  const scale=(canvas.width-2*padding)/map.width;
  const height=Math.round(map.height*scale+2*padding);
  if(canvas.height!==height)canvas.height=height;
  const ctx=canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.imageSmoothingEnabled=false;
  ctx.drawImage(map.bitmap,padding,padding,map.width*scale,map.height*scale);
  // 지도 원점(origin: x, y, yaw)과 해상도(m/픽셀)로 좌표를 바꿈
  const [ox,oy,angle]=map.origin;
  const cosine=Math.cos(angle),sine=Math.sin(angle);
  // 지도 좌표(m) -> 캔버스 픽셀. 그림의 y 는 아래로 커지므로 뒤집음
  function pixel([x,y]){
    const dx=x-ox,dy=y-oy;
    return [padding+(cosine*dx+sine*dy)*scale/map.resolution,
            padding+(map.height-(-sine*dx+cosine*dy)/map.resolution)*scale];
  }
  // 지도 좌표 점들을 차례로 잇는 선(점이 2개 미만이면 그리지 않음)
  function line(points,color,width){
    if(points.length<2)return;
    ctx.beginPath();
    ctx.moveTo(...pixel(points[0]));
    for(const point of points.slice(1))ctx.lineTo(...pixel(point));
    ctx.strokeStyle=color;
    ctx.lineWidth=width;
    ctx.stroke();
  }
  // 로드맵 통로
  for(const [from,to] of map.edges)line([map.nodes[from],map.nodes[to]],'#365db3',2);
  const fleet=state.fms||{};
  ctx.font='20px sans-serif';
  ctx.textAlign='left';
  // 노드: 락을 잡은 로봇이 있으면 그 색으로 크게, 운영 지점은 테두리 원.
  // 이름은 운영 지점이거나 이름에 '_' 가 없는 노드만 씀
  const stations=new Map((map.stations||[]).map(station=>[station.node,station]));
  for(const [id,point] of Object.entries(map.nodes)){
    const [x,y]=pixel(point),holder=(fleet.locks||{})[id],station=stations.get(id);
    if(opt.showNodes===false&&!station&&!holder)continue;
    if(station){
      ctx.beginPath();
      ctx.arc(x,y,11,0,2*Math.PI);
      ctx.strokeStyle=stationColor(station.role);
      ctx.lineWidth=3;
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(x,y,holder?6:4,0,2*Math.PI);
    ctx.fillStyle=holder?RC[holder]:'#365db3';
    ctx.fill();
    ctx.fillStyle=station?stationColor(station.role):'#13254a';
    if(station||!id.includes('_'))ctx.fillText(id,x+8,y-(station?14:7));
  }
  // 1 m 당 픽셀 수
  const metres=scale/map.resolution;
  // 연결된 로봇: 남은 경로 선, 선택 강조 원(반지름 13 cm), 몸체(12x11 cm
  // 사각형)와 앞쪽 삼각형, 이름. 비상 정지면 빨간색
  for(const robot of (fleet.robots||[])){
    if(!robot.online)continue;
    const color=robot.state==='E_STOP'?'#b91c1c':RC[robot.id];
    const path=(robot.route||[]).map(id=>map.nodes[id]).filter(Boolean);
    if(opt.showRoute!==false)line([[robot.x,robot.y],...path],color,4);
    const [x,y]=pixel([robot.x,robot.y]);
    if(opt.selected===robot.id){
      ctx.beginPath();
      ctx.arc(x,y,.13*metres,0,2*Math.PI);
      ctx.fillStyle=color+'44';
      ctx.fill();
    }
    ctx.save();
    ctx.translate(x,y);
    // 캔버스는 y 가 아래라 yaw 를 반대로 돌리고, 지도 원점 회전을 더함
    ctx.rotate(angle-robot.yaw);
    ctx.fillStyle=color;
    ctx.fillRect(-.06*metres,-.055*metres,.12*metres,.11*metres);
    ctx.beginPath();
    ctx.moveTo(.053*metres,0);
    ctx.lineTo(.013*metres,-.026*metres);
    ctx.lineTo(.013*metres,.026*metres);
    ctx.closePath();
    ctx.fillStyle='#fff';
    ctx.fill();
    ctx.restore();
    ctx.fillStyle='#172554';
    ctx.fillText(robot.id,x+8,y+.087*metres);
  }
}
