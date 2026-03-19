"""Cerebras AI API wrapper with key rotation / failover.

Provides generation & evaluation helpers for the Skill-Test assessment system:
MCQ, Coding, SQL, Interview, and Final Report.
"""

import json
import math
import random
import re
import asyncio
from typing import Any

from groq import Groq
from config import settings

# ─── Topic pools for variety ───────────────────────────────────────────
TOPIC_POOLS = {
    "concepts": [
        "design patterns", "concurrency", "memory management", "error handling",
        "testing", "security", "performance", "architecture", "debugging",
        "deployment", "networking", "APIs", "databases", "caching", "logging",
    ],
    "approaches": [
        "scenario-based", "code-output prediction", "bug-finding",
        "best-practice identification", "tradeoff analysis",
        "real-world problem solving", "optimization", "architecture decision",
    ],
    "themes": [
        "e-commerce system", "social media app", "banking system",
        "healthcare platform", "logistics system", "real-time chat",
        "streaming service", "IoT dashboard", "machine learning pipeline",
        "CI/CD workflow",
    ],
}


def _random_seed() -> int:
    return random.randint(0, 999_999)


def _pick_random(arr: list, n: int) -> list:
    return random.sample(arr, min(n, len(arr)))


# ─── Low-level Cerebras caller ─────────────────────────────────────────
async def cerebras_chat(
    messages: list[dict],
    *,
    model: str = "openai/gpt-oss-20b",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    response_format: dict | None = None,
) -> dict:
    """Call Groq chat completions, rotating through available keys on failure."""

    keys = settings.GROQ_API_KEYS
    if not keys:
        raise RuntimeError("No Groq API keys configured.")

    last_error: Exception | None = None

    for api_key in keys:
        try:
            client = Groq(api_key=api_key)

            create_kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
                "top_p": 1,
                "stream": False,
                "stop": None,
            }
            if response_format:
                create_kwargs["response_format"] = response_format

            # Groq SDK is sync; run call in worker thread from async context.
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                **create_kwargs,
            )

            data = completion.model_dump() if hasattr(completion, "model_dump") else completion
            if isinstance(data, dict):
                return data
            return dict(data)

        except Exception as exc:
            print(f"⚠️  Network error with key …{api_key[-5:]}: {exc}")
            last_error = exc

    raise last_error or RuntimeError("All AI API keys failed.")


