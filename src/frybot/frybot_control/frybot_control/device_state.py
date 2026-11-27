"""Common device STATE / ERROR codes ("기기별 상태 흐름 V0.10").

[수정 2026-11-18] W2: 기준 문서 V0.07 -> V0.10(코드 이름·번호는 같음).

One code has one meaning for every device. These are the *reported device* states; the business states (visit, table,
order, food item, task) stay separate and live in restaurant.py / fleet_core.py. An AMR with its serving arm is one
device (FrybotMobile); the two cooking arms are one device each (FrybotArm A / B).

The Task Manager keeps its own finer activity names (TO_PICKUP, GUIDING, LOADING ...); `mobile_state` and `arm_state`
map them onto the common codes for status reports and the operator screen.
"""

STATE = {            # variable: (code, Korean meaning)
    'COOKING':        ('STA_001', '조리 중'),
    'IDLE':           ('STA_002', '대기'),
    'INITIALIZING':   ('STA_003', '기동·초기 점검 중'),
    'MOVING':         ('STA_004', '이동 중'),
    'ARM_OPERATING':  ('STA_005', '팔 작업 중'),
    'RETURNING':      ('STA_006', '복귀 중'),
    'CHARGING':       ('STA_007', '충전 중'),
    'HOLDING':        ('STA_008', '동작 보류 중'),
    'FAULT_HANDLING': ('STA_009', '이상 대응 중'),
    'RECOVERY_CHECK': ('STA_010', '복구 점검 중'),
    'OUT_OF_SERVICE': ('STA_011', '운용 제외'),
    'OFFLINE':        ('STA_012', '연결 두절'),
    'UNKNOWN':        ('STA_013', '상태 미확인'),
    'OPERATING':      ('STA_014', '일반 가동 중'),
}
# 오류 이름: (코드, 한국어 뜻). RobotStatus.error 와 관리자 화면이 이 이름을 씀
ERROR = {
    'NO_ERROR':            ('ERR_000', '오류 없음 확인'),
    'COMMUNICATION_ERROR': ('ERR_001', '통신 이상'),
    'SENSOR_ERROR':        ('ERR_002', '센서 이상'),
    'DRIVE_ERROR':         ('ERR_003', '주행 구동 이상'),
    'ARM_ERROR':           ('ERR_004', '팔 구동 이상'),
    'GRIPPER_ERROR':       ('ERR_005', '말단 장치 이상'),
    'CHARGING_ERROR':      ('ERR_006', '충전 이상'),
    'BATTERY_ERROR':       ('ERR_007', '배터리 이상'),
    'EMERGENCY_STOP':      ('ERR_008', '비상정지 입력 확인'),
    'SELF_CHECK_ERROR':    ('ERR_009', '기기 점검 이상'),
    'UNCLASSIFIED_ERROR':  ('ERR_010', '미분류 오류'),
}
# Arm jobs of a cooking arm that are not cooking itself (placing the finished dish on the hand-over counter)
NON_COOKING_JOBS = {'PLACE_HANDOFF'}


def report(state, error=None):
    """{'state': 'MOVING', 'code': 'STA_004', 'ko': '이동 중', 'error': 'NO_ERROR', 'error_code': 'ERR_000'}.
    error=None means "no error observed": it is left empty instead of claiming ERR_000 (the sheet forbids that).

    Args:
        state: STATE 의 이름.
        error: ERROR 의 이름. None 이나 '' 면 오류 칸을 비움.

    Returns:
        state, code, ko, error, error_code 를 가진 dict.

    Raises:
        KeyError: STATE 나 ERROR 에 없는 이름일 때.
    """
    code, ko = STATE[state]
    return {'state': state, 'code': code, 'ko': ko, 'error': error or '', 'error_code': ERROR[error][0] if error else ''}


