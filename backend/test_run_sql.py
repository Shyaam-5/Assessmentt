import asyncio
import httpx

async def run():
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/run', json={
            'language':'sql', 
            'sqlSchema': 'CREATE TABLE test (id INT, name TEXT); INSERT INTO test VALUES (1, "Alice");',
            'code':'SELECT * FROM test;'
        })
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
