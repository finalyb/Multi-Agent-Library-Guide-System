"""
MySQL 馆藏数据库客户端（只读）

连接吉利学院图书馆真实馆藏数据库，提供：
1. 图书检索 — 按书名/作者/索书号查询
2. 馆藏状态 — 查看图书在馆情况
3. 分类浏览 — 按中图法分类浏览馆藏分布
"""
import pymysql
from typing import Optional, Any
from contextlib import contextmanager
from backend.utils.logger import log


class MySQLClient:
    """
    馆藏数据库只读客户端

    连接信息：
    - Host: 172.16.71.21
    - User: myview (只读)
    - 用途：为 RAG 知识库提供真实馆藏数据
    """

    def __init__(
        self,
        host: str = "172.16.71.21",
        user: str = "myview",
        password: str = "yangbo19861022",
        charset: str = "utf8mb4",
        connect_timeout: int = 10,
    ):
        self.host = host
        self.user = user
        self.password = password
        self.charset = charset
        self.connect_timeout = connect_timeout
        self._conn: Optional[pymysql.Connection] = None
        self._database: Optional[str] = None

    @contextmanager
    def _get_connection(self):
        """获取数据库连接（上下文管理器，自动关闭）"""
        conn = None
        try:
            conn = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                charset=self.charset,
                connect_timeout=self.connect_timeout,
            )
            if self._database:
                conn.select_db(self._database)
            yield conn
        except pymysql.Error as e:
            log.error(f"MySQL connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def discover_databases(self) -> list[str]:
        """发现所有数据库"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SHOW DATABASES")
            return [row[0] for row in cursor.fetchall()]

    def set_database(self, database: str) -> None:
        """设置默认数据库"""
        self._database = database
        log.info(f"MySQL database set to: {database}")

    def discover_tables(self) -> list[str]:
        """发现当前数据库的所有表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            return [row[0] for row in cursor.fetchall()]

    def describe_table(self, table_name: str) -> list[dict]:
        """获取表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def query(self, sql: str, params: tuple = None, limit: int = 100) -> list[dict]:
        """
        执行只读查询

        Args:
            sql: SQL查询语句
            params: 参数化查询参数
            limit: 自动追加 LIMIT（防止大数据量）

        Returns:
            查询结果列表 [{"col1": val1, ...}, ...]
        """
        # 自动追加 LIMIT
        sql_upper = sql.strip().upper()
        if "LIMIT" not in sql_upper:
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or ())
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def search_books(
        self,
        keyword: str = None,
        title: str = None,
        author: str = None,
        call_number: str = None,
        isbn: str = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        图书检索（智能匹配，自动探测表结构）

        先探测表结构，找到书名/作者/索书号等对应字段，再执行查询。
        """
        # Step 1: 探测表结构，找到对应字段
        tables = self.discover_tables()
        book_table = self._find_book_table(tables)

        if not book_table:
            log.warning("No book table found, trying generic query...")
            return self._generic_book_search(keyword or title or author or "", limit)

        columns = self.describe_table(book_table)
        col_names = [c["Field"].lower() for c in columns]

        # Step 2: 映射常见字段名
        title_col = self._find_column(col_names, ["title", "书名", "题名", "name", "book_name", "正题名"])
        author_col = self._find_column(col_names, ["author", "作者", "责任者", "著者", "writer"])
        call_col = self._find_column(col_names, ["call_number", "索书号", "call_no", "class_number", "索书号"])
        isbn_col = self._find_column(col_names, ["isbn", "isbn13", "isbn10", "标准编号"])
        publisher_col = self._find_column(col_names, ["publisher", "出版社", "出版者", "出版发行"])
        status_col = self._find_column(col_names, ["status", "状态", "loan_status", "借阅状态", "馆藏状态"])

        # Step 3: 构建查询
        conditions = []
        params = []

        if keyword and (title_col or author_col):
            keyword_conds = []
            kw = f"%{keyword}%"
            if title_col:
                keyword_conds.append(f"`{title_col}` LIKE %s")
                params.append(kw)
            if author_col:
                keyword_conds.append(f"`{author_col}` LIKE %s")
                params.append(kw)
            if call_col:
                keyword_conds.append(f"`{call_col}` LIKE %s")
                params.append(kw)
            conditions.append("(" + " OR ".join(keyword_conds) + ")")

        if title and title_col:
            conditions.append(f"`{title_col}` LIKE %s")
            params.append(f"%{title}%")

        if author and author_col:
            conditions.append(f"`{author_col}` LIKE %s")
            params.append(f"%{author}%")

        if call_number and call_col:
            conditions.append(f"`{call_col}` LIKE %s")
            params.append(f"{call_number}%")

        if isbn and isbn_col:
            conditions.append(f"`{isbn_col}` = %s")
            params.append(isbn)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM `{book_table}` WHERE {where_clause} LIMIT {limit}"

        # Step 4: 执行
        try:
            results = self.query(sql, tuple(params), limit)
            log.info(f"Book search: {len(results)} results for '{keyword or title or author}'")
            return results
        except Exception as e:
            log.error(f"Book search failed: {e}")
            return []

    def get_all_books(self, limit: int = 500) -> list[dict]:
        """获取所有图书（用于知识库同步）"""
        tables = self.discover_tables()
        book_table = self._find_book_table(tables)

        if not book_table:
            return []

        try:
            return self.query(f"SELECT * FROM `{book_table}`", limit=limit)
        except Exception as e:
            log.error(f"Get all books failed: {e}")
            return []

    def get_book_count(self) -> int:
        """获取馆藏总数"""
        tables = self.discover_tables()
        book_table = self._find_book_table(tables)

        if not book_table:
            return 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM `{book_table}`")
                return cursor.fetchone()[0]
        except Exception as e:
            log.error(f"Count failed: {e}")
            return 0

    def get_category_distribution(self) -> list[dict]:
        """
        获取馆藏分类分布

        尝试按索书号首字母（中图法分类）统计
        """
        tables = self.discover_tables()
        book_table = self._find_book_table(tables)

        if not book_table:
            return []

        columns = self.describe_table(book_table)
        col_names = [c["Field"].lower() for c in columns]
        call_col = self._find_column(col_names, ["call_number", "索书号", "call_no", "class_number"])

        if not call_col:
            return []

        try:
            # 按索书号首字母分组统计
            sql = f"""
                SELECT LEFT(`{call_col}`, 1) AS category_prefix, COUNT(*) AS count
                FROM `{book_table}`
                WHERE `{call_col}` IS NOT NULL AND `{call_col}` != ''
                GROUP BY LEFT(`{call_col}`, 1)
                ORDER BY count DESC
                LIMIT 30
            """
            return self.query(sql)
        except Exception as e:
            log.error(f"Category distribution failed: {e}")
            return []

    # ===== 辅助方法 =====

    def _find_book_table(self, tables: list[str]) -> Optional[str]:
        """在表列表中查找图书相关的表"""
        book_keywords = ["book", "图书", "馆藏", "holding", "item", "书目", "文献", "tushu"]
        for table in tables:
            table_lower = table.lower()
            for kw in book_keywords:
                if kw in table_lower:
                    return table
        # fallback: 返回第一个表
        return tables[0] if tables else None

    def _find_column(self, col_names: list[str], candidates: list[str]) -> Optional[str]:
        """在列名列表中查找匹配的列名"""
        for candidate in candidates:
            for col in col_names:
                if candidate in col:
                    return col
        return None

    def _generic_book_search(self, keyword: str, limit: int = 50) -> list[dict]:
        """
        通用搜索（当无法确定图书表时的降级方案）
        遍历所有表和列进行模糊匹配
        """
        tables = self.discover_tables()
        all_results = []

        for table in tables:
            try:
                columns = self.describe_table(table)
                text_cols = []
                for col in columns:
                    col_type = col.get("Type", "").lower()
                    if any(t in col_type for t in ["char", "text", "varchar"]):
                        text_cols.append(col["Field"])

                if not text_cols:
                    continue

                conditions = " OR ".join([f"`{c}` LIKE %s" for c in text_cols[:5]])
                kw = f"%{keyword}%"
                params = tuple([kw] * min(len(text_cols), 5))

                results = self.query(
                    f"SELECT * FROM `{table}` WHERE {conditions}",
                    params,
                    limit=limit - len(all_results),
                )
                for r in results:
                    r["_source_table"] = table
                all_results.extend(results)

                if len(all_results) >= limit:
                    break
            except Exception:
                continue

        return all_results[:limit]


# 全局单例（延迟初始化）
mysql_client: Optional[MySQLClient] = None


def get_mysql_client() -> MySQLClient:
    """获取 MySQL 客户端单例"""
    global mysql_client
    if mysql_client is None:
        mysql_client = MySQLClient()
    return mysql_client
