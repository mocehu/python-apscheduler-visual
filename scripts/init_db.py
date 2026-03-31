#!/usr/bin/env python
"""
数据库初始化脚本

用法:
  python scripts/init_db.py              # 创建不存在的表
  python scripts/init_db.py --reset      # 删除并重建所有表 (危险操作)
  python scripts/init_db.py --reset-config  # 重置系统配置为默认值
  python scripts/init_db.py --status     # 查看数据库表状态
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, init_db, reset_db, get_db_status, _session_factory
from app.models.sql_model import Base, SystemConfig, DEFAULT_CONFIG


def reset_config():
    """重置系统配置为默认值"""
    db = _session_factory()
    try:
        deleted = db.query(SystemConfig).delete()
        db.commit()
        print(f"✓ 已删除 {deleted} 个旧配置")
        
        for key, config in DEFAULT_CONFIG.items():
            db.add(SystemConfig(
                key=key,
                value=config["value"],
                description=config["description"]
            ))
        db.commit()
        print(f"✓ 已初始化 {len(DEFAULT_CONFIG)} 个默认配置")
    except Exception as e:
        db.rollback()
        print(f"✗ 重置配置失败: {e}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description='数据库初始化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/init_db.py              # 创建不存在的表
  python scripts/init_db.py --reset      # 重置数据库 (需要确认)
  python scripts/init_db.py --reset-config  # 重置系统配置
  python scripts/init_db.py --status     # 查看表状态
        """
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='删除并重建所有表 (危险操作，需要确认)'
    )
    parser.add_argument(
        '--reset-config',
        action='store_true',
        help='重置系统配置为默认值'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='显示当前数据库表状态'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='配合 --reset 使用，跳过确认提示'
    )
    args = parser.parse_args()

    if args.status:
        status = get_db_status()
        print("\n数据库表状态:")
        print("-" * 50)
        for table_name, exists in status.items():
            status_text = "✓ 存在" if exists else "✗ 不存在"
            print(f"  {table_name}: {status_text}")
        print("-" * 50)
        return

    if args.reset:
        if not args.force:
            print("\n⚠️  警告: 此操作将删除所有表并重建，数据将永久丢失!")
            confirm = input("确定要继续吗? (输入 'yes' 确认): ")
            if confirm.lower() != 'yes':
                print("操作已取消")
                return
        print("\n正在重置数据库...")
        reset_db()
        print("✓ 数据库已重置完成")
        return

    if args.reset_config:
        print("\n正在重置系统配置...")
        reset_config()
        return

    print("\n正在初始化数据库...")
    init_db()
    print("✓ 数据库表初始化完成")

    status = get_db_status()
    print("\n当前表状态:")
    for table_name, exists in status.items():
        if exists:
            print(f"  ✓ {table_name}")


if __name__ == '__main__':
    main()