#!/usr/bin/env python3
"""
MySQL 馆藏数据 → 知识库同步脚本

从吉利学院图书馆 MySQL 数据库拉取真实馆藏数据，
转换为知识库 JSON 格式，用于 RAG 检索。

运行方式: python scripts/sync_mysql_to_kb.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.mysql_client import MySQLClient
from backend.utils.logger import log, setup_logger


# 中图法分类号 → 楼层/区域映射
CLC_TO_LOCATION = {
    # 2F — 社会科学与文学
    "A": {"floor": "2F", "zone": "社会科学区", "name": "马列主义"},
    "B": {"floor": "2F", "zone": "社会科学区", "name": "哲学宗教"},
    "C": {"floor": "2F", "zone": "社会科学区", "name": "社会科学总论"},
    "D": {"floor": "2F", "zone": "社会科学区", "name": "政治法律"},
    "E": {"floor": "2F", "zone": "社会科学区", "name": "军事"},
    "F": {"floor": "2F", "zone": "社会科学区", "name": "经济"},
    "G": {"floor": "2F", "zone": "社会科学区", "name": "文化教育"},
    "H": {"floor": "2F", "zone": "语言学习区", "name": "语言文字"},
    "I": {"floor": "2F", "zone": "文学区", "name": "文学"},
    "J": {"floor": "2F", "zone": "社会科学区", "name": "艺术"},
    "K": {"floor": "2F", "zone": "社会科学区", "name": "历史地理"},
    # 3F — 自然科学
    "N": {"floor": "3F", "zone": "自然科学区", "name": "自然科学总论"},
    "O": {"floor": "3F", "zone": "自然科学区", "name": "数理化"},
    "P": {"floor": "3F", "zone": "自然科学区", "name": "天文地球"},
    "Q": {"floor": "3F", "zone": "自然科学区", "name": "生物科学"},
    "R": {"floor": "3F", "zone": "自然科学区", "name": "医药卫生"},
    "S": {"floor": "3F", "zone": "自然科学区", "name": "农业科学"},
    "T": {"floor": "3F", "zone": "自然科学区", "name": "工业技术"},
    "U": {"floor": "3F", "zone": "自然科学区", "name": "交通运输"},
    "V": {"floor": "3F", "zone": "自然科学区", "name": "航空航天"},
    "X": {"floor": "3F", "zone": "自然科学区", "name": "环境科学"},
    "Z": {"floor": "3F", "zone": "自然科学区", "name": "综合性图书"},
}


def classify_book(call_number: str) -> dict:
    """根据索书号首字母判断图书所在楼层和区域"""
    if not call_number:
        return {"floor": "未知", "zone": "未知", "name": "未知"}
    prefix = call_number.strip().upper()[0]
    return CLC_TO_LOCATION.get(prefix, {"floor": "未知", "zone": "未知", "name": "未知"})


def extract_key_info(book: dict) -> dict:
    """
    从MySQL原始记录中提取关键信息

    自动适配不同数据库的字段命名，输出统一格式
    """
    # 字段映射（尝试多种可能的列名）
    title = (
        book.get("title")
        or book.get("书名")
        or book.get("题名")
        or book.get("正题名")
        or book.get("name")
        or book.get("book_name")
        or "未知书名"
    )

    author = (
        book.get("author")
        or book.get("作者")
        or book.get("责任者")
        or book.get("著者")
        or ""
    )

    call_number = (
        book.get("call_number")
        or book.get("索书号")
        or book.get("call_no")
        or book.get("class_number")
        or ""
    )

    isbn = book.get("isbn") or book.get("isbn13") or book.get("标准编号") or ""

    publisher = book.get("publisher") or book.get("出版社") or book.get("出版者") or ""

    pub_year = str(book.get("pub_year") or book.get("出版年") or book.get("year") or "")

    status = book.get("status") or book.get("状态") or book.get("loan_status") or ""

    # 分类定位
    location = classify_book(call_number)

    return {
        "title": str(title),
        "author": str(author),
        "call_number": str(call_number),
        "isbn": str(isbn),
        "publisher": str(publisher),
        "pub_year": str(pub_year),
        "status": str(status),
        "floor": location["floor"],
        "zone": location["zone"],
        "category_name": location["name"],
    }


def main():
    setup_logger()
    log.info("=" * 60)
    log.info("MySQL → Knowledge Base Sync")
    log.info("=" * 60)

    client = MySQLClient()

    # Step 1: 发现数据库
    databases = client.discover_databases()
    log.info(f"Found {len(databases)} databases:")
    for db in databases:
        log.info(f"  - {db}")

    # Step 2: 选择馆藏数据库（通常包含 book/holding 等关键词）
    target_db = None
    for db in databases:
        db_lower = db.lower()
        if any(kw in db_lower for kw in ["book", "馆藏", "library", "opac", "书目"]):
            target_db = db
            break
    if not target_db:
        target_db = databases[0] if databases else None

    if not target_db:
        log.error("No database found!")
        return

    client.set_database(target_db)
    log.info(f"Selected database: {target_db}")

    # Step 3: 发现表结构
    tables = client.discover_tables()
    log.info(f"Found {len(tables)} tables in {target_db}:")
    for t in tables:
        log.info(f"  - {t}")
        # 展示每个表的前几个字段
        try:
            cols = client.describe_table(t)
            col_summary = ", ".join(
                f"{c['Field']}({c['Type']})" for c in cols[:6]
            )
            log.info(f"    Columns: {col_summary}" + ("..." if len(cols) > 6 else ""))
        except Exception:
            pass

    # Step 4: 拉取图书数据
    log.info(f"\nFetching book data...")
    book_count = client.get_book_count()
    log.info(f"Total books in database: {book_count}")

    books = client.get_all_books(limit=500)
    log.info(f"Fetched {len(books)} book records")

    # Step 5: 转换为统一格式
    processed = []
    for book in books:
        info = extract_key_info(book)
        processed.append(info)

    # 统计分类分布
    floor_dist = {}
    zone_dist = {}
    for b in processed:
        floor = b["floor"]
        zone = b["zone"]
        floor_dist[floor] = floor_dist.get(floor, 0) + 1
        zone_dist[zone] = zone_dist.get(zone, 0) + 1

    log.info("\n--- Floor Distribution ---")
    for floor, count in sorted(floor_dist.items()):
        log.info(f"  {floor}: {count} books")

    log.info("\n--- Zone Distribution ---")
    for zone, count in sorted(zone_dist.items(), key=lambda x: x[1], reverse=True):
        log.info(f"  {zone}: {count} books")

    # Step 6: 保存为知识库 JSON
    output_dir = Path(__file__).parent.parent / "backend" / "knowledge" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "book_locations.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    log.info(f"\n✅ Synced {len(processed)} books to: {output_path}")

    # Step 7: 生成分类摘要
    summary = {
        "source": f"mysql://{client.host}/{target_db}",
        "total_books": book_count,
        "synced_books": len(processed),
        "floor_distribution": floor_dist,
        "zone_distribution": zone_dist,
    }
    summary_path = output_dir / "book_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log.info(f"Summary saved to: {summary_path}")
    log.info("=" * 60)
    log.info("Sync complete! Run 'python scripts/build_kb.py' to rebuild RAG index.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
