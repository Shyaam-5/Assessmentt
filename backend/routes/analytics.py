"""Analytics routes for Admin, Mentor, and Student dashboards."""

from datetime import datetime, timedelta
from fastapi import APIRouter
from database import get_pool

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ─── Admin Dashboard ────────────────────────────────────────────

@router.get("/admin")
async def admin_analytics():
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Total students
            await cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'student'")
            total_students = (await cur.fetchone())["cnt"]

            # Total mentors
            await cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'mentor'")
            mentor_count = (await cur.fetchone())["cnt"]

            # Total submissions (code)
            await cur.execute("SELECT COUNT(*) AS cnt FROM submissions")
            total_submissions = (await cur.fetchone())["cnt"]

            # Success rate
            if total_submissions > 0:
                await cur.execute(
                    "SELECT COUNT(*) AS cnt FROM submissions WHERE status = 'accepted'"
                )
                accepted = (await cur.fetchone())["cnt"]
                success_rate = round(accepted / total_submissions * 100)
            else:
                success_rate = 0

            # Total content (tasks + problems + aptitude tests)
            await cur.execute("SELECT COUNT(*) AS cnt FROM tasks")
            total_tasks = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM problems")
            total_problems = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM aptitude_tests")
            total_aptitude = (await cur.fetchone())["cnt"]
            total_content = total_tasks + total_problems + total_aptitude

            # Submission trends (last 7 days)
            submission_trends = []
            for i in range(6, -1, -1):
                day = datetime.utcnow() - timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                label = day.strftime("%b %d")
                await cur.execute(
                    "SELECT COUNT(*) AS cnt FROM submissions WHERE DATE(submitted_at) = %s",
                    (day_str,),
                )
                cnt = (await cur.fetchone())["cnt"]
                submission_trends.append({"date": label, "count": cnt})

            # Language stats
            await cur.execute(
                """SELECT language, COUNT(*) AS value
                   FROM submissions
                   WHERE language IS NOT NULL AND language != ''
                   GROUP BY language
                   ORDER BY value DESC
                   LIMIT 5"""
            )
            language_rows = await cur.fetchall()
            language_stats = [
                {"name": r["language"], "value": r["value"]} for r in language_rows
            ]
            if not language_stats:
                language_stats = [{"name": "Python", "value": 0}]

            # Student Performance (Top 5)
            await cur.execute(
                """SELECT u.name, COUNT(s.id) as count, AVG(s.score) as AvgScore
                   FROM users u
                   JOIN submissions s ON u.id = s.student_id
                   WHERE u.role = 'student'
                   GROUP BY u.id
                   ORDER BY AvgScore DESC, count DESC
                   LIMIT 5"""
            )
            perf_rows = await cur.fetchall()
            student_performance = [
                {"name": r["name"], "count": r["count"], "score": round(r["AvgScore"] or 0)}
                for r in perf_rows
            ]

            # Recent submissions
            await cur.execute(
                """SELECT s.id, s.student_id, s.score, s.status, s.submitted_at,
                          u.name AS student_name
                   FROM submissions s
                   LEFT JOIN users u ON s.student_id = u.id
                   ORDER BY s.submitted_at DESC
                   LIMIT 10"""
            )
            recent_rows = await cur.fetchall()
            recent_submissions = []
            for r in recent_rows:
                recent_submissions.append({
                    "id": r["id"],
                    "studentName": r["student_name"] or "Unknown",
                    "score": r["score"] or 0,
                    "status": r["status"] or "pending",
                    "time": str(r["submitted_at"]) if r["submitted_at"] else "",
                })

    return {
        "totalStudents": total_students,
        "mentorCount": mentor_count,
        "totalSubmissions": total_submissions,
        "successRate": success_rate,
        "totalContent": total_content,
        "submissionTrends": submission_trends,
        "languageStats": language_stats,
        "studentPerformance": student_performance,
        "recentSubmissions": recent_submissions,
    }


# ─── Student Dashboard ──────────────────────────────────────────

