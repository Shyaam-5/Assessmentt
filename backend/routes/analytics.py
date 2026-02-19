"""Analytics routes for Admin, Mentor, and Student dashboards."""

from datetime import datetime, timedelta
from fastapi import APIRouter
from database import get_pool
import pymysql.cursors

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ─── Admin Dashboard ────────────────────────────────────────────

@router.get("/admin")
async def admin_analytics():
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Total students
            await cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'student'")
            total_students = (await cur.fetchone())["cnt"]

            # Total submissions (code + aptitude)
            await cur.execute("SELECT COUNT(*) AS cnt FROM submissions")
            code_sub_count = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM aptitude_submissions")
            apt_sub_count = (await cur.fetchone())["cnt"]
            total_submissions = code_sub_count + apt_sub_count

            # Total content (tasks + problems + aptitude tests)
            await cur.execute("SELECT COUNT(*) AS cnt FROM tasks")
            task_count = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM problems")
            prob_count = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM aptitude_tests")
            test_count = (await cur.fetchone())["cnt"]
            total_content = task_count + prob_count + test_count

            # Success rate (code passed + aptitude passed)
            await cur.execute("SELECT COUNT(*) AS cnt FROM submissions WHERE score >= 60")
            passed_code = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM aptitude_submissions WHERE status = 'passed'")
            passed_apt = (await cur.fetchone())["cnt"]
            success_rate = round(((passed_code + passed_apt) / total_submissions) * 100) if total_submissions > 0 else 0

            # Submission trends (last 7 days)
            await cur.execute(
                """SELECT DATE(submitted_at) AS date, COUNT(*) AS count
                   FROM submissions
                   WHERE submitted_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                   GROUP BY DATE(submitted_at)
                   ORDER BY date ASC"""
            )
            trends = await cur.fetchall()
            submission_trends = [
                {"date": t["date"].strftime("%b %d") if hasattr(t["date"], "strftime") else str(t["date"]), "count": t["count"]}
                for t in trends
            ]

            # Language stats
            await cur.execute(
                "SELECT language, COUNT(*) AS value FROM submissions GROUP BY language"
            )
            lang_rows = await cur.fetchall()
            language_stats = [
                {"name": r["language"] or "Unknown", "value": r["value"]} for r in lang_rows
            ]

            # Recent submissions
            await cur.execute(
                """SELECT s.id, u.name AS studentName, s.score, s.status, s.submitted_at AS time
                   FROM submissions s
                   JOIN users u ON s.student_id = u.id
                   ORDER BY s.submitted_at DESC LIMIT 5"""
            )
            recent_rows = await cur.fetchall()
            recent_submissions = [
                {
                    "id": r["id"],
                    "studentName": r["studentName"],
                    "score": r["score"],
                    "status": r["status"],
                    "time": str(r["time"]) if r["time"] else "",
                }
                for r in recent_rows
            ]

            # Student performance (Top 5)
            await cur.execute(
                """SELECT u.name, COUNT(s.id) AS count, AVG(s.score) AS score
                   FROM users u
                   JOIN submissions s ON u.id = s.student_id
                   GROUP BY u.id
                   ORDER BY score DESC, count DESC
                   LIMIT 5"""
            )
            perf_rows = await cur.fetchall()
            student_performance = [
                {"name": r["name"], "count": r["count"], "score": round(r["score"] or 0)}
                for r in perf_rows
            ]

    return {
        "totalStudents": total_students,
        "totalSubmissions": total_submissions,
        "successRate": success_rate,
        "totalContent": total_content,
        "submissionTrends": submission_trends,
        "languageStats": language_stats,
        "recentSubmissions": recent_submissions,
        "studentPerformance": student_performance,
    }


# ─── Student Dashboard ──────────────────────────────────────────

