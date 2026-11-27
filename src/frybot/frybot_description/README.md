# frybot_description

FryBot이 쓰는 로봇 모델입니다. 외부 저장소에서 쓰는 파일만 복사해 온 것이라, `pinky_pro`와 `mycobot_ros2`를 받지 않아도 빌드·실행됩니다.

| 폴더 | 내용 | 출처 | 라이선스 |
| --- | --- | --- | --- |
| `pinky/urdf`, `pinky/meshes` | Pinky Pro xacro와 메시 | [pinklab-art/pinky_pro](https://github.com/pinklab-art/pinky_pro) `pinky_description`, 커밋 014a09f | Apache-2.0 (`licenses/pinky_pro_LICENSE`) |
| `jetcobot` | JetCobot 280 = myCobot 280 Pi URDF와 메시 | [elephantrobotics/mycobot_ros2](https://github.com/elephantrobotics/mycobot_ros2) `mycobot_description/urdf/mycobot_280_pi`, 커밋 d42ff61 | BSD-2-Clause (`licenses/mycobot_description_LICENSE`) |

## 원본과 다른 점 (2026-11-17)

- 경로: `$(find pinky_description)/urdf` → `$(find frybot_description)/pinky/urdf`, `package://pinky_description/meshes` → `package://frybot_description/pinky/meshes`, `package://mycobot_description/urdf/mycobot_280_pi/` → `package://frybot_description/jetcobot/`
- `pinky/urdf/pinky_gz.urdf.xacro`: 램프 효과 플러그인(`pinky_gz_sim::LampControlPlugin`) 참조를 뺌. `pinky_gz_sim`을 빌드해야 하는 C++ 플러그인이고 주행·센서와 무관함
- myCobot은 `mycobot_280_pi.urdf`가 가리키는 메시(`G_base`, `joint1_pi`, `joint2`~`joint7`)와 그 텍스처만 가져옴. 그리퍼·펌프·카메라 플랜지 변형은 없음

원본이 바뀌면 같은 파일을 다시 복사하고 위 치환을 적용합니다.