@router.get("/student/{student_id}")
async def student_analytics(student_id: str):
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Completed tasks
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM task_completions WHERE student_id = %s",
                (student_id,),
            )
            completed_tasks = (await cur.fetchone())["cnt"]

            # Total tasks available
            await cur.execute("SELECT COUNT(*) AS cnt FROM tasks")
            total_tasks = (await cur.fetchone())["cnt"]

            # Completed problems (distinct problems with accepted submissions)
            await cur.execute(
                """SELECT COUNT(DISTINCT problem_id) AS cnt
                   FROM submissions
                   WHERE student_id = %s AND status = 'accepted'""",
                (student_id,),
            )
            completed_problems = (await cur.fetchone())["cnt"]

            # Total problems
            await cur.execute("SELECT COUNT(*) AS cnt FROM problems")
            total_problems = (await cur.fetchone())["cnt"]

            # Average task score
            await cur.execute(
                "SELECT AVG(score) AS avg FROM submissions WHERE student_id = %s AND task_id IS NOT NULL",
                (student_id,),
            )
            avg_task_row = await cur.fetchone()
            avg_task_score = round(avg_task_row["avg"] or 0)

            # Average problem score
            await cur.execute(
                "SELECT AVG(score) AS avg FROM submissions WHERE student_id = %s",
                (student_id,),
            )
            avg_problem_row = await cur.fetchone()
            avg_problem_score = round(avg_problem_row["avg"] or 0)

            # Completed aptitude tests
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM student_completed_aptitude WHERE student_id = %s",
                (student_id,),
            )
            completed_aptitude = (await cur.fetchone())["cnt"]

            # Total aptitude tests
            await cur.execute("SELECT COUNT(*) AS cnt FROM aptitude_tests")
            total_aptitude = (await cur.fetchone())["cnt"]

            # Recent submissions
            await cur.execute(
                """SELECT s.id, s.problem_id, s.score, s.status, s.submitted_at,
                          p.title
                   FROM submissions s
                   LEFT JOIN problems p ON s.problem_id = p.id
                   WHERE s.student_id = %s
                   ORDER BY s.submitted_at DESC
                   LIMIT 5""",
                (student_id,),
            )
            recent_rows = await cur.fetchall()
            recent_submissions = [
                {
                    "id": r["id"],
                    "title": r["title"] or "Untitled",
                    "score": r["score"] or 0,
                    "status": r["status"] or "pending",
                    "time": str(r["submitted_at"]) if r["submitted_at"] else "",
                }
                for r in recent_rows
            ]

            # Leaderboard (top students by average score)
            await cur.execute(
                """SELECT
                       u.id AS student_id,
                       u.name,
                       COALESCE(AVG(s.score), 0) AS avg_score,
                       COUNT(DISTINCT tc.task_id) AS task_count,
                       COUNT(DISTINCT s.problem_id) AS code_count,
                       COALESCE(apt.apt_count, 0) AS aptitude_count
                   FROM users u
                   LEFT JOIN submissions s ON u.id = s.student_id
                   LEFT JOIN task_completions tc ON u.id = tc.student_id
                   LEFT JOIN (
                       SELECT student_id, COUNT(*) AS apt_count
                       FROM student_completed_aptitude
                       GROUP BY student_id
                   ) apt ON u.id = apt.student_id
                   WHERE u.role = 'student'
                   GROUP BY u.id, u.name, apt.apt_count
                   ORDER BY avg_score DESC
                   LIMIT 10"""
            )
            lb_rows = await cur.fetchall()
            leaderboard = []
            for idx, r in enumerate(lb_rows):
                leaderboard.append({
                    "rank": idx + 1,
                    "studentId": r["student_id"],
                    "name": r["name"],
                    "avgScore": round(float(r["avg_score"])),
                    "taskCount": r["task_count"],
                    "codeCount": r["code_count"],
                    "aptitudeCount": r["aptitude_count"],
                })

            # Mentor info
            await cur.execute(
                """SELECT u2.id, u2.name, u2.email
                   FROM users u1
                   JOIN users u2 ON u1.mentor_id = u2.id
                   WHERE u1.id = %s""",
                (student_id,),
            )
            mentor_row = await cur.fetchone()
            mentor_info = None
            if mentor_row:
                mentor_info = {
                    "id": mentor_row["id"],
                    "name": mentor_row["name"],
                    "email": mentor_row["email"],
                }

            # Get Student Rank
            await cur.execute(
                """SELECT COUNT(*) + 1 as rank FROM (
                       SELECT u.id, COALESCE(AVG(s.score), 0) as avgScore
                       FROM users u
                       LEFT JOIN submissions s ON u.id = s.student_id
                       WHERE u.role = 'student'
                       GROUP BY u.id
                   ) sub
                   WHERE sub.avgScore > (
                       SELECT COALESCE(AVG(s2.score), 0)
                       FROM submissions s2
                       WHERE s2.student_id = %s
                   )""",
                (student_id,)
            )
            rank_row = await cur.fetchone()
            student_rank = rank_row["rank"] if rank_row else 0

    return {
        "completedTasks": completed_tasks,
        "totalTasks": total_tasks,
        "completedProblems": completed_problems,
        "totalProblems": total_problems,
        "avgTaskScore": avg_task_score,
        "avgProblemScore": avg_problem_score,
        "completedAptitude": completed_aptitude,
        "totalAptitude": total_aptitude,
        "recentSubmissions": recent_submissions,
        "leaderboard": leaderboard,
        "mentorInfo": mentor_info,
        "studentRank": student_rank,
    }


