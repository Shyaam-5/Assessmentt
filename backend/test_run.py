import asyncio
import httpx

async def run():
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/run', json={'language':'javascript', 'code':'console.log(5);'})
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
