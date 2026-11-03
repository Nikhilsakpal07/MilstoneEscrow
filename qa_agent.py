import os
import json
import re
import subprocess
from dotenv import load_dotenv

load_dotenv()

# Synchronize API keys for Google Gemini SDKs
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    os.environ["GOOGLE_API_KEY"] = gemini_key
    os.environ["GEMINI_API_KEY"] = gemini_key

# pyrefly: ignore[missing-import]
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
try:
    from google.antigravity.hooks import policy
except ImportError:
    policy = None


def _parse_agent_json(text: str) -> dict:
    """
    Extracts and parses the final JSON evaluation block from the agent's output.
    Expects {"passed": boolean, "feedback": "string"}.
    """
    text = text.strip()

    # 1. Try directly parsing the full text
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "passed" in data and "feedback" in data:
            return {"passed": bool(data["passed"]), "feedback": str(data["feedback"])}
    except Exception:
        pass

    # 2. Try extracting from markdown code block ```json { ... } ``` or ``` { ... } ```
    code_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if code_blocks:
        for block in reversed(code_blocks):
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "passed" in data and "feedback" in data:
                    return {"passed": bool(data["passed"]), "feedback": str(data["feedback"])}
            except Exception:
                continue

    # 3. Locate the last balanced { ... } JSON block in the text
    last_brace = text.rfind("}")
    if last_brace != -1:
        depth = 0
        start_idx = -1
        for i in range(last_brace, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    start_idx = i
                    break
        if start_idx != -1:
            candidate = text[start_idx : last_brace + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "passed" in data and "feedback" in data:
                    return {"passed": bool(data["passed"]), "feedback": str(data["feedback"])}
            except Exception:
                pass

    raise ValueError("Could not extract a valid JSON object with 'passed' and 'feedback' keys")


async def evaluate_submission(github_url: str, acceptance_criteria: str, bounty_id: int) -> dict:
    """
    Asynchronously evaluates a freelancer's code submission using the Gemini model.

    Args:
        github_url: URL to the freelancer's GitHub repository.
        acceptance_criteria: Criteria to validate the submission against.
        bounty_id: The ID of the bounty being evaluated.

    Returns:
        A dictionary with format: {"passed": bool, "feedback": str}
    """
    # 1. Define workspace and trajectory directories based on bounty_id
    workspace_dir = os.path.abspath(f"./workspaces/bounty_{bounty_id}")
    trajectory_dir = os.path.abspath(f"./trajectories/bounty_{bounty_id}")

    os.makedirs(workspace_dir, exist_ok=True)
    os.makedirs(trajectory_dir, exist_ok=True)

    # 2. Configure CapabilitiesConfig and LocalAgentConfig
    capabilities = CapabilitiesConfig(
        enable_subagents=True,
    )
    policies = [policy.allow_all()] if (policy and hasattr(policy, "allow_all")) else None

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    config_kwargs = {
        "capabilities": capabilities,
        "workspaces": [workspace_dir],
        "save_dir": trajectory_dir,
    }
    if policies:
        config_kwargs["policies"] = policies
    if api_key:
        config_kwargs["api_key"] = api_key
    if model_name:
        config_kwargs["model"] = model_name

    try:
        config = LocalAgentConfig(**config_kwargs)
    except TypeError:
        # Fallback to standard parameter names if signature differs
        config = LocalAgentConfig(
            workspace_dir=workspace_dir,
            trajectory_dir=trajectory_dir,
            capabilities=capabilities,
        )

    # 3. Instantiate the Antigravity Agent
    try:
        agent_instance = Agent(config=config, model=model_name)
    except TypeError:
        agent_instance = Agent(config=config)

    # 4. Formulate the prompt
    prompt = f"""You are an automated QA evaluation agent. Evaluate the code submission for bounty #{bounty_id}.

GitHub Repository: {github_url}
Acceptance Criteria:
{acceptance_criteria}

Instructions:
1. Use the terminal to `git clone` the provided repository: {github_url} into your current workspace.
2. Inspect the project and install standard dependencies (e.g., `pip install -r requirements.txt`, `npm install`, or the appropriate dependency manager).
3. Run the test suite (e.g., `pytest`, `npm test`, `unittest`, or project-specific test runners).
4. Evaluate the test output and codebase strictly against the provided acceptance criteria.
5. Output a raw JSON block at the very end of your response in the exact format:
{{"passed": boolean, "feedback": "string"}}

Ensure that "passed" is a boolean (true or false) indicating whether all tests and acceptance criteria were satisfied, and "feedback" is a clear summary of the evaluation results.
"""

    # 5. Execute agent with Gemini model
    response_text = ""
    try:
        print(f"[QA Agent] Launching Antigravity QA Agent with Gemini ({model_name}) for bounty #{bounty_id}...")
        if hasattr(agent_instance, "__aenter__"):
            async with agent_instance as agent:
                if hasattr(agent, "run") and callable(getattr(agent, "run")):
                    response = await agent.run(prompt)
                elif hasattr(agent, "chat") and callable(getattr(agent, "chat")):
                    response = await agent.chat(prompt)
                else:
                    raise RuntimeError("Agent instance does not support 'run' or 'chat' methods")

                if hasattr(response, "__aiter__"):
                    tokens = []
                    async for token in response:
                        tokens.append(str(token))
                    response_text = "".join(tokens)
                elif hasattr(response, "text"):
                    response_text = response.text
                else:
                    response_text = str(response)
        else:
            if hasattr(agent_instance, "run") and callable(getattr(agent_instance, "run")):
                response = await agent_instance.run(prompt)
            elif hasattr(agent_instance, "chat") and callable(getattr(agent_instance, "chat")):
                response = await agent_instance.chat(prompt)
            else:
                raise RuntimeError("Agent instance does not support 'run' or 'chat' methods")

            if hasattr(response, "__aiter__"):
                tokens = []
                async for token in response:
                    tokens.append(str(token))
                response_text = "".join(tokens)
            elif hasattr(response, "text"):
                response_text = response.text
            else:
                response_text = str(response)

        print(f"[QA Agent] Antigravity response received ({len(response_text)} chars). Parsing evaluation result...")
        return _parse_agent_json(response_text)

    except Exception as primary_err:
        print(f"[QA Agent Notice] Antigravity local harness error: {primary_err}. Attempting direct Gemini API evaluation fallback...")

        # Fallback to direct Gemini Model API via google.genai
        try:
            from google import genai

            # Clone or fetch repository
            clone_target = os.path.join(workspace_dir, "repo")
            if not os.path.exists(clone_target):
                subprocess.run(
                    ["git", "clone", github_url, clone_target],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            # Inspect repo files
            file_snippets = []
            scan_dir = clone_target if os.path.exists(clone_target) else workspace_dir
            for root, dirs, files in os.walk(scan_dir):
                if ".git" in root:
                    continue
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read(2500)
                            rel_name = os.path.relpath(fpath, scan_dir)
                            file_snippets.append(f"=== File: {rel_name} ===\n{content}\n")
                    except Exception:
                        continue

            repo_context = "\n".join(file_snippets[:12]) if file_snippets else "No source files could be read."

            fallback_prompt = f"""You are an autonomous code QA auditor. Evaluate this repository submission.
Bounty ID: {bounty_id}
GitHub Repository: {github_url}
Acceptance Criteria:
{acceptance_criteria}

Repository Source Code & Files Sample:
{repo_context}

Instructions:
1. Examine the repository files against the acceptance criteria.
2. Determine if the criteria are fully satisfied.
3. At the very end of your response, output a raw JSON block in the exact format:
{{"passed": boolean, "feedback": "string"}}
"""

            client = genai.Client(api_key=api_key)
            fallback_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            genai_res = client.models.generate_content(
                model=fallback_model,
                contents=fallback_prompt,
            )

            if genai_res and genai_res.text:
                print(f"[QA Agent] Direct Gemini API response received ({len(genai_res.text)} chars).")
                return _parse_agent_json(genai_res.text)

        except Exception as fallback_err:
            print(f"[QA Agent Error] Fallback Gemini evaluation also failed: {fallback_err}")

        return {
            "passed": False,
            "feedback": f"Gemini QA evaluation failed: {str(primary_err)}. Raw output: {response_text.strip()}",
        }
