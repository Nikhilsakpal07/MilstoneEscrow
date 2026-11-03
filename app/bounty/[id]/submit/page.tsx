"use client";

import React, { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

interface EvaluationResult {
  status: string;
  passed: boolean;
  feedback: string;
}

export default function SubmitWorkPage() {
  const params = useParams();
  const router = useRouter();
  const bountyId = params?.id;

  const [githubUrl, setGithubUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluationResult | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!githubUrl.trim()) {
      setError("Please provide a valid GitHub repository URL.");
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      setResult(null);

      const response = await fetch(
        `http://localhost:8000/api/bounties/${bountyId}/submit-work`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            github_url: githubUrl.trim(),
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || `Server responded with status ${response.status}`
        );
      }

      const data: EvaluationResult = await response.json();
      setResult(data);
    } catch (err: any) {
      console.error("Submission evaluation error:", err);
      setError(err.message || "An unexpected error occurred during submission.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900">Submit Work for Bounty</h1>
            <span className="font-mono text-xs px-2.5 py-0.5 font-bold bg-slate-200 text-slate-700 rounded-md">
              #{bountyId}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Submit your completed repository. Our autonomous QA agent will clone, install dependencies, run tests, and disburse escrow funds automatically upon passing.
          </p>
        </div>
        <Link
          href="/"
          className="text-sm text-slate-600 hover:text-slate-900 font-medium px-3 py-1.5 rounded-lg border border-slate-200 bg-white shadow-sm transition-colors"
        >
          &larr; Dashboard
        </Link>
      </div>

      {/* Submission Form Card */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8 space-y-6">
        {/* Error notification */}
        {error && (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-sm flex items-start gap-2">
            <svg
              className="w-5 h-5 text-rose-500 shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div>
              <p className="font-semibold">Submission Failed</p>
              <p className="mt-0.5">{error}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="github_url"
              className="block text-sm font-semibold text-slate-700 mb-1.5"
            >
              Public GitHub Repository URL <span className="text-rose-500">*</span>
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <svg
                  className="w-5 h-5"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    fillRule="evenodd"
                    clipRule="evenodd"
                    d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                  />
                </svg>
              </span>
              <input
                type="url"
                id="github_url"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/octocat/Hello-World"
                disabled={isLoading}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all disabled:bg-slate-100 disabled:text-slate-400 font-mono"
                required
              />
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Ensure the repository is public and includes necessary test commands (e.g. pytest, npm test).
            </p>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading || !githubUrl.trim()}
            className="w-full py-3 px-4 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed rounded-xl shadow-sm transition-all flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Evaluating Submission...</span>
              </>
            ) : (
              <span>Start AI Verification</span>
            )}
          </button>
        </form>

        {/* Distinct Loading State */}
        {isLoading && (
          <div className="p-6 bg-blue-50/70 border border-blue-200/80 rounded-2xl space-y-4 animate-pulse">
            <div className="flex items-center gap-3">
              <div className="w-6 h-6 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
              <div>
                <h4 className="text-sm font-bold text-blue-900">
                  AI Agent evaluating code...
                </h4>
                <p className="text-xs text-blue-700 mt-0.5">
                  Google Antigravity Agent has spawned a sandbox container.
                </p>
              </div>
            </div>

            <div className="space-y-2 text-xs text-blue-800/80 pl-9">
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                <span>Cloning repository to isolated workspace</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                <span>Installing dependencies &amp; running test suites</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                <span>Validating acceptance criteria &amp; triggering PayPal payout</span>
              </div>
            </div>
          </div>
        )}

        {/* Evaluation Output Result */}
        {result && (
          <div
            className={`p-6 rounded-2xl border transition-all ${
              result.passed
                ? "bg-emerald-50/70 border-emerald-200"
                : "bg-rose-50/70 border-rose-200"
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <span
                  className={`w-3 h-3 rounded-full ${
                    result.passed ? "bg-emerald-500" : "bg-rose-500"
                  }`}
                />
                <h3
                  className={`text-base font-bold ${
                    result.passed ? "text-emerald-900" : "text-rose-900"
                  }`}
                >
                  {result.passed ? "Evaluation Passed!" : "Evaluation Failed"}
                </h3>
              </div>
              <span
                className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
                  result.passed
                    ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                    : "bg-rose-100 text-rose-800 border-rose-300"
                }`}
              >
                STATUS: {result.status}
              </span>
            </div>

            {result.passed && (
              <p className="text-xs text-emerald-700 font-medium mb-3">
                &check; Escrow funds have been successfully captured and paid out to the freelancer's PayPal account!
              </p>
            )}

            {/* AI Feedback Display */}
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1.5">
                AI Feedback &amp; Audit Output:
              </p>
              <div className="bg-white/80 p-4 rounded-xl border border-slate-200/80 text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
                {result.feedback}
              </div>
            </div>

            <div className="mt-5 flex items-center justify-end gap-3">
              <button
                onClick={() => router.push("/")}
                className={`text-xs font-semibold px-4 py-2 rounded-lg transition-all ${
                  result.passed
                    ? "bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                    : "bg-slate-800 hover:bg-slate-900 text-white shadow-sm"
                }`}
              >
                Return to Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

