import argparse
import sys

import psycopg

from app.core.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="显式授予已有用户管理员角色")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    database_url = get_settings().database_url.replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            UPDATE users
            SET role = 'admin', updated_at = now()
            WHERE lower(email) = lower(%s)
            RETURNING id, email, role
            """,
            (args.email.strip(),),
        ).fetchone()
        if row is None:
            print(f"用户不存在：{args.email}", file=sys.stderr)
            return 1
        connection.commit()
        print(f"已授予管理员角色：{row[1]} ({row[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
