import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    try:
        async with engine.connect() as connection:
            result = await connection.scalar(text("SELECT 1"))
            print(f"database_ready={result == 1}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
