"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

interface Milestone {
  id: number;
  description: string;
  deadline: string;
  percentage: number;
  amount_usd: number;
  status: string;
  paypal_payout_batch_id?: string;
}

interface BountyDetail {
  id: number;
  title: string;
  acceptance_criteria: string;
  amount_usd: number;
  remaining_amount_usd: number;
  freelancer_email: string;
  status: string;
  milestones: Milestone[];
}

interface ExtractedReceiptData {
  total_amount?: string;
  date?: string;
  vendor?: string;
  items?: string[];
}

interface EvaluationResult {
  status: string;
  milestone_id: number;
  milestone_description: string;
  milestone_status: string;
  milestone_amount_paid: number;
  remaining_amount_usd: number;
  passed: boolean;
  feedback: string;
  extracted_data?: ExtractedReceiptData;
}

type SubmissionMode = "receipt" | "github";

export default function SubmitWorkPage() {
  const params = useParams();
  const router = useRouter();
  const bountyId = params?.id;

  const [bounty, setBounty] = useState<BountyDetail | null>(null);
  const [selectedMilestoneId, setSelectedMilestoneId] = useState<number | null>(null);

  // Form state
  const [submissionMode, setSubmissionMode] = useState<SubmissionMode>("receipt");
  const [githubUrl, setGithubUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);

  const [isLoadingBounty, setIsLoadingBounty] = useState(true);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluationResult | null>(null);

  // Fetch bounty and milestone details
  const fetchBounty = async () => {
    try {
      setIsLoadingBounty(true);
      const res = await fetch(`http://localhost:8000/api/bounties/${bountyId}`);
      if (!res.ok) {
        throw new Error(`Failed to load bounty #${bountyId}`);
      }
      const data: BountyDetail = await res.json();
      setBounty(data);

      const pending = data.milestones?.find((m) => m.status !== "COMPLETED");
      if (pending) {
        setSelectedMilestoneId(pending.id);
      } else if (data.milestones && data.milestones.length > 0) {
        setSelectedMilestoneId(data.milestones[0].id);
      }
    } catch (err: any) {
      console.error("Fetch bounty error:", err);
      setError(err.message || "Failed to load bounty information.");
    } finally {
      setIsLoadingBounty(false);
    }
  };

  useEffect(() => {
    if (bountyId) {
      fetchBounty();
    }
  }, [bountyId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setError(null);

      if (file.type.startsWith("image/")) {
        const url = URL.createObjectURL(file);
        setFilePreview(url);
      } else {
        setFilePreview(null);
      }
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
    if (filePreview) {
      URL.revokeObjectURL(filePreview);
      setFilePreview(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedMilestoneId) {
      setError("Please select a milestone to submit work for.");
      return;
    }

    if (submissionMode === "receipt" && !selectedFile) {
      setError("Please upload a receipt, invoice, or proof image/PDF.");
      return;
    }

    if (submissionMode === "github" && !githubUrl.trim()) {
      setError("Please enter a valid GitHub repository URL.");
      return;
    }

    try {
      setIsEvaluating(true);
      setError(null);
      setResult(null);

      const formData = new FormData();
      formData.append("milestone_id", selectedMilestoneId.toString());

      if (submissionMode === "receipt" && selectedFile) {
        formData.append("files", selectedFile);
      } else if (submissionMode === "github") {
        formData.append("github_url", githubUrl.trim());
      }

      const response = await fetch(
        `http://localhost:8000/api/bounties/${bountyId}/milestones/${selectedMilestoneId}/submit-work`,
        {
          method: "POST",
          body: formData,
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
      fetchBounty();
    } catch (err: any) {
      console.error("Submission evaluation error:", err);
      setError(err.message || "An unexpected error occurred during submission.");
    } finally {
      setIsEvaluating(false);
    }
  };

  const selectedMilestone = bounty?.milestones?.find(
    (m) => m.id === selectedMilestoneId
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900">
              Submit Milestone Proof of Work
            </h1>
            <span className="font-mono text-xs px-2.5 py-0.5 font-bold bg-blue-100 text-blue-800 rounded-md">
              Bounty #{bountyId}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Submit either financial receipts / proof documents or GitHub code. Google Gemini audits the submission and triggers milestone payouts automatically.
          </p>
        </div>
        <Link
          href="/"
          className="text-sm text-slate-600 hover:text-slate-900 font-medium px-3 py-1.5 rounded-lg border border-slate-200 bg-white shadow-sm transition-colors"
        >
          &larr; Dashboard
        </Link>
      </div>

      {isLoadingBounty ? (
        <div className="flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-slate-200">
          <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-500 mt-3">Loading milestone details...</p>
        </div>
      ) : (
        <>
          {/* Bounty & Milestones Overview */}
          {bounty && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">{bounty.title}</h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Beneficiary / Freelancer:{" "}
                    <span className="font-mono font-medium text-slate-700">
                      {bounty.freelancer_email}
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-4 text-right">
                  <div>
                    <span className="block text-xs text-slate-400">Total Escrow</span>
                    <span className="font-mono text-sm font-bold text-slate-800">
                      ${bounty.amount_usd.toFixed(2)}
                    </span>
                  </div>
                  <div className="border-l border-slate-200 pl-4">
                    <span className="block text-xs text-slate-400">Remaining Funds</span>
                    <span className="font-mono text-sm font-bold text-emerald-600">
                      ${(bounty.remaining_amount_usd ?? bounty.amount_usd).toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Milestone Selection List */}
              <div className="space-y-2">
                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  Select Milestone to Submit:
                </label>
                <div className="grid grid-cols-1 gap-2.5">
                  {bounty.milestones?.map((m, idx) => {
                    const isSelected = selectedMilestoneId === m.id;
                    const isCompleted = m.status === "COMPLETED";

                    return (
                      <div
                        key={m.id}
                        onClick={() => !isCompleted && setSelectedMilestoneId(m.id)}
                        className={`p-3.5 rounded-xl border text-xs transition-all flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 cursor-pointer ${
                          isCompleted
                            ? "bg-slate-50/80 border-slate-200 opacity-60 cursor-default"
                            : isSelected
                            ? "bg-blue-50/60 border-blue-400 ring-2 ring-blue-500/20"
                            : "bg-white border-slate-200 hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <input
                            type="radio"
                            name="milestone_select"
                            checked={isSelected}
                            disabled={isCompleted}
                            onChange={() => setSelectedMilestoneId(m.id)}
                            className="text-blue-600 focus:ring-blue-500"
                          />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-slate-800">
                                Phase #{idx + 1}: {m.description}
                              </span>
                              {isCompleted && (
                                <span className="bg-emerald-100 text-emerald-800 px-2 py-0.2 rounded-full font-bold text-[10px]">
                                  PAID OUT
                                </span>
                              )}
                            </div>
                            <span className="text-slate-400 text-[11px] mt-0.5 block">
                              Deadline: {m.deadline || "None"} &bull; Allocation: {m.percentage}%
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-3 self-end sm:self-auto">
                          <span className="font-mono font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg">
                            ${m.amount_usd.toFixed(2)} USD
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-md font-semibold text-[10px] uppercase border ${
                              m.status === "COMPLETED"
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                : m.status === "REJECTED"
                                ? "bg-rose-50 text-rose-700 border-rose-200"
                                : m.status === "AUDITING"
                                ? "bg-purple-50 text-purple-700 border-purple-200"
                                : "bg-blue-50 text-blue-700 border-blue-200"
                            }`}
                          >
                            {m.status}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Submission Form Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8 space-y-6">
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
                  <p className="font-semibold">Submission Error</p>
                  <p className="mt-0.5">{error}</p>
                </div>
              </div>
            )}

            {/* Targeted Milestone Summary Banner */}
            {selectedMilestone && (
              <div className="p-3 bg-blue-50/70 border border-blue-200 rounded-xl text-xs text-blue-900 flex items-center justify-between">
                <div>
                  <span className="font-bold">Targeted Phase: </span>
                  <span>{selectedMilestone.description}</span>
                </div>
                <span className="font-mono font-bold text-emerald-700 bg-white px-2 py-0.5 rounded border border-blue-200">
                  Payout: ${selectedMilestone.amount_usd.toFixed(2)}
                </span>
              </div>
            )}

            {/* Submission Mode Tabs */}
            <div className="border-b border-slate-200">
              <nav className="flex space-x-6 text-sm font-semibold">
                <button
                  type="button"
                  onClick={() => setSubmissionMode("receipt")}
                  className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                    submissionMode === "receipt"
                      ? "border-blue-600 text-blue-600"
                      : "border-transparent text-slate-500 hover:text-slate-800"
                  }`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <span>Receipt / Proof Upload (Images &amp; PDFs)</span>
                </button>

                <button
                  type="button"
                  onClick={() => setSubmissionMode("github")}
                  className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                    submissionMode === "github"
                      ? "border-blue-600 text-blue-600"
                      : "border-transparent text-slate-500 hover:text-slate-800"
                  }`}
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path
                      fillRule="evenodd"
                      clipRule="evenodd"
                      d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                    />
                  </svg>
                  <span>GitHub Repository URL</span>
                </button>
              </nav>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Mode 1: File Upload */}
              {submissionMode === "receipt" && (
                <div className="space-y-4">
                  <label className="block text-sm font-semibold text-slate-700">
                    Upload Receipt or Proof Document <span className="text-rose-500">*</span>
                  </label>

                  {!selectedFile ? (
                    <div className="border-2 border-dashed border-slate-300 rounded-2xl p-6 text-center hover:border-blue-400 transition-colors bg-slate-50/50">
                      <svg
                        className="w-10 h-10 text-slate-400 mx-auto mb-2"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                        />
                      </svg>
                      <p className="text-sm font-semibold text-slate-700">
                        Drop receipt images (PNG, JPG, WEBP) or PDFs here
                      </p>
                      <p className="text-xs text-slate-400 mt-1 mb-3">
                        Ideal for donation receipts, supply invoices, proof of delivery, or NGO expenditure records.
                      </p>
                      <label className="inline-block px-4 py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-sm cursor-pointer transition-colors">
                        Browse Files
                        <input
                          type="file"
                          accept="image/png, image/jpeg, image/jpg, image/webp, application/pdf"
                          onChange={handleFileChange}
                          className="hidden"
                          disabled={isEvaluating}
                        />
                      </label>
                    </div>
                  ) : (
                    <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {filePreview ? (
                          <img
                            src={filePreview}
                            alt="Receipt Preview"
                            className="w-14 h-14 object-cover rounded-lg border border-slate-200"
                          />
                        ) : (
                          <div className="w-14 h-14 bg-red-50 text-red-600 rounded-lg flex items-center justify-center font-bold text-xs border border-red-200">
                            PDF
                          </div>
                        )}
                        <div>
                          <p className="text-xs font-bold text-slate-800 line-clamp-1">
                            {selectedFile.name}
                          </p>
                          <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                            {(selectedFile.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={removeFile}
                        disabled={isEvaluating}
                        className="text-xs text-rose-600 hover:text-rose-800 font-semibold p-1.5 hover:bg-rose-50 rounded-lg transition-colors"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Mode 2: GitHub URL */}
              {submissionMode === "github" && (
                <div>
                  <label
                    htmlFor="github_url"
                    className="block text-sm font-semibold text-slate-700 mb-1.5"
                  >
                    Public GitHub Repository URL <span className="text-rose-500">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
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
                      disabled={isEvaluating}
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all font-mono disabled:bg-slate-100 disabled:text-slate-400"
                    />
                  </div>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={
                  isEvaluating ||
                  !selectedMilestoneId ||
                  (submissionMode === "receipt" && !selectedFile) ||
                  (submissionMode === "github" && !githubUrl.trim())
                }
                className="w-full py-3 px-4 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed rounded-xl shadow-sm transition-all flex items-center justify-center gap-2"
              >
                {isEvaluating ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Auditing Proof with Google Gemini...</span>
                  </>
                ) : (
                  <span>
                    Submit Proof &bull; Request ${selectedMilestone?.amount_usd?.toFixed(2) || "0.00"} Payout
                  </span>
                )}
              </button>
            </form>

            {/* Distinct Loading State */}
            {isEvaluating && (
              <div className="p-6 bg-blue-50/70 border border-blue-200/80 rounded-2xl space-y-4 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="w-6 h-6 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
                  <div>
                    <h4 className="text-sm font-bold text-blue-900">
                      Google Gemini 1.5 Pro auditing milestone proof of work...
                    </h4>
                    <p className="text-xs text-blue-700 mt-0.5">
                      Target Phase: {selectedMilestone?.description}
                    </p>
                  </div>
                </div>

                <div className="space-y-2 text-xs text-blue-800/80 pl-9">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                    <span>
                      {submissionMode === "receipt"
                        ? "Extracting receipt totals, transaction date, vendor & itemized purchases"
                        : "Cloning repository & inspecting test suites"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                    <span>Cross-referencing extracted proof against milestone scope &amp; acceptance criteria</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                    <span>
                      Disbursing ${selectedMilestone?.amount_usd.toFixed(2)} USD via PayPal Payouts upon verification
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Evaluation Result */}
            {result && (
              <div
                className={`p-6 rounded-2xl border transition-all space-y-4 ${
                  result.passed
                    ? "bg-emerald-50/70 border-emerald-200"
                    : "bg-rose-50/70 border-rose-200"
                }`}
              >
                <div className="flex items-center justify-between">
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
                      {result.passed
                        ? `Milestone #${result.milestone_id} Approved & Paid Out!`
                        : `Milestone #${result.milestone_id} Verification Failed`}
                    </h3>
                  </div>
                  <span
                    className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
                      result.passed
                        ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                        : "bg-rose-100 text-rose-800 border-rose-300"
                    }`}
                  >
                    STATUS: {result.milestone_status}
                  </span>
                </div>

                {result.passed && (
                  <div className="p-3 bg-white/80 rounded-xl border border-emerald-200 text-xs text-emerald-800 space-y-1">
                    <p className="font-semibold">
                      &check; PayPal Payout of ${result.milestone_amount_paid.toFixed(2)} USD was successfully sent to the beneficiary!
                    </p>
                    <p className="text-slate-600 font-mono">
                      Remaining escrow balance: ${result.remaining_amount_usd.toFixed(2)} USD
                    </p>
                  </div>
                )}

                {/* Gemini Extracted Data Card */}
                {result.extracted_data && (
                  <div className="p-4 bg-white/90 rounded-xl border border-slate-200 text-xs space-y-2.5">
                    <h4 className="font-bold text-slate-800 flex items-center gap-1.5">
                      <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      <span>Gemini 1.5 Pro Extracted Receipt Data</span>
                    </h4>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 border-y border-slate-100 py-2">
                      <div>
                        <span className="block text-[11px] text-slate-400">Total Extracted</span>
                        <span className="font-bold font-mono text-slate-800">
                          {result.extracted_data.total_amount || "Not identified"}
                        </span>
                      </div>
                      <div>
                        <span className="block text-[11px] text-slate-400">Receipt Date</span>
                        <span className="font-bold text-slate-800">
                          {result.extracted_data.date || "Not identified"}
                        </span>
                      </div>
                      <div>
                        <span className="block text-[11px] text-slate-400">Vendor / Recipient</span>
                        <span className="font-bold text-slate-800 truncate block">
                          {result.extracted_data.vendor || "Not identified"}
                        </span>
                      </div>
                    </div>

                    {result.extracted_data.items && result.extracted_data.items.length > 0 && (
                      <div>
                        <span className="block text-[11px] text-slate-400 mb-1">
                          Itemized Goods / Services Verified:
                        </span>
                        <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                          {result.extracted_data.items.map((item, i) => (
                            <li key={i} className="line-clamp-1">
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* AI Reasoning Feedback */}
                <div>
                  <p className="text-xs font-semibold text-slate-700 mb-1.5">
                    AI Auditor Reasoning:
                  </p>
                  <div className="bg-white/80 p-4 rounded-xl border border-slate-200 text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
                    {result.feedback}
                  </div>
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    onClick={() => router.push("/")}
                    className="text-xs font-semibold px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-900 text-white shadow-sm transition-all"
                  >
                    Return to Dashboard
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
