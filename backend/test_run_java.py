import asyncio
import httpx

async def run():
    java_code = """
public class Solution {
    public static void main(String[] args) {
        System.out.println("Hello from Java!");
    }
}
"""
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/run', json={'language':'java', 'code': java_code})
        print("Java code execution result:")
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
