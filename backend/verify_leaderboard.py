import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_leaderboard():
    print("Testing Leaderboard Endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/leaderboard", timeout=5)
        if response.status_code == 200:
            print("✅ Leaderboard Endpoint Accessible")
            data = response.json()
            print(f"Received {len(data)} leaderboard entries")
            if len(data) > 0:
                print("Sample Entry:", json.dumps(data[0], indent=2))
        else:
            print(f"❌ Leaderboard Endpoint Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception testing leaderboard: {e}")

def get_first_student_id():
    try:
        # Assuming we can get a student ID from leaderboard or another way
        # For now, let's try to get it from leaderboard
        response = requests.get(f"{BASE_URL}/leaderboard", timeout=5)
        if response.status_code == 200 and len(response.json()) > 0:
            return response.json()[0]['studentId']
    except:
        pass
    return None

def test_student_analytics(student_id):
    if not student_id:
        print("Skipping Student Analytics Test (No Student ID found)")
        return

    print(f"\nTesting Student Analytics for {student_id}...")
    try:
        response = requests.get(f"{BASE_URL}/analytics/student/{student_id}", timeout=5)
        if response.status_code == 200:
            print("✅ Student Analytics Endpoint Accessible")
            data = response.json()
            if "studentRank" in data:
                print(f"✅ Rank Field Present: {data['studentRank']}")
            else:
                print("❌ Rank Field MISSING in response")
        else:
            print(f"❌ Student Analytics Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception testing analytics: {e}")

if __name__ == "__main__":
    test_leaderboard()
    sid = get_first_student_id()
    test_student_analytics(sid)
