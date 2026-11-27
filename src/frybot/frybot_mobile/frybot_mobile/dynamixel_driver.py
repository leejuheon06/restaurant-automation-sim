"""Pinky Pro 바퀴용 다이나믹셀 모터 두 개를 다루는 얇은 래퍼.

dynamixel_sdk(프로토콜 2.0)로 포트를 열고, 모터를 속도 제어 모드로
설정하고, 두 바퀴의 목표 RPM 을 한 패킷(SyncWrite)으로 보내고, 현재
속도·위치를 한 번에(BulkRead) 읽는다. pinky_driver 가 쓴다.
"""
# [수정 2026-11-17] pinky_pro 의존 제거: pinky_pro(pinklab-art, Apache-2.0,
# 커밋 014a09f)의 pinky_bringup/dynamixel_driver.py 를 그대로 복사함. 동작은 바꾸지 않음
import time

# [수정 2026-11-20] import * 금지 규칙: 쓰는 이름만 명시해서 가져옴(동작 같음)
from dynamixel_sdk import COMM_SUCCESS
from dynamixel_sdk import DXL_HIBYTE
from dynamixel_sdk import DXL_HIWORD
from dynamixel_sdk import DXL_LOBYTE
from dynamixel_sdk import DXL_LOWORD
from dynamixel_sdk import GroupBulkRead
from dynamixel_sdk import GroupSyncWrite
from dynamixel_sdk import PacketHandler
from dynamixel_sdk import PortHandler