# ─── Helper: call Cerebras and return content string ───────────────────
async def _call_cerebras(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Convenience wrapper that returns the assistant content string."""
    result = await cerebras_chat(
        messages, temperature=temperature, max_tokens=max_tokens,
    )
    return (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )


# ─── JSON parser (handles code-fenced responses) ──────────────────────
def parse_json(text: str) -> Any:
    """Parse JSON from AI response, handling markdown code blocks."""
    if not text:
        return None
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Code-block extraction
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Find first JSON array or object
    m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════
#  MCQ GENERATION
# ═══════════════════════════════════════════════════════════════════════

async def generate_mcq_questions(skills: list[str], count: int = 10) -> list[dict]:
    skills_str = ", ".join(skills[:15])
    seed = _random_seed()
    focus_topics = ", ".join(_pick_random(TOPIC_POOLS["concepts"], 4))
    question_style = ", ".join(_pick_random(TOPIC_POOLS["approaches"], 3))

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert technical interviewer. Generate multiple choice questions for a technical assessment.\n"
                "Each question must be relevant to the candidate's skills and test practical knowledge.\n"
                "Return ONLY a valid JSON array, no other text.\n"
                "Each question object must have these exact fields:\n"
                '- "id": number (1, 2, 3...)\n'
                '- "question": string (the question text)\n'
                '- "skill": string (which skill this tests)\n'
                '- "difficulty": string ("easy", "medium", or "hard")\n'
                '- "options": array of exactly 4 strings\n'
                '- "correct_answer": number (0-3 index of correct option)\n'
                '- "explanation": string (brief explanation of correct answer)'
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Seed: {seed}] Generate {count} UNIQUE technical MCQ questions based on these skills: {skills_str}\n\n"
                f"IMPORTANT: Generate completely NEW and UNIQUE questions every time. DO NOT use common or frequently-asked questions.\n"
                f"Focus on these specific topics for THIS session: {focus_topics}\n"
                f"Use these question styles: {question_style}\n\n"
                "Distribution:\n- 30% Easy questions (fundamentals)\n- 50% Medium questions (practical application)\n"
                "- 20% Hard questions (advanced concepts)\n\n"
                "Make questions practical and real-world oriented. Cover different skills proportionally.\n"
                'Be creative and avoid generic questions like "What is X?" - instead test applied knowledge.\n'
                "Return ONLY a valid JSON array."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.95, max_tokens=8000)
        questions = parse_json(response)

        if not questions or not isinstance(questions, list):
            return generate_fallback_mcq(skills, count)

        valid: list[dict] = []
        for i, q in enumerate(questions):
            if q and q.get("question") and q.get("options") and isinstance(q.get("correct_answer"), (int, float)):
                q["id"] = i + 1
                opts = q["options"]
                if isinstance(opts, list) and len(opts) >= 4:
                    q["options"] = opts[:4]
                    valid.append(q)

        return valid if valid else generate_fallback_mcq(skills, count)
    except Exception as exc:
        print(f"MCQ generation failed: {exc}")
        return generate_fallback_mcq(skills, count)


def generate_fallback_mcq(skills: list[str], count: int = 10) -> list[dict]:
    questions: list[dict] = []
    for i in range(min(count, len(skills) * 3)):
        skill = skills[i % len(skills)]
        questions.append({
            "id": i + 1,
            "question": f"Which of the following best describes a core concept of {skill}?",
            "skill": skill,
            "difficulty": ["easy", "medium", "hard"][i % 3],
            "options": [
                f"A fundamental principle of {skill}",
                f"A framework commonly used with {skill}",
                f"A design pattern in {skill}",
                f"A tool used alongside {skill}",
            ],
            "correct_answer": 0,
            "explanation": f"This is a fundamental concept in {skill}.",
        })
    return questions


# ═══════════════════════════════════════════════════════════════════════
#  CODING PROBLEM GENERATION
# ═══════════════════════════════════════════════════════════════════════

async def generate_coding_problems(
    skills: list[str], count: int = 3, difficulty_level: str = "mixed",
) -> list[dict]:
    prog_keywords = {
        "python", "java", "javascript", "typescript", "c++", "c#", "go",
        "rust", "c", "dsa", "data structures", "algorithms", "react",
        "node", "express",
    }
    prog_skills = [s for s in skills if s.lower() in prog_keywords]
    relevant = prog_skills if prog_skills else skills[:3]
    skills_str = ", ".join(relevant[:5])

    if difficulty_level == "easy":
        diff_instr = f'All {count} problems should be "easy" difficulty (basic logic/implementation).'
    elif difficulty_level == "medium":
        diff_instr = f'All {count} problems should be "medium" difficulty (data structures/algorithms).'
    elif difficulty_level == "hard":
        diff_instr = f'All {count} problems should be "hard" difficulty (complex problem solving).'
    else:
        if count == 1:
            diff_instr = "Generate 1 easy problem."
        elif count == 2:
            diff_instr = "Generate 1 easy and 1 medium problem."
        else:
            diff_instr = "Distribute difficulty across easy, medium, and hard."

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an expert coding challenge designer. Generate coding problems for a technical assessment.\n"
                f"Return ONLY a valid JSON array with EXACTLY {count} problems. Each problem object must have:\n"
                '- "id": number\n- "title": string\n'
                '- "description": string (clear problem statement with examples)\n'
                '- "difficulty": "easy" | "medium" | "hard"\n'
                '- "skills_tested": array of strings\n'
                '- "input_format": string\n- "output_format": string\n'
                '- "sample_input": string\n- "sample_output": string\n'
                '- "test_cases": array of objects with "input" and "expected_output" strings\n'
                '- "starter_code": object with keys "python", "javascript", "java", "cpp".\n'
                "  This code must include:\n"
                "  1. The solution function definition (empty or pass).\n"
                "  2. Driver code that reads from STDIN, parses the input according to input_format, calls the solution function, and prints the result to STDOUT.\n"
                "  3. Comments indicating where the user should write their code.\n"
                '- "time_limit_seconds": number\n'
                '- "hints": array of strings (2-3 hints)'
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Seed: {_random_seed()}] Generate EXACTLY {count} UNIQUE coding problem(s) that test these skills: {skills_str}\n\n"
                f"{diff_instr}\n\n"
                "IMPORTANT: Generate completely DIFFERENT problems every time. Avoid common problems like Two Sum, FizzBuzz, Palindrome, Fibonacci, Reverse String.\n"
                f"Think of creative, unique problem scenarios from: {', '.join(_pick_random(TOPIC_POOLS['themes'], 3))}.\n\n"
                "Each problem should have at least 3 test cases.\n"
                'Make sure the "starter_code" for each language is correct and runnable.\n'
                f"Return ONLY a valid JSON array with exactly {count} problem(s)."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.9, max_tokens=8000)
        problems = parse_json(response)
        if problems and isinstance(problems, list) and len(problems) > 0:
            result = []
            for idx, p in enumerate(problems[:count]):
                p["id"] = p.get("id", idx + 1)
                if p.get("sample_input") and p.get("sample_output"):
                    p.setdefault("examples", [{"input": p["sample_input"], "output": p["sample_output"], "explanation": p.get("sample_explanation", "")}])
                else:
                    p.setdefault("examples", [])
                result.append(p)
            return result
        return generate_fallback_coding(skills, count, difficulty_level)
    except Exception as exc:
        print(f"Coding generation failed: {exc}")
        return generate_fallback_coding(skills, count, difficulty_level)


def generate_fallback_coding(
    skills: list[str], count: int = 3, difficulty_level: str = "mixed",
) -> list[dict]:
    all_problems = [
        {
            "id": 1, "title": "Two Sum", "difficulty": "easy",
            "description": "Given an array of integers nums and an integer target, return indices of the two numbers that add up to target.",
            "skills_tested": ["arrays", "hash-maps"],
            "input_format": "First line: space-separated integers\nSecond line: target integer",
            "output_format": "Space-separated indices",
            "sample_input": "2 7 11 15\n9", "sample_output": "0 1",
            "starter_code": {
                "python": 'import sys\n\ndef two_sum(nums, target):\n    # Write your code here\n    pass\n\nif __name__ == "__main__":\n    nums = list(map(int, input().split()))\n    target = int(input())\n    result = two_sum(nums, target)\n    if result:\n        print(f"{result[0]} {result[1]}")',
                "javascript": 'const fs = require("fs");\nfunction twoSum(nums, target) {\n    // Write your code here\n    return [];\n}\nconst input = fs.readFileSync(0, "utf-8").trim().split("\\n");\nconst nums = input[0].split(" ").map(Number);\nconst target = Number(input[1]);\nconst result = twoSum(nums, target);\nconsole.log(result.join(" "));',
                "java": "",
                "cpp": "",
            },
            "examples": [{"input": "2 7 11 15\n9", "output": "0 1", "explanation": "nums[0] + nums[1] = 9"}],
            "test_cases": [
                {"input": "2 7 11 15\n9", "expected_output": "0 1"},
                {"input": "3 2 4\n6", "expected_output": "1 2"},
                {"input": "3 3\n6", "expected_output": "0 1"},
            ],
            "time_limit_seconds": 5,
            "hints": ["Try using a hash map", "Store complement values"],
        },
        {
            "id": 2, "title": "Valid Parentheses", "difficulty": "medium",
            "description": "Given a string containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.",
            "skills_tested": ["stacks", "string-processing"],
            "input_format": "A string of brackets",
            "output_format": "true or false",
            "sample_input": "()[]{}", "sample_output": "true",
            "starter_code": {
                "python": 'import sys\n\ndef is_valid(s):\n    # Write your code here\n    return False\n\nif __name__ == "__main__":\n    s = sys.stdin.read().strip()\n    print("true" if is_valid(s) else "false")',
                "javascript": 'const fs = require("fs");\nfunction isValid(s) { return false; }\nconst s = fs.readFileSync(0,"utf-8").trim();\nconsole.log(isValid(s) ? "true" : "false");',
                "java": "", "cpp": "",
            },
            "examples": [{"input": "()[]{}", "output": "true", "explanation": "All brackets properly matched"}],
            "test_cases": [
                {"input": "()", "expected_output": "true"},
                {"input": "()[]{}", "expected_output": "true"},
                {"input": "(]", "expected_output": "false"},
            ],
            "time_limit_seconds": 5,
            "hints": ["Use a stack", "Push opening brackets, pop for closing"],
        },
        {
            "id": 3, "title": "Longest Substring Without Repeating Characters", "difficulty": "hard",
            "description": "Given a string s, find the length of the longest substring without repeating characters.",
            "skills_tested": ["sliding-window", "hash-maps"],
            "input_format": "A string",
            "output_format": "An integer",
            "sample_input": "abcabcbb", "sample_output": "3",
            "starter_code": {
                "python": 'import sys\n\ndef length_of_longest(s):\n    # Write your code here\n    return 0\n\nif __name__ == "__main__":\n    s = sys.stdin.read().strip()\n    print(length_of_longest(s))',
                "javascript": 'const fs = require("fs");\nfunction lengthOfLongestSubstring(s) { return 0; }\nconst s = fs.readFileSync(0,"utf-8").trim();\nconsole.log(lengthOfLongestSubstring(s));',
                "java": "", "cpp": "",
            },
            "examples": [{"input": "abcabcbb", "output": "3", "explanation": 'Longest is "abc"'}],
            "test_cases": [
                {"input": "abcabcbb", "expected_output": "3"},
                {"input": "bbbbb", "expected_output": "1"},
                {"input": "pwwkew", "expected_output": "3"},
            ],
            "time_limit_seconds": 5,
            "hints": ["Sliding window technique", "Use a set to track characters"],
        },
    ]
    filtered = all_problems
    if difficulty_level and difficulty_level != "mixed":
        filtered = [p for p in all_problems if p["difficulty"] == difficulty_level] or all_problems
    return filtered[: min(count, len(filtered))]


# ═══════════════════════════════════════════════════════════════════════
#  SQL PROBLEM GENERATION
# ═══════════════════════════════════════════════════════════════════════

async def generate_sql_problems(
    skills: list[str], count: int = 3, table_names: dict | None = None,
) -> list[dict]:
    tables = table_names or {
        "employees": "employees",
        "departments": "departments",
        "projects": "projects",
        "orders": "orders",
    }

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert SQL instructor. Generate SQL problems that can be tested against a sandbox database.\n\n"
                f"The sandbox database has these tables:\n"
                f"- {tables['employees']} (id INT, name TEXT, department TEXT, salary DECIMAL, hire_date DATE, manager_id INT)\n"
                f"- {tables['departments']} (id INT, name TEXT, budget DECIMAL, location TEXT)\n"
                f"- {tables['projects']} (id INT, name TEXT, department_id INT, start_date DATE, end_date DATE, status TEXT)\n"
                f"- {tables['orders']} (id INT, customer_name TEXT, product TEXT, quantity INT, price DECIMAL, order_date DATE)\n\n"
                f"IMPORTANT: Use EXACTLY these table names: {tables['employees']}, {tables['departments']}, {tables['projects']}, {tables['orders']}\n\n"
                "Return ONLY a valid JSON array. Each problem must have:\n"
                '- "id": number\n- "title": string\n- "description": string\n'
                '- "difficulty": "easy" | "medium" | "hard"\n- "hint": string\n'
                '- "expected_columns": array of strings\n- "reference_query": string'
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Seed: {_random_seed()}] Generate {count} UNIQUE SQL problems with increasing difficulty.\n\n"
                "IMPORTANT: Generate completely DIFFERENT problems every time.\n"
                f"Think of creative query scenarios involving: {', '.join(_pick_random(['joins', 'subqueries', 'window functions', 'aggregation', 'string functions', 'date functions', 'CASE statements', 'CTEs', 'self-joins', 'UNION', 'HAVING', 'nested queries'], 4))}.\n\n"
                f"Remember: Use these EXACT table names: {tables['employees']}, {tables['departments']}, {tables['projects']}, {tables['orders']}\n\n"
                "Return ONLY a valid JSON array."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.9, max_tokens=4000)
        problems = parse_json(response)
        if problems and isinstance(problems, list) and len(problems) > 0:
            return problems[:count]
        return _default_sql_problems(count)
    except Exception as exc:
        print(f"SQL generation failed: {exc}")
        return _default_sql_problems(count)


def _default_sql_problems(count: int = 3) -> list[dict]:
    all_p = [
        {
            "id": 1, "title": "Employee Salary Report", "difficulty": "easy",
            "description": "Find all employees who earn more than the average salary. Display their name, department, and salary. Order by salary descending.",
            "hint": "Use a subquery with AVG().",
            "expected_columns": ["name", "department", "salary"],
            "reference_query": "SELECT name, department, salary FROM employees WHERE salary > (SELECT AVG(salary) FROM employees) ORDER BY salary DESC",
        },
        {
            "id": 2, "title": "Department Statistics", "difficulty": "medium",
            "description": "Show each department with the count of employees and average salary. Only include departments with more than 1 employee. Order by average salary descending.",
            "hint": "Use GROUP BY with HAVING clause.",
            "expected_columns": ["department", "employee_count", "avg_salary"],
            "reference_query": "SELECT department, COUNT(*) as employee_count, ROUND(AVG(salary), 2) as avg_salary FROM employees GROUP BY department HAVING COUNT(*) > 1 ORDER BY avg_salary DESC",
        },
        {
            "id": 3, "title": "Top Revenue Products", "difficulty": "hard",
            "description": "Find the top 3 products by total revenue (quantity * price). Show product name, total quantity sold, and total revenue.",
            "hint": "Use GROUP BY with aggregate functions and LIMIT.",
            "expected_columns": ["product", "total_quantity", "total_revenue"],
            "reference_query": "SELECT product, SUM(quantity) as total_quantity, SUM(quantity * price) as total_revenue FROM orders GROUP BY product ORDER BY total_revenue DESC LIMIT 3",
        },
    ]
    return all_p[: min(count, len(all_p))]


# ═══════════════════════════════════════════════════════════════════════
#  INTERVIEW QUESTION GENERATION
# ═══════════════════════════════════════════════════════════════════════

async def generate_interview_question(
    skills: list[str],
    previous_qa: list[dict],
    question_number: int = 1,
    total_questions: int = 5,
) -> dict:
    prev_context = ""
    if previous_qa:
        for i, qa in enumerate(previous_qa[-3:]):
            prev_context += f"Q{i+1}: {qa.get('question','')}\nA{i+1}: {qa.get('answer','No answer')}\nScore: {qa.get('score','N/A')}/10\n"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior technical interviewer conducting an AI-powered interview.\n"
                "Ask one focused, insightful question at a time.\n"
                "Return a JSON object with:\n"
                '- "question": string\n- "category": string\n'
                '- "difficulty": "easy" | "medium" | "hard"\n'
                '- "expected_key_points": array of strings\n'
                '- "follow_up_context": string'
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Seed: {_random_seed()}] Skills to test: {', '.join(skills)}\n\n"
                f"Question {question_number} of {total_questions}.\n\n"
                f"Previous Q&A Context:\n{prev_context or 'This is the first question.'}\n\n"
                "Generate the next interview question. Make it progressively more challenging.\n"
                f"Focus on: {', '.join(_pick_random(TOPIC_POOLS['concepts'], 2))}\n\n"
                "Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.95, max_tokens=2000)
        data = parse_json(response)
        if data and data.get("question"):
            # Normalise key name
            if "expected_key_points" in data and "key_points" not in data:
                data["key_points"] = data.pop("expected_key_points")
            return data
        return _fallback_question(skills, question_number)
    except Exception as exc:
        print(f"Interview question generation failed: {exc}")
        return _fallback_question(skills, question_number)


def _fallback_question(skills: list[str], question_number: int = 1) -> dict:
    skill = skills[question_number % len(skills)] if skills else "programming"
    return {
        "question": f"Can you explain your understanding of {skill} and describe how you would use it in a real project?",
        "category": skill,
        "difficulty": "easy" if question_number <= 3 else ("medium" if question_number <= 7 else "hard"),
        "key_points": ["Technical depth", "Practical experience", "Problem-solving approach"],
        "follow_up_context": "Fallback question",
    }


# ═══════════════════════════════════════════════════════════════════════
#  INTERVIEW ANSWER EVALUATION
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_interview_answer(
    question: str, answer: str, key_points: list[str] | None = None,
) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a technical interview evaluator. Evaluate the candidate's answer objectively.\n"
                "Return a JSON object with:\n"
                '- "score": number (0-10)\n- "feedback": string\n'
                '- "strengths": array of strings\n- "weaknesses": array of strings\n'
                '- "key_points_covered": array of strings\n- "suggestion": string'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Expected Key Points: {json.dumps(key_points or [])}\n\n"
                f"Candidate's Answer: {answer}\n\n"
                "Evaluate this answer. Be fair but thorough. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.3, max_tokens=2000)
        evaluation = parse_json(response)
        if evaluation and isinstance(evaluation.get("score"), (int, float)):
            return evaluation
        return {"score": 5, "feedback": "Answer received. Unable to perform detailed evaluation.", "strengths": [], "weaknesses": [], "key_points_covered": [], "suggestion": "Try to provide more detailed explanations."}
    except Exception as exc:
        print(f"Evaluation failed: {exc}")
        return {"score": 5, "feedback": "Evaluation service temporarily unavailable.", "strengths": [], "weaknesses": [], "key_points_covered": [], "suggestion": "Please try again."}


# ═══════════════════════════════════════════════════════════════════════
#  SQL QUERY EVALUATION (AI-based, no prod DB execution)
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_sql_query(problem: dict, student_query: str) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert SQL evaluator. Compare a student's SQL query against a reference solution.\n\n"
                "Evaluate if the student's query would produce the SAME result as the reference query.\n"
                "Consider: column names/aliases, filtering logic, joins, grouping, ordering, aggregations, and correct table names.\n"
                "Minor style differences are OK as long as the OUTPUT would be equivalent.\n\n"
                "Return ONLY a valid JSON object with:\n"
                '- "passed": boolean\n- "feedback": string\n- "score": number 0-100'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Problem: {problem.get('title', '')}\n"
                f"Description: {problem.get('description', '')}\n"
                f"Expected columns: {json.dumps(problem.get('expected_columns', []))}\n"
                f"Reference query: {problem.get('reference_query', 'Not available')}\n\n"
                f"Student's query: {student_query}\n\n"
                "Evaluate if the student's query is correct. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.2, max_tokens=1500)
        evaluation = parse_json(response)
        if evaluation and isinstance(evaluation.get("passed"), bool):
            return evaluation
        return {"passed": False, "feedback": "Unable to evaluate query. Please try again.", "score": 0}
    except Exception as exc:
        print(f"SQL evaluation failed: {exc}")
        return {"passed": False, "feedback": "Evaluation service temporarily unavailable.", "score": 0}


# ═══════════════════════════════════════════════════════════════════════
#  FINAL REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════

async def generate_final_report(
    test_title: str,
    skills: list[str],
    mcq_results: dict,
    coding_results: dict,
    sql_results: dict,
    interview_results: dict,
    proctoring_violations: int = 0,
) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert career coach and technical interviewer preparing a detailed placement report.\n\n"
                "Return a JSON object with:\n"
                '- "overall_rating": string ("Excellent" | "Good" | "Average" | "Below Average" | "Not Recommended")\n'
                '- "summary": string (detailed executive summary)\n'
                '- "strengths": array of strings\n- "weaknesses": array of strings\n'
                '- "skill_gap_analysis": array of objects with "skill", "current_level", "target_level", "gap_description"\n'
                '- "roadmap": array of objects with "week" (1-4), "focus_area", "action_items" (array)\n'
                '- "performance_metrics": object with "accuracy", "speed", "completeness", "code_quality" (0-100)\n'
                '- "concept_mastery": object with concept names as keys and scores 0-100\n'
                '- "section_feedback": object with keys "mcq", "coding", "sql", "interview" — each a string\n'
                '- "mcq_question_analysis": array of objects with "question_summary", "correct", "skill", "feedback"'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Test: {test_title}\nSkills Tested: {json.dumps(skills)}\n\n"
                f"MCQ Results:\n- Score: {mcq_results.get('score', 0)}%\n- Correct: {mcq_results.get('correct', 0)}/{mcq_results.get('total', 0)}\n- Passed: {mcq_results.get('passed', False)}\n"
                f"- Question Details: {json.dumps(mcq_results.get('questionDetails', []))}\n\n"
                f"Coding Results:\n- Score: {coding_results.get('score', 0)}%\n- Problems Solved: {coding_results.get('solved', 0)}/{coding_results.get('total', 0)}\n- Passed: {coding_results.get('passed', False)}\n\n"
                f"SQL Results:\n- Score: {sql_results.get('score', 0)}%\n- Problems Solved: {sql_results.get('solved', 0)}/{sql_results.get('total', 0)}\n- Passed: {sql_results.get('passed', False)}\n\n"
                f"AI Interview Results:\n- Average Score: {interview_results.get('avgScore', 0)}/10\n- Questions Answered: {interview_results.get('answered', 0)}/{interview_results.get('total', 0)}\n- Passed: {interview_results.get('passed', False)}\n\n"
                f"Proctoring:\n- Total Violations: {proctoring_violations}\n\n"
                "Generate a comprehensive, detailed report. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.5, max_tokens=6000)
        report = parse_json(response)
        if report and report.get("overall_rating"):
            return report
        return _default_report()
    except Exception as exc:
        print(f"Report generation failed: {exc}")
        return _default_report()


def _default_report() -> dict:
    return {
        "overall_rating": "Average",
        "summary": "Report generation encountered an issue. Please review individual test results.",
        "strengths": [],
        "weaknesses": [],
        "skill_gap_analysis": [],
        "roadmap": [],
        "performance_metrics": {"accuracy": 0, "speed": 0, "completeness": 0, "code_quality": 0},
        "concept_mastery": {},
        "section_feedback": {"mcq": "N/A", "coding": "N/A", "sql": "N/A", "interview": "N/A"},
        "mcq_question_analysis": [],
    }


# ═══════════════════════════════════════════════════════════════════════
#  AGENTIC EVALUATION — APTITUDE MODULE
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_aptitude_submission(
    test_title: str,
    question_results: list[dict],
    score: float,
    category_breakdown: dict | None = None,
) -> dict:
    """AI agent that holistically evaluates an aptitude test submission.

    Returns a rich evaluation including per-category insight, conceptual
    gap analysis, and a personalised improvement roadmap.
    """
    wrong_answers = [
        {
            "question": qr.get("question", ""),
            "category": qr.get("category", "general"),
            "student_answer": qr.get("userAnswer", ""),
            "correct_answer": qr.get("correctAnswer", ""),
            "explanation": qr.get("explanation", ""),
        }
        for qr in question_results
        if not qr.get("isCorrect", False)
    ]

    correct_count = sum(1 for qr in question_results if qr.get("isCorrect"))
    total = len(question_results)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert aptitude assessment coach. Analyse a student's aptitude test results and "
                "produce a structured evaluation that identifies conceptual gaps, mindset issues, and a "
                "concrete improvement plan.\n\n"
                "Return ONLY a valid JSON object with these keys:\n"
                '- "overall_feedback": string (2-3 sentence executive summary)\n'
                '- "performance_band": string ("Excellent" | "Good" | "Average" | "Needs Improvement" | "Critical")\n'
                '- "strengths": array of strings\n'
                '- "improvement_areas": array of strings\n'
                '- "per_category_insights": array of objects with {"category", "insight", "tip"}\n'
                '- "recommended_topics": array of strings (topics to study)\n'
                '- "wrong_answer_analysis": array of objects with {"question_summary", "likely_misconception", "correct_concept"}\n'
                '- "study_plan": array of objects with {"week", "focus", "tasks"} for 2 weeks'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Test: {test_title}\n"
                f"Score: {round(score)}% ({correct_count}/{total} correct)\n\n"
                f"Category breakdown: {json.dumps(category_breakdown or {})}\n\n"
                f"Wrong answers ({len(wrong_answers)}):\n{json.dumps(wrong_answers, indent=2)}\n\n"
                "Analyse this aptitude test performance. Focus on patterns in wrong answers to identify "
                "underlying conceptual gaps. Be constructive and specific. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.4, max_tokens=3000)
        result = parse_json(response)
        if result and result.get("overall_feedback"):
            print(f"[EvalAgent] Aptitude evaluation complete – band: {result.get('performance_band')}")
            return result
    except Exception as exc:
        print(f"[EvalAgent] Aptitude evaluation failed: {exc}")

    return {
        "overall_feedback": f"You scored {round(score)}% ({correct_count}/{total}). Review the incorrect answers to strengthen your aptitude skills.",
        "performance_band": "Average" if score >= 50 else "Needs Improvement",
        "strengths": ["Attempted all questions"],
        "improvement_areas": ["Review incorrect answers", "Practice more aptitude problems"],
        "per_category_insights": [],
        "recommended_topics": [],
        "wrong_answer_analysis": [],
        "study_plan": [],
    }


# ═══════════════════════════════════════════════════════════════════════
#  AGENTIC EVALUATION — GLOBAL TEST MODULE
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_global_test_submission(
    test_title: str,
    section_scores: dict,
    question_results: list[dict],
    total_score: float,
    proctoring_violations: int = 0,
    time_spent: int = 0,
) -> dict:
    """AI agent that evaluates a multi-section global test submission.

    Provides section-level analysis, holistic feedback, and a personalised
    improvement plan across aptitude, verbal, logical, coding, and SQL sections.
    """
    wrong_by_section: dict[str, list] = {}
    for qr in question_results:
        if not qr.get("isCorrect", False):
            sec = qr.get("section", "general")
            wrong_by_section.setdefault(sec, []).append({
                "question_summary": (qr.get("question") or "")[:120],
                "user_answer": qr.get("userAnswer", "")[:80],
                "correct_answer": qr.get("correctAnswer", "")[:80],
            })

    time_mins = round(time_spent / 60, 1) if time_spent else 0

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert placement test evaluator. Analyse a candidate's comprehensive global test results "
                "spanning aptitude, verbal, logical, coding, and SQL sections.\n\n"
                "Return ONLY a valid JSON object with:\n"
                '- "overall_feedback": string (executive summary)\n'
                '- "placement_readiness": string ("Ready" | "Nearly Ready" | "Needs Preparation" | "Not Ready")\n'
                '- "section_analysis": object with keys for each section — each has {"score", "verdict", "feedback", "tips"}\n'
                '- "strengths": array of strings\n'
                '- "weaknesses": array of strings\n'
                '- "recommended_focus": array of strings (top 3 areas)\n'
                '- "interview_readiness_notes": string\n'
                '- "action_plan": array of objects with {"priority" (1-5), "area", "action", "timeline"}\n'
                '- "proctoring_note": string (comment on behaviour integrity if violations > 0, else empty string)'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Test: {test_title}\n"
                f"Overall Score: {round(total_score)}%\n"
                f"Time Spent: {time_mins} minutes\n"
                f"Proctoring Violations: {proctoring_violations}\n\n"
                f"Section Scores: {json.dumps(section_scores)}\n\n"
                f"Wrong Answers by Section (sample):\n{json.dumps(wrong_by_section, indent=2)[:2000]}\n\n"
                "Provide a thorough, balanced evaluation. Highlight where the candidate excels and where they "
                "need focused preparation. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.4, max_tokens=3500)
        result = parse_json(response)
        if result and result.get("overall_feedback"):
            print(f"[EvalAgent] Global test evaluation complete – readiness: {result.get('placement_readiness')}")
            return result
    except Exception as exc:
        print(f"[EvalAgent] Global test evaluation failed: {exc}")

    return {
        "overall_feedback": f"You scored {round(total_score)}% overall. Review weaker sections and practise regularly.",
        "placement_readiness": "Needs Preparation" if total_score < 60 else "Nearly Ready",
        "section_analysis": {
            sec: {"score": section_scores.get(sec, 0), "verdict": "N/A", "feedback": "Review this section.", "tips": []}
            for sec in section_scores
        },
        "strengths": [],
        "weaknesses": [],
        "recommended_focus": [sec for sec, sc in sorted(section_scores.items(), key=lambda x: x[1])[:3]],
        "interview_readiness_notes": "Focus on strengthening weak areas before interviews.",
        "action_plan": [],
        "proctoring_note": f"{proctoring_violations} violations detected." if proctoring_violations > 0 else "",
    }


# ═══════════════════════════════════════════════════════════════════════
#  AGENTIC EVALUATION — SKILL TEST MCQ ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_mcq_with_ai(
    questions: list[dict],
    answers: dict,
    skills: list[str],
) -> list[dict]:
    """Enrich MCQ results with AI-powered per-question conceptual analysis.

    Returns a list of per-question objects: { question_id, concept_gap,
    misconception, correct_concept, tip, severity }.
    Only analyses questions that were answered incorrectly.
    """
    wrong_questions = []
    for q in questions:
        sa = answers.get(str(q.get("id"))) or answers.get(q.get("id"))
        si = ord(sa.upper()) - 65 if isinstance(sa, str) and len(sa) == 1 and sa.isalpha() else (int(sa) if isinstance(sa, (int, float)) else -1)
        ci = q.get("correct_answer", -2)
        if isinstance(ci, str) and len(ci) == 1 and ci.isalpha():
            ci = ord(ci.upper()) - 65
        try:
            ci = int(ci)
        except Exception:
            ci = -2
        if si != ci:
            opts = q.get("options", [])
            wrong_questions.append({
                "id": q.get("id"),
                "question": q.get("question", ""),
                "skill": q.get("skill", "General"),
                "student_answer_index": si,
                "correct_answer_index": ci,
                "student_answer_text": opts[si] if 0 <= si < len(opts) else str(sa),
                "correct_answer_text": opts[ci] if 0 <= ci < len(opts) else str(ci),
                "explanation": q.get("explanation", ""),
            })

    if not wrong_questions:
        return []  # All correct — nothing to enrich

    messages = [
        {
            "role": "system",
            "content": (
                "You are a technical skill assessment coach. For each wrong MCQ answer, identify:\n"
                "1. The likely conceptual gap or misconception\n"
                "2. The correct underlying concept\n"
                "3. A practical tip to fix it\n"
                "4. Severity: 'minor' (close miss) | 'moderate' (partial understanding) | 'major' (fundamental gap)\n\n"
                "Return ONLY a valid JSON array. Each object must have:\n"
                '- "question_id": number or string\n'
                '- "concept_gap": string\n'
                '- "misconception": string\n'
                '- "correct_concept": string\n'
                '- "tip": string\n'
                '- "severity": "minor" | "moderate" | "major"'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Skills being tested: {', '.join(skills)}\n\n"
                f"Wrong answers ({len(wrong_questions)}):\n"
                f"{json.dumps(wrong_questions, indent=2)[:3000]}\n\n"
                "Analyse each wrong answer and return the enriched feedback array. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.3, max_tokens=3000)
        result = parse_json(response)
        if result and isinstance(result, list):
            print(f"[EvalAgent] MCQ enrichment complete – {len(result)} items")
            return result
    except Exception as exc:
        print(f"[EvalAgent] MCQ enrichment failed: {exc}")

    # Fallback: basic per-question feedback
    return [
        {
            "question_id": wq["id"],
            "concept_gap": f"Review {wq['skill']} concepts",
            "misconception": "Answer based on incomplete understanding.",
            "correct_concept": wq.get("explanation") or "Refer to the explanation for this question.",
            "tip": f"Study {wq['skill']} fundamentals and practise similar problems.",
            "severity": "moderate",
        }
        for wq in wrong_questions
    ]


# ═══════════════════════════════════════════════════════════════════════
#  AGENTIC EVALUATION — COMMUNICATION MODULE HOLISTIC REPORT
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_comm_attempt(
    module_a_score: float,
    module_b_score: float,
    module_c_score: float,
    module_d_score: float,
    module_a_data: list | None = None,
    module_b_data: list | None = None,
    module_c_data: list | None = None,
    module_d_data: list | None = None,
) -> dict:
    """AI agent that holistically evaluates a full communication test attempt.

    Combines scores and response data from all 4 modules (Read & Speak,
    Listen & Repeat, Topic Speaking, Grammar Quiz) into a unified report.
    """
    overall = (module_a_score + module_b_score + module_c_score + module_d_score) / 4

    module_summary = {
        "Module A – Read & Speak": {"score": round(module_a_score, 1), "items": len(module_a_data or [])},
        "Module B – Listen & Repeat": {"score": round(module_b_score, 1), "items": len(module_b_data or [])},
        "Module C – Topic Speaking": {"score": round(module_c_score, 1), "items": len(module_c_data or [])},
        "Module D – Grammar Quiz": {"score": round(module_d_score, 1), "items": len(module_d_data or [])},
    }

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert English language coach specialising in corporate communication skills. "
                "Evaluate a student's performance across four communication modules and provide a comprehensive "
                "development report.\n\n"
                "The modules are:\n"
                "  A – Read & Speak (pronunciation & reading fluency)\n"
                "  B – Listen & Repeat (listening comprehension & reproduction accuracy)\n"
                "  C – Topic Speaking (spontaneous speaking, coherence, vocabulary)\n"
                "  D – Grammar Quiz (grammar accuracy)\n\n"
                "Return ONLY a valid JSON object with:\n"
                '- "overall_band": string ("A+" | "A" | "B" | "C" | "D" | "F")\n'
                '- "overall_summary": string (2-3 sentence executive summary)\n'
                '- "fluency_feedback": string\n'
                '- "pronunciation_feedback": string\n'
                '- "grammar_feedback": string\n'
                '- "vocabulary_feedback": string\n'
                '- "module_insights": object keyed by module name with {"verdict", "feedback", "tips"}\n'
                '- "strengths": array of strings\n'
                '- "development_areas": array of strings\n'
                '- "corporate_readiness": string ("High" | "Medium" | "Low")\n'
                '- "roadmap": array of objects with {"week" (1-4), "focus", "activities"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Overall Communication Score: {round(overall, 1)}%\n\n"
                f"Module Scores:\n{json.dumps(module_summary, indent=2)}\n\n"
                "Provide a detailed but encouraging assessment. Identify which communication skill "
                "dimension needs the most attention and suggest practical exercises. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.45, max_tokens=3000)
        result = parse_json(response)
        if result and result.get("overall_band"):
            print(f"[EvalAgent] Comm evaluation complete – band: {result.get('overall_band')}")
            return result
    except Exception as exc:
        print(f"[EvalAgent] Comm evaluation failed: {exc}")

    band = "A" if overall >= 85 else ("B" if overall >= 70 else ("C" if overall >= 55 else ("D" if overall >= 40 else "F")))
    return {
        "overall_band": band,
        "overall_summary": f"You achieved an overall communication score of {round(overall, 1)}%. Keep practising regularly.",
        "fluency_feedback": "Continue practising Read & Speak exercises to improve fluency.",
        "pronunciation_feedback": "Work on Listen & Repeat exercises to refine pronunciation.",
        "grammar_feedback": "Review grammar rules and practise fill-in-the-blank exercises.",
        "vocabulary_feedback": "Expand vocabulary through reading and Topic Speaking practice.",
        "module_insights": {},
        "strengths": [],
        "development_areas": [],
        "corporate_readiness": "Medium" if overall >= 60 else "Low",
        "roadmap": [],
    }


# ═══════════════════════════════════════════════════════════════════════
#  AGENTIC EVALUATION — GRAMMAR QUIZ MODULE D (per-question AI feedback)
# ═══════════════════════════════════════════════════════════════════════

async def evaluate_grammar_answers(
    wrong_answers: list[dict],
) -> list[dict]:
    """Generate AI explanations for wrong Grammar Quiz (Module D) answers.

    Each item in wrong_answers should have: sentence, student_answer, correct_answer, category.
    Returns a list of {question_index, ai_explanation, grammar_rule, example} objects.
    """
    if not wrong_answers:
        return []

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert English grammar teacher. For each incorrectly answered grammar question, "
                "provide a clear, friendly explanation of why the student's answer is wrong and why the correct "
                "answer is right. Include the grammar rule and a new example sentence.\n\n"
                "Return ONLY a valid JSON array. Each object must have:\n"
                '- "question_index": number or string (from input)\n'
                '- "ai_explanation": string (friendly 2-3 sentence explanation)\n'
                '- "grammar_rule": string (the rule that applies)\n'
                '- "example": string (another example using the same rule)'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Wrong answers ({len(wrong_answers)}):\n"
                f"{json.dumps(wrong_answers, indent=2)[:2500]}\n\n"
                "Explain each mistake kindly and clearly. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        response = await _call_cerebras(messages, temperature=0.35, max_tokens=2500)
        result = parse_json(response)
        if result and isinstance(result, list):
            print(f"[EvalAgent] Grammar feedback complete – {len(result)} explanations")
            return result
    except Exception as exc:
        print(f"[EvalAgent] Grammar feedback failed: {exc}")

    return [
        {
            "question_index": wa.get("question_index", 0),
            "ai_explanation": f"The correct answer is '{wa.get('correct_answer')}'. Review the {wa.get('category', 'grammar')} rule.",
            "grammar_rule": f"Review {wa.get('category', 'grammar')} rules.",
            "example": "",
        }
        for wa in wrong_answers
    ]
