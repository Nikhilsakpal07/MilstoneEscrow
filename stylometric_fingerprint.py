import os
import ast
import re
import json
import hashlib
import tempfile
import subprocess
from collections import Counter
from sqlalchemy.orm import Session
from datetime import datetime

import models
from qa_agent import _generate_with_gemini

COMMON_RESERVED_WORDS = {
    "self", "cls", "def", "class", "return", "import", "from", "as",
    "if", "elif", "else", "for", "while", "in", "is", "not", "and", "or",
    "try", "except", "finally", "with", "yield", "lambda", "pass", "break",
    "continue", "global", "nonlocal", "true", "false", "none", "const",
    "let", "var", "function", "async", "await", "export", "default",
    "print", "str", "int", "float", "bool", "list", "dict", "set", "len",
    "range", "enumerate", "zip", "open", "type", "id", "data", "res",
}


def extract_code_stylometrics(workspace_dir: str) -> dict:
    """
    Extracts Abstract Syntax Tree (AST) node sequences, variable naming conventions,
    identifier tokens, and stylistic fingerprints across submitted codebase.
    """
    ast_node_types: list[str] = []
    identifiers: list[str] = []
    function_names: list[str] = []
    class_names: list[str] = []
    code_snippets: list[str] = []

    # Scan python files first for full AST parsing
    python_files = []
    all_code_files = []

    for root, _, files in os.walk(workspace_dir):
        if ".git" in root or "node_modules" in root or "__pycache__" in root or ".venv" in root:
            continue
        for f in files:
            lower = f.lower()
            fpath = os.path.join(root, f)
            if lower.endswith(".py"):
                python_files.append(fpath)
            elif lower.endswith((".js", ".jsx", ".ts", ".tsx")):
                all_code_files.append(fpath)

    # 1. Parse AST for Python files
    for pf in python_files[:15]:
        try:
            with open(pf, "r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read()
            if not source.strip():
                continue
            tree = ast.parse(source)
            for node in ast.walk(tree):
                node_name = type(node).__name__
                ast_node_types.append(node_name)
                if isinstance(node, ast.Name):
                    identifiers.append(node.id)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_names.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    class_names.append(node.name)
                elif isinstance(node, ast.arg):
                    identifiers.append(node.arg)

            if len(code_snippets) < 3 and len(source) > 60:
                code_snippets.append(source[:1200])
        except Exception:
            continue

    # 2. If no python files, or in addition, extract identifiers from JS/TS
    if not identifiers and all_code_files:
        for jf in all_code_files[:15]:
            try:
                with open(jf, "r", encoding="utf-8", errors="ignore") as fh:
                    source = fh.read()
                matches = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", source)
                identifiers.extend(matches)
                # Pseudo AST node approximation from JS tokens
                ast_node_types.extend(re.findall(r"(?:function|class|const|let|var|if|for|while|return|import)", source))
                if len(code_snippets) < 3 and len(source) > 60:
                    code_snippets.append(source[:1200])
            except Exception:
                continue

    # Filter out common reserved words
    filtered_ids = [
        ident for ident in identifiers
        if ident.lower() not in COMMON_RESERVED_WORDS and len(ident) > 1
    ]

    # Calculate variable naming style breakdown
    snake_case_count = sum(1 for i in filtered_ids if "_" in i and i.islower())
    camel_case_count = sum(1 for i in filtered_ids if re.match(r"^[a-z]+[A-Z0-9]", i))
    pascal_case_count = sum(1 for i in filtered_ids if re.match(r"^[A-Z][a-z0-9]+[A-Z]", i))
    total_distinctive = max(1, len(filtered_ids))
    avg_len = round(sum(len(i) for i in filtered_ids) / total_distinctive, 2)

    # Compute normalized AST sequence hash
    ast_seq_str = "-".join(ast_node_types[:300]) if ast_node_types else "generic-code-structure"
    ast_hash = hashlib.sha256(ast_seq_str.encode("utf-8")).hexdigest()

    # Distinctive top identifiers (most frequent idiosyncratic terms)
    id_counts = Counter(filtered_ids)
    top_identifiers = [name for name, _ in id_counts.most_common(40)]

    naming_style = {
        "snake_case_count": snake_case_count,
        "camel_case_count": camel_case_count,
        "pascal_case_count": pascal_case_count,
        "snake_to_camel_ratio": round(snake_case_count / max(1, camel_case_count), 2),
        "avg_identifier_length": avg_len,
        "total_identifiers_analyzed": len(filtered_ids),
    }

    code_sample = "\n\n--- FILE SNIPPET ---\n\n".join(code_snippets[:2]) if code_snippets else "No source code read"

    return {
        "ast_hash": ast_hash,
        "ast_nodes_count": len(ast_node_types),
        "naming_style": naming_style,
        "identifiers": top_identifiers,
        "code_summary": code_sample,
    }


def evaluate_sybil_stylometric_fingerprint(
    workspace_dir: str | None = None,
    freelancer_email: str = "",
    bounty_id: int = 0,
    milestone_id: int = 0,
    github_url: str | None = None,
    db: Session | None = None,
) -> dict:
    """
    Sybil Attack Detection:
    1. Extracts AST structure and naming style of current code submission.
    2. Queries historical submissions from OTHER freelancer accounts in the database.
    3. If an exact AST hash match or high stylometric similarity is found across different accounts,
       calls Gemini to verify whether this is an identical author operating a Sybil attack.
    4. If flagged as Sybil match, returns is_sybil_match=True and blocks payout.
    5. Otherwise saves fingerprint and returns is_sybil_match=False.
    """
    if db is None:
        return {"is_sybil_match": False, "message": "No database session provided"}

    target_dir = workspace_dir
    temp_dir_obj = None

    if not target_dir or not os.path.exists(target_dir):
        temp_dir_obj = tempfile.TemporaryDirectory()
        target_dir = temp_dir_obj.name
        if github_url:
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", github_url, target_dir],
                    capture_output=True,
                    timeout=30,
                    text=True,
                )
            except Exception as clone_err:
                print(f"[Stylometrics] Git clone notice: {clone_err}")

    try:
        current_fp = extract_code_stylometrics(target_dir)
    finally:
        if temp_dir_obj:
            try:
                temp_dir_obj.cleanup()
            except Exception:
                pass

    current_clean_email = (freelancer_email or "").strip().lower()

    # Query fingerprints from OTHER accounts
    other_fps = (
        db.query(models.CodeFingerprint)
        .filter(models.CodeFingerprint.freelancer_email != current_clean_email)
        .order_by(models.CodeFingerprint.id.desc())
        .limit(20)
        .all()
    )

    if not other_fps:
        # First submission or no other accounts in DB yet; save and proceed
        new_record = models.CodeFingerprint(
            freelancer_email=current_clean_email,
            bounty_id=bounty_id,
            milestone_id=milestone_id,
            github_url=github_url,
            ast_hash=current_fp["ast_hash"],
            naming_style=current_fp["naming_style"],
            identifiers=current_fp["identifiers"],
            code_summary=current_fp["code_summary"],
            created_at=datetime.utcnow().isoformat(),
        )
        db.add(new_record)
        db.commit()
        return {
            "is_sybil_match": False,
            "stylometric_fingerprint": current_fp,
            "message": "Baseline stylometric fingerprint stored. No multi-account conflict detected.",
        }

    # Compare against other accounts
    for prev_fp in other_fps:
        exact_ast_match = (prev_fp.ast_hash == current_fp["ast_hash"])
        curr_ids = set(current_fp["identifiers"])
        prev_ids = set(prev_fp.identifiers or [])
        intersection = curr_ids.intersection(prev_ids)
        jaccard = len(intersection) / max(1, len(curr_ids.union(prev_ids)))

        # Heuristic trigger: exact AST hash or high identifier overlap across different accounts
        if exact_ast_match or jaccard > 0.40 or len(intersection) >= 8:
            print(
                f"[Stylometrics Alert] Potential Sybil match between current '{current_clean_email}' "
                f"and historical account '{prev_fp.freelancer_email}' (Exact AST={exact_ast_match}, Jaccard={jaccard:.2f}, Overlap={len(intersection)})"
            )

            # Gemini Forensic Verification Prompt
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            client = genai.Client(api_key=api_key)

            sybil_prompt = f"""You are the Chief Code Stylometry and Anti-Sybil Forensic Auditor on MilestoneEscrow.
Two submissions have been received from two DIFFERENT freelancer accounts. You must determine if they represent a Sybil Attack (the exact same author or generator operating multiple fake accounts to game the escrow payout system).

ACCOUNT A (Historical User): {prev_fp.freelancer_email}
- AST Topology Hash: {prev_fp.ast_hash}
- Naming Conventions: {json.dumps(prev_fp.naming_style)}
- Distinctive Identifier Tokens: {prev_fp.identifiers}
- Code Snippet:
\"\"\"{prev_fp.code_summary[:1200]}\"\"\"

ACCOUNT B (Current Submitting User): {current_clean_email}
- AST Topology Hash: {current_fp['ast_hash']}
- Naming Conventions: {json.dumps(current_fp['naming_style'])}
- Distinctive Identifier Tokens: {current_fp['identifiers']}
- Code Snippet:
\"\"\"{current_fp['code_summary'][:1200]}\"\"\"

Instructions:
1. Compare the syntactic tree patterns, variable naming idiosyncrasies, capitalization habits, and helper function idioms.
2. If both submissions originate from the same developer or cloned codebase across multiple accounts, flag as a Sybil attack.
3. Output strictly a raw JSON block at the very end in the format:
{{
  "is_sybil_match": boolean,
  "confidence_score": float,
  "stylistic_evidence": "Detailed explanation of matched naming, syntax patterns, or differences",
  "flagged_accounts": ["{prev_fp.freelancer_email}", "{current_clean_email}"]
}}
"""
            try:
                response = _generate_with_gemini(client, sybil_prompt, preferred_model="gemini-3.5-flash")
                resp_text = response.text or ""
                # Parse JSON
                start = resp_text.rfind("{")
                end = resp_text.rfind("}")
                if start != -1 and end != -1:
                    parsed_decision = json.loads(resp_text[start : end + 1])
                    if parsed_decision.get("is_sybil_match", False):
                        return {
                            "is_sybil_match": True,
                            "matched_account": prev_fp.freelancer_email,
                            "confidence_score": parsed_decision.get("confidence_score", 0.95),
                            "stylistic_evidence": parsed_decision.get("stylistic_evidence", "Exact AST and identifier stylometric match across accounts."),
                            "current_fingerprint": current_fp,
                        }
            except Exception as e:
                print(f"[Stylometrics] Gemini forensic evaluation error: {e}")
                # Fallback to exact AST match heuristic
                if exact_ast_match:
                    return {
                        "is_sybil_match": True,
                        "matched_account": prev_fp.freelancer_email,
                        "confidence_score": 0.98,
                        "stylistic_evidence": f"Identical AST structure hash ({current_fp['ast_hash']}) detected across distinct user accounts.",
                        "current_fingerprint": current_fp,
                    }

    # No Sybil attack detected; save fingerprint
    new_record = models.CodeFingerprint(
        freelancer_email=current_clean_email,
        bounty_id=bounty_id,
        milestone_id=milestone_id,
        github_url=github_url,
        ast_hash=current_fp["ast_hash"],
        naming_style=current_fp["naming_style"],
        identifiers=current_fp["identifiers"],
        code_summary=current_fp["code_summary"],
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(new_record)
    db.commit()

    return {
        "is_sybil_match": False,
        "stylometric_fingerprint": current_fp,
        "message": "Stylometric AST check passed. No Sybil collision found.",
    }

