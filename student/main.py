# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi[standard]",
#   "uvicorn",
#   "requests",
# ]
# ///

from pydantic import BaseModel, Field
import requests
import os
import json
import time
import base64
from fastapi import FastAPI
from typing import List, Dict, Any
import google.genai as genai
from google.genai import types
from google.genai.errors import APIError

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# --- CONSTANTS (Adjusted for Gemini) ---
# Use the stable, fast, and free-tier-friendly model
MODEL_NAME = "gemini-2.5-flash" 
MAX_RETRIES = 5       # Increased attempts for network resilience
INITIAL_DELAY = 4     # Starting delay in seconds (will double: 4, 8, 16, 32...)

system_instruction = "You are an expert web developer whose SOLE purpose is to generate the JSON array of files needed to satisfy the user's request. You MUST NOT include any conversational text, explanations, or markdown fences (```json) in your response. The output must be ONLY a valid JSON array that strictly adheres to the schema provided."

# Use GEMINI_API_KEY environment variable
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set. Please set it.")

# Initialize the Gemini Client. It automatically reads the GEMINI_API_KEY
client = genai.Client(api_key=GEMINI_API_KEY)


# --- Standard MIT License Content ---
# It's safer to provide the exact license text than trust the LLM to write it.
MIT_LICENSE_TEXT = """
MIT License

Copyright (c) [YEAR] [FULL NAME]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


app = FastAPI()


# Pydantic is the standard way to enforce output JSON structure with Gemini.
class CodeFile(BaseModel):
    """Schema for a single generated file."""
    name: str = Field(..., description="The filename, e.g., 'index.html', 'style.css', 'README.md'")
    content: str = Field(..., description="The complete and full content of the file.")

# --- Create a wrapper model for the list ---
class GeneratedCode(BaseModel):
    """The complete response, consisting of a list of generated files."""
    files: List[CodeFile] = Field(..., description="An array of all files to be generated.")

def validate_secret(secret: str) -> bool:
    # Placeholder for secret validation logic
    return secret == os.getenv("secret")

def create_github_repo(repo_name: str):
    # use github api to create a repo with the given name
    payload = {"name": repo_name, 
               "private": False,
               "auto_init": True,
               "license_template": "mit"
               }
    # put Setting to application/vnd.github+json is recommended
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.post(
        "https://api.github.com/user/repos",
        headers=headers,
        json=payload,
    )
    if response.status_code != 201:
        raise Exception(f"Failed to create repo: {response.status_code}, {response.text}")
    else:
        return response.json()

def enable_github_pages(repo_name: str):
    # takes repo name as argument and enables githb pages for that repo using github api
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {
        "build_type": "legacy",
        "source": {
            "branch": "main",
            "path": "/"
        }
    } 
    response = requests.post(
        f"https://api.github.com/repos/sirjanhere/{repo_name}/pages",
        headers=headers,
        json=payload
    )
    if response.status_code != 201:
        raise Exception(f"Failed to enable github pages: {response.status_code}, {response.text}")

def get_sha_of_latest_commit(repo_name: str, branch: str = "main") -> str:
    # takes repo name and branch name as argument and returns the sha of the latest commit on that branch using github api
    response = requests.get(f"https://api.github.com/repos/sirjanhere/{repo_name}/commits/{branch}")
    if response.status_code != 200:
        raise Exception(f"Failed to get latest commit sha: {response.status_code}, {response.text}")
    return response.json().get("sha")

def push_files_to_repo(repo_name: str, files: list[dict], round: int):
    # takes a repo name and json array with object that have fields name of the file and content of the file and use github api to push those files to the repo
    # TODO: can use git cli to push files to the repo instead of github api
    if round == 2:
        latest_sha = get_sha_of_latest_commit(repo_name)
    else:
        latest_sha = None
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    for file in files:
        file_name = file.get("name")
        file_content = file.get("content")
        # If the content is bytes, convert it to base64 string
        if isinstance(file_content, bytes):
            file_content = base64.b64encode(file_content).decode('utf-8')
        else:
            # If content is a string, still encode it to base64
            file_content = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
        payload = {
                "message": f"Add {file_name}",
                "content": file_content
            }
        if latest_sha:
            payload["sha"] = latest_sha
        if not file_name or not file_content:
            continue
        # create a new file in the repo
        response = requests.put(
            f"https://api.github.com/repos/sirjanhere/{repo_name}/contents/{file_name}",
            headers=headers,
            json=payload
        )
        if response.status_code != 201:
            raise Exception(f"Failed to push file {file_name}: {response.status_code}, {response.text}")


def notify_evaluation_server(data: dict, repo_name: str, status: str = "success", extra: dict | None = None):
    """Send repo & commit details to the evaluation_url from the TDS request."""
    evaluation_url = data.get("evaluation_url")
    if not evaluation_url:
        print("No evaluation URL provided.")
        return

    # Build repo and pages URL
    repo_url = f"https://github.com/sirjanhere/{repo_name}"
    pages_url = f"https://sirjanhere.github.io/{repo_name}/"

    payload = {
        "email": data.get("email"),
        "task": data.get("task"),
        "round": data.get("round"),
        "nonce": data.get("nonce"),
        "repo_url": repo_url,
        "commit_sha": get_sha_of_latest_commit(repo_name),
        "pages_url": pages_url,
    }

    if extra:
        payload.update(extra)

    try:
        response = requests.post(evaluation_url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Evaluation callback failed: {response.status_code}, {response.text}")
        else:
            print("✅ Evaluation server notified successfully.")
    except Exception as e:
        print(f"Error notifying evaluation server: {e}")

def generate_code_with_llm(brief: str, attachments: List[Dict[str, str]], round_num: int) -> List[Dict[str, str]]:
    """
    Uses the Gemini API with JSON mode to generate code files for the project.
    """
    print(f"Generating code for Round {round_num} using {MODEL_NAME}...")

    # 1. Prepare the Detailed Prompt
    user_prompt = f"""
    You are an expert web developer specializing in minimal, clean, and secure code.
    Your task is to generate ALL files for a functional, complete web application.
    
    **APPLICATION BRIEF (Round {round_num}):**
    {brief}

    **ATTACHMENTS (for context and usage):**
    {attachments}

    **STRICT REQUIREMENTS:**
    1. **GitHub Pages Compatible:** Code MUST be pure HTML, CSS, and vanilla JavaScript. DO NOT use Node.js, Python frameworks, or any server-side language.
    2. **Minimal and Complete:** Provide the smallest, most efficient codebase that satisfies the brief.
    3. **README.md:** Generate a professional and complete README.md.
    4. **Output:** Your entire response must be ONLY a JSON array of files that strictly adheres to the provided schema.

    The application must read a captcha image URL from the '?url=' query parameter, display the image, and show a placeholder solved value within 1-2 seconds.
    """

    # 2. Call the API with Retry and Structured Output Logic
    last_error_message = ""
    for attempt in range(MAX_RETRIES):
        delay = INITIAL_DELAY * (2 ** attempt) 
        
        try:
            # --- GEMINI API CALL ---
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                        # types.Content(role="system", parts=[{"text": system_instruction}]),
                        types.Content(role="user", parts=[{"text": user_prompt}]),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    # Enforce JSON output format
                    response_mime_type="application/json",
                    # Enforce the Pydantic schema structure
                    response_schema=GeneratedCode, 
                    temperature=0.2,
                ),
            )
            # -------------------------

            # 3. Parse and Validate LLM Response
            # The SDK handles the response, which is guaranteed to be JSON matching the schema.
            # We use .parsed to get the Pydantic objects, then convert to standard dicts.
            try:
                # response.parsed contains the Pydantic objects
                files_wrapper: GeneratedCode = response.parsed
                files_pydantic: List[CodeFile] = files_wrapper.files
                files = [f.model_dump() for f in files_pydantic] # Convert to list[dict]

                if not isinstance(files, list) or not all(isinstance(f, dict) for f in files):
                     raise ValueError("LLM response content failed Pydantic validation and type check.")
            
            except Exception as e:
                # Catch parsing errors or any unexpected structure
                last_error_message = f"Invalid JSON/Schema from LLM: {e}. Raw Text: {response.text[:200]}..."
                print(f"Attempt {attempt + 1} failed: {last_error_message}")
                time.sleep(delay)
                continue

            # 4. Inject Standard MIT LICENSE File
            files.append({"name": "LICENSE", "content": MIT_LICENSE_TEXT})
            
            return files

        except APIError as e:
            # Handle API/Rate-Limit errors (Gemini errors are wrapped in APIError)
            last_error_message = f"Gemini API Error: {e}"
            print(f"Attempt {attempt + 1} failed: {last_error_message}. Retrying in {delay}s...")
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
            else:
                break # Exit the loop to raise the final exception
        
        except Exception as e:
            # Catch network errors, timeouts, and other general exceptions
            last_error_message = f"Network or General Error: {e}"
            print(f"Attempt {attempt + 1} failed: {last_error_message}. Retrying in {delay}s...")
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
            else:
                break

    # If the loop completes without success
    raise Exception(f"Failed to generate code after {MAX_RETRIES} attempts. Last error: {last_error_message}")


def write_code_with_llm():
    # hardcode with a simple file for now
    # TODO: integrate with LLM to generate code
    return [
        {
            "name": "index.html",
            "content": """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Hello World</title>
                </head>
                <body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;">
                <h1>Hello World</h1>
                <p>This is a test page pushed by LLM for round 1 for Github pages deployment.</p>
                </body>
                </html>
            """
        }
    ]

def round1(data):
    # Generate all files using LLM based on the brief and attachments
    files = generate_code_with_llm(
        brief=data.get("brief", ""),
        attachments=data.get("attachments", []),
        round_num=1
    )
    # create_github_repo(f"{data['task']}_{data['nonce']}")
    # enable_github_pages(f"{data['task']}_{data['nonce']}")
    # push_files_to_repo(f"{data['task']}_{data['nonce']}", files, 1)
    # notify_evaluation_server(data, f"{data['task']}_{data['nonce']}")
    for f in files:
        print(f"Generated file: {f['name']}, length: {len(f['content'])}")

def round2(data):
    pass

# post endpoint that takes a json object with following fields: email, secret, task, round, nonce, brief, checks(array), evaluation_url, attachments (array with object with fields name and url)

@app.post("/handle_task")
def handle_task(data: dict):
    # validate the secret
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid secret"}
    else:
        # process the task
        # depending on the round, call the respective function
        if data.get("round") == 1:
            round1(data)
            return {"message": "Round 1 started"}
        elif data.get("round") == 2:
            round2(data)
            return {"message": "Round 2 started"}
        else:
            return {"error": "Invalid round"}
        pass
    return {"message": "Task received", "data": data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

