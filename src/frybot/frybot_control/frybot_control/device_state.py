"""Common device STATE / ERROR codes ("기기별 상태 흐름 V0.07" on Confluence, 2026-11-14).

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
# Codes a device type may report (table "기기별 적용 코드")
APPLIES = {
    'FrybotMobile': {'IDLE', 'INITIALIZING', 'MOVING', 'ARM_OPERATING', 'RETURNING', 'CHARGING', 'HOLDING',
                     'FAULT_HANDLING', 'RECOVERY_CHECK', 'OUT_OF_SERVICE', 'OFFLINE', 'UNKNOWN'},
    'FrybotArm': {'COOKING', 'IDLE', 'INITIALIZING', 'ARM_OPERATING', 'HOLDING', 'FAULT_HANDLING', 'RECOVERY_CHECK',
                  'OUT_OF_SERVICE', 'OFFLINE', 'UNKNOWN'},
}
# Arm jobs of a cooking arm that are not cooking itself (placing the finished dish on the hand-over counter)
NON_COOKING_JOBS = {'PLACE_HANDOFF'}


def report(state, error=None):
    """{'state': 'MOVING', 'code': 'STA_004', 'ko': '이동 중', 'error': 'NO_ERROR', 'error_code': 'ERR_000'}.
    error=None means "no error observed": it is left empty instead of claiming ERR_000 (the sheet forbids that)."""
    code, ko = STATE[state]
    return {'state': state, 'code': code, 'ko': ko, 'error': error or '', 'error_code': ERROR[error][0] if error else ''}


def mobile_state(activity, online=True, seen=True):
    """Common device state of an AMR from the Task Manager's activity name (FleetCore.robot_state)."""
    if not seen:
        return report('UNKNOWN')
    if not online:
        return report('OFFLINE', 'COMMUNICATION_ERROR')
    if activity == 'E_STOP':
        return report('FAULT_HANDLING', 'EMERGENCY_STOP')
    if activity == 'SUSPENDED':
        return report('HOLDING', 'UNCLASSIFIED_ERROR')
    if activity in ('LOADING', 'UNLOADING', 'COLLECTING', 'RETURNING_DISHES'):
        return report('ARM_OPERATING', 'NO_ERROR')
    if activity == 'RETURNING':
        return report('RETURNING', 'NO_ERROR')
    if activity == 'CHARGING':
        return report('CHARGING', 'NO_ERROR')
    if activity in ('IDLE', 'STANDBY'):
        return report('IDLE', 'NO_ERROR')
    return report('MOVING', 'NO_ERROR')          # TO_START GUIDING TO_PICKUP SERVING TO_TABLE TO_DISH_RETURN


def arm_state(job):
    """Common device state of a cooking arm from the arm job it is running ('' = none)."""
    if not job:
        return report('IDLE', 'NO_ERROR')
    return report('ARM_OPERATING' if job in NON_COOKING_JOBS else 'COOKING', 'NO_ERROR')
