"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PayPalButtons } from "@paypal/react-paypal-js";

export default function CreateBountyPage() {
  const router = useRouter();

  const [formData, setFormData] = useState({
    title: "",
    acceptance_criteria: "",
    amount_usd: "",
    freelancer_email: "",
  });

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const isFormValid =
    formData.title.trim() !== "" &&
    formData.acceptance_criteria.trim() !== "" &&
    formData.freelancer_email.trim() !== "" &&
    !isNaN(Number(formData.amount_usd)) &&
    Number(formData.amount_usd) > 0;

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (error) setError(null);
  };

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Create New Milestone Bounty</h1>
          <p className="text-sm text-slate-500 mt-1">
            Specify requirements and lock funds in escrow via PayPal Authorization.
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
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8 space-y-6">
        {/* Error message */}
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

        <form onSubmit={(e) => e.preventDefault()} className="space-y-5">
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
              placeholder="e.g., Build Stripe Checkout Integration"
              className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all"
              required
            />
          </div>

          {/* Acceptance Criteria */}
          <div>
            <label
              htmlFor="acceptance_criteria"
              className="block text-sm font-semibold text-slate-700 mb-1.5"
            >
              Acceptance Criteria <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="acceptance_criteria"
              name="acceptance_criteria"
              rows={4}
              value={formData.acceptance_criteria}
              onChange={handleInputChange}
              placeholder="Detail the exact tests, behavior, and deliverables the AI QA agent will verify..."
              className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all resize-y"
              required
            />
            <p className="text-xs text-slate-400 mt-1">
              The Antigravity AI Agent will clone the submitted repository and audit against these criteria.
            </p>
          </div>

          {/* Amount & Freelancer Email Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="amount_usd"
                className="block text-sm font-semibold text-slate-700 mb-1.5"
              >
                Amount (USD) <span className="text-rose-500">*</span>
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
                  placeholder="100.00"
                  className="w-full pl-8 pr-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-all font-mono"
                  required
                />
              </div>
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
        </form>

        {/* PayPal Escrow Authorization Section */}
        <div className="pt-4 border-t border-slate-200">
          <div className="mb-4">
            <h2 className="text-sm font-semibold text-slate-800">
              Authorize Escrow Funds
            </h2>
            <p className="text-xs text-slate-500">
              Funds are authorized and held securely in escrow. They are captured and paid out only after AI QA verification passes.
            </p>
          </div>

          {isSubmitting ? (
            <div className="flex flex-col items-center justify-center p-6 bg-slate-50 rounded-xl border border-slate-200 gap-2">
              <div className="w-6 h-6 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-xs font-medium text-slate-600">
                Saving bounty and locking escrow funds...
              </p>
            </div>
          ) : !isFormValid ? (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center">
              <p className="text-xs text-slate-500 font-medium">
                Please complete all form fields above to activate PayPal Escrow authorization.
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
                    };

                    const response = await fetch("http://localhost:8000/api/bounties", {
                      method: "POST",
                      headers: {
                        "Content-Type": "application/json",
                      },
                      body: JSON.stringify(payload),
                    });

                    if (response.ok) {
                      // Redirect to dashboard upon 200/201 response
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

