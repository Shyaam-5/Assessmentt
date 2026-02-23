import asyncio
import httpx

async def run():
    c_code = """
#include <stdio.h>
int main() {
    printf("Hello from C!\\n");
    return 0;
}
"""
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/run', json={'language':'c', 'code': c_code})
        print("C code execution result:")
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
