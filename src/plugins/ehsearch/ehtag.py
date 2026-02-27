import sqlite3
import threading

from loguru import logger


class TagTranslator:
    """
    一个单例模式的标签翻译类。

    该类在首次初始化时连接到一个 SQLite 数据库，并提供一个接口
    将形如 'namespace:tag' 的标签列表翻译成更易读的名称。
    如果数据库中存在对应的名称，则使用该名称；否则，使用原始标签。
    """

    _instance = None
    _lock = threading.Lock()  # 用于确保线程安全的单例创建

    def __new__(cls, *args, **kwargs):
        """
        重写 __new__ 方法来实现单例模式。
        """
        if not cls._instance:
            with cls._lock:
                # 再次检查，防止多线程环境下重复创建实例
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "tags.db"):
        """
        初始化数据库连接。

        由于是单例模式，实际的初始化代码只会执行一次。
        我们使用一个标志 `_initialized` 来防止重复初始化。

        Args:
            db_path (str): SQLite 数据库文件的路径。
        """
        # 防止重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return

        logger.info(f"正在初始化 TagTranslator 并加载数据库: {db_path}")
        try:
            # check_same_thread=False 允许在不同线程中使用此连接对象
            # 这在某些Web框架或多线程应用中很方便
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self._check_table()
            self._initialized = True
            logger.info("初始化完成")
        except sqlite3.Error as e:
            logger.error(f"数据库错误: {e}")
            self._initialized = False
            raise  # 抛出异常，因为没有数据库，这个类无法工作

    def _check_table(self):
        """检查 'tags_data' 表是否存在，如果不存在则提示。"""
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tags_data';"
        )
        if self.cursor.fetchone() is None:
            raise sqlite3.OperationalError(
                "错误: 数据库中未找到名为 'tags_data' 的表。"
            )

    def trans_all(self, input_tags: list[str]) -> list[str]:
        """
        翻译一个 'namespace:tag' 格式的字符串列表。

        Args:
            input_tags (List[str]): 需要翻译的字符串列表，
                                    例如 ['language:translated', 'artist:unknown_artist']。

        Returns:
            List[str]: 翻译后的字符串列表。如果找到匹配的 'tran'，则返回 'tran'；
                       否则，返回原始的 'tag'部分。
        """
        if not self._initialized:
            raise RuntimeError("TagTranslator 未成功初始化。")

        translated_list = []
        query = "SELECT tran FROM tags_data WHERE namespace = ? AND tag = ?"

        for item in input_tags:
            try:
                # 将 "namespace:tag" 分割
                namespace, tag = item.split(":", 1)
            except ValueError:
                # 如果输入格式不正确（不含 ':'），直接将整个字符串作为结果
                translated_list.append(item)
                continue

            # 执行查询
            self.cursor.execute(query, (namespace, tag))
            result = self.cursor.fetchone()  # fetchone() 获取查询结果的第一行

            if result:
                # 如果查询到结果，result 是一个元组，例如 ('中文',)
                # 我们取第一个元素作为翻译后的名称
                translated_list.append(f"{namespace}: {result[0]}")
            else:
                # 如果没有查询到结果，使用原始的 tag
                translated_list.append(f"{namespace}: {tag}")

        return translated_list

    def close(self):
        """关闭数据库连接。"""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
            print("--- 数据库连接已关闭 ---")
            self._initialized = False  # 标记为未初始化，以便可以重新创建（如果需要）


if __name__ == "__main__":
    import os

    DB_FILE = r"F:\python\nanofish2\src\plugins\ehsearch\sql\o.db"

    # 2. 获取 TagTranslator 的实例
    # 无论调用多少次，都将返回同一个对象实例
    translator1 = TagTranslator(db_path=DB_FILE)
    translator2 = TagTranslator(db_path=DB_FILE)  # 这里的初始化信息不会再次打印

    # 验证是否为同一个实例
    print(
        f"\n- translator1 和 translator2 是同一个实例吗? {translator1 is translator2}\n"
    )

    # 3. 准备要翻译的输入数据
    #    - 'language:translated' 和 'artist:van_gogh' 应该能被翻译
    #    - 'character:nonexistent_char' 在数据库中不存在，应该返回 'tag' 部分
    #    - 'invalid-format' 是一个错误格式的输入
    input_list = [
        "language:english",
        "language:translated",
        "parody:blue archive",
        "character:kisaki ryuuge",
        "character:sensei",
        "group:poison gray",
        "artist:matsuriuta",
        "female:chinese dress",
        "female:defloration",
        "female:hair buns",
        "female:halo",
        "female:impregnation",
        "female:lolicon",
        "female:nakadashi",
        "female:sole female",
        "female:twintails",
        "other:multi-work series",
        "other:rough translation",
    ]

    print(f"输入列表: {input_list}")

    # 4. 调用 trans_all 方法进行翻译
    output_list = translator1.trans_all(input_list)

    # 5. 打印结果
    print(f"翻译结果: {output_list}")

    # 6. 程序结束时，关闭数据库连接
    translator1.close()
