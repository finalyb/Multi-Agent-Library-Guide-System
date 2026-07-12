"""
知识库数据加载器

从 JSON 文件加载图书馆知识库数据，并提供统一的数据访问接口。
支持FAQ、楼层布局、规章制度三种数据类型。
"""
import json
from pathlib import Path
from typing import Optional
from backend.config import settings
from backend.utils.logger import log


class KnowledgeBaseLoader:
    """知识库数据加载与查询"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or settings.KNOWLEDGE_DIR
        self._faq: list[dict] = []
        self._floor_plans: dict = {}
        self._rules: list[dict] = []
        self._loaded = False

    def load_all(self) -> None:
        """加载所有知识库数据"""
        if self._loaded:
            return

        try:
            self._faq = self._load_json("library_faq.json")
            self._floor_plans = self._load_json("floor_plans.json")
            self._rules = self._load_json("library_rules.json")
            self._loaded = True
            log.info(
                f"Knowledge base loaded: {len(self._faq)} FAQs, "
                f"{len(self._floor_plans.get('floors', []))} floors, "
                f"{len(self._rules)} rules"
            )
        except Exception as e:
            log.error(f"Failed to load knowledge base: {e}")
            raise

    def _load_json(self, filename: str) -> dict | list:
        """加载单个JSON文件"""
        filepath = self.data_dir / filename
        if not filepath.exists():
            log.warning(f"Data file not found: {filepath}")
            return [] if filename != "floor_plans.json" else {}
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    # ===== FAQ 查询 =====

    def get_all_faqs(self) -> list[dict]:
        """获取全部FAQ"""
        self.load_all()
        return self._faq

    def get_faq_by_category(self, category: str) -> list[dict]:
        """按类别查询FAQ"""
        self.load_all()
        return [f for f in self._faq if f.get("category") == category]

    def search_faq_by_keyword(self, keyword: str) -> list[dict]:
        """关键词搜索FAQ（简单匹配）"""
        self.load_all()
        keyword_lower = keyword.lower()
        results = []
        for faq in self._faq:
            text = json.dumps(faq, ensure_ascii=False).lower()
            if keyword_lower in text:
                results.append(faq)
        return results

    def get_faq_categories(self) -> list[str]:
        """获取所有FAQ类别"""
        self.load_all()
        return list(set(f.get("category", "未分类") for f in self._faq))

    # ===== 楼层查询 =====

    def get_floor_plans(self) -> dict:
        """获取完整楼层布局数据"""
        self.load_all()
        return self._floor_plans

    def get_floor(self, floor: str) -> Optional[dict]:
        """获取指定楼层信息"""
        self.load_all()
        for f in self._floor_plans.get("floors", []):
            if f["floor"] == floor:
                return f
        return None

    def get_zone_by_id(self, zone_id: str) -> Optional[dict]:
        """根据zone ID查找区域"""
        self.load_all()
        for floor in self._floor_plans.get("floors", []):
            for zone in floor.get("zones", []):
                if zone["id"] == zone_id:
                    return zone
        return None

    def search_zone_by_name(self, name: str) -> list[dict]:
        """按名称搜索区域"""
        self.load_all()
        results = []
        for floor in self._floor_plans.get("floors", []):
            for zone in floor.get("zones", []):
                if name in zone.get("name", "") or name in zone.get("description", ""):
                    results.append({"floor": floor["floor"], "floor_name": floor["name"], **zone})
        return results

    def get_graph_edges(self) -> list[dict]:
        """获取导航图的边"""
        self.load_all()
        return self._floor_plans.get("graph_edges", [])

    # ===== 规章制度查询 =====

    def get_all_rules(self) -> list[dict]:
        """获取全部规章制度"""
        self.load_all()
        return self._rules

    def get_rules_by_category(self, category: str) -> list[dict]:
        """按类别查询规章制度"""
        self.load_all()
        return [r for r in self._rules if r.get("category") == category]

    # ===== RAG用：将所有知识转为统一的文档格式 =====

    def get_all_documents(self) -> list[dict]:
        """
        获取所有知识库文档（统一格式，用于RAG索引构建）

        Returns:
            [{"id": ..., "content": ..., "metadata": {...}}, ...]
        """
        self.load_all()
        docs = []

        # FAQ文档
        for faq in self._faq:
            docs.append({
                "id": faq["id"],
                "content": f"问题：{faq['question']}\n答案：{faq['answer']}",
                "metadata": {
                    "type": "faq",
                    "category": faq.get("category", ""),
                    "keywords": faq.get("keywords", []),
                },
            })

        # 规章制度文档
        for rule in self._rules:
            docs.append({
                "id": rule["id"],
                "content": f"{rule['title']}：{rule['content']}",
                "metadata": {
                    "type": "rule",
                    "category": rule.get("category", ""),
                },
            })

        # 楼层与区域描述
        for floor in self._floor_plans.get("floors", []):
            for zone in floor.get("zones", []):
                docs.append({
                    "id": zone["id"],
                    "content": f"{floor['floor']} {floor['name']} - {zone['name']}：{zone['description']}。位置提示：{zone.get('navigation_hint', '')}",
                    "metadata": {
                        "type": "location",
                        "floor": floor["floor"],
                        "zone_name": zone["name"],
                    },
                })

        return docs


# 全局单例
kb_loader = KnowledgeBaseLoader()
