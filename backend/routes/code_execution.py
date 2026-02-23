"""Local Code Execution using Subprocess."""

import os
import tempfile
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["code_execution"])

class RunRequest(BaseModel):
    language: str
    code: str
    stdin: str | None = ""
    sqlSchema: str | None = ""
    problemId: str | None = None

import subprocess

async def run_in_subprocess(cmd: list[str], stdin_data: str | None = None, timeout: int = 5) -> dict:
    """Run a command asynchronously with a timeout using subprocess.run."""
    try:
        def execute():
            return subprocess.run(
                cmd,
                input=stdin_data.encode() if stdin_data else None,
                capture_output=True,
                timeout=timeout
            )
            
        proc = await asyncio.to_thread(execute)
        
        return {
            "output": proc.stdout.decode(errors='replace'),
            "error": proc.stderr.decode(errors='replace'),
            "exitCode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "error": f"Execution timed out after {timeout} seconds.",
            "exitCode": 124,
        }
    except FileNotFoundError as e:
        tool = cmd[0]
        return {
            "output": "",
            "error": f"Execution failed: '{tool}' is not installed or not in PATH.",
            "exitCode": 1,
        }
    except Exception as e:
        import traceback
        return {
            "output": "",
            "error": f"Internal Error: {type(e).__name__} - {str(e)}",
            "exitCode": 1,
        }


@router.post("/run")
async def run_code(body: RunRequest):
    lang_lower = body.language.lower()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cmd = []
        compile_res = None
        
        try:
            if lang_lower in ["python", "python3"]:
                file_path = os.path.join(temp_dir, "script.py")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(body.code)
                cmd = ["python", file_path]
                
            elif lang_lower in ["javascript", "js", "node"]:
                file_path = os.path.join(temp_dir, "script.js")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(body.code)
                cmd = ["node", file_path]
                
            elif lang_lower in ["java"]:
                file_path = os.path.join(temp_dir, "Solution.java")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(body.code)
                # Compiling java is not strictly needed for Java 11+ single-files, 
                # but we'll run it directly
                cmd = ["java", file_path]
                
            elif lang_lower in ["cpp", "c++"]:
                file_path = os.path.join(temp_dir, "script.cpp")
                exe_path = os.path.join(temp_dir, "script.exe") if os.name == 'nt' else os.path.join(temp_dir, "script")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(body.code)
                
                # Compile step
                compile_res = await run_in_subprocess(["g++", file_path, "-o", exe_path], timeout=5)
                if compile_res["exitCode"] != 0:
                    return compile_res  # Return compile error
                cmd = [exe_path]
                
            elif lang_lower in ["c"]:
                file_path = os.path.join(temp_dir, "script.c")
                exe_path = os.path.join(temp_dir, "script.exe") if os.name == 'nt' else os.path.join(temp_dir, "script")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(body.code)
                
                compile_res = await run_in_subprocess(["gcc", file_path, "-o", exe_path], timeout=5)
                if compile_res["exitCode"] != 0:
                    return compile_res
                cmd = [exe_path]
                
            elif lang_lower in ["sql", "sqlite3"]:
                db_path = os.path.join(temp_dir, "test.db")
                sql_script = os.path.join(temp_dir, "script.sql")
                
                sql_content = ""
                if body.sqlSchema:
                    sql_content += body.sqlSchema + ";\n"
                sql_content += body.code
                if not sql_content.strip().endswith(';'):
                    sql_content += ";"
                sql_content += "\n"
                
                with open(sql_script, "w", encoding="utf-8") as f:
                    f.write(sql_content)
                    
                sql_script_posix = sql_script.replace("\\", "/")
                cmd = ["sqlite3", db_path, f".read {sql_script_posix}"]
                
            else:
                return {
                    "output": "",
                    "error": f"Language '{lang_lower}' is not supported for local execution.",
                    "exitCode": 1,
                }
                
            # Execute the constructed command
            result = await run_in_subprocess(cmd, stdin_data=body.stdin, timeout=10)
            return result
            
        except Exception as e:
            return {
                "output": "",
                "error": f"Internal execution error: {str(e)}",
                "exitCode": 1,
            }
