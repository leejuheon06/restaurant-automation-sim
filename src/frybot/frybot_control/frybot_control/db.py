"""SQLite store for the central control (table names follow the team's logical data model, state names follow
State Diagram v4). The plan targets MySQL 8.4; this keeps the same tables in a local file so the simulation runs
without a database server."""
import json
import sqlite3
import threading

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
    def __init__(self, path=':memory:'):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.c.executescript(SCHEMA)

    def upsert(self, table, row):
        cols = ','.join(row)
        with self.lock:
            self.c.execute(f'INSERT OR REPLACE INTO {table}({cols}) VALUES({",".join("?" * len(row))})', list(row.values()))
            self.c.commit()

    def insert(self, table, row):
        return self.upsert(table, row)

    def event(self, t, event, detail):
        with self.lock:
            self.c.execute('INSERT INTO event_log(created_at,event,detail) VALUES(?,?,?)',
                           (t, event, json.dumps(detail, ensure_ascii=False)))
            self.c.commit()