def mobile_state(activity, online=True, seen=True, error=''):
    """Common device state of an AMR from the Task Manager's activity name (FleetCore.robot_state).
    `error`: what the robot reports itself in RobotStatus.error (an ERROR name); it is shown unless the Task Manager
    already knows a cause of its own (emergency stop, suspended task, connection lost).

    Args:
        activity: FleetCore.robot_state() 의 활동 이름(MOVING, LOADING 등).
        online: 상태 보고가 이어지고 있는지.
        seen: 상태 보고를 한 번이라도 받았는지. 지금 호출처(fleet_core
            snapshot)는 넘기지 않아 늘 True(확인 필요: 쓰임이 남았는지).
        error: 로봇이 보고한 오류 이름.

    Returns:
        report() 와 같은 형식의 dict.
    """
    rep = _mobile_state(activity, online, seen)
    # 관제가 따로 정한 오류가 없을 때만 로봇이 보고한 오류를 보임.
    # 통신 이상은 보류(HOLDING), 다른 오류는 이상 대응 중(FAULT_HANDLING)
    if error in ERROR and error != 'NO_ERROR' and rep['error'] in ('', 'NO_ERROR'):
        hold = 'HOLDING' if error == 'COMMUNICATION_ERROR' else 'FAULT_HANDLING'
        rep = report(hold, error)
    return rep


# 관제 활동 이름만으로 정하는 공통 상태. 위에서부터 먼저 맞는 조건이 이김
def _mobile_state(activity, online=True, seen=True):
    # [수정 2026-11-20] T-49: 기동 때 자동 위치 추정 중(아직 온라인 아님)
    if activity == 'LOCALIZING':
        return report('INITIALIZING', 'NO_ERROR')
    # [수정 2026-11-20] T-49: 위치를 못 찾음(관리자가 RViz 로 정해야 함)
    if activity == 'NOT_LOCALIZED':
        return report('INITIALIZING', 'SELF_CHECK_ERROR')
    if not seen:  # 상태 보고를 한 번도 받지 못함
        return report('UNKNOWN')
    if not online:  # 상태 보고가 끊김
        return report('OFFLINE', 'COMMUNICATION_ERROR')
    if activity == 'E_STOP':
        return report('FAULT_HANDLING', 'EMERGENCY_STOP')
    # [수정 2026-11-17] UR-18: 관리자의 일시 중단은 오류가 아닌 보류
    if activity == 'PAUSED':
        return report('HOLDING', 'NO_ERROR')
    # 임무 보류: 원인(reason)은 임무 이벤트에 있어 여기서는 미분류 오류로 둠
    if activity == 'SUSPENDED':
        return report('HOLDING', 'UNCLASSIFIED_ERROR')
    # 서빙 팔 작업(적재·내림·식기 회수·퇴식구 반납)
    if activity in ('LOADING', 'UNLOADING', 'COLLECTING', 'RETURNING_DISHES'):
        return report('ARM_OPERATING', 'NO_ERROR')
    if activity == 'RETURNING':
        return report('RETURNING', 'NO_ERROR')
    if activity == 'CHARGING':
        return report('CHARGING', 'NO_ERROR')
    if activity in ('IDLE', 'STANDBY'):  # STANDBY: 대기 위치에 서 있음
        return report('IDLE', 'NO_ERROR')
    return report('MOVING', 'NO_ERROR')          # TO_START GUIDING TO_PICKUP SERVING TO_TABLE TO_DISH_RETURN


def arm_state(job):
    """Common device state of a cooking arm from the arm job it is running ('' = none).

    Args:
        job: 진행 중인 팔 작업 이름. 없으면 ''.

    Returns:
        report() 와 같은 형식의 dict. NON_COOKING_JOBS 는 팔 작업 중,
        나머지 작업은 조리 중.
    """
    if not job:
        return report('IDLE', 'NO_ERROR')
    return report('ARM_OPERATING' if job in NON_COOKING_JOBS else 'COOKING', 'NO_ERROR')
