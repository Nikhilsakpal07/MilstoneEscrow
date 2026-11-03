import asyncio
import json
from qa_agent import evaluate_submission


async def main():
    print("========================================")
    print("Starting QA Agent Submission Test")
    print("========================================")

    # Public repository to test
    github_url = "https://github.com/octocat/Hello-World"
    acceptance_criteria = (
        "The repository must be cloned successfully, and contain a README "
        "confirming 'Hello World' or basic starter code."
    )
    bounty_id = 999

    print(f"Bounty ID           : {bounty_id}")
    print(f"GitHub Repository   : {github_url}")
    print(f"Acceptance Criteria : {acceptance_criteria}\n")
    print("Invoking evaluate_submission() (spawning Antigravity Agent)...")

    result = await evaluate_submission(
        github_url=github_url,
        acceptance_criteria=acceptance_criteria,
        bounty_id=bounty_id,
    )

    print("\n========================================")
    print("QA Agent Output Received:")
    print("========================================")
    print(json.dumps(result, indent=2))
    print(f"\nPassed   : {result.get('passed')}")
    print(f"Feedback : {result.get('feedback')}")


if __name__ == "__main__":
    asyncio.run(main())

