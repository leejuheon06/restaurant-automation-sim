// Open-RMF libraries as back ends for the FryBot Task Manager (path planning, negotiation, task allocation).
//
// Everything below calls Open-RMF's own code unchanged:
//   P  rmf_traffic  agv::Planner + schedule::Database + ScheduleRouteValidator     (traffic-aware path planning)
//   N  rmf_traffic  schedule::Negotiation + agv::SimpleNegotiator                  (robots negotiate their itineraries)
//   T  rmf_task     TaskPlanner with Delivery requests                             (task allocation with task queues)
//
// Line protocol on stdin/stdout, times in seconds relative to "now" of the request:
//   G n m footprint_radius vicinity_radius | n lines "x y" | m lines "a b" (undirected lane)
//   P start goal speed k            | k obstacles: "O npts" + npts lines "x y t"
//        -> "OK w" + w lines "x y t"                      | "FAIL reason"
//   N r k budget_sec                | r lines "start goal speed t0" | k obstacles as above
//        -> "OK" + per robot "R w" + w lines "x y t"      | "FAIL reason"
//   T speed a q greedy              | a lines "waypoint available_time" | q lines "id pickup pickup_wait dropoff dropoff_wait earliest high"
//        -> "OK" + per agent "A n" + n lines "id deployment_time finish_time"   | "FAIL reason"
#include <rmf_traffic/agv/Planner.hpp>
#include <rmf_traffic/agv/RouteValidator.hpp>
#include <rmf_traffic/agv/SimpleNegotiator.hpp>
#include <rmf_traffic/geometry/Circle.hpp>
#include <rmf_traffic/schedule/Database.hpp>
#include <rmf_traffic/schedule/Negotiation.hpp>
#include <rmf_traffic/schedule/Participant.hpp>

#include <rmf_battery/agv/BatterySystem.hpp>
#include <rmf_battery/agv/MechanicalSystem.hpp>
#include <rmf_battery/agv/PowerSystem.hpp>
#include <rmf_battery/agv/SimpleDevicePowerSink.hpp>
#include <rmf_battery/agv/SimpleMotionPowerSink.hpp>
#include <rmf_task/BinaryPriorityScheme.hpp>
#include <rmf_task/TaskPlanner.hpp>
#include <rmf_task/requests/Delivery.hpp>

#include <atomic>
#include <chrono>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std::chrono_literals;
namespace rt = rmf_traffic;

static const std::string MAP = "store";
static const rt::Time T0 = rt::Time(rt::Duration(std::chrono::hours(1000)));
static rt::Time at(double s) { return T0 + rt::time::from_seconds(s); }
static double sec(rt::Time t) { return rt::time::to_seconds(t - T0); }

struct World
{
  rt::agv::Graph graph;
  double fr = 0.0775, vr = 0.0775;

  rt::Profile profile() const
  {
    return rt::Profile{
      rt::geometry::make_final_convex<rt::geometry::Circle>(fr),
      rt::geometry::make_final_convex<rt::geometry::Circle>(vr)};
  }

  // the offline simulation drives straight node to node at constant speed without turning time
  rt::agv::VehicleTraits traits(double speed) const
  {
    return rt::agv::VehicleTraits{{speed, 5.0}, {60.0, 200.0}, profile()};
  }
};

// Other robots that are not being planned: their remaining motion goes into the traffic schedule.
static void read_obstacles(
  std::size_t k, const World& w, const std::shared_ptr<rt::schedule::Database>& db,
  std::vector<rt::schedule::Participant>& keep)
{
  for (std::size_t o = 0; o < k; ++o)
  {
    std::string tag;
    std::size_t npts;
    std::cin >> tag >> npts;
    rt::Trajectory traj;
    for (std::size_t i = 0; i < npts; ++i)
    {
      double x, y, t;
      std::cin >> x >> y >> t;
      traj.insert(at(t), {x, y, 0.0}, {0.0, 0.0, 0.0});
    }
    keep.push_back(rt::schedule::make_participant(
      rt::schedule::ParticipantDescription{
        "other" + std::to_string(o), "frybot", rt::schedule::ParticipantDescription::Rx::Unresponsive, w.profile()},
      db));
    if (traj.size() >= 2)
      keep.back().set(keep.back().assign_plan_id(), {rt::Route{MAP, std::move(traj)}});
  }
}

static void print_itinerary(const char* head, const std::vector<rt::Route>& itinerary)
{
  std::size_t n = 0;
  for (const auto& r : itinerary)
    n += r.trajectory().size();
  std::cout << head << " " << n << "\n";
  for (const auto& r : itinerary)
    for (const auto& p : r.trajectory())
      std::cout << p.position().x() << " " << p.position().y() << " " << sec(p.time()) << "\n";
}