# ─── Mentor Dashboard ───────────────────────────────────────────

@router.get("/mentor/{mentor_id}")
async def mentor_analytics(mentor_id: str):
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Allocated students
            await cur.execute(
                "SELECT id, name FROM users WHERE role = 'student' AND mentor_id = %s",
                (mentor_id,),
            )
            student_rows = await cur.fetchall()
            student_ids = [r["id"] for r in student_rows]
            total_students = len(student_ids)

            # Submission counts for mentor's students
            if student_ids:
                placeholders = ",".join(["%s"] * len(student_ids))

                # Task submissions
                await cur.execute(
                    f"SELECT COUNT(*) AS cnt FROM task_completions WHERE student_id IN ({placeholders})",
                    student_ids,
                )
                task_submissions = (await cur.fetchone())["cnt"]

                # Code submissions
                await cur.execute(
                    f"SELECT COUNT(*) AS cnt FROM submissions WHERE student_id IN ({placeholders})",
                    student_ids,
                )
                code_submissions = (await cur.fetchone())["cnt"]

                # Aptitude submissions
                await cur.execute(
                    f"SELECT COUNT(*) AS cnt FROM student_completed_aptitude WHERE student_id IN ({placeholders})",
                    student_ids,
                )
                aptitude_submissions = (await cur.fetchone())["cnt"]

                # Average score
                await cur.execute(
                    f"SELECT AVG(score) AS avg FROM submissions WHERE student_id IN ({placeholders})",
                    student_ids,
                )
                avg_row = await cur.fetchone()
                avg_score = round(float(avg_row["avg"] or 0))

                # Submission trends
                submission_trends = []
                for i in range(6, -1, -1):
                    day = datetime.utcnow() - timedelta(days=i)
                    day_str = day.strftime("%Y-%m-%d")
                    label = day.strftime("%b %d")
                    await cur.execute(
                        f"""SELECT COUNT(*) AS cnt FROM submissions
                            WHERE student_id IN ({placeholders})
                            AND DATE(submitted_at) = %s""",
                        student_ids + [day_str],
                    )
                    cnt = (await cur.fetchone())["cnt"]
                    submission_trends.append({"date": label, "count": cnt})

                # Language stats
                await cur.execute(
                    f"""SELECT language, COUNT(*) AS value
                        FROM submissions
                        WHERE student_id IN ({placeholders})
                          AND language IS NOT NULL AND language != ''
                        GROUP BY language
                        ORDER BY value DESC
                        LIMIT 5""",
                    student_ids,
                )
                lang_rows = await cur.fetchall()
                language_stats = [
                    {"name": r["language"], "value": r["value"]} for r in lang_rows
                ]
                if not language_stats:
                    language_stats = [{"name": "Python", "value": 0}]

                # Recent activity
                await cur.execute(
                    f"""SELECT s.id, s.score, s.status, s.submitted_at,
                               u.name AS student_name
                        FROM submissions s
                        LEFT JOIN users u ON s.student_id = u.id
                        WHERE s.student_id IN ({placeholders})
                        ORDER BY s.submitted_at DESC
                        LIMIT 10""",
                    student_ids,
                )
                activity_rows = await cur.fetchall()
                recent_activity = [
                    {
                        "id": r["id"],
                        "studentName": r["student_name"] or "Unknown",
                        "score": r["score"] or 0,
                        "status": r["status"] or "pending",
                        "time": str(r["submitted_at"]) if r["submitted_at"] else "",
                    }
                    for r in activity_rows
                ]

            else:
                task_submissions = 0
                code_submissions = 0
                aptitude_submissions = 0
                avg_score = 0
                submission_trends = [
                    {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%b %d"), "count": 0}
                    for i in range(6, -1, -1)
                ]
                language_stats = [{"name": "Python", "value": 0}]
                recent_activity = []

            # Total content created by mentor
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE mentor_id = %s",
                (mentor_id,),
            )
            total_tasks = (await cur.fetchone())["cnt"]
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM problems WHERE mentor_id = %s",
                (mentor_id,),
            )
            total_problems = (await cur.fetchone())["cnt"]

    return {
        "totalStudents": total_students,
        "taskSubmissions": task_submissions,
        "codeSubmissions": code_submissions,
        "aptitudeSubmissions": aptitude_submissions,
        "avgScore": avg_score,
        "totalTasks": total_tasks,
        "totalProblems": total_problems,
        "submissionTrends": submission_trends,
        "languageStats": language_stats,
        "recentActivity": recent_activity,
    }
