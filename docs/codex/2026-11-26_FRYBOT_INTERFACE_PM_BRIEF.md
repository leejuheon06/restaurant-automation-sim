# Frybot 인터페이스 PM 브리핑

2026-11-26 Confluence 재조회 · 시험 결과는 11월 25일 작업 기록 기준

## 현재 상태

- **현재 I/F 목록이 가리키는 01~44 적용 기준은 통합 v0.3이다.** 이전 통합 v0.2와 같은 URL이며, 별도의 v0.3 페이지도 남아 있다. 아래 로컬 구현 이력은 개정 전 v0.2 기준 작업을 기록한 것이다. [I/F 목록](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24641549) · [통합 v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) · [별도 v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28573701)
- **11월 25일에는 웹 경로 3건과 ROS 2 이름 8건을 당시 v0.2에 맞춰 변경했다.** 당시 빌드·pytest가 통과했고 경량 시뮬레이션에서 임무 10건을 중단 없이 완료했다. 변경 후 관제와 실기기를 함께 연결한 시험 결과는 이번 검토에서 확인하지 못했다. [적용 및 검증 기록](../2026-11-25_IF_V02_CHECK.md#9-적용-결과)

## PM이 확인할 결정

| 결정 | 권고 및 근거 |
| --- | --- |
| 배포할 ROS 2 주소와 타입 | 19·20번은 통합 v0.3의 `/fms/submit_task`·`/fms/command`와 로컬의 `/frybot/tasks/submit`·`/frybot/tasks/control`이 다르다. 11월 25일 이름 변경 8건을 현행 문서와 다시 대조해 연동 참여 팀과 주소·타입을 합의한다. 안내의 `NavigateRoute`와 서빙·조리 팔의 `ArmJob` 사용은 이미 통합 v0.3에 반영돼 있다. [통합 v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) · [로컬 서비스 등록](../../src/frybot/frybot_control/frybot_control/task_manager_node.py#L98) |
| 실기기 정지와 재가동 | 문서 33·35번의 통신 감시 기준은 2초, 로컬 기본값은 1초다. 시험에 사용할 설정을 합의하고 통신 두절·관제 재시작 때 주행과 팔의 실제 정지를 확인한다. 정지 요청 접수, 정지 상태 보고, 현장 점검 후 재가동 승인을 각각 확인한다. [통합 v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) · [로컬 AMR 설정](../../src/frybot/frybot_mobile/frybot_mobile/mobile_controller.py#L208) · [재가동 요청](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26116147) |
| 주문·방문 데이터의 완료 기준 | 웹에서 4초 응답 대기를 끝낸 뒤 같은 요청을 재전송해도 주문이 한 번만 생성되고 결과를 다시 확인할 수 있어야 한다. 테이블 재사용 뒤 이전 방문의 요청이 새 방문에 적용되지 않는지도 확인한다. [코드 수정 항목](2026-11-25_FRYBOT_INTERFACE_COMPARISON.md#2-코드-수정이-필요한-부분) |
| 서빙 완료와 AI 인수 범위 | 현재 서빙 완료는 팔의 `UNLOAD` 성공을 기준으로 한다. 음식이 테이블에 실제로 놓였다는 확인 방식과 결과가 불분명할 때의 운영 절차를 정한다. AI 관측·카메라 전송은 현행 문서 38·39번에서도 설계 상태다. 이번 인수에 포함하면 오래된 관측을 버리는 조건을 확인한다. [서빙 완료 판단](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25755717) · [통합 v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) |

## 진척 보고에 쓸 문장

> 11월 25일 이름 변경은 빌드와 경량 시뮬레이션을 통과했습니다. 현행 통합 v0.3과 로컬의 연동 주소 차이를 먼저 정리하고, 정지·재가동, 주문 중복 방지, 실물 서빙 완료를 통합 시험에서 확인해야 합니다.