class DynamixelDriver:
    """좌우 바퀴 다이나믹셀의 속도 명령과 피드백 읽기.

    Args:
        port: 직렬 장치 경로(예: /dev/ttyAMA5).
        baudrate: 통신 속도(bps).
        dxl_ids: [왼쪽 바퀴 ID, 오른쪽 바퀴 ID]. 순서가 RPM 인자 순서와 같다.
    """

    def __init__(self, port, baudrate, dxl_ids):
        # 컨트롤 테이블 주소(다이나믹셀 X 시리즈 기준, 정확한 모델은 확인 필요)
        self.ADDR_OPERATING_MODE    = 11
        self.ADDR_TORQUE_ENABLE     = 64
        self.ADDR_LED_RED           = 65
        self.ADDR_GOAL_VELOCITY     = 104
        self.ADDR_PROFILE_ACCEL     = 108
        self.ADDR_PRESENT_VELOCITY  = 128
        self.ADDR_PRESENT_POSITION  = 132

        # 위 항목의 바이트 길이
        self.LEN_GOAL_VELOCITY      = 4
        self.LEN_PRESENT_VELOCITY   = 4
        self.LEN_PRESENT_POSITION   = 4

        self.PROTOCOL_VERSION       = 2.0
        self.DXL_IDS                = dxl_ids
        self.BAUDRATE               = baudrate
        self.DEVICENAME             = port

        # 속도 값 1 = 0.229 rpm. RPM x 이 계수 = Goal Velocity 값
        self.RPM_TO_VALUE_SCALE = 1 / 0.229

        # 포트·패킷 처리기, 두 모터 목표 속도 동시 쓰기, 속도·위치 묶음 읽기
        self.portHandler = PortHandler(self.DEVICENAME)
        self.packetHandler = PacketHandler(self.PROTOCOL_VERSION)

        self.groupSyncWrite = GroupSyncWrite(self.portHandler, self.packetHandler, self.ADDR_GOAL_VELOCITY, self.LEN_GOAL_VELOCITY)
        self.groupBulkRead = GroupBulkRead(self.portHandler, self.packetHandler)

    def begin(self):
        """직렬 포트를 열고 통신 속도를 맞춘다.

        Returns:
            둘 다 성공하면 True.
        """
        if not self.portHandler.openPort(): return False
        if not self.portHandler.setBaudRate(self.BAUDRATE): return False
        return True

    # [수정 2026-11-25] T-59: 끊긴 통신의 '사용 중' 표시를 지우고, 토크 끄기
    # 결과를 검사해 실패하면 다시 씀(전에는 결과를 버려 실패해도 몰랐음)
    def terminate(self, retries: int = 3) -> bool:
        """0 RPM 을 보내고 토크·LED 를 끈 뒤 포트를 닫는다.

        Args:
            retries: 모터마다 토크 끄기 쓰기를 시도할 최대 횟수.

        Returns:
            모든 모터의 토크 끄기 쓰기가 성공(COMM_SUCCESS, 오류 0)하면 True.
        """
        # 통신 도중 예외로 끊긴 거래가 is_using 을 True 로 남기면 아래 쓰기가
        # 모두 COMM_PORT_BUSY 로 패킷을 보내지 않음. spin 이 끝난 뒤라 이
        # 포트를 쓰는 다른 곳은 없음
        self.portHandler.is_using = False
        self.set_double_rpm(0, 0)
        time.sleep(0.1)
        ok = True
        for dxl_id in self.DXL_IDS:
            ok = self._torque_off(dxl_id, retries) and ok
            self.packetHandler.write1ByteTxRx(
                self.portHandler, dxl_id, self.ADDR_LED_RED, 0)  # LED OFF
        time.sleep(0.1)
        self.portHandler.closePort()
        return ok

    # [수정 2026-11-25] 신규 (T-59): 토크 끄기 한 모터(결과 검사·재시도)
    def _torque_off(self, dxl_id: int, retries: int) -> bool:
        """모터 하나의 Torque Enable 에 0 을 쓴다.

        Args:
            dxl_id: 모터 ID.
            retries: 최대 시도 횟수.

        Returns:
            쓰기가 COMM_SUCCESS 이고 모터 오류가 0 이면 True.
        """
        for _ in range(retries):
            res, err = self.packetHandler.write1ByteTxRx(
                self.portHandler, dxl_id, self.ADDR_TORQUE_ENABLE, 0)
            if res == COMM_SUCCESS and err == 0:
                return True
            self.portHandler.is_using = False
            time.sleep(0.02)
        return False

    def initialize_motors(self, profile_accel=200):
        """모터마다 재부팅 후 속도 제어 모드, 가속 프로파일, 토크·LED 를 켠다.

        재부팅 실패는 경고만 하고 넘어간다.

        Args:
            profile_accel: Profile Acceleration 값(단위는 모델 문서 확인 필요).

        Returns:
            모든 쓰기가 COMM_SUCCESS 이면 True, 하나라도 실패하면 False.
        """
        for dxl_id in self.DXL_IDS:
            try: 
                self.packetHandler.reboot(self.portHandler, dxl_id)
                time.sleep(0.5)
            except Exception as e:
                print(f"Warning: Could not reboot motor {dxl_id}. Error: {e}")

            # 운영 모드 1 = 속도 제어
            if self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, self.ADDR_OPERATING_MODE, 1)[0] != COMM_SUCCESS: return False
            if self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, self.ADDR_PROFILE_ACCEL, profile_accel)[0] != COMM_SUCCESS: return False
            if self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, self.ADDR_TORQUE_ENABLE, 1)[0] != COMM_SUCCESS: return False
            if self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, self.ADDR_LED_RED, 1)[0] != COMM_SUCCESS: return False
        return True

    def set_double_rpm(self, rpm_l, rpm_r):
        """두 바퀴의 목표 속도를 한 SyncWrite 패킷으로 보낸다.

        Args:
            rpm_l: 왼쪽 모터 RPM(부호 = 모터 기준 회전 방향).
            rpm_r: 오른쪽 모터 RPM.

        Returns:
            패킷 전송이 성공하면 True. 모터가 실제로 따랐는지는 모른다.
        """
        velocities = [rpm_l, rpm_r]
        self.groupSyncWrite.clearParam()

        for i, dxl_id in enumerate(self.DXL_IDS):
            dxl_vel = int(velocities[i] * self.RPM_TO_VALUE_SCALE)
            # 32비트 값을 리틀 엔디언 4바이트로 나눔
            param = [DXL_LOBYTE(DXL_LOWORD(dxl_vel)), DXL_HIBYTE(DXL_LOWORD(dxl_vel)),
                     DXL_LOBYTE(DXL_HIWORD(dxl_vel)), DXL_HIBYTE(DXL_HIWORD(dxl_vel))]
            if not self.groupSyncWrite.addParam(dxl_id, param): return False

        return self.groupSyncWrite.txPacket() == COMM_SUCCESS

    def get_feedback(self):
        """두 모터의 현재 속도(RPM)와 위치(펄스)를 한 번에 읽는다.

        Present Velocity(128)와 Present Position(132)이 붙어 있어 128 부터
        8바이트를 읽는다. 위치는 누적 펄스(한 바퀴 4096, pinky_driver 기준).

        Returns:
            (rpm_l, rpm_r, pos_l, pos_r). 통신 실패면 (None, None, None, None).
        """
        self.groupBulkRead.clearParam()
        read_len = self.LEN_PRESENT_VELOCITY + self.LEN_PRESENT_POSITION
        
        for dxl_id in self.DXL_IDS:
            self.groupBulkRead.addParam(dxl_id, self.ADDR_PRESENT_VELOCITY, read_len)

        if self.groupBulkRead.txRxPacket() != COMM_SUCCESS:
            return None, None, None, None
        
        id_l, id_r = self.DXL_IDS[0], self.DXL_IDS[1]
        if not self.groupBulkRead.isAvailable(id_l, self.ADDR_PRESENT_VELOCITY, read_len) or \
           not self.groupBulkRead.isAvailable(id_r, self.ADDR_PRESENT_VELOCITY, read_len):
            return None, None, None, None

        vel_raw_l = self.groupBulkRead.getData(id_l, self.ADDR_PRESENT_VELOCITY, self.LEN_PRESENT_VELOCITY)
        pos_raw_l = self.groupBulkRead.getData(id_l, self.ADDR_PRESENT_POSITION, self.LEN_PRESENT_POSITION)
        
        vel_raw_r = self.groupBulkRead.getData(id_r, self.ADDR_PRESENT_VELOCITY, self.LEN_PRESENT_VELOCITY)
        pos_raw_r = self.groupBulkRead.getData(id_r, self.ADDR_PRESENT_POSITION, self.LEN_PRESENT_POSITION)
        
        # 부호 없는 32비트 -> 부호 있는 값(2의 보수)
        if vel_raw_l > 2**31: vel_raw_l -= 2**32
        if pos_raw_l > 2**31: pos_raw_l -= 2**32
        rpm_l = vel_raw_l / self.RPM_TO_VALUE_SCALE

        if vel_raw_r > 2**31: vel_raw_r -= 2**32
        if pos_raw_r > 2**31: pos_raw_r -= 2**32
        rpm_r = vel_raw_r / self.RPM_TO_VALUE_SCALE

        return rpm_l, rpm_r, pos_raw_l, pos_raw_r