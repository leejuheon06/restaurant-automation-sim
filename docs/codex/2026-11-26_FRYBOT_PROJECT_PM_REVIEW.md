# FryBot 프로젝트 PM 검토

2026-11-26 · Confluence 프로젝트 공간과 FryBot 로컬 작업 기록 기준

**11월 27일 Sprint 4의 목표는 기능 20%, 2차 전체 연동시험, 릴리즈 v0.2와 시험 보고서다.** 1차 연동시험에서 실물 서빙·복귀는 확인했다. 2차 시험 계획은 11월 25일 스탠드업에서 진행 중이었고, 이번 조회에서 합격 결과나 릴리즈 증빙은 확인하지 못했다. 릴리즈 v0.2와 인터페이스 정의서 v0.3은 서로 다른 버전 체계다. [스프린트 일정표](https://oneteam1.atlassian.net/wiki/spaces/1/pages/7307279) · [11월 25일 스탠드업](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28672002) · [현행 통합 I/F](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124)

## 1. 기획과 요구사항

- 프로젝트 목표는 고객 접수·테이블 배정 → AMR 안내 → 주문 → 조리 → 서빙 → 이용 종료·식기 회수 → 테이블 재개방까지 이어지는 무인 레스토랑 시연이다. 관리자 관제, 장비 장애 대응, 임무 복구도 요구사항에 들어 있다. 헌장 초안은 전체 데모 영상, 구성원별 기능, 개발 기록, 정량 결과를 산출물로 제시한다. [프로젝트 헌장](https://oneteam1.atlassian.net/wiki/spaces/1/pages/8552449) · [UR v2](https://oneteam1.atlassian.net/wiki/spaces/1/pages/11370552) · [전체 시나리오 v2](https://oneteam1.atlassian.net/wiki/spaces/1/pages/294935)
- SR v2에서 2인석 4개·4인석 2개, 중복 배정 방지, 고객 동행 이탈 시 감속·정지, 치킨·볶음밥 조리, 실물 접시 적재·하역, 통행 우선순위, 식기 회수 후 테이블 재개방은 `R`로 표시돼 있다. 통합 조회, 충전·가용 조회, 운영 이력 조회 일부는 `O`로 표시돼 있다. Sprint 4의 기능 20%를 판정하려면 이번 릴리즈에서 검증할 UR/SR ID를 정해야 한다. [SR v2](https://oneteam1.atlassian.net/wiki/spaces/1/pages/12386314) · [스프린트 일정표](https://oneteam1.atlassian.net/wiki/spaces/1/pages/7307279)

## 2. 설계에서 확인한 점과 결정 사항

| 영역 | 확인한 내용 | PM이 정할 것 |
| --- | --- | --- |
| 고객·관리자 화면 | 키오스크, 테이블 주문, 관리자 관제 화면은 React 목업과 OpenAPI가 있다. 개발표준은 React → FastAPI → MySQL·ROS 2를 그리고, 로컬 FryBot은 자체 웹과 SQLite로도 동작한다. [GUI 구현](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24707508) · [개발표준](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24445808) | 2차 시험에서 어느 화면·백엔드·DB 조합을 쓸지, 방문·테이블·주문 상태를 누가 갱신할지 지정한다. |
| 데이터·실행 식별자 | ERD v3는 공개 MySQL 기준선이고 통합 ERD v0.2는 중복 제거·음식 단위·실행 시도 모델을 추가하는 설계안이다. ERD 설계안의 임무 ID는 중앙 관제 DB가 발급하는 `BIGINT`와 ROS `int32`를 전제한다. 현행 I/F 19번은 Task Manager 발급 문자열로 정의한다. [ERD v3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25034755) · [통합 ERD v0.2](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26214609) · [통합 I/F v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) | 임무 ID의 발급 주체와 전송·저장 타입, 주문 재전송 처리와 결과 조회의 책임을 확정한다. |
| ROS 2·장비 연동 | 아키텍처는 관제와 AI 서버, AMR 본체·서빙 팔, 조리 마스터·조리 팔 A/B를 구분한다. 현행 I/F와 로컬은 19·20번 서비스 주소·타입이 다르고, 2차 ROS 계약 문서에도 v0.2 후보가 남아 있다. [시스템 아키텍처](https://oneteam1.atlassian.net/wiki/spaces/1/pages/786434) · [2차 ROS 계약](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26771458) · [I/F 검토](2026-11-26_FRYBOT_INTERFACE_PM_BRIEF.md) | 시험 빌드와 장비 배포본, ROS 주소·타입, 맵 버전을 운영 담당자와 함께 고정한다. |
| 상태·완료·복구 | 상태도와 시퀀스는 명령 수락, 실행 완료, 결과 미확정, 복구 승인을 분리한다. 서빙은 코드상 `UNLOAD` 성공 뒤 완료 처리되며 실물 전달 확인은 별도 결정 항목이다. [기기 상태도](https://oneteam1.atlassian.net/wiki/spaces/1/pages/13697058) · [서비스 시퀀스](https://oneteam1.atlassian.net/wiki/spaces/1/pages/13303809) · [서빙](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25755717) | 접시 인계·전달·회수 각각의 완료 근거를 정한다. 결과가 불분명할 때 재실행 전에 확인하는 절차와 정지 후 재가동 승인자를 정한다. |
| 비전·자동 퇴식 | SR은 태블릿 이용 종료와 의자 QR을 다룬다. CCTV 실험은 빈자리 상태 전환을 확인했으며 5분 빈자리 판정부터 실제 AMR 회수 호출까지의 검증은 남아 있다. 손님 안내용 YOLO11s는 추론 속도 기준 1차 선정이며 실제 안내 정확도 검증은 별도다. AMR 카메라 시험은 TCP, 통합 I/F 39번은 UDP 설계다. [SR v2](https://oneteam1.atlassian.net/wiki/spaces/1/pages/12386314) · [CCTV 실험](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28475396) · [AMR AI 시험](https://oneteam1.atlassian.net/wiki/spaces/1/pages/29491202) · [현행 I/F](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) | 데모에서 이용 종료를 확정할 입력과 자동 회수 범위를 정한다. 영상·AI가 포함되면 실제 카메라 경로와 관측 만료 시 동작을 시험한다. |
| 담당과 의사결정 | 역할표는 과제마다 최종 책임자 `A` 1명을 제시하면서 범위·일정·관제·통합 시연 등 일부 행에 복수 `A`가 남아 있다. 11월 25일 스탠드업에는 이주헌이 PM과 로봇팔·AMR로 기록돼 있다. [역할표](https://oneteam1.atlassian.net/wiki/spaces/1/pages/5111810) · [11월 25일 스탠드업](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28672002) | 2차 시험 범위, 장비 진행·중단, 릴리즈 판정의 최종 책임자를 각각 한 명으로 확인한다. |

## 3. 시험 증빙과 Sprint 4에서 남길 결과

- **1차 실기기 시험:** 서빙 4건 완료, 서빙 후 복귀, 2대 회피 시나리오, ESTOP 정지가 보고됐다. 시험 중 도킹 벽 접촉, 초기 위치 추정 실패, 근접·위치 추정 틀어짐이 있었고, 최종 회피 실행의 최소 중심 거리는 14.5 cm로 당시 비교 기준 15.5 cm보다 작았다. 1차 보고서는 해당 수정의 실기기 재검증을 남겨 뒀다. 시험 빌드는 `4ab5d33`에 미커밋 변경이 포함된 상태였다. [1차 전체 연동테스트](https://oneteam1.atlassian.net/wiki/spaces/1/pages/27918499)
- **11월 25일 인터페이스 변경:** 빌드·pytest와 경량 시뮬레이션의 임무 10건 완료가 기록됐다. 2차 결과를 정리할 때 이 기록과 실기기 통합 결과를 각각 근거로 남긴다. 현행 I/F의 통신 감시 2초, 정량 목표와 로컬 코드의 1초 차이는 시험 설정을 확정할 때 반영한다. [로컬 적용 기록](../2026-11-25_IF_V02_CHECK.md#9-적용-결과) · [통행 허가](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25788458) · [정량적 목표](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28082190)
- **정량 목표:** 서빙 임무 완수율 95% 이상(20회 이상), ESTOP 0.5초·4 cm 이내, 도착 오차 중앙값 1.5 cm·최대 3 cm 이하, 위치 추정 오차 2 cm·3도 이하와 위치 튐 0건, 3대 30분 운전에서 1초 초과 상태 보고 끊김 0건이다. 프로젝트 목표 문서의 수치이며, 현재 달성 판정은 별도 실측 결과가 필요하다. [정량적 목표](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28082190)
- **2차 시험 범위 제안:** 대표 메뉴 하나로 접수 → 중복 없는 주문 → 조리 및 인계 → 실물 서빙을 연결한다. 결과 미확정 시 조회, 통신 두절과 정지·현장 재가동, 도킹·근접 재시험을 함께 기록한다. 시험 보고서에는 UR/SR, 빌드·장비·맵, 실제 결과, 재시험 담당자를 남긴다. 독립 검증한 조리·AI·회수는 연결된 구간까지 증빙한다. [2차 연동시험 계약](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26771458) · [개발표준](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24445808)

## 일정표에 적힌 다음 마일스톤

| 날짜 | 계획상 목표 |
| --- | --- |
| 11월 27일 | 릴리즈 v0.2, 기능 20%, 2차 전체 연동시험 |
| 12월 4일 | 릴리즈 v0.3, 기능 50%, 3차 전체 연동시험 |
| 12월 10일 | 릴리즈 v0.4, 기능 80%, 4차 전체 연동시험 |
| 12월 18일 | 릴리즈 v0.5, 기능 100%, 5차 전체 연동시험 |
| 12월 24일 | 릴리즈 v1.0, 안정화, 최종 연동시험과 Validation Report |
| 12월 28~29일 | 최종 발표와 데모 |

일정표의 상태 표시는 11월 9일 기준이다. 위 표에는 계획 일자를 사용했다. [스프린트 일정표](https://oneteam1.atlassian.net/wiki/spaces/1/pages/7307279)

## 검토 범위

Confluence 프로젝트 공간의 검색 결과 209건에서 페이지 208개 본문을 조회했다. 기획·역할·일정, UR/SR, 시나리오, 아키텍처·지도, 화면, 데이터·ERD, ROS 2/I/F, 기술조사, 회의·업무 기록, 시험·검증을 대조했다. 주요 설계 첨부 16건도 조회해 HW/SW 아키텍처·지도·화면 시안을 확인하고 시퀀스·상태도·ERD 원본 구성을 확인했다. 첨부 영상 재생과 다른 시스템에 연결된 외부 자료는 이번 검토 범위 밖이며, 새 실기기 시험은 수행하지 않았다.
