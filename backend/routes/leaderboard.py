from fastapi import APIRouter, Depends, HTTPException, Query
from database import get_pool
from typing import List, Optional, Dict, Any

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])

@router.get("", response_model=List[Dict[str, Any]])
async def get_leaderboard(
    mentorId: Optional[str] = Query(None, description="Filter by mentor ID")
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                # Base query to get student stats
                query = """
                    SELECT 
                        u.id as studentId, 
                        u.name, 
                        COALESCE(AVG(s.score), 0) as avgScore,
                        COUNT(s.id) as totalSubmissions,
                        SUM(CASE WHEN s.status = 'accepted' THEN 1 ELSE 0 END) as acceptedSubmissions,
                        u.mentor_id
                    FROM users u
                    LEFT JOIN submissions s ON u.id = s.student_id
                    WHERE u.role = 'student'
                """
                
                params = []
                if mentorId:
                    query += " AND u.mentor_id = %s"
                    params.append(mentorId)
                    
                query += " GROUP BY u.id, u.name, u.mentor_id ORDER BY avgScore DESC"
                
                await cursor.execute(query, params)
                students = await cursor.fetchall()
                
                leaderboard = []
                for i, student in enumerate(students):
                    # Get violations count
                    await cursor.execute("""
                        SELECT 
                            COUNT(*) as plagiarism_count 
                        FROM submissions 
                        WHERE student_id = %s AND plagiarism_detected = 'true'
                    """, (student['studentId'],))
                    violation_data = await cursor.fetchone()
                    plagiarism_count = violation_data['plagiarism_count'] if violation_data else 0
                    
                    leaderboard.append({
                        "rank": i + 1,
                        "studentId": student['studentId'],
                        "name": student['name'],
                        "avgScore": round(float(student['avgScore'])),
                        "totalSubmissions": student['totalSubmissions'],
                        "acceptedSubmissions": int(student['acceptedSubmissions']),
                        "violations": {
                            "plagiarism": plagiarism_count,
                        }
                    })
                    
                return leaderboard

            except Exception as e:
                print(f"Leaderboard Error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

