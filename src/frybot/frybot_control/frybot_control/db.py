"""SQLite store for the central control (table names follow the team's logical data model, state names follow
State Diagram v4). The plan targets MySQL 8.4; this keeps the same tables in a local file so the simulation runs
without a database server."""
import json
import sqlite3
import threading

# 표 정의. 상태 이름은 restaurant.py 와 같고 task 는 관제의 임무 이벤트를,
# incident 는 임무 보류(SUSPENDED) 기록을, event_log 는 실행 로그를 담음.
# uk_visit_active_table: 한 테이블에 진행 중인 방문이 둘 생기지 않게 막음
SCHEMA = '''
CREATE TABLE IF NOT EXISTS dining_table(table_id INTEGER PRIMARY KEY, seats INT, status TEXT, visit_id INT, updated_at REAL);
CREATE TABLE IF NOT EXISTS visit(visit_id INTEGER PRIMARY KEY, party_size INT, table_id INT, status TEXT, created_at REAL, seated_at REAL, ended_at REAL);
CREATE UNIQUE INDEX IF NOT EXISTS uk_visit_active_table ON visit(table_id) WHERE status IN ('ASSIGNED','GUIDING','SEATED','GUIDE_FAILED');
CREATE TABLE IF NOT EXISTS orders(order_id INTEGER PRIMARY KEY, visit_id INT, table_id INT, status TEXT, created_at REAL, completed_at REAL);
CREATE TABLE IF NOT EXISTS order_item(item_id INTEGER PRIMARY KEY, order_id INT, menu TEXT, status TEXT, cook_task_id TEXT, serve_task_id TEXT, ready_at REAL, delivered_at REAL);
CREATE TABLE IF NOT EXISTS task(task_id TEXT PRIMARY KEY, task_type TEXT, state TEXT, robot_id TEXT, visit_id INT, order_id INT, item_id INT, table_id INT, reason TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS incident(incident_id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, robot_id TEXT, task_id TEXT, order_id INT, error_code TEXT, failed_state TEXT, result TEXT, occurred_at REAL, resolved_at REAL);
CREATE TABLE IF NOT EXISTS event_log(log_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, event TEXT, detail TEXT);
'''


class Store:
    """중앙 관제의 SQLite 저장소(실행 폴더의 frybot.db).

    ROS 콜백과 AI 결과 수신(HTTP) 스레드가 함께 쓰므로 연결 하나를
    check_same_thread=False 로 열고 lock 으로 쓰기를 한 번에 하나씩 한다.

    Args:
        path: DB 파일 경로. 기본값은 메모리 DB(파일 없음).
    """

    def __init__(self, path=':memory:'):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.c.executescript(SCHEMA)

    def upsert(self, table, row):
        """한 행을 넣거나 같은 기본 키의 행을 바꾼다(INSERT OR REPLACE).

        표·열 이름은 SQL 에 그대로 들어가므로 코드 안의 고정 이름만 넘긴다.

        Args:
            table: 표 이름(SCHEMA 의 표).
            row: 열 이름 -> 값.
        """
        cols = ','.join(row)
        with self.lock:
            self.c.execute(f'INSERT OR REPLACE INTO {table}({cols}) VALUES({",".join("?" * len(row))})', list(row.values()))
            self.c.commit()

    def event(self, t, event, detail):
        """실행 로그 한 줄을 event_log 표에 더한다.

        Args:
            t: 시각(unix 초).
            event: 이벤트 이름.
            detail: 내용. JSON 문자열로 저장한다.
        """
        with self.lock:
            self.c.execute('INSERT INTO event_log(created_at,event,detail) VALUES(?,?,?)',
                           (t, event, json.dumps(detail, ensure_ascii=False)))
            self.c.commit()
