"""
One-time migration script to generate embeddings for knowledge base entries.
Run this after seeding the database: python database/migrations/embed_knowledge_base.py
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])


async def embed_knowledge_base():
    """Generate embeddings for all knowledge base entries without embeddings."""

    # Connect to database
    conn = await asyncpg.connect(
        dsn=os.environ["DATABASE_URL"],
        ssl="require"
    )

    try:
        # Fetch all entries without embeddings
        rows = await conn.fetch(
            "SELECT id, title, content FROM knowledge_base WHERE embedding IS NULL"
        )

        print(f"Found {len(rows)} entries without embeddings")

        for i, row in enumerate(rows, 1):
            # Combine title and content for embedding
            text = f"{row['title']}\n\n{row['content']}"

            # Generate embedding using Gemini
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text
            )
            embedding = result["embedding"]

            # Update database with embedding
            await conn.execute(
                "UPDATE knowledge_base SET embedding = $1, updated_at = NOW() WHERE id = $2",
                embedding,
                row["id"]
            )

            print(f"[{i}/{len(rows)}] Embedded: {row['title'][:50]}...")

        print(f"\n✓ Successfully embedded {len(rows)} entries")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(embed_knowledge_base())
