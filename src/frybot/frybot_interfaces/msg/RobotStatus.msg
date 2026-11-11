builtin_interfaces/Time stamp
string robot_id
string state          # IDLE MOVING WAIT_GRANT PAUSED_GUEST ARM_BUSY CHARGING E_STOP
float64 x
float64 y
float64 yaw
float32 battery       # 0..100
bool charging
string task_id
int32 plan_version
int32 reached_index   # index of last reached waypoint of the active route (-1 none)
string node_id        # last reached roadmap node
string arm_state      # IDLE or current arm job
string error
