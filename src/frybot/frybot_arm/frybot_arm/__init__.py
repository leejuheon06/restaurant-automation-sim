"""Frybot Cooking Package: 조리 팔 A(치킨) / B(웍)의 소프트웨어.

SW 아키텍처 v016 대응:
  FrybotArm Master Controller -> master_controller.py
  FrybotArm Controller        -> arm_controller.py
  Camera Streamer             -> camera_streamer.py
"""

# 조리 팔 ID. frybot_control/layout.py 의 COOK_ARMS 키와 같아야 함.
ARM_IDS = ('cook_arm_a', 'cook_arm_b')

# Task Manager 가 조리 팔 작업을 보내는 액션 (Master Controller 가 받음).
MASTER_ACTION = '/frybot_arm/arm_job'
