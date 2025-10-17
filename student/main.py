# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi[standard]",
#   "uvicorn",
#   "requests",
# ]
# ///

import requests
import os
import base64
from fastapi import FastAPI

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
app = FastAPI()

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
    files = write_code_with_llm()
    create_github_repo(f"{data['task']}_{data['nonce']}")
    enable_github_pages(f"{data['task']}_{data['nonce']}")
    push_files_to_repo(f"{data['task']}_{data['nonce']}", files, 1)
    notify_evaluation_server(data, f"{data['task']}_{data['nonce']}")

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

