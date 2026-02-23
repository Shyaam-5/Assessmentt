import asyncio
import httpx

async def run():
    payload = {
        "language": "javascript",
        "version": "18.15.0",
        "files": [{"content": "console.log(5);"}]
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post('https://emkc.org/api/v2/piston/execute', json=payload)
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
