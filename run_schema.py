"""Run database schema setup."""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run_schema():
    """Execute schema.sql against the database."""
    database_url = os.getenv("DATABASE_URL")

    # Read schema file
    with open("database/schema.sql", "r") as f:
        schema_sql = f.read()

    # Connect and execute
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(schema_sql)
        print("Database schema created successfully")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_schema())
