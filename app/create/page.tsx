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

export default function CreateBountyPage() {
  const router = useRouter();

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

  // Milestone helpers
  const totalPercentage = milestones.reduce(
    (sum, m) => sum + (Number(m.percentage) || 0),
    0
  );
  const isPercentageValid = Math.abs(totalPercentage - 100) < 0.01;

  const totalAmountNum = parseFloat(formData.amount_usd) || 0;

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
          <h1 className="text-2xl font-bold text-slate-900">
            Create Milestone-Based Bounty
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Authorize total escrow funds with PayPal and disburse payments in milestone increments.
          </p>
        </div>
        <Link
          href="/"
          className="text-sm text-slate-600 hover:text-slate-900 font-medium px-3 py-1.5 rounded-lg border border-slate-200 bg-white shadow-sm transition-colors"
        >
          &larr; Back
        </Link>
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

        <form onSubmit={(e) => e.preventDefault()} className="space-y-6">
          {/* Section 1: General Bounty Info */}
          <div className="space-y-4">
            <h2 className="text-base font-bold text-slate-800 border-b border-slate-100 pb-2">
              1. General Details
            </h2>

            {/* Title */}
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
                placeholder="e.g., Build Multi-Tier SaaS Authentication System"
                className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all"
                required
              />
            </div>

            {/* Overall Acceptance Criteria */}
            <div>
              <label
                htmlFor="acceptance_criteria"
                className="block text-sm font-semibold text-slate-700 mb-1.5"
              >
                Overall Acceptance Criteria <span className="text-rose-500">*</span>
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
                  2. Milestone Breakdown
                </h2>
                <p className="text-xs text-slate-500">
                  Define milestone phases. Payouts are triggered per milestone upon AI verification.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={distributeEvenly}
                  className="text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition-colors"
                >
                  Distribute Evenly
                </button>
                <button
                  type="button"
                  onClick={addMilestone}
                  className="text-xs font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1"
                >
                  + Add Milestone
                </button>
              </div>
            </div>

            {/* Dynamic Milestone Rows */}
            <div className="space-y-3">
              {milestones.map((m, index) => {
                const milestoneAmount = (totalAmountNum * (Number(m.percentage) || 0)) / 100;

                return (
                  <div
                    key={m.id}
                    className="p-4 bg-slate-50/80 rounded-xl border border-slate-200 space-y-3 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-700 bg-white border border-slate-200 px-2.5 py-0.5 rounded-md">
                        Phase #{index + 1}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-md">
                          Payout: ${milestoneAmount.toFixed(2)} USD
                        </span>
                        {milestones.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeMilestone(m.id)}
                            className="text-xs text-rose-500 hover:text-rose-700 font-semibold p-1 hover:bg-rose-50 rounded"
                            title="Remove milestone"
                          >
                            &times; Remove
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                      {/* Description */}
                      <div className="md:col-span-6">
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Milestone Scope &amp; Deliverable <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={m.description}
                          onChange={(e) =>
                            handleMilestoneChange(m.id, "description", e.target.value)
                          }
                          placeholder="e.g. Design DB schema, models and CRUD APIs"
                          className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                          required
                        />
                      </div>

                      {/* Deadline */}
                      <div className="md:col-span-3">
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Deadline <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="date"
                          value={m.deadline}
                          onChange={(e) =>
                            handleMilestoneChange(m.id, "deadline", e.target.value)
                          }
                          className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                          required
                        />
                      </div>

                      {/* Percentage */}
                      <div className="md:col-span-3">
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Allocation (%) <span className="text-rose-500">*</span>
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
                            className="w-full pl-3 pr-7 py-1.5 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white font-mono"
                            required
                          />
                          <span className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none text-slate-400 text-xs font-medium">
                            %
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Total Percentage Status Bar */}
            <div
              className={`p-3 rounded-xl border flex items-center justify-between text-xs font-semibold ${
                isPercentageValid
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : "bg-amber-50 text-amber-800 border-amber-200"
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
        </form>

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
      </div>
    </div>
  );
}