@router.get("/student/{student_id}")
async def student_analytics(student_id: str):
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Get student's mentor from allocation table
            await cur.execute(
                """SELECT m.id AS mentor_id, m.name AS mentor_name, m.email AS mentor_email
                   FROM mentor_student_allocations msa
                   JOIN users m ON msa.mentor_id = m.id
                   WHERE msa.student_id = %s
                   LIMIT 1""",
                (student_id,),
            )
            alloc_row = await cur.fetchone()
            mentor_info = None
            mentor_id = None
            if alloc_row:
                mentor_info = {
                    "id": alloc_row["mentor_id"],
                    "name": alloc_row["mentor_name"],
                    "email": alloc_row["mentor_email"],
                }
                mentor_id = alloc_row["mentor_id"]

            # Average problem score
            await cur.execute(
                "SELECT COALESCE(AVG(score), 0) AS avg FROM submissions WHERE student_id = %s AND problem_id IS NOT NULL",
                (student_id,),
            )
            avg_problem_score = round((await cur.fetchone())["avg"] or 0)

            # Average task score
            await cur.execute(
                "SELECT COALESCE(AVG(score), 0) AS avg FROM submissions WHERE student_id = %s AND task_id IS NOT NULL",
                (student_id,),
            )
            avg_task_score = round((await cur.fetchone())["avg"] or 0)

            # Total submissions
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM submissions WHERE student_id = %s",
                (student_id,),
            )
            total_submissions = (await cur.fetchone())["cnt"]

            # Tasks - total available (from mentor or admin) and completed
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE (mentor_id = %s OR mentor_id = 'admin-001') AND status = 'live'",
                (mentor_id,),
            )
            total_tasks = (await cur.fetchone())["cnt"]
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM task_completions WHERE student_id = %s",
                (student_id,),
            )
            completed_tasks = (await cur.fetchone())["cnt"]

            # Problems - total available and completed
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM problems WHERE (mentor_id = %s OR mentor_id = 'admin-001') AND status = 'live'",
                (mentor_id,),
            )
            total_problems = (await cur.fetchone())["cnt"]
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM problem_completions WHERE student_id = %s",
                (student_id,),
            )
            completed_problems = (await cur.fetchone())["cnt"]

            # Aptitude tests
            await cur.execute("SELECT COUNT(*) AS cnt FROM aptitude_tests WHERE status = 'live'")
            total_aptitude = (await cur.fetchone())["cnt"]
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM student_completed_aptitude WHERE student_id = %s",
                (student_id,),
            )
            completed_aptitude = (await cur.fetchone())["cnt"]

            # Submission trends (last 7 days)
            await cur.execute(
                """SELECT DATE(submitted_at) AS date, COUNT(*) AS count
                   FROM submissions
                   WHERE student_id = %s AND submitted_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                   GROUP BY DATE(submitted_at)
                   ORDER BY date ASC""",
                (student_id,),
            )
            trends = await cur.fetchall()
            submission_trends = [
                {"date": t["date"].strftime("%b %d") if hasattr(t["date"], "strftime") else str(t["date"]), "count": t["count"]}
                for t in trends
            ]

            # Recent submissions with problem/task title
            await cur.execute(
                """SELECT s.id, s.score, s.status, s.language, s.submitted_at AS time,
                          p.title AS problemTitle, t.title AS taskTitle
                   FROM submissions s
                   LEFT JOIN problems p ON s.problem_id = p.id
                   LEFT JOIN tasks t ON s.task_id = t.id
                   WHERE s.student_id = %s
                   ORDER BY s.submitted_at DESC LIMIT 5""",
                (student_id,),
            )
            recent_rows = await cur.fetchall()
            recent_submissions = [
                {
                    "id": r["id"],
                    "title": r["problemTitle"] or r["taskTitle"] or "Unknown",
                    "score": r["score"],
                    "status": r["status"],
                    "language": r["language"],
                    "time": str(r["time"]) if r["time"] else "",
                }
                for r in recent_rows
            ]

            # Leaderboard
            await cur.execute(
                """SELECT u.id AS studentId, u.name,
                          COUNT(DISTINCT tc.task_id) AS taskCount,
                          COUNT(DISTINCT pc.problem_id) AS codeCount,
                          COUNT(DISTINCT sca.aptitude_test_id) AS aptitudeCount,
                          COALESCE(AVG(sub.score), 0) AS avgScore
                   FROM users u
                   LEFT JOIN task_completions tc ON u.id = tc.student_id
                   LEFT JOIN problem_completions pc ON u.id = pc.student_id
                   LEFT JOIN student_completed_aptitude sca ON u.id = sca.student_id
                   LEFT JOIN submissions sub ON u.id = sub.student_id
                   WHERE u.role = 'student'
                   GROUP BY u.id
                   ORDER BY avgScore DESC, (taskCount + codeCount + aptitudeCount) DESC
                   LIMIT 10"""
            )
            lb_rows = await cur.fetchall()
            leaderboard = [
                {
                    "rank": idx + 1,
                    "studentId": r["studentId"],
                    "name": r["name"],
                    "taskCount": int(r["taskCount"] or 0),
                    "codeCount": int(r["codeCount"] or 0),
                    "aptitudeCount": int(r["aptitudeCount"] or 0),
                    "avgScore": round(float(r["avgScore"] or 0)),
                }
                for idx, r in enumerate(lb_rows)
            ]

    return {
        "mentorInfo": mentor_info,
        "avgProblemScore": avg_problem_score,
        "avgTaskScore": avg_task_score,
        "totalSubmissions": total_submissions,
        "totalTasks": total_tasks,
        "completedTasks": completed_tasks,
        "totalProblems": total_problems,
        "completedProblems": completed_problems,
        "totalAptitude": total_aptitude,
        "completedAptitude": completed_aptitude,
        "submissionTrends": submission_trends,
        "recentSubmissions": recent_submissions,
        "leaderboard": leaderboard,
    }