static void cmd_plan(const World& w)
{
  std::size_t start, goal, k;
  double speed;
  std::cin >> start >> goal >> speed >> k;
  auto db = std::make_shared<rt::schedule::Database>();
  std::vector<rt::schedule::Participant> others;
  read_obstacles(k, w, db, others);
  auto me = rt::schedule::make_participant(
    rt::schedule::ParticipantDescription{
      "me", "frybot", rt::schedule::ParticipantDescription::Rx::Responsive, w.profile()}, db);
  rt::agv::Planner::Options options{
    rt::agv::ScheduleRouteValidator::make(db, me.id(), w.profile()), rt::Duration(1s),
    std::shared_ptr<const std::atomic_bool>(nullptr), std::nullopt, std::optional<std::size_t>(40000)};
  const rt::agv::Planner planner{rt::agv::Planner::Configuration{w.graph, w.traits(speed)}, options};
  const auto result = planner.plan(rt::agv::Planner::Start{at(0.0), start, 0.0}, rt::agv::Planner::Goal{goal});
  if (!result)
  {
    std::cout << "FAIL " << (result.disconnected() ? "disconnected" : result.saturated() ? "saturated" : "blocked")
              << std::endl;
    return;
  }
  print_itinerary("OK", result->get_itinerary());
  std::cout.flush();
}

static void cmd_negotiate(const World& w)
{
  std::size_t r, k;
  double budget;
  std::cin >> r >> k >> budget;
  struct Req { std::size_t start, goal; double speed, t0; };
  std::vector<Req> reqs(r);
  for (auto& q : reqs)
    std::cin >> q.start >> q.goal >> q.speed >> q.t0;
  auto db = std::make_shared<rt::schedule::Database>();
  std::vector<rt::schedule::Participant> others;
  read_obstacles(k, w, db, others);

  std::vector<rt::schedule::Participant> robots;
  std::vector<rt::schedule::ParticipantId> ids;
  for (std::size_t i = 0; i < r; ++i)
  {
    robots.push_back(rt::schedule::make_participant(
      rt::schedule::ParticipantDescription{
        "robot" + std::to_string(i), "frybot", rt::schedule::ParticipantDescription::Rx::Responsive, w.profile()},
      db));
    ids.push_back(robots.back().id());
  }
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(budget);
  auto interrupt = std::make_shared<bool>(false);
  std::unordered_map<rt::schedule::ParticipantId, std::unique_ptr<rt::agv::SimpleNegotiator>> negotiators;
  for (std::size_t i = 0; i < r; ++i)
  {
    rt::agv::SimpleNegotiator::Options opt;
    opt.interrupt_flag(interrupt);
    negotiators[ids[i]] = std::make_unique<rt::agv::SimpleNegotiator>(
      robots[i].plan_id_assigner(),
      rt::agv::Planner::Start{at(reqs[i].t0), reqs[i].start, 0.0},
      rt::agv::Planner::Goal{reqs[i].goal},
      rt::agv::Planner::Configuration{w.graph, w.traits(reqs[i].speed)}, opt);
  }

  // The same loop Open-RMF's fleet adapters run: every participant proposes, the others respond to (accommodate or
  // reject) each proposal, until one table holds an itinerary for everybody.
  auto negotiation = rt::schedule::Negotiation::make_shared(db, ids);
  if (!negotiation)
  {
    std::cout << "FAIL make" << std::endl;
    return;
  }
  std::vector<rt::schedule::Negotiation::TablePtr> queue;
  for (const auto id : ids)
    queue.push_back(negotiation->table(id, {}));
  std::size_t rounds = 0;
  while (!queue.empty() && !negotiation->ready())
  {
    if (std::chrono::steady_clock::now() > deadline || ++rounds > 400)
    {
      *interrupt = true;
      break;
    }
    const auto top = queue.back();
    queue.pop_back();
    if (!top || top->defunct())
      continue;
    if (!top->submission())
    {
      negotiators.at(top->participant())->respond(top->viewer(), rt::schedule::SimpleResponder::make(top));
      if (top->submission())
      {
        for (const auto& child : top->children())
          queue.push_back(child);
      }
      else if (const auto parent = top->parent())
      {
        if (parent->rejected())            // the parent has to come up with another proposal
          queue.push_back(parent);
      }
    }
  }
  if (!negotiation->ready())
  {
    std::cout << "FAIL " << (*interrupt ? "timeout" : "no_agreement") << std::endl;
    return;
  }
  const auto winner = negotiation->evaluate(rt::schedule::QuickestFinishEvaluator());
  if (!winner)
  {
    std::cout << "FAIL evaluate" << std::endl;
    return;
  }
  const auto& proposal = winner->proposal();
  std::cout << "OK\n";
  for (std::size_t i = 0; i < r; ++i)
  {
    bool found = false;
    for (const auto& s : proposal)
    {
      if (s.participant == ids[i])
      {
        print_itinerary("R", s.itinerary);
        found = true;
        break;
      }
    }
    if (!found)
      std::cout << "R 0\n";
  }
  std::cout.flush();
}

