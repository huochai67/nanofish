import json
import sqlite3
import argparse
import sys


def create_database_and_table(db_path):
    """连接到SQLite数据库并创建表（如果不存在）"""
    try:
        # 连接到数据库，如果文件不存在则会创建
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 创建表的SQL语句
        # 添加了 UNIQUE 约束来防止 (namespace, tag) 组合的重复记录
        create_table_query = """
        CREATE TABLE IF NOT EXISTS tags_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            tag TEXT NOT NULL,
            tran TEXT NOT NULL,
            UNIQUE(namespace, tag)
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        return conn, cursor
    except sqlite3.Error as e:
        print(f"数据库错误: {e}", file=sys.stderr)
        return None, None


def process_json_to_sqlite(json_path, db_path):
    """
    读取JSON文件，解析数据，并将其插入SQLite数据库。
    """
    # 1. 连接数据库并创建表
    conn, cursor = create_database_and_table(db_path)
    if not conn:
        return

    # 2. 读取并解析JSON文件
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误: JSON文件未找到 '{json_path}'", file=sys.stderr)
        conn.close()
        return
    except json.JSONDecodeError:
        print(f"错误: JSON文件格式无效 '{json_path}'", file=sys.stderr)
        conn.close()
        return

    # 3. 遍历数据并插入数据库
    insert_count = 0
    skipped_count = 0

    # 检查顶层'data'键是否存在且为列表
    if "data" not in data or not isinstance(data["data"], list):
        print("错误: JSON文件缺少顶层 'data' 数组，或其格式不正确。", file=sys.stderr)
        conn.close()
        return

    # 遍历 `json['data']` 数组 (第一层)
    for item in data["data"]:
        try:
            # 提取 namespace
            namespace = item["namespace"]

            # 检查内部'data'键是否存在且为列表
            if "data" not in item or not isinstance(item["data"], dict):
                print(
                    f"警告: 在 namespace '{namespace}' 中缺少'dict'数组，已跳过。",
                    file=sys.stderr,
                )
                continue

            # 遍历 `item['data']` 数组 (第二层)
            for index, key in enumerate(item["data"].keys()):
                value = item["data"][key]
                # 提取 tag 和 tran
                tag = key
                tran = value["name"]

                # 准备插入数据
                sql = "INSERT OR IGNORE INTO tags_data (namespace, tag, tran) VALUES (?, ?, ?)"
                cursor.execute(sql, (namespace, tag, tran))

                # cursor.rowcount 会返回受上一条命令影响的行数
                # 如果是1，表示插入成功；如果是0，表示因为UNIQUE约束而忽略了
                if cursor.rowcount > 0:
                    insert_count += 1
                else:
                    skipped_count += 1

        except KeyError as e:
            print(f"警告: 在处理某条记录时缺少键 {e}，已跳过该记录。", file=sys.stderr)
            continue
        except TypeError:
            print(f"警告: 记录的结构不符合预期，已跳过。", file=sys.stderr)
            continue

    # 4. 提交更改并关闭连接
    conn.commit()
    conn.close()

    print("处理完成！")
    print(f"成功插入 {insert_count} 条新记录。")
    print(f"因重复而跳过 {skipped_count} 条记录。")
    print(f"数据库已保存至: {db_path}")


if __name__ == "__main__":

    # 执行主函数
    process_json_to_sqlite(
        r"F:\python\nanofish2\src\plugins\ehsearch\sql\db.text.json", "o.db"
    )
