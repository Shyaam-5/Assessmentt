import asyncio
import httpx

async def run():
    java_code = """
import java.util.Scanner;
public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        if (sc.hasNextInt()) {
            System.out.println("Echo: " + sc.nextInt());
        } else {
            System.out.println("Nothing Scanner read.");
        }
    }
}
"""
    async with httpx.AsyncClient() as client:
        # Simulate browser passing a number
        resp = await client.post('http://localhost:8000/api/run', json={'language':'java', 'code': java_code, 'stdin': '5'})
        print("Java code execution result with int:")
        print(resp.json())
        
        # Simulate empty or space
        resp = await client.post('http://localhost:8000/api/run', json={'language':'java', 'code': java_code, 'stdin': ' '})
        print("Java code execution result with space:")
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(run())
