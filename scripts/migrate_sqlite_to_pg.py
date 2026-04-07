#!/usr/bin/env python3
"""
SQLite → PostgreSQL 数据迁移脚本

用法:
  python3 scripts/migrate_sqlite_to_pg.py --sqlite data/data.db --pg postgresql://user:pass@host:5432/aitokenperf
"""

import argparse
import asyncio
import json
import sys

import aiosqlite
import asyncpg


# 按依赖顺序排列的表
TABLES = ["users", "profiles", "user_settings", "scheduled_tasks", "results"]
# sessions 不迁移（token 已失效）


async def get_sqlite_tables(sqlite_path: str) -> list[str]:
    """获取 SQLite 中实际存在的表"""
    async with aiosqlite.connect(sqlite_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def copy_table(sqlite_path: str, pg_conn: asyncpg.Connection, table: str, reset_sequences: bool = True):
    """复制单个表的数据"""
    async with aiosqlite.connect(sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"SELECT * FROM {table}")
        rows = await cursor.fetchall()
        if not rows:
            print(f"  {table}: 0 rows (skip)")
            return 0

        columns = [desc[0] for desc in cursor.description]
        col_list = ", ".join(columns)
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))

        # 批量插入
        batch_size = 100
        inserted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values = []
            for row in batch:
                vals = []
                for col in columns:
                    v = row[col]
                    # SQLite 存储布尔为 0/1，PG 需要 bool
                    if table == "profiles" and col == "is_active":
                        v = bool(v)
                    vals.append(v)
                values.append(vals)

            await pg_conn.copy_records_to_table(
                table, records=values, columns=columns
            )
            inserted += len(batch)

        # 重置序列（SERIAL 列）
        if reset_sequences and columns[0] == "id":
            max_id = max(r["id"] for r in rows)
            seq_name = f"{table}_id_seq"
            await pg_conn.execute(
                f"SELECT setval('{seq_name}', {max_id})"
            )

        print(f"  {table}: {inserted} rows")
        return inserted


async def migrate(sqlite_path: str, pg_url: str):
    """执行完整迁移"""
    print(f"SQLite: {sqlite_path}")
    print(f"PostgreSQL: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    print()

    # 检查 SQLite 表
    sqlite_tables = await get_sqlite_tables(sqlite_path)
    print(f"SQLite tables found: {', '.join(sqlite_tables)}")

    # 连接 PG
    pg_pool = await asyncpg.create_pool(pg_url, min_size=1, max_size=2)
    try:
        async with pg_pool.acquire() as conn:
            # 检查 PG 是否已初始化
            pg_tables = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
            pg_table_names = [r["tablename"] for r in pg_tables]
            if not pg_table_names:
                print("\nError: PostgreSQL tables not found. Run init_db() first.")
                sys.exit(1)

            print(f"PostgreSQL tables found: {', '.join(pg_table_names)}")
            print()

            # 禁用外键约束检查
            await conn.execute("SET session_replication_role = 'replica'")

            total = 0
            for table in TABLES:
                if table in sqlite_tables and table in pg_table_names:
                    n = await copy_table(sqlite_path, conn, table)
                    total += n
                else:
                    print(f"  {table}: skipped (not in both databases)")

            # 恢复外键约束检查
            await conn.execute("SET session_replication_role = 'origin'")

            print(f"\nDone. Migrated {total} total rows.")
    finally:
        await pg_pool.close()


def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 数据迁移")
    parser.add_argument("--sqlite", required=True, help="SQLite 数据库路径 (e.g. data/data.db)")
    parser.add_argument("--pg", required=True, help="PostgreSQL 连接 URL (e.g. postgresql://user:pass@host:5432/db)")
    args = parser.parse_args()

    asyncio.run(migrate(args.sqlite, args.pg))


if __name__ == "__main__":
    main()
