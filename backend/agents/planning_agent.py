"""
规划Agent (Planning Agent)

职责：空间路径生成 —— 基于楼层图数据生成从A到B的文本导航指引
角色边界：不参与对话、不做知识检索、不生成最终回复

这是导航能力的核心 —— 评委最直观感受"智能"的环节
"""
import heapq
from typing import Optional
from backend.agents.base import BaseAgent
from backend.agents.protocol import AgentRole, AgentContext, UserIntent
from backend.knowledge.data_loader import kb_loader
from backend.utils.logger import log


class FloorGraph:
    """
    楼层导航图

    基于 floor_plans.json 中的 graph_edges 构建有向图，
    使用 A* 算法计算两点间最短路径。
    """

    def __init__(self):
        self.nodes: set[str] = set()
        self.edges: dict[str, list[tuple[str, float, dict]]] = {}  # from -> [(to, distance, edge_data)]
        self._node_info: dict[str, dict] = {}  # node_id -> zone info
        self._loaded = False

    def load(self) -> None:
        """从知识库加载图数据"""
        if self._loaded:
            return

        # 加载节点（区域信息）
        floor_plans = kb_loader.get_floor_plans()
        for floor in floor_plans.get("floors", []):
            floor_num = floor["floor"]
            # 添加电梯和楼梯节点
            elevator_id = f"{floor_num}_elevator"
            stair_a_id = f"{floor_num}_stair_a"
            stair_b_id = f"{floor_num}_stair_b"

            self.add_node(elevator_id, {
                "name": f"{floor_num}电梯",
                "floor": floor_num,
                "type": "elevator",
            })
            self.add_node(stair_a_id, {
                "name": f"{floor_num}楼梯A",
                "floor": floor_num,
                "type": "stairs",
            })
            self.add_node(stair_b_id, {
                "name": f"{floor_num}楼梯B",
                "floor": floor_num,
                "type": "stairs",
            })

            # 添加区域节点
            for zone in floor.get("zones", []):
                self.add_node(zone["id"], {
                    "name": zone["name"],
                    "floor": floor_num,
                    "type": "zone",
                    "description": zone.get("description", ""),
                })

        # 加载边
        for edge in floor_plans.get("graph_edges", []):
            self.add_edge(
                edge["from"],
                edge["to"],
                edge.get("distance", 1),
                edge,
            )

        self._loaded = True
        log.info(f"Floor graph loaded: {len(self.nodes)} nodes, {len(self.edges)} edges")

    def add_node(self, node_id: str, info: dict) -> None:
        self.nodes.add(node_id)
        self._node_info[node_id] = info
        if node_id not in self.edges:
            self.edges[node_id] = []

    def add_edge(self, from_node: str, to_node: str, distance: float, edge_data: dict) -> None:
        # 确保节点存在
        if from_node not in self.nodes:
            self.add_node(from_node, {})
        if to_node not in self.nodes:
            self.add_node(to_node, {})
        # 添加双向边
        self.edges.setdefault(from_node, []).append((to_node, distance, edge_data))
        # 反向边（如果原边是walkway，反向也设walkway）
        reverse_data = {**edge_data}
        if edge_data.get("from"):
            reverse_data["from"], reverse_data["to"] = edge_data.get("to", ""), edge_data.get("from", "")
            reverse_data["direction"] = "反向"
        self.edges.setdefault(to_node, []).append((from_node, distance, reverse_data))

    def get_node_info(self, node_id: str) -> Optional[dict]:
        return self._node_info.get(node_id)

    def find_closest_node(self, location_desc: str) -> Optional[str]:
        """
        根据位置描述找到最近的图节点

        Args:
            location_desc: 如 "2F 文学区"、"3F 期刊阅览室"

        Returns:
            节点ID，或 None
        """
        # 精确匹配
        for node_id, info in self._node_info.items():
            name = info.get("name", "")
            if location_desc in name or name in location_desc:
                return node_id

        # 模糊匹配
        for node_id, info in self._node_info.items():
            name = info.get("name", "")
            desc = info.get("description", "")
            combined = name + desc
            for word in location_desc.replace(" ", "").replace("F", ""):
                if word and word in combined:
                    return node_id

        # 默认：1F大厅
        return "zone_1f_lobby"

    def a_star(self, start: str, goal: str) -> Optional[list[tuple[str, float, dict]]]:
        """
        A* 最短路径算法

        Returns:
            路径列表 [(node_id, cumulative_distance, edge_data), ...] 或 None
        """
        if start not in self.nodes or goal not in self.nodes:
            log.warning(f"[Planning] Node not found: start={start}, goal={goal}")
            return None

        # 启发式函数：节点的楼层差（简化，实际可用欧氏距离）
        def heuristic(node: str) -> float:
            start_info = self._node_info.get(start, {})
            goal_info = self._node_info.get(goal, {})
            start_floor = int(start_info.get("floor", "1F")[0])
            goal_floor = int(goal_info.get("floor", "1F")[0])
            return abs(start_floor - goal_floor) * 5  # 楼层差加权

        # (priority, counter, node, g_score, path)
        import itertools
        counter = itertools.count()
        open_set = [(heuristic(start), next(counter), start, 0.0, [])]
        visited = set()

        while open_set:
            _, _, current, g_score, path = heapq.heappop(open_set)

            if current in visited:
                continue
            visited.add(current)

            if current == goal:
                # 构建完整路径（含边信息）
                full_path = []
                for i, (node, _) in enumerate(path):
                    edge_data = {}
                    if i < len(path) - 1:
                        next_node = path[i + 1][0]
                        # 查找边数据
                        for neighbor, dist, data in self.edges.get(node, []):
                            if neighbor == next_node:
                                edge_data = data
                                break
                    full_path.append((node, path[i][1] if i > 0 else 0, edge_data))
                # 添加目标节点
                last_edge = {}
                if path:
                    for neighbor, dist, data in self.edges.get(path[-1][0], []):
                        if neighbor == goal:
                            last_edge = data
                            break
                full_path.append((goal, g_score, last_edge))
                return full_path

            for neighbor, distance, edge_data in self.edges.get(current, []):
                if neighbor in visited:
                    continue
                new_g = g_score + distance
                new_path = path + [(current, new_g)]
                f_score = new_g + heuristic(neighbor)
                heapq.heappush(open_set, (f_score, next(counter), neighbor, new_g, new_path))

        return None