static void cmd_tasks(const World& w)
{
  double speed;
  std::size_t a, q;
  int greedy;
  std::cin >> speed >> a >> q >> greedy;
  struct Agent { std::size_t wp; double t; };
  std::vector<Agent> agents(a);
  for (auto& g : agents)
    std::cin >> g.wp >> g.t;

  const auto planner = std::make_shared<rt::agv::Planner>(
    rt::agv::Planner::Configuration{w.graph, w.traits(speed)}, rt::agv::Planner::Options{nullptr});
  // battery is not part of this comparison: a very large battery that never needs a recharge
  const auto battery = *rmf_battery::agv::BatterySystem::make(24.0, 1.0e6, 5.0);
  const auto mech = *rmf_battery::agv::MechanicalSystem::make(1.0, 1.0, 0.1);
  const auto power = *rmf_battery::agv::PowerSystem::make(1.0);
  const auto motion = std::make_shared<rmf_battery::agv::SimpleMotionPowerSink>(battery, mech);
  const auto device = std::make_shared<rmf_battery::agv::SimpleDevicePowerSink>(battery, power);
  const rmf_task::TaskPlanner::Configuration config{
    rmf_task::Parameters{planner, battery, motion, device, device},
    rmf_task::Constraints{0.01, 1.0, false},
    rmf_task::BinaryPriorityScheme::make_cost_calculator()};
  rmf_task::TaskPlanner task_planner{config, rmf_task::TaskPlanner::Options{greedy != 0}};

  std::vector<rmf_task::ConstRequestPtr> requests;
  for (std::size_t i = 0; i < q; ++i)
  {
    std::string id;
    std::size_t pickup, dropoff;
    double pw, dw, earliest;
    int high;
    std::cin >> id >> pickup >> pw >> dropoff >> dw >> earliest >> high;
    requests.push_back(rmf_task::requests::Delivery::make(
      pickup, rt::time::from_seconds(pw), dropoff, rt::time::from_seconds(dw), rmf_task::Payload{{}}, id, at(earliest),
      high ? rmf_task::BinaryPriorityScheme::make_high_priority()
           : rmf_task::BinaryPriorityScheme::make_low_priority()));
  }
  std::vector<rmf_task::State> states;
  for (const auto& g : agents)
    states.push_back(rmf_task::State().load_basic(rt::agv::Planner::Start{at(g.t), g.wp, 0.0}, g.wp, 1.0));

  const auto result = task_planner.plan(at(0.0), states, requests);
  const auto assignments = std::get_if<rmf_task::TaskPlanner::Assignments>(&result);
  if (!assignments)
  {
    std::cout << "FAIL planner" << std::endl;
    return;
  }
  std::cout << "OK\n";
  for (const auto& agent : *assignments)
  {
    std::cout << "A " << agent.size() << "\n";
    for (const auto& as : agent)
    {
      const auto finish = as.finish_state().time();
      std::cout << as.request()->booking()->id() << " " << sec(as.deployment_time()) << " "
                << (finish ? sec(*finish) : -1.0) << "\n";
    }
  }
  std::cout.flush();
}

int main()
{
  std::ios::sync_with_stdio(false);
  World w;
  std::string cmd;
  while (std::cin >> cmd)
  {
    if (cmd == "G")
    {
      std::size_t n, m;
      std::cin >> n >> m >> w.fr >> w.vr;
      w.graph = rt::agv::Graph();
      for (std::size_t i = 0; i < n; ++i)
      {
        double x, y;
        std::cin >> x >> y;
        w.graph.add_waypoint(MAP, Eigen::Vector2d{x, y});
      }
      for (std::size_t i = 0; i < m; ++i)
      {
        std::size_t a, b;
        std::cin >> a >> b;
        w.graph.add_lane(a, b);
        w.graph.add_lane(b, a);
      }
      std::cout << "OK 0" << std::endl;
    }
    else if (cmd == "P")
      cmd_plan(w);
    else if (cmd == "N")
      cmd_negotiate(w);
    else if (cmd == "T")
      cmd_tasks(w);
  }
  return 0;
}
