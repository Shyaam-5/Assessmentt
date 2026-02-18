import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"
MENTOR_ID = "mentor123" # Replace with valid mentor ID if needed

def test_mentor_analytics():
    print("Testing Mentor Analytics Endpoint...")
    try:
        # We need a valid mentor ID. Let's try to fetch one from users first if possible,
        # or just use a dummy one if we are mocking.
        # But wait, we can't easily fetch users without auth.
        # Let's hope the user who ran the previous test has some data.
        # Or we can just try to hit the endpoint with a known ID or randomly.
        # Better: Login as mentor? No, auth is complex.
        # Strategy: Use a hardcoded ID if we know one, or try to get from leaderboard?
        # Leaderboard has 'studentId', not mentor.
        # Let's try to get a student, then find their mentor.
        
        # 1. Get a student
        resp = requests.get(f"{BASE_URL}/leaderboard", timeout=5)
        student_id = None
        if resp.status_code == 200 and len(resp.json()) > 0:
            student_id = resp.json()[0]['studentId']
        
        mentor_id = None
        if student_id:
            # 2. Get student analytics to find mentor
            resp = requests.get(f"{BASE_URL}/analytics/student/{student_id}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('mentorInfo'):
                    mentor_id = data['mentorInfo']['id']
                    print(f"Found Mentor ID: {mentor_id}")

        if not mentor_id:
            print("Could not find a valid mentor ID dynamically. Skipping.")
            return

        # 3. Test Mentor Analytics
        response = requests.get(f"{BASE_URL}/analytics/mentor/{mentor_id}", timeout=5)
        if response.status_code == 200:
            print("✅ Mentor Analytics Endpoint Accessible")
            data = response.json()
            keys = data.keys()
            print("Response Keys:", list(keys))
            
            if "allocatedStudents" not in keys:
                print("✅ allocatedStudents REMOVED")
            else:
                print("❌ allocatedStudents STILL PRESENT")

            if "menteePerformance" not in keys:
                print("✅ menteePerformance REMOVED")
            else:
                print("❌ menteePerformance STILL PRESENT")

            if "totalStudents" in keys and "avgScore" in keys:
                print("✅ Core stats PRESENT")
            else:
                print("❌ Core stats MISSING")
                
        else:
            print(f"❌ Mentor Analytics Failed: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"❌ Exception testing mentor analytics: {e}")

if __name__ == "__main__":
    test_mentor_analytics()
