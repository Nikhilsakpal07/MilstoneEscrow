"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";

interface PendingMilestone {
  bounty_id: number;
  bounty_title: string;
  bounty_amount_usd: number;
  bounty_remaining_usd: number;
  freelancer_email: string;
  acceptance_criteria: string;
  bounty_status: string;
  milestone_id: number;
  milestone_description: string;
  milestone_amount_usd: number;
  milestone_deadline: string;
  milestone_status: string;
  authorization_ids: string[];
  requires_human_approval: boolean;
  latest_ai_feedback: string;
  passed: boolean;
}

interface ApprovalResponse {
  status: string;
  bounty_id: number;
  milestone_id: number;
  milestone_status: string;
  payout_amount: number;
  paypal_payout_batch_id: string;
  captures: Array<{
    authorization_id: string;
    capture_id?: string;
    status: string;
  }>;
  remaining_amount_usd: number;
  bounty_status: string;
}

export default function AdminDashboardPage() {
  const [pendingItems, setPendingItems] = useState<PendingMilestone[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Action states
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [approvalSuccess, setApprovalSuccess] = useState<ApprovalResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Sponsoring dialog state
  const [activeSponsorMilestone, setActiveSponsorMilestone] = useState<{
    bounty_id: number;
    milestone_id: number;
    description: string;
  } | null>(null);
  const [sponsorName, setSponsorName] = useState("");
  const [sponsorOrderId, setSponsorOrderId] = useState("");
  const [sponsorAuthId, setSponsorAuthId] = useState("");
  const [sponsorAmount, setSponsorAmount] = useState("");
  const [isSponsoring, setIsSponsoring] = useState(false);

  const fetchPending = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("http://localhost:8000/api/admin/pending");
      if (!res.ok) {
        throw new Error(`Failed to load pending admin milestones (${res.status})`);
      }
      const data: PendingMilestone[] = await res.json();
      setPendingItems(data);
    } catch (err: any) {
      console.error("Fetch pending milestones error:", err);
      setError(err.message || "Failed to connect to backend server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  const handleFinalApprove = async (bountyId: number, milestoneId: number) => {
    const itemKey = `${bountyId}-${milestoneId}`;
    try {
      setProcessingId(itemKey);
      setActionError(null);
      setApprovalSuccess(null);

      const res = await fetch(
        `http://localhost:8000/api/admin/bounties/${bountyId}/milestones/${milestoneId}/approve`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            admin_notes: "Human co-signer signed off on high-value multi-sig milestone.",
          }),
        }
      );

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Approval failed with status ${res.status}`);
      }

      const result: ApprovalResponse = await res.json();
      setApprovalSuccess(result);
      // Refresh pending items
      await fetchPending();
    } catch (err: any) {
      console.error("Final approval error:", err);
      setActionError(err.message || "Failed to execute final human approval.");
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (bountyId: number, milestoneId: number) => {
    if (!confirm("Are you sure you want to reject this milestone payout?")) return;
    const itemKey = `${bountyId}-${milestoneId}`;
    try {
      setProcessingId(itemKey);
      setActionError(null);

      const res = await fetch(
        `http://localhost:8000/api/admin/bounties/${bountyId}/milestones/${milestoneId}/reject`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            rejection_reason: "Admin rejected high-value milestone payout during multi-sig review.",
          }),
        }
      );

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Rejection failed with status ${res.status}`);
      }

      await fetchPending();
    } catch (err: any) {
      console.error("Admin rejection error:", err);
      setActionError(err.message || "Failed to reject milestone.");
    } finally {
      setProcessingId(null);
    }
  };

  const handleAddSponsor = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeSponsorMilestone) return;

    try {
      setIsSponsoring(true);
      setActionError(null);

      const payload: any = {
        sponsor_name: sponsorName.trim() || "Co-Sponsor",
      };
      if (sponsorAuthId.trim()) {
        payload.authorization_id = sponsorAuthId.trim();
      } else if (sponsorOrderId.trim()) {
        payload.paypal_order_id = sponsorOrderId.trim();
      } else {
        throw new Error("Please provide either a PayPal Authorization ID or Order ID.");
      }

      if (sponsorAmount.trim() && !isNaN(Number(sponsorAmount))) {
        payload.amount_usd = parseFloat(sponsorAmount);
      }

      const res = await fetch(
        `http://localhost:8000/api/bounties/${activeSponsorMilestone.bounty_id}/milestones/${activeSponsorMilestone.milestone_id}/sponsor`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Sponsoring failed with status ${res.status}`);
      }

      setActiveSponsorMilestone(null);
      setSponsorName("");
      setSponsorOrderId("");
      setSponsorAuthId("");
      setSponsorAmount("");
      await fetchPending();
    } catch (err: any) {
      console.error("Add sponsor error:", err);
      setActionError(err.message || "Failed to add sponsor authorization.");
    } finally {
      setIsSponsoring(false);
    }
  };

  const totalPendingAmount = pendingItems.reduce(
    (sum, item) => sum + (Number(item.milestone_amount_usd) || 0),
    0
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <span className="p-1.5 bg-amber-100 text-amber-800 rounded-lg">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              </span>
              <span>Hybrid Multi-Sig Admin Portal</span>
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
              Co-Signer Protocol
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Bounties with value <strong className="text-slate-700">&gt; $5,000 USD</strong> require dual authorization.
            Autonomous AI evaluates submissions, and human administrators provide the final cryptographic sign-off before PayPal Payouts are executed.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchPending}
            disabled={loading}
            className="text-xs font-semibold px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm transition-colors flex items-center gap-1.5"
          >
            <svg
              className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span>Refresh</span>
          </button>
          <Link
            href="/"
            className="text-xs font-semibold px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm transition-colors"
          >
            &larr; Main Dashboard
          </Link>
        </div>
      </div>

      {/* Metrics Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <span className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Pending Multi-Sig Approvals
          </span>
          <div className="flex items-baseline gap-2 mt-2">
            <span className="text-3xl font-extrabold text-amber-600 font-mono">
              {pendingItems.length}
            </span>
            <span className="text-xs text-slate-500">milestone(s) awaiting signature</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <span className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">
            High-Value Funds in Escrow
          </span>
          <div className="flex items-baseline gap-2 mt-2">
            <span className="text-3xl font-extrabold text-slate-900 font-mono">
              ${totalPendingAmount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </span>
            <span className="text-xs text-slate-500">USD locked</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <span className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Security Policy Threshold
          </span>
          <div className="flex items-baseline gap-2 mt-2">
            <span className="text-3xl font-extrabold text-indigo-600 font-mono">
              $5,000+
            </span>
            <span className="text-xs text-slate-500">USD &bull; Hybrid Co-Signing</span>
          </div>
        </div>
      </div>

      {/* Global Action / Error Messages */}
      {actionError && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-start gap-2">
          <svg className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="font-bold">Admin Operation Failed</p>
            <p className="mt-0.5">{actionError}</p>
          </div>
        </div>
      )}

      {approvalSuccess && (
        <div className="p-5 bg-emerald-50 border border-emerald-200 rounded-2xl space-y-2.5">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <h3 className="text-sm font-bold text-emerald-900">
              Multi-Sig Co-Signer Approval Executed Successfully!
            </h3>
          </div>
          <div className="text-xs text-emerald-800 space-y-1 pl-4">
            <p className="font-semibold">
              &check; PayPal Payout of ${approvalSuccess.payout_amount.toFixed(2)} USD was sent to the payee.
            </p>
            <p className="font-mono text-[11px] text-emerald-700">
              PayPal Batch ID: <span className="font-bold">{approvalSuccess.paypal_payout_batch_id || "BATCH_PROCESSED"}</span>
            </p>
            {approvalSuccess.captures && approvalSuccess.captures.length > 0 && (
              <p className="text-[11px] text-emerald-700">
                Simultaneously captured {approvalSuccess.captures.length} authorized sponsor ID(s) and pooled funds into escrow.
              </p>
            )}
            <p className="text-[11px] text-slate-600">
              Remaining Escrow Balance: ${approvalSuccess.remaining_amount_usd.toFixed(2)} USD
            </p>
          </div>
        </div>
      )}

      {/* Pending Items List */}
      <div className="space-y-4">
        <h2 className="text-base font-bold text-slate-800 flex items-center justify-between">
          <span>High-Value Milestones Pending Final Human Approval</span>
          <span className="text-xs font-normal text-slate-500">
            {pendingItems.length} record(s) found
          </span>
        </h2>

        {loading ? (
          <div className="flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-slate-200">
            <div className="w-8 h-8 border-4 border-amber-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-slate-500 mt-3">Fetching multi-sig pending milestones...</p>
          </div>
        ) : pendingItems.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
            <div className="w-12 h-12 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-base font-bold text-slate-800">
              All Multi-Sig Milestones are Cleared!
            </h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              No submissions currently require human co-signing. Submissions over $5,000 will automatically appear here once approved by the AI evaluation agent.
            </p>
            <div className="pt-2">
              <Link
                href="/create"
                className="text-xs font-semibold px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-sm inline-block"
              >
                Create High-Value Bounty (&gt; $5,000)
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {pendingItems.map((item) => {
              const itemKey = `${item.bounty_id}-${item.milestone_id}`;
              const isProcessing = processingId === itemKey;

              return (
                <div
                  key={itemKey}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden hover:border-slate-300 transition-all"
                >
                  {/* Card Header */}
                  <div className="p-5 sm:p-6 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-slate-50/50">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs px-2.5 py-0.5 font-bold bg-blue-100 text-blue-800 rounded-md">
                          Bounty #{item.bounty_id}
                        </span>
                        <h3 className="text-base font-bold text-slate-900">{item.bounty_title}</h3>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 uppercase">
                          PENDING_ADMIN
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        Payee: <span className="font-mono font-medium text-slate-700">{item.freelancer_email}</span> &bull; Total Escrow Value:{" "}
                        <span className="font-mono font-bold text-slate-900">${item.bounty_amount_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })} USD</span>
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <span className="block text-[10px] font-semibold text-slate-400 uppercase">Milestone Payout</span>
                        <span className="text-lg font-bold font-mono text-emerald-600">
                          ${item.milestone_amount_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })} USD
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="p-5 sm:p-6 space-y-4">
                    {/* Milestone details */}
                    <div>
                      <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                        Milestone Deliverable Phase:
                      </h4>
                      <p className="text-sm font-semibold text-slate-800">
                        Phase #{item.milestone_id}: {item.milestone_description}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Deadline: {item.milestone_deadline || "Open"}
                      </p>
                    </div>

                    {/* Multi-Sponsor Pooling Section */}
                    <div className="p-3.5 bg-blue-50/60 rounded-xl border border-blue-200/80 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                          </svg>
                          <span className="text-xs font-bold text-blue-900">
                            Multi-Sponsor Pooled Authorization IDs ({item.authorization_ids?.length || 0})
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setActiveSponsorMilestone({
                              bounty_id: item.bounty_id,
                              milestone_id: item.milestone_id,
                              description: item.milestone_description,
                            })
                          }
                          className="text-[11px] font-semibold text-blue-700 hover:text-blue-900 underline"
                        >
                          + Add Sponsor Payout Source
                        </button>
                      </div>

                      {item.authorization_ids && item.authorization_ids.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {item.authorization_ids.map((aid, idx) => (
                            <span
                              key={idx}
                              className="font-mono text-[10px] px-2 py-0.5 rounded bg-white text-slate-800 border border-blue-200 shadow-2xs font-semibold"
                            >
                              Sponsor #{idx + 1}: {aid}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <p className="text-[11px] text-blue-700/80">
                          Primary escrow authorization will be captured upon final approval.
                        </p>
                      )}
                    </div>

                    {/* AI Evaluation Reason & Multi-Sig Trigger */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-emerald-500" />
                          <span>AI Auditor Verification (Passed):</span>
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          Dual Multi-Sig Required
                        </span>
                      </div>
                      <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                        {item.latest_ai_feedback}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="pt-2 flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => handleReject(item.bounty_id, item.milestone_id)}
                        disabled={isProcessing}
                        className="px-4 py-2 rounded-xl text-xs font-semibold text-rose-700 hover:bg-rose-50 border border-rose-200 transition-colors disabled:opacity-50"
                      >
                        Reject Payout
                      </button>

                      <button
                        type="button"
                        onClick={() => handleFinalApprove(item.bounty_id, item.milestone_id)}
                        disabled={isProcessing}
                        className="px-6 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 shadow-md shadow-emerald-600/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                      >
                        {isProcessing ? (
                          <>
                            <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            <span>Capturing Pooled Authorizations &amp; Disbursing Payout...</span>
                          </>
                        ) : (
                          <>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            <span>
                              Final Approve &bull; Disburse ${item.milestone_amount_usd.toFixed(2)} USD via PayPal
                            </span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Sponsoring Modal */}
      {activeSponsorMilestone && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">Add Sponsor Authorization</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Milestone #{activeSponsorMilestone.milestone_id}: {activeSponsorMilestone.description}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveSponsorMilestone(null)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleAddSponsor} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Sponsor Organization / Contributor Name:
                </label>
                <input
                  type="text"
                  value={sponsorName}
                  onChange={(e) => setSponsorName(e.target.value)}
                  placeholder="e.g. Humanitarian Relief Fund, Hackathon Sponsor"
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  PayPal Authorization ID <span className="text-rose-500">*</span>:
                </label>
                <input
                  type="text"
                  value={sponsorAuthId}
                  onChange={(e) => setSponsorAuthId(e.target.value)}
                  placeholder="e.g. 5XR1234567890123A"
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Or enter a PayPal Order ID below to auto-authorize.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  PayPal Order ID (Optional):
                </label>
                <input
                  type="text"
                  value={sponsorOrderId}
                  onChange={(e) => setSponsorOrderId(e.target.value)}
                  placeholder="e.g. 8W98765432109876B"
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Pledged Amount (USD, Optional):
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={sponsorAmount}
                  onChange={(e) => setSponsorAmount(e.target.value)}
                  placeholder="e.g. 1000.00"
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setActiveSponsorMilestone(null)}
                  disabled={isSponsoring}
                  className="px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSponsoring || (!sponsorAuthId.trim() && !sponsorOrderId.trim())}
                  className="px-4 py-2 text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 rounded-lg shadow-sm transition-all flex items-center gap-1.5"
                >
                  {isSponsoring ? (
                    <>
                      <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Authorizing...</span>
                    </>
                  ) : (
                    <span>Add to Pooled Milestone</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