# ─── Mentor Dashboard ───────────────────────────────────────────

@router.get("/mentor/{mentor_id}")
async def mentor_analytics(mentor_id: str):
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Allocated students with details
            await cur.execute(
                """SELECT u.id, u.name, u.email, u.created_at,
                          (SELECT COUNT(*) FROM submissions WHERE student_id = u.id) AS submissionCount,
                          (SELECT AVG(score) FROM submissions WHERE student_id = u.id) AS avgScore,
                          (SELECT COUNT(*) FROM task_completions WHERE student_id = u.id) AS tasksCompleted,
                          (SELECT COUNT(*) FROM problem_completions WHERE student_id = u.id) AS problemsCompleted,
                          (SELECT submitted_at FROM submissions WHERE student_id = u.id ORDER BY submitted_at DESC LIMIT 1) AS lastActive
                   FROM users u
                   JOIN mentor_student_allocations msa ON u.id = msa.student_id
                   WHERE msa.mentor_id = %s
                   ORDER BY u.name ASC""",
                (mentor_id,),
            )
            allocations = await cur.fetchall()

            student_ids = [a["id"] for a in allocations]
            allocated_students = [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "email": s["email"],
                    "submissionCount": s["submissionCount"] or 0,
                    "avgScore": round(float(s["avgScore"] or 0)),
                    "tasksCompleted": s["tasksCompleted"] or 0,
                    "problemsCompleted": s["problemsCompleted"] or 0,
                    "lastActive": str(s["lastActive"]) if s["lastActive"] else None,
                    "joinedAt": str(s["created_at"]) if s["created_at"] else None,
                }
                for s in allocations
            ]

            if not student_ids:
                return {
                    "totalStudents": 0,
                    "totalSubmissions": 0,
                    "avgScore": 0,
                    "totalTasks": 0,
                    "totalProblems": 0,
                    "submissionTrends": [],
                    "languageStats": [],
                    "recentActivity": [],
                    "studentPerformance": [],
                    "allocatedStudents": [],
                }

            total_students = len(student_ids)
            ph = ",".join(["%s"] * len(student_ids))

            # Submission counts broken down
            await cur.execute(
                f"SELECT COUNT(*) AS cnt FROM task_completions WHERE student_id IN ({ph})",
                student_ids,
            )
            task_submissions = (await cur.fetchone())["cnt"]

            await cur.execute(
                f"SELECT COUNT(*) AS cnt FROM submissions WHERE student_id IN ({ph})",
                student_ids,
            )
            code_submissions = (await cur.fetchone())["cnt"]

            await cur.execute(
                f"SELECT COUNT(*) AS cnt FROM student_completed_aptitude WHERE student_id IN ({ph})",
                student_ids,
            )
            aptitude_submissions = (await cur.fetchone())["cnt"]

            total_submissions = task_submissions + code_submissions + aptitude_submissions

            # Average score
            await cur.execute(
                f"SELECT AVG(score) AS avg FROM submissions WHERE student_id IN ({ph})",
                student_ids,
            )
            avg_score = round(float((await cur.fetchone())["avg"] or 0))

            # Total content by mentor
            await cur.execute("SELECT COUNT(*) AS cnt FROM tasks WHERE mentor_id = %s", (mentor_id,))
            task_count = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM problems WHERE mentor_id = %s", (mentor_id,))
            prob_count = (await cur.fetchone())["cnt"]

            # Submission trends (last 7 days)
            await cur.execute(
                f"""SELECT DATE(submitted_at) AS date, COUNT(*) AS count
                    FROM submissions
                    WHERE student_id IN ({ph}) AND submitted_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                    GROUP BY DATE(submitted_at)
                    ORDER BY date ASC""",
                student_ids,
            )
            trends = await cur.fetchall()
            submission_trends = [
                {"date": t["date"].strftime("%b %d") if hasattr(t["date"], "strftime") else str(t["date"]), "count": t["count"]}
                for t in trends
            ]

            # Language stats
            await cur.execute(
                f"SELECT language, COUNT(*) AS value FROM submissions WHERE student_id IN ({ph}) GROUP BY language",
                student_ids,
            )
            lang_rows = await cur.fetchall()
            language_stats = [
                {"name": r["language"] or "Unknown", "value": r["value"]} for r in lang_rows
            ]

            # Recent activity
            await cur.execute(
                f"""SELECT s.id, u.name AS studentName, s.score, s.status, s.submitted_at AS time
                    FROM submissions s
                    JOIN users u ON s.student_id = u.id
                    WHERE s.student_id IN ({ph})
                    ORDER BY s.submitted_at DESC LIMIT 5""",
                student_ids,
            )
            recent_rows = await cur.fetchall()
            recent_activity = [
                {
                    "id": r["id"],
                    "studentName": r["studentName"],
                    "score": r["score"],
                    "status": r["status"],
                    "time": str(r["time"]) if r["time"] else "",
                }
                for r in recent_rows
            ]

            # Student performance (mentee performance)
            await cur.execute(
                f"""SELECT u.name, COUNT(s.id) AS count, AVG(s.score) AS score
                    FROM users u
                    JOIN submissions s ON u.id = s.student_id
                    WHERE u.id IN ({ph})
                    GROUP BY u.id
                    ORDER BY score DESC, count DESC
                    LIMIT 5""",
                student_ids,
            )
            perf_rows = await cur.fetchall()
            student_performance = [
                {"name": r["name"], "count": r["count"], "score": round(float(r["score"] or 0))}
                for r in perf_rows
            ]

    return {
        "totalStudents": total_students,
        "totalSubmissions": total_submissions,
        "taskSubmissions": task_submissions,
        "codeSubmissions": code_submissions,
        "aptitudeSubmissions": aptitude_submissions,
        "avgScore": avg_score,
        "totalTasks": task_count,
        "totalProblems": prob_count,
        "submissionTrends": submission_trends,
        "languageStats": language_stats,
        "recentActivity": recent_activity,
        "menteePerformance": student_performance,
        "allocatedStudents": allocated_students,
    }
