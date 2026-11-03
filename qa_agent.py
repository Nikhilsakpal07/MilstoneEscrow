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


def _format_result(data: dict) -> dict:
    """Helper to ensure standard JSON schema returned to callers."""
    res = {
        "passed": bool(data.get("passed", False)),
        "feedback": str(data.get("feedback", "No feedback provided.")),
    }
    if "extracted_data" in data and isinstance(data["extracted_data"], dict):
        res["extracted_data"] = data["extracted_data"]
    return res


def _parse_agent_json(text: str) -> dict:
    """
    Extracts and parses the final JSON evaluation block from the model's output.
    Expects {"passed": boolean, "feedback": "string", optional "extracted_data": {...}}.
    """
    text = text.strip()

    # 1. Try directly parsing the full text
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "passed" in data:
            return _format_result(data)
    except Exception:
        pass

    # 2. Try extracting from markdown code block ```json { ... } ``` or ``` { ... } ```
    code_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if code_blocks:
        for block in reversed(code_blocks):
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "passed" in data:
                    return _format_result(data)
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
                if isinstance(data, dict) and "passed" in data:
                    return _format_result(data)
            except Exception:
                pass

    raise ValueError("Could not extract a valid JSON object with 'passed' and 'feedback' keys")


async def evaluate_multimodal_submission(
    files: list[tuple[bytes, str, str]],
    acceptance_criteria: str,
    bounty_id: int,
    milestone_id: int | None = None,
    milestone_description: str | None = None,
) -> dict:
    """
    Uses Google Gemini 1.5 Pro to evaluate physical-world proof of work and financial receipts.
    Extracts receipt total, date, and items, and verifies whether they logically fulfill
    the milestone criteria.

    Args:
        files: List of (file_bytes, mime_type, filename) tuples.
        acceptance_criteria: Overall bounty acceptance criteria.
        bounty_id: The bounty ID.
        milestone_id: Optional milestone ID.
        milestone_description: Scope and requirements for the specific milestone.

    Returns:
        Structured dictionary with format:
        {"passed": bool, "feedback": str, "extracted_data": {...}}
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY must be set in environment variables.")

    client = genai.Client(api_key=api_key)

    # Build Gemini multimodal Part objects
    parts = []
    for file_bytes, mime_type, fname in files:
        clean_mime = (mime_type or "").lower().strip()
        if not clean_mime or clean_mime in ("application/octet-stream", "binary/octet-stream"):
            if fname.lower().endswith(".pdf"):
                clean_mime = "application/pdf"
            elif fname.lower().endswith(".png"):
                clean_mime = "image/png"
            elif fname.lower().endswith((".jpg", ".jpeg")):
                clean_mime = "image/jpeg"
            elif fname.lower().endswith(".webp"):
                clean_mime = "image/webp"
            else:
                clean_mime = "image/jpeg"

        part = types.Part.from_bytes(data=file_bytes, mime_type=clean_mime)
        parts.append(part)

    # Formulate auditing prompt specifically for financial receipts & physical proof
    prompt = f"""You are an autonomous auditor evaluating physical-world proof of work and financial receipts (such as NGO donations, humanitarian supplies, charity purchases, or on-the-ground service receipts) for milestone escrow release.

Bounty ID: #{bounty_id}
Milestone ID: #{milestone_id or 'General'}
Milestone Scope & Required Deliverable:
{milestone_description or 'Verify receipt and proof of work fulfills milestone requirements.'}

Overall Acceptance Criteria:
{acceptance_criteria}

Instructions:
1. Examine the provided receipt(s), document(s), or photo evidence carefully.
2. Extract the key financial and transactional fields:
   - Receipt / Transaction Total Amount (numerical value and currency)
   - Date of transaction or receipt
   - Itemized list of purchased items, services, or donation activities
   - Vendor / Merchant / Recipient Organization name
3. Cross-reference the extracted receipt items, total amount, and date against the milestone scope and acceptance criteria:
   - Does the receipt demonstrate valid proof of work for this milestone?
   - Do the items and total amount reasonably satisfy the milestone requirement?
4. Output your final response strictly as a raw JSON block at the very end in the exact format:
{{
  "passed": boolean,
  "feedback": "Detailed reasoning explaining the audit decision and how the receipt satisfies or fails the milestone criteria.",
  "extracted_data": {{
    "total_amount": "extracted total with currency (e.g. $150.00 USD)",
    "date": "extracted date (e.g. YYYY-MM-DD)",
    "vendor": "merchant or organization name",
    "items": ["list", "of", "items", "or", "services"]
  }}
}}

