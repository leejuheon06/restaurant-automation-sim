// [수정 2026-11-17] GUI 화면 구성도 초안 v0.1 반영: 관리자·키오스크·테이블 화면이
// 함께 쓰는 표시 이름, 상태 분류, 매장 지도 그리기. map.js 뒤에 불러온다.
// HTML 에 넣을 글자의 특수 문자(& < > " ') 를 바꿔 넣는다
const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => (
  {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
// 받침에 따라 '이' 또는 '가'를 붙인다
const iGa = word => {
  const code = String(word).charCodeAt(String(word).length - 1) - 0xAC00;
  return word + (code >= 0 && code <= 11171 && code % 28 ? '이' : '가');
};
// 로봇 id 의 숫자 부분('pinky2' → 2), 숫자가 없으면 0
const robotNo = id => parseInt(String(id).replace(/\D/g, '')) || 0;
// 화면에 쓰는 로봇 이름('pinky2' → 'AMR-2')
const amrLabel = id => 'AMR-' + (robotNo(id) || '?');
// 유닉스 초 → 브라우저 현지 시각 HH:MM:SS
const clock = sec => {
  const d = new Date(sec * 1000), two = n => String(n).padStart(2, '0');
  return two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds());
};
// 걸린 초 → MM:SS (음수는 0)
const mmss = sec => {
  const s = Math.max(0, Math.round(sec));
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
};

// 로봇 상태(관제 /fms/state 의 robots[].state) → 표시 이름
// [수정 2026-11-17] UR-18: PAUSED(일시 중단) 추가
const ROBOT_KO = {
  PAUSED: '일시 중단', E_STOP: '비상 정지', SUSPENDED: '임무 중단', LOADING: '적재 중', UNLOADING: '전달 중',
  COLLECTING: '식기 수거 중', RETURNING_DISHES: '식기 반납 중', MOVING: '이동 중',
  TO_START: '입구로 이동', GUIDING: '안내 중', TO_PICKUP: '받는 곳 이동', SERVING: '서빙 이동',
  TO_DISH_RETURN: '퇴식구 이동', TO_TABLE: '테이블 이동', RETURNING: '복귀 중', STANDBY: '대기',
  CHARGING: '충전 중', IDLE: '대기'};
// 임무 유형 → 표시 이름
const TASK_KO = {GUIDE: '안내', SERVE: '서빙', COLLECT: '식기 회수', MOVE: '이동', COOK: '조리'};
// 임무 상태 → 표시 이름
const TASK_STATE_KO = {PENDING: '대기', IN_PROGRESS: '수행 중', DONE: '완료', SUSPENDED: '중단',
                       CANCELED: '취소'};
// [수정 2026-11-25] I/F 정의서 v0.2 이름: /frybot/state -> /frybot/central/view_state
// [수정 2026-11-26] I/F v0.3 최종 판 이름:
// /frybot/central/view_state -> /frybot/state
// 테이블 상태(식당 /frybot/state 의 tables[].state) → 표시 이름
const TABLE_KO = {AVAILABLE: '이용 가능', ASSIGNED: '안내 중', IN_USE: '이용 중',
                  VACANT_CHECK: '빈자리 확인', COLLECTING: '정리 대기',
                  CLOSED: '사용 중지'};  // [수정 2026-11-17] UR-15
// 음식 상태 -> 주문 진행 5단계 (접수, 조리, 서빙 준비, 서빙, 완료)
// [수정 2026-11-18] W2: v4 음식 상태 LOADED(적재 완료, 출발 전)는 '서빙 준비'
const ITEM_STAGE = {ORDERED: 0, QUEUED: 0, COOKING: 1, READY: 2, LOADED: 2, SERVING: 3,
                    DELIVERED: 4};
// ITEM_STAGE 의 단계 번호 → 표시 이름
const STAGE_KO = ['접수', '조리', '서빙 준비', '서빙', '완료'];
// [수정 2026-11-17] UR-17, 21: 팔 상태, 임무를 줄 수 없는 이유
const ARM_KO = {IDLE: '대기', COOKING: '조리 중', ARM_OPERATING: '작업 중', FAULT_HANDLING: '이상 대응 중',
                OFFLINE: '연결 두절', UNKNOWN: '상태 미확인'};
const UNAVAILABLE_KO = {OFFLINE: '연결 두절', PAUSED: '일시 중단', E_STOP: '비상 정지', ON_TASK: '임무 수행 중',
                        ARM_BUSY: '팔 작업 중', LOW_BATTERY: '배터리 부족',
                        // [수정 2026-11-17] G2: 오류 보고 중인 로봇은 배정 불가
                        ERROR: '오류 보고 중'};
// 날짜가 오늘이 아니면 월-일을 함께 적는다 (기간 조회용)
const stamp = sec => {
  const d = new Date(sec * 1000), two = n => String(n).padStart(2, '0');
  return (d.toDateString() === new Date().toDateString() ? '' : two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ') + clock(sec);
};

// 로봇 분류: 상단 요약, 목록 배지, 지도 색이 같은 기준을 쓴다
const CAT = {
  guide: {ko: '안내', fg: '#8AB8FF', bg: '#16264A', map: '#8B5CF6'},
  serve: {ko: '서빙', fg: '#5BE3A0', bg: '#123524', map: '#22C55E'},
  work: {ko: '회수·이동', fg: '#F5B942', bg: '#3A2E12', map: '#F59E0B'},
  idle: {ko: '대기', fg: '#E7EAF0', bg: '#2A3142', map: '#9CA3AF'},
  charge: {ko: '충전', fg: '#8AB8FF', bg: '#16263F', map: '#5B9BFF'},
  hold: {ko: '일시 중단', fg: '#F5B942', bg: '#3A2E12', map: '#D97706'},
  error: {ko: '오류', fg: '#FF8A78', bg: '#3B1512', map: '#FF7A66'},
  late: {ko: '수신 지연', fg: '#F5B942', bg: '#3A2E12', map: '#6B7280'}};
// 로봇 하나의 분류(CAT 의 키). 연결·정지·오류를 임무보다 먼저 본다
function robotCat(r) {
  if (!r.online) return 'late';
  if (r.state === 'PAUSED') return 'hold';
  if (r.state === 'E_STOP' || r.state === 'SUSPENDED' || r.error) return 'error';
  if (r.task_type === 'GUIDE') return 'guide';
  if (r.task_type === 'SERVE') return 'serve';
  if (r.task_type) return 'work';
  if (r.charging || r.state === 'CHARGING') return 'charge';
  return 'idle';
}
// 임무 유형별 단계 (로봇 상태 이름, 표시 이름)
const STEPS = {
  GUIDE: [['TO_START', '입구로 이동'], ['GUIDING', '손님 안내 (후진 주행)']],
  SERVE: [['TO_PICKUP', '받는 곳 이동'], ['LOADING', '적재 확인'], ['SERVING', '서빙 이동'],
          ['UNLOADING', '도착 · 로봇팔 전달']],
  COLLECT: [['TO_TABLE', '테이블 이동'], ['COLLECTING', '식기 수거'],
            ['TO_DISH_RETURN', '퇴식구 이동'], ['RETURNING_DISHES', '식기 반납']],
  MOVE: [['MOVING', '목적 노드로 이동']]};

// 매장 지도 색. dark 는 관리자 화면, light 는 손님용 태블릿 화면
const PALETTE = {
  dark: {floor: '#1C2230', border: '#4A5670', charge: '#16263F', chargeLine: '#5B9BFF',
         kitchen: '#2A1E14', pass: '#F59E0B', wall: '#3A4560', bench: '#2A3142', benchLine: '#4A5670',
         text: '#E7EAF0', muted: '#A3ACBD', lane: '#2F3B57', node: '#44527A', bay: '#18281F',
         bayLine: '#3DD68C', chair: '#C9CFDA', chairUsed: '#4A5670', entrance: '#C4B5FD',
         table: {AVAILABLE: '#6E5442', ASSIGNED: '#2F6FEB', IN_USE: '#1E7A4F', VACANT_CHECK: '#B7791F',
                 COLLECTING: '#5A6375', CLOSED: '#3A3F4B'},
         arm: '#2A3142', armBusy: '#14A394', armLine: '#2DD4BF'},
  light: {floor: '#FFFFFF', border: '#C9CED8', charge: '#E6F0FF', chargeLine: '#2563EB',
          kitchen: '#FFF1E6', pass: '#C2410C', wall: '#3A4152', bench: '#E9ECF1', benchLine: '#C3C9D3',
          text: '#1C1E24', muted: '#5A6375', lane: '#DCE3F0', node: '#B8C4DE', bay: '#EEF8EE',
          bayLine: '#4C9A52', chair: '#FFFFFF', chairUsed: '#B5ADA2', entrance: '#6D28D9',
          table: {AVAILABLE: '#8B6B55', ASSIGNED: '#2563EB', IN_USE: '#15803D', VACANT_CHECK: '#B45309',
                  COLLECTING: '#6B7280', CLOSED: '#9CA3AF'},
          arm: '#E9ECF1', armBusy: '#2DD4BF', armLine: '#0F8276'}};

// 기존 매장 도면(200x100 cm)을 그린다. opt: theme('dark'|'light'), selected(로봇 id),
// showRoute, showNodes, highlightTable(테이블 id), minimal(로봇·손님 생략)
function drawStore(cv, L, S, opt) {
  if (!L) return;
  opt = opt || {};
  S = S || {};
  const P = PALETTE[opt.theme === 'light' ? 'light' : 'dark'];
  // 그리는 범위(m, 조리대 포함 2.34 × 1.22)와 여백, 캔버스 1 m 당 픽셀 k
  const W = 2.34, H = 1.22, pad = 0.08, k = cv.width / (W + pad * 2);
  const height = Math.round((H + pad * 2) * k);
  if (cv.height !== height) cv.height = height;
  const c = cv.getContext('2d');
  // 지도 좌표(m, y 위쪽) → 캔버스 픽셀(y 아래쪽).
  // fs: 캔버스 폭에 맞춘 글자 크기
  const X = x => (x + pad) * k, Y = y => (1.0 - y + pad + 0.12) * k;
  const fs = px => Math.max(11, Math.round(px * k / 290));
  // 사각형 r=[x0, y0, x1, y1] 채우기·테두리(dash 가 있으면 점선)
  const rect = (r, fill, stroke, dash) => {
    c.beginPath();
    c.rect(X(r[0]), Y(r[3]), (r[2] - r[0]) * k, (r[3] - r[1]) * k);
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) {
      c.setLineDash(dash || []); c.strokeStyle = stroke; c.lineWidth = 1.5; c.stroke(); c.setLineDash([]);
    }
  };
  // 글자 쓰기. size 13 이상이면 굵게
  const text = (t, x, y, size, col, align) => {
    c.fillStyle = col || P.text;
    c.font = (size >= 13 ? '700 ' : '') + fs(size || 11) + 'px "Noto Sans KR",sans-serif';
    c.textAlign = align || 'center';
    c.fillText(t, X(x), Y(y));
  };
  // 바닥, 충전 구역, 조리 구역, 벽, 조리대, 받는 곳, 퇴식구, 입구
  c.clearRect(0, 0, cv.width, cv.height);
  rect([0, 0, 2, 1], P.floor, P.border);
  rect(L.zones.charge, P.charge);
  rect(L.zones.cook_zone, P.kitchen);
  rect(L.zones.wall, P.wall);
  rect([2.045, 0.08, 2.11, 0.92], P.bench, P.benchLine);
  text('조리대', 2.078, 0.5, 10, P.muted);
  rect(L.zones.fry_pickup, null, P.pass, [5, 4]);
  rect(L.zones.wok_pickup, null, P.pass, [5, 4]);
  text('튀김 받는 곳', 1.83, 0.84, 10, P.pass);
  text('볶음밥 받는 곳', 1.83, 0.15, 10, P.pass);
  text('퇴식구', L.dish_return[0], L.dish_return[1] + 0.07, 10, P.pass);
  text('▼ 입구 · 접수', L.door[0], 1.035, 12, P.entrance);
  // 비켜 서는 곳, 대기 위치, 충전대
  for (const r of Object.values(L.bays || {})) {
    rect(r, P.bay, P.bayLine, [4, 3]);
    text('비켜 서는 곳', (r[0] + r[2]) / 2, (r[1] + r[3]) / 2 - 0.012, 9, P.bayLine);
  }
  for (const r of Object.values(L.standby || {})) {
    rect(r, P.bay, P.bayLine);
    text('대기 위치', (r[0] + r[2]) / 2, (r[1] + r[3]) / 2 - 0.012, 9, P.bayLine);
  }
  Object.entries(L.chargers).forEach(([name, r]) => {
    rect(r, null, P.chargeLine);
    text('⚡' + name.replace('CH', 'C'), (r[0] + r[2]) / 2, (r[1] + r[3]) / 2 - 0.012, 10, P.chargeLine);
  });
  // S: /api/state 응답(fms 관제, rest 식당, world 매장 시뮬)
  const fleet = S.fms || {}, rest = S.rest || {}, world = S.world || {};
  // 로드맵 통로와 노드. 락이 잡힌 노드는 잡은 로봇 색(RC, map.js)으로
  // 크게 그림
  if (opt.showNodes !== false) {
    c.strokeStyle = P.lane; c.lineWidth = 1;
    for (const [a, b] of L.edges) {
      c.beginPath(); c.moveTo(X(L.nodes[a][0]), Y(L.nodes[a][1]));
      c.lineTo(X(L.nodes[b][0]), Y(L.nodes[b][1])); c.stroke();
    }
    const locks = fleet.locks || {};
    for (const [name, p] of Object.entries(L.nodes)) {
      c.beginPath(); c.arc(X(p[0]), Y(p[1]), locks[name] ? 5 : 2, 0, 7);
      c.fillStyle = locks[name] ? RC[locks[name]] + 'AA' : P.node; c.fill();
    }
  }
  // 테이블(상태 색)과 의자(보이는 QR 수만큼 빈 의자로)
  const tableState = {};
  (rest.tables || []).forEach(t => { tableState[t.id] = t; });
  const chairs = world.chairs || {};
  for (const [id, t] of Object.entries(L.tables)) {
    const state = (tableState[id] || {}).state || 'AVAILABLE';
    const free = chairs[id] === undefined ? t.seats : chairs[id];
    t.chairs.forEach((chair, j) => rect(chair, j < free ? P.chair : P.chairUsed, P.benchLine));
    rect(t.table, P.table[state] || P.table.AVAILABLE, null);
    if (state === 'COLLECTING') rect(t.table, null, P.muted, [4, 3]);
    const cx = (t.table[0] + t.table[2]) / 2, cy = (t.table[1] + t.table[3]) / 2;
    if (String(opt.highlightTable) === String(id)) {
      c.beginPath(); c.arc(X(cx), Y(cy), 0.13 * k, 0, 7);
      c.strokeStyle = P.pass; c.lineWidth = 4; c.stroke();
    }
    text('T' + id, cx, cy + 0.012, 11, '#FFFFFF');
    text(TABLE_KO[state] || state, cx, cy - 0.035, 8, '#FFFFFF');
  }
  // 조리 팔 A(튀김)·B(웍): 받는 곳의 음식 수, 작업 중이면 강조, 장치 상태
  const cooking = fleet.cooking || {}, slots = cooking.slots || {}, owner = cooking.resources || {};
  [['FRY_PICKUP', 'cook_arm_a', 'ARM_A', '튀김'], ['WOK_PICKUP', 'cook_arm_b', 'ARM_B', '웍']]
    .forEach(([slot, arm, res, label]) => {
      const p = L.cook_arms[arm].pos, device = (cooking.arms || {})[arm];
      for (let j = 0; j < (slots[slot] || 0); j++) {
        c.beginPath(); c.arc(X(1.96), Y(p[1] - 0.05 + 0.05 * j), 5, 0, 7);
        c.fillStyle = '#F59E0B'; c.fill();
      }
      c.beginPath(); c.arc(X(p[0]), Y(p[1]), 0.07 * k, 0, 7);
      c.fillStyle = owner[res] ? P.armBusy : P.arm; c.fill();
      c.strokeStyle = P.armLine; c.lineWidth = 2; c.stroke();
      text(label, p[0], p[1] - 0.012, 10, P.text);
      text(device ? device.ko : '', p[0], p[1] - 0.115, 9, P.muted);
    });
  // 아래부터 로봇·손님(minimal 이면 생략)
  if (opt.minimal) return;
  // 로봇: 남은 경로(점선), 선택 표시, 몸체·방향, 실은 음식, 이름 → 테이블
  for (const r of (fleet.robots || [])) {
    const cat = CAT[robotCat(r)], x = X(r.x), y = Y(r.y), radius = 0.058 * k;
    if (opt.showRoute !== false && r.route && r.route.length) {
      c.beginPath(); c.moveTo(x, y);
      r.route.forEach(n => { if (L.nodes[n]) c.lineTo(X(L.nodes[n][0]), Y(L.nodes[n][1])); });
      c.setLineDash([7, 5]); c.strokeStyle = cat.map; c.lineWidth = 2.5; c.stroke(); c.setLineDash([]);
    }
    if (opt.selected === r.id) {
      c.beginPath(); c.arc(x, y, radius + 7, 0, 7); c.fillStyle = cat.map + '44'; c.fill();
    }
    c.beginPath(); c.arc(x, y, radius, 0, 7); c.fillStyle = cat.map; c.fill();
    c.strokeStyle = '#FFFFFF'; c.lineWidth = opt.selected === r.id ? 3 : 1.5; c.stroke();
    c.beginPath(); c.moveTo(x, y);
    c.lineTo(x + Math.cos(-r.yaw) * radius * 1.5, y + Math.sin(-r.yaw) * radius * 1.5);
    c.strokeStyle = '#FFFFFF'; c.lineWidth = 2.5; c.stroke();
    if (r.carrying) {
      c.beginPath(); c.arc(x + radius * 0.8, y - radius * 0.8, 5, 0, 7); c.fillStyle = '#FBBF24'; c.fill();
    }
    c.fillStyle = '#FFFFFF'; c.font = '700 ' + fs(12) + 'px sans-serif'; c.textAlign = 'center';
    c.fillText(String(robotNo(r.id)), x, y + fs(12) * 0.36);
    const task = (fleet.tasks || []).find(t => t.id === r.task);
    const target = task && task.table ? ' → T' + task.table : '';
    c.fillStyle = cat.map; c.font = fs(10) + 'px "Noto Sans KR",sans-serif';
    c.fillText(amrLabel(r.id) + target, x, y + radius + fs(10) + 4);
  }
  // 손님(매장 시뮬에서만): 인원수만큼 점, 멈춰 섰으면 (멈춤)
  for (const [vid, g] of Object.entries(world.guests || {})) {
    if (g.phase === 'GONE') continue;
    const col = GC[vid % GC.length];
    for (let j = 0; j < g.party; j++) {
      c.beginPath();
      c.arc(X(g.x + 0.035 * (j % 2) - 0.017), Y(g.y + 0.035 * Math.floor(j / 2) - 0.017), 5, 0, 7);
      c.fillStyle = col; c.fill(); c.strokeStyle = '#FFFFFF'; c.lineWidth = 1; c.stroke();
    }
    text('손님' + vid + (g.straggle ? ' (멈춤)' : ''), g.x, g.y + 0.06, 9, col);
  }
}
