"""Packaged maps and the graph stored in each map's ROS coordinate frame."""
import base64
import json
import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import yaml

# 지도 폴더들의 위치: 패키지 안 maps/<map_id>/ (setup.py 의 package_data 로
# 설치됨. --symlink-install 이면 소스 폴더)
MAP_ROOT = Path(__file__).with_name('maps')
# [수정 2026-11-17] 가상 매장 도면(layout.py 의 200x100 cm)도 maps/proto 에
# 저장하고 지도 이름 'proto' 로 고름. 주행 그래프와 테이블 정보는 계속
# layout.py 가 만들므로, 'proto' 는 코드 안에서 실측 지도가 아닌 것('')으로 봄
PROTO_MAP_ID = 'proto'
PROTO_LABEL = '가상 매장 도면 · proto'  # 지도 목록에 보일 이름


# [수정 2026-11-18] P1(D1): 지도를 쓰는 ROS 노드는 지도 이름 없이 뜨지 않음.
# 예전에는 FRYBOT_MAP_ID 가 없으면 조용히 가상 매장 도면(proto)으로 떴음.
# 오프라인 도구(fleet_bench, replay_run, pytest)는 active_map_id
# 로 빈 값을 proto 로 읽는 지금 동작을 그대로 씀
# [수정 2026-11-20] 위 줄에서 지운 selected_map_id 를 뺌
def require_map_id(node_name: str) -> str:
    """ROS 노드가 쓸 지도 이름을 돌려준다. 없으면 노드를 멈춘다.

    Args:
        node_name: 오류 안내에 쓸 노드 이름.

    Returns:
        환경 변수 FRYBOT_MAP_ID 의 값('proto' 또는 실측 지도 이름).

    Raises:
        RuntimeError: FRYBOT_MAP_ID 가 없거나 비었을 때.
    """
    map_id = os.environ.get('FRYBOT_MAP_ID', '')
    if not map_id:
        raise RuntimeError(
            f'{node_name}: 지도 이름(FRYBOT_MAP_ID)이 없습니다. 런치'
            f'(real.launch.py map_id:=..., sim.launch.py)로 띄우거나 '
            f'FRYBOT_MAP_ID 를 지정하세요. 쓸 수 있는 값: '
            f'{[PROTO_MAP_ID] + map_ids()}')
    return map_id


def active_map_id() -> str:
    """실행 중인 실측 지도의 이름을 돌려준다.

    Returns:
        실측 지도 이름. 가상 매장 도면(proto)이면 빈 문자열.
    """
    map_id = os.environ.get('FRYBOT_MAP_ID', '')
    return '' if map_id == PROTO_MAP_ID else map_id


def map_ids():
    """실측 지도 이름 목록(가상 매장 도면 proto 는 넣지 않음).

    roadmap.json 이 있는 maps/ 아래 폴더만 지도로 친다.

    Returns:
        이름순으로 정렬한 지도 이름 목록.
    """
    return sorted(path.name for path in MAP_ROOT.iterdir()
                  if path.is_dir() and path.name != PROTO_MAP_ID
                  and (path / 'roadmap.json').is_file())


@lru_cache
def profile(map_id):
    """지도 폴더의 roadmap.json 을 읽어 돌려준다(지도마다 한 번만 읽음).

    lru_cache 로 같은 dict 를 계속 돌려주므로 호출하는 쪽은 값을 바꾸지
    않아야 한다.

    Args:
        map_id: 지도 이름('proto' 또는 실측 지도 이름).

    Returns:
        roadmap.json 내용(label, map_yaml, nodes, edges, homes 등)에
        'id'(지도 이름)와 'yaml'(Nav2 지도 설정 파일의 절대 경로)을 더한 dict.

    Raises:
        ValueError: 목록에 없는 지도 이름일 때.
    """
    if map_id != PROTO_MAP_ID and map_id not in map_ids():
        raise ValueError(f'Unknown FryBot map: {map_id}')
    folder = MAP_ROOT / map_id
    with (folder / 'roadmap.json').open() as stream:
        graph = json.load(stream)
    graph['id'] = map_id
    graph['yaml'] = str(folder / graph['map_yaml'])
    return graph


# [수정 2026-11-26] 2단계 보완(기획 결정): 지도 단위 후진 도킹 설정.
# 실측 지도는 roadmap.json 의 "dock_backwards"(없으면 true), 가상 매장은 false
def dock_backwards(map_id: str) -> bool:
    """그 지도의 도크에 뒤로 들어가는지 돌려준다.

    Args:
        map_id: 지도 이름. '' 또는 'proto' 면 가상 매장.

    Returns:
        가상 매장은 False(앞 카메라로 마커를 보며 전진 도킹). 실측 지도는
        roadmap.json 의 "dock_backwards" 값, 키가 없으면 True(2026-11-26
        결정: 모든 도크 후진).

    Raises:
        ValueError: 목록에 없는 지도 이름일 때(profile).
    """
    if not map_id or map_id == PROTO_MAP_ID:
        return False
    return bool(profile(map_id).get('dock_backwards', True))


@lru_cache
def map_display(map_id):
    """관리자 화면에 그릴 지도 정보를 돌려준다(web_service 의 /api/map).

    Args:
        map_id: 지도 이름.

    Returns:
        id, label, nodes, edges, homes, 지도 원점(origin)·해상도
        (resolution)·픽셀 크기(width, height), 회색조 PNG 를 data URL 로
        담은 image 를 가진 dict.

    Raises:
        ValueError: 목록에 없는 지도 이름일 때(profile 에서).
    """
    # PIL 은 이 함수에서만 쓰므로 여기서 가져옴(로봇 쪽은 불러오지 않음)
    from PIL import Image

    graph = profile(map_id)
    yaml_path = Path(graph['yaml'])
    with yaml_path.open() as stream:
        metadata = yaml.safe_load(stream)
    with Image.open(yaml_path.parent / metadata['image']) as image:
        width, height = image.size
        # 웹 화면이 바로 그릴 수 있게 회색조 PNG 로 바꿔 메모리에 씀
        png = BytesIO()
        image.convert('L').save(png, format='PNG')
    return {
        'id': map_id, 'label': graph['label'], 'nodes': graph['nodes'], 'edges': graph['edges'],
        'origin': metadata['origin'], 'resolution': metadata['resolution'],
        'width': width, 'height': height, 'homes': graph['homes'],
        'image': 'data:image/png;base64,' + base64.b64encode(png.getvalue()).decode('ascii'),
    }
