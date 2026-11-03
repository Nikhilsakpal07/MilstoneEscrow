"use client";

import React, { useState } from "react";

interface PredictiveRiskBadgeProps {
  riskScore?: string | null;
  riskPercentage?: number | null;
  riskFactors?: string[] | null;
  recommendedAction?: string | null;
  compact?: boolean;
}

export default function PredictiveRiskBadge({
  riskScore = "LOW",
  riskPercentage = 15,
  riskFactors = [],
  recommendedAction,
  compact = false,
}: PredictiveRiskBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const score = (riskScore || "LOW").toUpperCase();
  const pct = riskPercentage ?? (score === "HIGH" ? 85 : score === "MEDIUM" ? 50 : 15);

  let badgeColor = "bg-emerald-50 text-emerald-700 border-emerald-300 ring-emerald-500/20";
  let dotColor = "bg-emerald-500";
  let label = "Low Risk";

  if (score === "HIGH") {
    badgeColor = "bg-rose-50 text-rose-800 border-rose-300 ring-rose-500/20";
    dotColor = "bg-rose-600 animate-pulse";
    label = "High Risk";
  } else if (score === "MEDIUM") {
    badgeColor = "bg-amber-50 text-amber-800 border-amber-300 ring-amber-500/20";
    dotColor = "bg-amber-500";
    label = "Medium Risk";
  }

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setShowTooltip(!showTooltip)}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border transition-all flex items-center gap-1.5 ring-1 ${badgeColor} cursor-pointer hover:shadow-xs`}
        title="Click to view AI Predictive Risk Breakdown"
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
        <span>{label}</span>
        {!compact && (
          <span className="font-mono text-[10px] opacity-75">
            ({pct}%)
          </span>
        )}
      </button>

      {/* Popover / Tooltip */}
      {showTooltip && (
        <div
          className="absolute z-50 bottom-full left-0 mb-2 w-72 p-3 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-700 pointer-events-auto"
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
        >
          <div className="flex items-center justify-between border-b border-slate-700 pb-1.5 mb-2">
            <span className="font-bold flex items-center gap-1.5 text-white">
              <span>🤖 Gemini Predictive Risk</span>
              <span className={`px-1.5 py-0.2 rounded text-[9px] font-mono uppercase ${
                score === "HIGH" ? "bg-rose-500 text-white" : score === "MEDIUM" ? "bg-amber-500 text-slate-900" : "bg-emerald-500 text-slate-900"
              }`}>
                {score} &bull; {pct}%
              </span>
            </span>
          </div>

          <p className="text-[11px] text-slate-300 mb-2 leading-relaxed">
            AI risk model correlates approaching milestone deadlines against submission update frequency.
          </p>

          {riskFactors && riskFactors.length > 0 && (
            <div className="space-y-1 mb-2">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Key Factors:
              </span>
              <ul className="list-disc list-inside space-y-0.5 text-[11px] text-slate-200">
                {riskFactors.map((f, i) => (
                  <li key={i} className="line-clamp-2">{f}</li>
                ))}
              </ul>
            </div>
          )}

          {recommendedAction && (
            <div className="pt-1.5 border-t border-slate-800 text-[10px] text-indigo-300">
              <strong>Action:</strong> {recommendedAction}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

