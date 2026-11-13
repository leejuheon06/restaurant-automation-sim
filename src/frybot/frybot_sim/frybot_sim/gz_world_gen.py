"""Generate the Gazebo (gz sim) world of the store from the layout: floor, outer walls, tables and chairs."""
import sys

from frybot_control import layout as L


def box(name, r, z0, h, rgba):
    x, y = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    sx, sy = r[2] - r[0], r[3] - r[1]
    c = ' '.join(str(v) for v in rgba)
    return f'''
    <model name="{name}"><static>true</static><pose>{x:.3f} {y:.3f} {z0 + h / 2:.3f} 0 0 0</pose><link name="link">
      <collision name="c"><geometry><box><size>{sx:.3f} {sy:.3f} {h:.3f}</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>{sx:.3f} {sy:.3f} {h:.3f}</size></box></geometry>
        <material><ambient>{c}</ambient><diffuse>{c}</diffuse></material></visual></link></model>'''


def world_sdf(fortress=False):
    lay = L.to_json()
    m = [box('wall_cook', lay['zones']['wall'], 0, 0.22, (0.15, 0.15, 0.15, 1)),
         box('wall_left', [-0.08, -0.08, -0.06, 1.08], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('wall_bottom', [-0.08, -0.08, 2.04, -0.06], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('wall_top_a', [-0.08, 1.06, 0.12, 1.08], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('wall_top_b', [0.32, 1.06, 2.04, 1.08], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('counter', [2.045, 0.08, 2.11, 0.92], 0, 0.10, (0.8, 0.8, 0.8, 1))]
    for tid, t in lay['tables'].items():
        m.append(box(f'table_{tid}', t['table'], 0, 0.20, (0.55, 0.38, 0.28, 1)))
        for j, c in enumerate(t['chairs']):
            m.append(box(f'chair_{tid}_{j}', c, 0, 0.18, (0.95, 0.95, 0.95, 1)))
    sdf = f'''<?xml version="1.0"?>
<sdf version="1.8"><world name="frybot_store">
  <physics name="1ms" type="ignored"><max_step_size>0.002</max_step_size><real_time_factor>1.0</real_time_factor></physics>
  <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
  <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
  <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
  <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
  <light type="directional" name="sun"><cast_shadows>false</cast_shadows><pose>0 0 10 0 0 0</pose>
    <diffuse>0.9 0.9 0.9 1</diffuse><direction>-0.3 0.2 -0.9</direction></light>
  <model name="floor"><static>true</static><link name="link">
    <collision name="c"><geometry><plane><normal>0 0 1</normal><size>6 4</size></plane></geometry></collision>
    <visual name="v"><geometry><plane><normal>0 0 1</normal><size>6 4</size></plane></geometry>
      <material><ambient>0.95 0.95 0.93 1</ambient><diffuse>0.95 0.95 0.93 1</diffuse></material></visual></link></model>
  {''.join(m)}
</world></sdf>
'''
    if fortress:                       # Fortress (ROS 2 Humble) still uses the ignition names
        sdf = sdf.replace('gz-sim-', 'ignition-gazebo-').replace('gz::sim::systems', 'ignition::gazebo::systems')
    return sdf


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/frybot_store.sdf'
    with open(out, 'w') as f:
        f.write(world_sdf())
    print(out)


if __name__ == '__main__':
    main()
