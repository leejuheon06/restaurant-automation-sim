"""Bring a robot's Nav2 stack up when its lifecycle manager did not finish the start-up.

With Gazebo and several Nav2 stacks starting together, a lifecycle `change_state` response is sometimes lost
("failed to send response ... (timeout)"). The lifecycle manager then waits for that response for ever: its nodes
stay unconfigured / inactive, the robot never drives, and the manager no longer answers its own services either.

So this node does not go through the manager. After a grace period it reads the lifecycle state of every Nav2 node
of every robot and, where a node is not active, sends the missing transitions itself (configure, then activate),
one node after the other in start-up order.

Nav2 lifecycle 관리자가 기동을 끝내지 못한 로봇의 Nav2 노드를 이 노드가
직접 configure → activate 한다(gazebo.launch.py 에서만 띄움). 유예 시간
뒤에도 active 가 아닌 노드를 기동 순서대로 한 단계씩 민다.
"""
import rclpy
from lifecycle_msgs.msg import State, Transition
from lifecycle_msgs.srv import ChangeState, GetState
from rclpy.node import Node

# 로봇마다 감시할 Nav2 lifecycle 노드 이름
NODES = ['controller_server', 'planner_server', 'bt_navigator', 'docking_server']        # start-up order


class Watchdog(Node):
    """로봇들의 Nav2 노드 lifecycle 상태를 2초마다 보고 기동을 마저 한다."""
    def __init__(self):
        super().__init__('nav2_watchdog')
        # robot_ids: 감시할 로봇 이름(gazebo.launch.py 가 넘김)
        self.robots = self.declare_parameter('robot_ids', ['pinky1', 'pinky2', 'pinky3']).value
        self.grace = self.declare_parameter('grace_sec', 25.0).value        # wall seconds the manager gets first
        # (로봇, 노드)마다 상태 조회·상태 전이 서비스 클라이언트
        self.get = {(r, n): self.create_client(GetState, f'/{r}/{n}/get_state') for r in self.robots for n in NODES}
        self.chg = {(r, n): self.create_client(ChangeState, f'/{r}/{n}/change_state')
                    for r in self.robots for n in NODES}
        self.state = {k: None for k in self.get}       # last known lifecycle state id
        self.asked = {k: -100.0 for k in self.get}     # when we last sent a transition
        # seen: 로봇의 서비스가 처음 다 보인 시각, ok: Nav2 가 active 인 로봇
        self.seen, self.ok = {}, set()
        self.t = 0.0  # 경과 시간(타이머마다 2초씩 더함)
        self.create_timer(2.0, self._tick)  # 2초마다 점검

    # 상태를 다시 조회하고(결과는 다음 틱에 씀), 유예 시간이 지났는데
    # active 가 아니면 첫 비활성 노드에 configure/activate 를 보냄.
    # 같은 노드에는 10초에 한 번만 보냄
    def _tick(self):
        self.t += 2.0
        for r in self.robots:
            # 그 로봇의 Nav2 노드 서비스가 아직 다 안 떴으면 건너뜀
            if not all(self.get[(r, n)].service_is_ready() for n in NODES):
                continue
            self.seen.setdefault(r, self.t)
            for n in NODES:
                self.get[(r, n)].call_async(GetState.Request()).add_done_callback(
                    lambda f, k=(r, n): self._got(f, k))
            states = [self.state[(r, n)] for n in NODES]
            if all(s == State.PRIMARY_STATE_ACTIVE for s in states):
                if r not in self.ok:
                    self.ok.add(r)
                    self.get_logger().info(f'{r}: Nav2 active')
                continue
            self.ok.discard(r)
            if self.t - self.seen[r] < self.grace:
                continue                                   # the lifecycle manager may still be working on it
            for n in NODES:                                # first node that is not active: push it one step
                s = self.state[(r, n)]
                if s == State.PRIMARY_STATE_ACTIVE:
                    continue
                tr = {State.PRIMARY_STATE_UNCONFIGURED: Transition.TRANSITION_CONFIGURE,
                      State.PRIMARY_STATE_INACTIVE: Transition.TRANSITION_ACTIVATE}.get(s)
                if tr is not None and self.t - self.asked[(r, n)] >= 10.0 and self.chg[(r, n)].service_is_ready():
                    self.asked[(r, n)] = self.t
                    what = 'configure' if tr == Transition.TRANSITION_CONFIGURE else 'activate'
                    self.get_logger().warn(f'{r}: {n} is not active after start-up, sending {what}')
                    self.chg[(r, n)].call_async(ChangeState.Request(transition=Transition(id=tr)))
                break

    # 상태 조회 응답의 현재 상태 id 를 저장
    def _got(self, fut, key):
        if fut.result() is not None:
            self.state[key] = fut.result().current_state.id


def main():
    """nav2_watchdog 노드를 띄우고 Ctrl+C 까지 돈다."""
    rclpy.init()
    try:
        rclpy.spin(Watchdog())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
