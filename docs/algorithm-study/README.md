# Frybot 알고리즘 학습 자료

2026-11-19 소스 기준. 기존 알고리즘 목록 17개를 순서대로 설명한 43쪽 한국어 자료입니다.

- [PDF 열기](output/pdf/Frybot_Algorithms_Study.pdf): 인쇄·책갈피·논문 링크 포함
- [HTML 열기](Frybot_Algorithms_Study.html): 이미지가 포함된 단독 파일, 클릭 가능한 목차
- [Markdown 원문](study.md): 내용 수정 및 검색
- `assets/`: 직접 제작한 18개 SVG 도식
- `source_snapshot.json`: 분석한 코드의 SHA-256과 함수 위치
- `build_study.py`: SVG·HTML·PDF 재생성 스크립트
- `layout_check.json`: 문서 시트와 PDF 페이지 대응 검증

각 항목은 목적·유래·원리와 그림, 코드 세부 사항·계산 예시·한계·질문을 두 페이지로 나누었습니다. 문헌은 원 논문과 공식 문서를 구분했으며, 프로젝트 고유 규칙에 원 논문을 임의로 지정하지 않았습니다.

기본 설정과 선택 옵션 및 실행 조건을 구분합니다. 코드 상태는 기존 수정 사항이 있는 작업 트리 기준이므로 Git HEAD만으로 재현할 수 없습니다. 제어 코드나 실행 설정은 변경하지 않았습니다.

## 다시 생성하기

Python 3.12, `Noto Sans CJK KR` 시스템 글꼴과 다음 패키지를 사용했습니다.

```bash
python3 -m venv /tmp/frybot-study-venv
/tmp/frybot-study-venv/bin/pip install -r requirements-docs.txt
/tmp/frybot-study-venv/bin/python build_study.py
```

이 명령은 현재 디렉터리의 `study.md`와 워크스페이스 소스를 읽고 도식·HTML·PDF·코드 스냅샷을 갱신합니다. 소스 변경 후 재생성하면 현재 문서 해설과 맞는지도 별도로 검토해야 합니다.

최초 검증: 43개 시트 = PDF 43쪽, 책갈피 61개, 링크 89개. 한글·도표·전체 페이지 배치를 렌더링해 확인했습니다. 도식은 교육용이며 실측 성능 데이터나 실제 마커 인쇄용 이미지가 아닙니다.
