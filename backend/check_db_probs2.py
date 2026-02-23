import asyncio
from database import get_pool, init_db
import pymysql.cursors

async def run():
    await init_db()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute("SELECT id, title, enable_proctoring FROM problems WHERE title LIKE '%Vowel%'")
            probs = await cur.fetchall()
            for p in probs:
                print(p)
            await cur.execute("SELECT id, title, enable_proctoring FROM problems WHERE enable_proctoring = 'true' LIMIT 3")
            probs2 = await cur.fetchall()
            print("Problems with proctoring enabled:")
            for p in probs2:
                print(p)

if __name__ == "__main__":
    asyncio.run(run())