class PlanningAgent(BaseAgent):
    """
    规划Agent — 路径规划与导航生成

    边界：
    - 可以做：路径计算、方向描述生成
    - 不能做：对话交互、知识检索、事实核查
    """

    role = AgentRole.PLANNING
    allowed_actions = ["path_calculation", "directions_generation"]
    forbidden_actions = ["conversation", "knowledge_retrieval", "fact_verification"]

    def __init__(self):
        super().__init__()
        self.graph = FloorGraph()

    async def execute(self, context: AgentContext) -> AgentContext:
        """执行路径规划"""
        # 确保图已加载
        if not self.graph._loaded:
            self.graph.load()

        # Step 1: 确定起点和终点
        start_desc = context.current_location or "1F 入口大厅"
        end_desc = context.target_location

        if not end_desc:
            # 尝试从检索结果中提取位置
            self._extract_target_from_results(context)
            end_desc = context.target_location

        if not end_desc:
            log.warning("[Planning] No target location specified")
            return context

        # Step 2: 找到最近的图节点
        start_node = self.graph.find_closest_node(start_desc)
        end_node = self.graph.find_closest_node(end_desc)

        log.info(f"[Planning] Path: {start_node} → {end_node}")

        # Step 3: A* 路径搜索
        path = self.graph.a_star(start_node, end_node)

        if not path:
            log.warning(f"[Planning] No path found: {start_node} → {end_node}")
            context.path_result = {
                "from_location": start_desc,
                "to_location": end_desc,
                "error": "暂未找到导航路径，请到1F总服务台咨询",
            }
            return context

        # Step 4: 生成文本方向描述
        directions = self._generate_directions(path)

        context.path_result = {
            "from_location": start_desc,
            "to_location": end_desc,
            "from_node": start_node,
            "to_node": end_node,
            "path_nodes": [node for node, _, _ in path],
            "total_distance": path[-1][1] if path else 0,
            "steps": len(directions),
            "directions": directions,
        }

        log.info(f"[Planning] Path generated: {len(directions)} steps")
        return context

    def _extract_target_from_results(self, context: AgentContext) -> None:
        """从检索结果中提取目标位置"""
        for doc in context.search_results:
            metadata = doc.get("metadata", {})
            if metadata.get("type") == "location":
                floor = metadata.get("floor", "")
                zone_name = metadata.get("zone_name", "")
                if floor and zone_name:
                    context.target_location = f"{floor} {zone_name}"
                    return

    def _generate_directions(self, path: list[tuple[str, float, dict]]) -> list[str]:
        """
        将路径节点序列转换为人类可读的导航指令

        Args:
            path: [(node_id, distance, edge_data), ...]

        Returns:
            导航步骤列表
        """
        directions = []
        step_num = 1

        for i, (node, dist, edge_data) in enumerate(path):
            if i == 0:
                # 起点
                info = self.graph.get_node_info(node)
                if info:
                    directions.append(f"您现在位于{info.get('floor', '')}的{info.get('name', node)}")
                continue

            # 边的类型决定指令格式
            edge_type = edge_data.get("type", "walkway")

            if edge_type == "elevator":
                directions.append(f"{step_num}. 乘坐电梯到目标楼层")
                step_num += 1
            elif edge_type == "stairs":
                floor_hint = edge_data.get("direction", "上楼")
                directions.append(f"{step_num}. {floor_hint}")
                step_num += 1
            else:
                # walkway - 普通步行
                direction = edge_data.get("direction", "")
                if direction:
                    directions.append(f"{step_num}. {direction}")
                    step_num += 1

        # 到达提示
        if path:
            last_node = path[-1][0]
            last_info = self.graph.get_node_info(last_node)
            if last_info:
                directions.append(f"🎯 您已到达{last_info.get('name', '目的地')}！")

        return directions


# 全局单例
floor_graph = FloorGraph()
