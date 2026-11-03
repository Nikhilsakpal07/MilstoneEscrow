"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PayPalButtons } from "@paypal/react-paypal-js";

interface MilestoneRow {
  id: string;
  description: string;
  deadline: string;
  percentage: number;
}

interface ParsedEscrowResponse {
  title?: string;
  acceptance_criteria?: string;
  amount_usd?: number;
  freelancer_email?: string;
  milestones?: Array<{
    description: string;
    deadline: string;
    percentage: number;
    amount_usd?: number;
  }>;
  ai_summary?: string;
}

export default function CreateBountyPage() {
  const router = useRouter();

  // Dual-mode UI toggle: "conversational" vs "detailed"
  const [creationMode, setCreationMode] = useState<"conversational" | "detailed">("conversational");

  // Mode 1: Conversational Chat State
  const [naturalPrompt, setNaturalPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedPreview, setGeneratedPreview] = useState<ParsedEscrowResponse | null>(null);

  // Mode 2: Detailed Builder Form State
  const [formData, setFormData] = useState({
    title: "",
    acceptance_criteria: "",
    amount_usd: "",
    freelancer_email: "",
  });

  const [milestones, setMilestones] = useState<MilestoneRow[]>([
    {
      id: "1",
      description: "Milestone 1: Foundation & Core Feature Development",
      deadline: "",
      percentage: 50,
    },
    {
      id: "2",
      description: "Milestone 2: Integration, Testing & Final Delivery",
      deadline: "",
      percentage: 50,
    },
  ]);

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Quick prompt suggestions for Conversational Escrow
  const promptSuggestions = [
    {
      label: "Web App Launch",
      prompt: "Pay $500 total, $100 on design in 7 days, $400 on deployment in 14 days, send to dev@example.com",
    },
    {
      label: "NGO Relief Supplies",
      prompt: "Total budget $3,000 USD for refugee emergency care: $1,200 on medical procurement in 5 days, $1,800 on verified on-ground distribution in 12 days, beneficiary is aid@redcross.org",
    },
    {
      label: "High-Value Enterprise Audit",
      prompt: "Pay $6,000 total for full security audit: $2,000 on architecture review in 10 days, $4,000 on penetration testing and patch verification in 21 days, send to sec-lead@enterprise.com",
    },
  ];

  // Milestone helpers
  const totalPercentage = milestones.reduce(
    (sum, m) => sum + (Number(m.percentage) || 0),
    0
  );
  const isPercentageValid = Math.abs(totalPercentage - 100) < 0.01;
  const totalAmountNum = parseFloat(formData.amount_usd) || 0;

  // Conversational Escrow Handler
  const handleGenerateScope = async (promptToUse?: string) => {
    const textToParse = promptToUse || naturalPrompt;
    if (!textToParse.trim()) {
      setError("Please describe the bounty scope or pick a prompt suggestion.");
      return;
    }

    try {
      setIsGenerating(true);
      setError(null);
      setGeneratedPreview(null);

      const res = await fetch("http://localhost:8000/api/bounties/generate-scope", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: textToParse.trim() }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `AI parsing failed with status ${res.status}`);
      }

      const data: ParsedEscrowResponse = await res.json();
      setGeneratedPreview(data);

      // Pre-populate Detailed Builder state
      if (data.title) setFormData((prev) => ({ ...prev, title: data.title || "" }));
      if (data.acceptance_criteria) setFormData((prev) => ({ ...prev, acceptance_criteria: data.acceptance_criteria || "" }));
      if (data.amount_usd) setFormData((prev) => ({ ...prev, amount_usd: data.amount_usd ? data.amount_usd.toString() : "" }));
      if (data.freelancer_email) setFormData((prev) => ({ ...prev, freelancer_email: data.freelancer_email || "" }));

      if (data.milestones && data.milestones.length > 0) {
        setMilestones(
          data.milestones.map((m, idx) => ({
            id: (idx + 1).toString(),
            description: m.description,
            deadline: m.deadline || "",
            percentage: Number(m.percentage) || 0,
          }))
        );
      }
    } catch (err: any) {
      console.error("Conversational Escrow error:", err);
      setError(err.message || "Failed to parse natural language requirements.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (error) setError(null);
  };

  const handleMilestoneChange = (
    id: string,
    field: keyof MilestoneRow,
    value: string | number
  ) => {
    setMilestones((prev) =>
      prev.map((m) => (m.id === id ? { ...m, [field]: value } : m))
    );
    if (error) setError(null);
  };

  const addMilestone = () => {
    const nextNum = milestones.length + 1;
    const remainingPct = Math.max(0, 100 - totalPercentage);
    setMilestones((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        description: `Milestone ${nextNum}: Deliverable phase`,
        deadline: "",
        percentage: remainingPct,
      },
    ]);
  };

  const removeMilestone = (id: string) => {
    if (milestones.length <= 1) return;
    setMilestones((prev) => prev.filter((m) => m.id !== id));
  };

  const distributeEvenly = () => {
    if (milestones.length === 0) return;
    const count = milestones.length;
    const basePct = Math.floor((100 / count) * 100) / 100;
    const remainder = Math.round((100 - basePct * count) * 100) / 100;

    setMilestones((prev) =>
      prev.map((m, idx) => ({
        ...m,
        percentage: idx === 0 ? Number((basePct + remainder).toFixed(2)) : basePct,
      }))
    );
  };

  const isFormValid =
    formData.title.trim() !== "" &&
    formData.acceptance_criteria.trim() !== "" &&
    formData.freelancer_email.trim() !== "" &&
    !isNaN(Number(formData.amount_usd)) &&
    Number(formData.amount_usd) > 0 &&
    isPercentageValid &&
    milestones.length > 0 &&
    milestones.every(
      (m) =>
        m.description.trim() !== "" &&
        m.deadline.trim() !== "" &&
        Number(m.percentage) > 0
    );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <span>Create Milestone Escrow Bounty</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Build multi-phase escrows using Google Gemini natural language parsing or the manual detailed builder.
          </p>
        </div>
        <Link
          href="/"
          className="text-sm text-slate-600 hover:text-slate-900 font-medium px-3 py-1.5 rounded-lg border border-slate-200 bg-white shadow-sm transition-colors"
        >
          &larr; Back
        </Link>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="bg-slate-100 p-1.5 rounded-2xl flex items-center gap-1 border border-slate-200 shadow-inner">
        <button
          type="button"
          onClick={() => setCreationMode("conversational")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
            creationMode === "conversational"
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <span className="text-base">✨</span>
          <span>Conversational Escrow (Gemini 1.5 Pro)</span>
        </button>

        <button
          type="button"
          onClick={() => setCreationMode("detailed")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
            creationMode === "detailed"
              ? "bg-white text-blue-700 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <span className="text-base">🛠️</span>
          <span>Detailed Builder (Manual Form)</span>
          {formData.title && (
            <span className="w-2 h-2 rounded-full bg-emerald-500" title="Configured" />
          )}
        </button>
      </div>

      {/* Main Card */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8 space-y-8">
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
            <span>{error}</span>
          </div>
        )}

        {/* ======================================================== */}
        {/* MODE 1: CONVERSATIONAL ESCROW GENERATOR                  */}
        {/* ======================================================== */}
        {creationMode === "conversational" && (
          <div className="space-y-6">
            <div className="p-4 bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border border-indigo-100 flex items-start gap-3">
              <span className="p-2 bg-indigo-600 text-white rounded-lg text-lg">✨</span>
              <div>
                <h3 className="text-sm font-bold text-indigo-950">
                  Autonomous Escrow Architect AI
                </h3>
                <p className="text-xs text-indigo-900/80 mt-0.5 leading-relaxed">
                  Describe what you want to fund in plain English (e.g. <em>&quot;Pay $500 total, $100 on design, $400 on launch&quot;</em>).
                  Google Gemini 1.5 Pro will parse it into a strict, mathematically validated milestone schedule.
                </p>
              </div>
            </div>

            {/* Quick Prompt Presets */}
            <div className="space-y-2">
              <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Quick Starters:
              </span>
              <div className="flex flex-wrap gap-2">
                {promptSuggestions.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setNaturalPrompt(item.prompt);
                      handleGenerateScope(item.prompt);
                    }}
                    className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 hover:border-slate-300 text-slate-700 transition-colors text-left"
                  >
                    <span className="font-semibold text-slate-900">{item.label}:</span>{" "}
                    <span className="text-slate-500 font-mono text-[11px] line-clamp-1">{item.prompt}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Natural Language Prompt Textarea */}
            <div className="space-y-2">
              <label htmlFor="naturalPrompt" className="block text-sm font-semibold text-slate-700">
                Your Contract or Bounty Description:
              </label>
              <textarea
                id="naturalPrompt"
                rows={4}
                value={naturalPrompt}
                onChange={(e) => setNaturalPrompt(e.target.value)}
                placeholder="e.g. I need a responsive fullstack landing page. Total budget $800. $200 for Figma wireframes in 5 days, $300 for Next.js frontend in 10 days, $300 for final production deploy and testing in 14 days. Beneficiary email is dev@freelancer.com"
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm transition-all"
                disabled={isGenerating}
              />
            </div>

            <button
              type="button"
              onClick={() => handleGenerateScope()}
              disabled={isGenerating || !naturalPrompt.trim()}
              className="w-full py-3 px-4 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl shadow-md transition-all flex items-center justify-center gap-2"
            >
              {isGenerating ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Google Gemini 1.5 Pro Architecting Escrow...</span>
                </>
              ) : (
                <>
                  <span>✨ Generate Structured Escrow with AI</span>
                </>
              )}
            </button>

            {/* Generated Escrow Preview Card */}
            {generatedPreview && (
              <div className="p-6 bg-slate-50 rounded-2xl border border-indigo-200 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                    <h3 className="text-base font-bold text-slate-900">
                      {generatedPreview.title || "AI Structured Escrow Plan"}
                    </h3>
                  </div>
                  <span className="text-base font-extrabold font-mono text-emerald-700">
                    ${(generatedPreview.amount_usd || 0).toFixed(2)} USD
                  </span>
                </div>

                {generatedPreview.ai_summary && (
                  <p className="text-xs text-slate-600 italic leading-relaxed">
                    &ldquo;{generatedPreview.ai_summary}&rdquo;
                  </p>
                )}

                <div className="space-y-1.5 text-xs text-slate-700">
                  <span className="font-semibold text-slate-900">Acceptance Criteria:</span>
                  <div className="bg-white p-3 rounded-xl border border-slate-200 text-xs text-slate-600 whitespace-pre-wrap">
                    {generatedPreview.acceptance_criteria}
                  </div>
                </div>

                {/* Milestone Phases List */}
                <div className="space-y-2">
                  <span className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Phased Milestones ({generatedPreview.milestones?.length || 0}):
                  </span>
                  <div className="grid grid-cols-1 gap-2">
                    {generatedPreview.milestones?.map((m, idx) => (
                      <div
                        key={idx}
                        className="p-3 bg-white rounded-xl border border-slate-200 flex items-center justify-between gap-3 text-xs"
                      >
                        <div>
                          <p className="font-bold text-slate-800">
                            Phase #{idx + 1}: {m.description}
                          </p>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            Deadline: {m.deadline} &bull; Allocation: {m.percentage}%
                          </p>
                        </div>
                        <span className="font-mono font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg shrink-0">
                          ${((m.amount_usd || (totalAmountNum * (m.percentage / 100)))).toFixed(2)} USD
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Switch to Detailed Builder CTA */}
                <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <span className="text-xs text-slate-500">
                    All fields have been auto-populated into the Detailed Builder.
                  </span>
                  <button
                    type="button"
                    onClick={() => setCreationMode("detailed")}
                    className="py-2.5 px-5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm transition-colors flex items-center justify-center gap-1.5"
                  >
                    <span>Open in Detailed Builder to Edit or Fund with PayPal</span>
                    <span>&rarr;</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ======================================================== */}
        {/* MODE 2: DETAILED BUILDER (MANUAL FORM)                   */}
        {/* ======================================================== */}
        {creationMode === "detailed" && (
          <form onSubmit={(e) => e.preventDefault()} className="space-y-6">
            {/* Notice if pre-filled by AI */}
            {generatedPreview && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center justify-between">
                <span>✓ Pre-filled with AI Escrow Architect structure. You can edit any details below.</span>
                <button
                  type="button"
                  onClick={() => setCreationMode("conversational")}
                  className="font-bold underline ml-2"
                >
                  Back to Chat
                </button>
              </div>
            )}

            {/* Section 1: General Bounty Info */}
            <div className="space-y-4">
              <h2 className="text-base font-bold text-slate-800 border-b border-slate-100 pb-2">
                1. General Details
              </h2>

              <div>
                <label
                  htmlFor="title"
                  className="block text-sm font-semibold text-slate-700 mb-1.5"
                >
                  Bounty Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  id="title"
                  name="title"
                  value={formData.title}
                  onChange={handleInputChange}
                  placeholder="e.g. Implement Next.js Escrow Dashboard or Medical Relief Delivery"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all"
                  required
                />
              </div>

              <div>
                <label
                  htmlFor="acceptance_criteria"
                  className="block text-sm font-semibold text-slate-700 mb-1.5"
                >
                  Comprehensive Acceptance Criteria <span className="text-rose-500">*</span>
                </label>
                <textarea
                  id="acceptance_criteria"
                  name="acceptance_criteria"
                  rows={3}
                  value={formData.acceptance_criteria}
                  onChange={handleInputChange}
                  placeholder="Core criteria checked by the AI QA agent across submissions..."
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all resize-y"
                  required
                />
              </div>

              {/* Total Amount & Freelancer Email */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="amount_usd"
                    className="block text-sm font-semibold text-slate-700 mb-1.5"
                  >
                    Total Escrow Amount (USD) <span className="text-rose-500">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400 font-medium">
                      $
                    </span>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      id="amount_usd"
                      name="amount_usd"
                      value={formData.amount_usd}
                      onChange={handleInputChange}
                      placeholder="500.00"
                      className="w-full pl-8 pr-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all font-mono font-medium"
                      required
                    />
                  </div>
                  {totalAmountNum > 5000 && (
                    <div className="mt-2 p-2.5 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-900 flex items-center gap-2">
                      <svg className="w-4 h-4 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <span>
                        <strong>Hybrid Multi-Sig Triggered (&gt; $5,000 USD):</strong> AI approval will set status to <code className="bg-amber-100 px-1 py-0.5 rounded">PENDING_ADMIN</code>, requiring human administrator sign-off before PayPal Payouts are released.
                      </span>
                    </div>
                  )}
                </div>

                <div>
                  <label
                    htmlFor="freelancer_email"
                    className="block text-sm font-semibold text-slate-700 mb-1.5"
                  >
                    Freelancer PayPal Email <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="email"
                    id="freelancer_email"
                    name="freelancer_email"
                    value={formData.freelancer_email}
                    onChange={handleInputChange}
                    placeholder="freelancer@example.com"
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all"
                    required
                  />
                </div>
              </div>
            </div>

            {/* Section 2: Milestone Breakdown */}
            <div className="space-y-4 pt-4 border-t border-slate-100">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-slate-800">
                    2. Milestone Allocation &amp; Schedule
                  </h2>
                  <p className="text-xs text-slate-500">
                    Define incremental deliverables. The percentages must sum to exactly 100%.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={distributeEvenly}
                    className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
                  >
                    Distribute Evenly
                  </button>
                  <button
                    type="button"
                    onClick={addMilestone}
                    className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 transition-colors"
                  >
                    + Add Milestone
                  </button>
                </div>
              </div>

              {/* Milestone Rows */}
              <div className="space-y-3">
                {milestones.map((m, idx) => {
                  const mAmount = totalAmountNum > 0
                    ? ((totalAmountNum * (Number(m.percentage) || 0)) / 100).toFixed(2)
                    : "0.00";

                  return (
                    <div
                      key={m.id}
                      className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                          <span className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-[10px]">
                            {idx + 1}
                          </span>
                          Milestone #{idx + 1}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-emerald-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                            ${mAmount} USD
                          </span>
                          {milestones.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeMilestone(m.id)}
                              className="text-xs text-rose-500 hover:text-rose-700 font-semibold px-1.5 py-0.5 rounded hover:bg-rose-50 transition-colors"
                              title="Remove milestone"
                            >
                              &times; Remove
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
                        <div className="sm:col-span-6">
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Deliverable Scope / Description <span className="text-rose-500">*</span>
                          </label>
                          <input
                            type="text"
                            value={m.description}
                            onChange={(e) =>
                              handleMilestoneChange(m.id, "description", e.target.value)
                            }
                            placeholder="e.g. Design Wireframes, Backend MVP, or Supply Delivery"
                            className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500 text-xs"
                            required
                          />
                        </div>

                        <div className="sm:col-span-3">
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Deadline <span className="text-rose-500">*</span>
                          </label>
                          <input
                            type="date"
                            value={m.deadline}
                            onChange={(e) =>
                              handleMilestoneChange(m.id, "deadline", e.target.value)
                            }
                            className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500 text-xs font-mono"
                            required
                          />
                        </div>

                        <div className="sm:col-span-3">
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Allocation % <span className="text-rose-500">*</span>
                          </label>
                          <div className="relative">
                            <input
                              type="number"
                              min="1"
                              max="100"
                              step="0.1"
                              value={m.percentage}
                              onChange={(e) =>
                                handleMilestoneChange(
                                  m.id,
                                  "percentage",
                                  parseFloat(e.target.value) || 0
                                )
                              }
                              className="w-full pl-3 pr-7 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500 text-xs font-mono text-right"
                              required
                            />
                            <span className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none text-slate-400 text-xs">
                              %
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Total percentage validation indicator */}
              <div
                className={`p-3 rounded-xl border text-xs font-medium flex items-center justify-between transition-colors ${
                  isPercentageValid
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-amber-50 border-amber-200 text-amber-800"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span>{isPercentageValid ? "✓ Total Allocation:" : "⚠ Allocation Status:"}</span>
                  <span className="font-mono text-sm">{totalPercentage.toFixed(1)}%</span>
                </div>
                <div>
                  {isPercentageValid ? (
                    <span className="text-emerald-700">Perfect (100% of ${totalAmountNum.toFixed(2)})</span>
                  ) : (
                    <span className="text-amber-700">Must equal 100% (currently {totalPercentage.toFixed(1)}%)</span>
                  )}
                </div>
              </div>
            </div>

            {/* Section 3: PayPal Escrow Authorization */}
            <div className="pt-4 border-t border-slate-200 space-y-4">
              <div>
                <h2 className="text-base font-bold text-slate-800">
                  3. Authorize Total Escrow Funds
                </h2>
                <p className="text-xs text-slate-500">
                  PayPal locks the total ${totalAmountNum.toFixed(2)} USD in escrow. Funds remain safely in escrow and are disbursed milestone-by-milestone only when the AI QA agent verifies each deliverable.
                </p>
              </div>

              {isSubmitting ? (
                <div className="flex flex-col items-center justify-center p-6 bg-slate-50 rounded-xl border border-slate-200 gap-2">
                  <div className="w-6 h-6 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
                  <p className="text-xs font-medium text-slate-600">
                    Authorizing PayPal escrow and configuring milestones...
                  </p>
                </div>
              ) : !isFormValid ? (
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center">
                  <p className="text-xs text-slate-500 font-medium">
                    {!isPercentageValid
                      ? `Milestone allocations currently sum to ${totalPercentage.toFixed(1)}%. Please adjust them to equal exactly 100%.`
                      : "Please complete all bounty and milestone fields with valid amounts and deadlines to activate PayPal authorization."}
                  </p>
                </div>
              ) : (
                <div className="w-full relative z-0">
                  <PayPalButtons
                    style={{
                      layout: "vertical",
                      color: "blue",
                      shape: "rect",
                      label: "paypal",
                    }}
                    disabled={!isFormValid || isSubmitting}
                    createOrder={(data, actions) => {
                      return actions.order.create({
                        intent: "AUTHORIZE",
                        purchase_units: [
                          {
                            description: `MilestoneEscrow: ${formData.title}`,
                            amount: {
                              currency_code: "USD",
                              value: Number(formData.amount_usd).toFixed(2),
                            },
                          },
                        ],
                      });
                    }}
                    onApprove={async (data, actions) => {
                      try {
                        setIsSubmitting(true);
                        setError(null);

                        const orderID = data.orderID;
                        if (!orderID) {
                          throw new Error("Missing order ID from PayPal approval.");
                        }

                        console.log("Captured Order ID:", data.orderID);

                        const payload = {
                          title: formData.title,
                          acceptance_criteria: formData.acceptance_criteria,
                          amount_usd: parseFloat(formData.amount_usd),
                          freelancer_email: formData.freelancer_email,
                          paypal_order_id: data.orderID,
                          milestones: milestones.map((m) => ({
                            description: m.description,
                            deadline: m.deadline,
                            percentage: Number(m.percentage),
                          })),
                        };

                        const response = await fetch("http://localhost:8000/api/bounties", {
                          method: "POST",
                          headers: {
                            "Content-Type": "application/json",
                          },
                          body: JSON.stringify(payload),
                        });

                        if (response.ok) {
                          router.push("/");
                        } else {
                          const errData = await response.json().catch(() => ({}));
                          throw new Error(
                            errData.detail || `Server returned status ${response.status}`
                          );
                        }
                      } catch (err: any) {
                        console.error("Bounty creation error:", err);
                        setError(err.message || "Failed to create bounty after PayPal approval.");
                      } finally {
                        setIsSubmitting(false);
                      }
                    }}
                    onError={(err) => {
                      console.error("PayPal button error:", err);
                      setError("A PayPal error occurred during authorization. Please try again.");
                    }}
                  />
                </div>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
