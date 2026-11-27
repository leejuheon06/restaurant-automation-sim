"""Pinky Pro 배터리 값 발행 노드(실기기 전용, robot.launch.py 가 띄움).

pinkylib.Battery 로 읽은 잔량을 battery/percent, 전압(V)을 battery/voltage
(둘 다 std_msgs/Float32)로 5초마다 낸다. 잔량은 mobile_controller 가
battery_topic 으로 받아 % 로 쓰고, 전압은 pinky_driver 가 저전압 경고에 쓴다.
"""
# [수정 2026-11-17] pinky_pro 의존 제거: pinky_pro(pinklab-art, Apache-2.0,
# 커밋 014a09f)의 pinky_bringup/battery_publisher.py 를 복사함.
# [수정 2026-11-18] P2(D3): 원본의 노드 이름 battery_publihser 는 오타라,
# 실행 파일과 같은 pinky_battery 로 바꿈. 동작은 바꾸지 않고 이름만 바꿈
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from pinkylib import Battery 

class BatteryPublisher(Node):
    """배터리 잔량·전압을 주기적으로 발행하는 노드."""

    def __init__(self):
        super().__init__('pinky_battery')
        
        self.battery = Battery()  # pinkylib 의 배터리 읽기 객체(로봇에만 설치)

        # 잔량 토픽. 값 범위(0~100 인지)는 pinkylib 로 확인 필요(R2-3)
        self.percentage_publisher = self.create_publisher(
            Float32,
            'battery/percent',
            10
        )
        
        # 전압 토픽(V): pinky_driver 의 저전압 경고(6.8 V 이하)용
        self.voltage_publisher = self.create_publisher(
            Float32,
            'battery/voltage',
            10
        )

        # 두 값 모두 5초(timer_period) 주기로 따로 발행
        self.timer_period = 5.0
        self.percentage_timer = self.create_timer(self.timer_period, self.percentage_callback)
        self.voltage_timer = self.create_timer(self.timer_period, self.voltage_callback)

    def percentage_callback(self):
        """배터리 잔량을 읽어 battery/percent 로 발행한다."""
        pct_msg = Float32()
        pct_msg.data = float(self.battery.battery_percentage())
        self.percentage_publisher.publish(pct_msg)

    def voltage_callback(self):
        """배터리 전압(V)을 읽어 battery/voltage 로 발행한다."""
        volt_msg = Float32()
        volt_msg.data = float(self.battery.get_voltage()) 
        self.voltage_publisher.publish(volt_msg)

def main(args=None):
    """pinky_battery 노드를 띄운다.

    Args:
        args: rclpy.init 에 넘길 명령행 인자.
    """
    rclpy.init(args=args)
    
    publisher = BatteryPublisher()
    
    try:
        rclpy.spin(publisher)
    except KeyboardInterrupt:
        pass
    finally:
        publisher.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