Ensure that "passed" is a boolean (true or false). Do not include any text outside or after the JSON block.
"""

    contents = [*parts, prompt]
    primary_model = os.getenv("GEMINI_MULTIMODAL_MODEL", "gemini-1.5-pro")

    print(f"[QA Agent] Analyzing {len(parts)} multimodal proof document(s) with Google Gemini ({primary_model}) for bounty #{bounty_id}...")

    try:
        response = client.models.generate_content(
            model=primary_model,
            contents=contents,
        )
    except Exception as model_err:
        print(f"[QA Agent Notice] Primary model ({primary_model}) returned error: {model_err}. Trying fallback model...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )

    response_text = response.text or ""
    print(f"[QA Agent] Received Gemini response ({len(response_text)} chars). Parsing evaluation result...")
    return _parse_agent_json(response_text)


async def evaluate_submission(
    github_url: str | None = None,
    files: list[tuple[bytes, str, str]] | None = None,
    acceptance_criteria: str = "",
    bounty_id: int = 0,
    milestone_id: int | None = None,
    milestone_description: str | None = None,
) -> dict:
    """
    Main evaluation entry point:
    - If uploaded files (receipts/photos/PDFs) are provided, triggers Gemini 1.5 Pro multimodal evaluation.
    - If a GitHub URL is provided, runs code repository cloning and test suite audit.
    """
    # 1. Multimodal File Submission (Receipts / Proof of work)
    if files and len(files) > 0:
        return await evaluate_multimodal_submission(
            files=files,
            acceptance_criteria=acceptance_criteria,
            bounty_id=bounty_id,
            milestone_id=milestone_id,
            milestone_description=milestone_description,
        )

    # 2. GitHub URL Repository Submission
    if not github_url or not github_url.strip():
        return {
            "passed": False,
            "feedback": "Submission rejected: Neither a valid GitHub repository URL nor proof documents/receipts were provided.",
        }

    scope_tag = f"m_{milestone_id}" if milestone_id is not None else "full"
    workspace_dir = os.path.abspath(f"./workspaces/bounty_{bounty_id}_{scope_tag}")
    trajectory_dir = os.path.abspath(f"./trajectories/bounty_{bounty_id}_{scope_tag}")

    os.makedirs(workspace_dir, exist_ok=True)
    os.makedirs(trajectory_dir, exist_ok=True)

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
        config = LocalAgentConfig(
            workspace_dir=workspace_dir,
            trajectory_dir=trajectory_dir,
            capabilities=capabilities,
        )

    try:
        agent_instance = Agent(config=config, model=model_name)
    except TypeError:
        agent_instance = Agent(config=config)

    milestone_info = (
        f"\nMilestone Being Evaluated: Milestone #{milestone_id}\nMilestone Description:\n{milestone_description}\n"
        if milestone_id is not None and milestone_description
        else ""
    )

    prompt = f"""You are an automated QA evaluation agent. Evaluate the code submission for bounty #{bounty_id}.{milestone_info}
GitHub Repository: {github_url}
Acceptance Criteria:
{acceptance_criteria}

Instructions:
1. Use the terminal to `git clone` the provided repository: {github_url} into your current workspace.
2. Inspect the project and install standard dependencies (e.g., `pip install -r requirements.txt`, `npm install`, or appropriate dependency manager).
3. Run the test suite (e.g., `pytest`, `npm test`, `unittest`, or project-specific test runners).
4. Evaluate the test output and codebase strictly against the criteria.
5. Output a raw JSON block at the very end of your response in the exact format:
{{"passed": boolean, "feedback": "string"}}

Ensure that "passed" is a boolean (true or false) indicating whether all tests and criteria were satisfied, and "feedback" is a clear summary of the evaluation results.
"""

    response_text = ""
    try:
        print(f"[QA Agent] Launching Antigravity QA Agent with Gemini ({model_name}) for bounty #{bounty_id} ({scope_tag})...")
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

        try:
            from google import genai

            clone_target = os.path.join(workspace_dir, "repo")
            if not os.path.exists(clone_target):
                subprocess.run(
                    ["git", "clone", github_url, clone_target],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

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
Bounty ID: {bounty_id} ({scope_tag})
{milestone_info}
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
