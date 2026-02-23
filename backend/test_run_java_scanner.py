import asyncio
import httpx

async def run():
    java_code = """
import java.util.Scanner;
public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.println("Echo: " + sc.nextLine());
    }
}
"""
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/run', json={'language':'java', 'code': java_code, 'stdin': 'Hello World'})
        print("Java code execution result:")
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
