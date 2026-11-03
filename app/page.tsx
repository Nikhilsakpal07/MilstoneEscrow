"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { AgGridReact } from "ag-grid-react";
import { ColDef, ICellRendererParams } from "ag-grid-community";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

interface Milestone {
  id: number;
  description: string;
  deadline: string;
  percentage: number;
  amount_usd: number;
  status: string;
}

interface Bounty {
  id: number;
  title: string;
  acceptance_criteria: string;
  amount_usd: number;
  remaining_amount_usd: number;
  freelancer_email: string;
  status: string;
  milestones: Milestone[];
}

// Custom Cell Renderer for color-coding bounty statuses
const StatusBadgeRenderer = (params: ICellRendererParams) => {
  const status = (params.value || "").toUpperCase();

  let badgeClasses = "bg-gray-100 text-gray-800 border-gray-300";

  switch (status) {
    case "LOCKED":
      badgeClasses = "bg-blue-50 text-blue-700 border-blue-200 ring-1 ring-blue-500/20";
      break;
    case "IN_PROGRESS":
      badgeClasses = "bg-sky-50 text-sky-700 border-sky-200 ring-1 ring-sky-500/20";
      break;
    case "COMPLETED":
      badgeClasses = "bg-emerald-50 text-emerald-700 border-emerald-200 ring-1 ring-emerald-500/20";
      break;
    case "REJECTED":
      badgeClasses = "bg-rose-50 text-rose-700 border-rose-200 ring-1 ring-rose-500/20";
      break;
    case "AUDITING":
      badgeClasses = "bg-purple-50 text-purple-700 border-purple-200 ring-1 ring-purple-500/20";
      break;
    case "PENDING_ADMIN":
      badgeClasses = "bg-amber-100 text-amber-900 border-amber-300 ring-1 ring-amber-500/40 font-bold";
      break;
    case "AWAITING_FUNDS":
      badgeClasses = "bg-amber-50 text-amber-700 border-amber-200 ring-1 ring-amber-500/20";
      break;
  }

  return (
    <div className="flex items-center h-full">
      <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide border ${badgeClasses}`}>
        {params.value}
      </span>
    </div>
  );
};

// Milestone Progress Renderer
const MilestoneProgressRenderer = (params: ICellRendererParams) => {
  const milestones: Milestone[] = params.data?.milestones || [];
  if (!milestones.length) return <span className="text-slate-400 text-xs">No milestones</span>;

  const completed = milestones.filter((m) => m.status === "COMPLETED").length;
  const total = milestones.length;
  const isAllDone = completed === total;

  return (
    <div className="flex items-center h-full gap-2 text-xs">
      <span
        className={`px-2 py-0.5 rounded font-mono font-bold border ${
          isAllDone
            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
            : completed > 0
            ? "bg-blue-50 text-blue-700 border-blue-200"
            : "bg-slate-100 text-slate-600 border-slate-200"
        }`}
      >
        {completed}/{total} Completed
      </span>
    </div>
  );
};

// Custom Cell Renderer for the Submit Work Action button
const ActionCellRenderer = (params: ICellRendererParams) => {
  const bountyId = params.data?.id;
  const status = params.data?.status;
  const isCompleted = status === "COMPLETED";
  const isPendingAdmin = status === "PENDING_ADMIN";

  return (
    <div className="flex items-center h-full gap-2">
      {isPendingAdmin ? (
        <Link
          href="/admin"
          className="text-xs font-bold px-3 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white shadow-sm transition-colors flex items-center gap-1"
        >
          <span>Admin Review</span>
          <span className="text-[10px]">&rarr;</span>
        </Link>
      ) : (
        <Link
          href={`/bounty/${bountyId}/submit`}
          className={`text-xs font-medium px-3 py-1 rounded transition-colors ${
            isCompleted
              ? "bg-slate-100 text-slate-500 hover:bg-slate-200"
              : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm"
          }`}
        >
          {isCompleted ? "View Audit" : "Submit Work"}
        </Link>
      )}
    </div>
  );
};

export default function DashboardPage() {
  const [bounties, setBounties] = useState<Bounty[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBounties = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("http://localhost:8000/api/bounties");
      if (!res.ok) {
        throw new Error(`Failed to fetch bounties (status ${res.status})`);
      }
      const data = await res.json();
      setBounties(data);
    } catch (err: any) {
      console.error("Fetch bounties error:", err);
      setError(err.message || "Failed to connect to backend server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBounties();
  }, []);

  // AG Grid Column Definitions
  const columnDefs = useMemo<ColDef[]>(
    () => [
      {
        field: "id",
        headerName: "ID",
        width: 80,
        sortable: true,
        filter: true,
        cellClass: "font-mono font-medium text-slate-600",
      },
      {
        field: "title",
        headerName: "Bounty Title",
        flex: 2,
        minWidth: 200,
        sortable: true,
        filter: true,
        cellClass: "font-medium text-slate-900",
      },
      {
        field: "amount_usd",
        headerName: "Total Funds",
        width: 120,
        sortable: true,
        filter: true,
        valueFormatter: (params) =>
          params.value != null ? `$${Number(params.value).toFixed(2)}` : "$0.00",
        cellClass: "font-mono font-semibold text-slate-700",
      },
      {
        field: "remaining_amount_usd",
        headerName: "Remaining Escrow",
        width: 150,
        sortable: true,
        filter: true,
        valueFormatter: (params) =>
          params.value != null ? `$${Number(params.value).toFixed(2)}` : "$0.00",
        cellClass: "font-mono font-bold text-emerald-600",
      },
      {
        headerName: "Milestones",
        width: 160,
        cellRenderer: MilestoneProgressRenderer,
        sortable: false,
        filter: false,
      },
      {
        field: "freelancer_email",
        headerName: "Freelancer Email",
        flex: 1.5,
        minWidth: 200,
        sortable: true,
        filter: true,
        cellClass: "text-slate-600",
      },
      {
        field: "status",
        headerName: "Status",
        width: 140,
        cellRenderer: StatusBadgeRenderer,
        sortable: true,
        filter: true,
      },
      {
        headerName: "Governance",
        width: 145,
        valueGetter: (params) => {
          const isHigh = (params.data?.amount_usd || 0) > 5000;
          return isHigh ? "Multi-Sig" : "Auto-Escrow";
        },
        cellRenderer: (params: ICellRendererParams) => {
          const isHigh = params.value === "Multi-Sig";
          return (
            <div className="flex items-center h-full">
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase border ${
                  isHigh
                    ? "bg-amber-50 text-amber-800 border-amber-300"
                    : "bg-slate-50 text-slate-600 border-slate-200"
                }`}
              >
                {isHigh ? "🛡️ >$5K Multi-Sig" : "Auto AI"}
              </span>
            </div>
          );
        },
      },
      {
        headerName: "Action",
        width: 140,
        cellRenderer: ActionCellRenderer,
        sortable: false,
        filter: false,
      },
    ],
    []
  );

  const defaultColDef = useMemo<ColDef>(
    () => ({
      resizable: true,
    }),
    []
  );

  return (
    <div className="space-y-6">
      {/* Pending Multi-Sig Notification Banner */}
      {bounties.some((b) => b.status === "PENDING_ADMIN") && (
        <div className="p-4 bg-amber-50 border border-amber-300 rounded-2xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-3">
            <span className="p-2 bg-amber-100 text-amber-800 rounded-xl">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </span>
            <div>
              <h4 className="text-sm font-bold text-amber-900">
                Hybrid Multi-Sig Sign-off Required
              </h4>
              <p className="text-xs text-amber-800 mt-0.5">
                One or more high-value milestone submissions (&gt; $5,000 USD) have passed AI evaluation and are waiting for human co-signer approval.
              </p>
            </div>
          </div>
          <Link
            href="/admin"
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded-xl shadow-xs transition-colors shrink-0 flex items-center gap-1.5"
          >
            <span>Open Multi-Sig Admin Portal</span>
            <span>&rarr;</span>
          </Link>
        </div>
      )}

      {/* Top Banner & Stats */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Milestone Escrow Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Track multi-phase milestone escrows, authorized PayPal funds, and AI verification status.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchBounties}
            className="px-3 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors flex items-center gap-1.5"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Refresh
          </button>
          <Link
            href="/create"
            className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-all"
          >
            + Create Bounty
          </Link>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={fetchBounties}
            className="underline font-semibold hover:text-rose-900"
          >
            Retry
          </button>
        </div>
      )}

      {/* AG Grid Data Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden p-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-80 gap-3">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-slate-500">Loading bounties &amp; milestones...</p>
          </div>
        ) : bounties.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-3 text-slate-400">
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-slate-800">No bounties found</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
              Create your first milestone escrow bounty with dynamic phase breakdowns.
            </p>
            <Link
              href="/create"
              className="mt-4 inline-block px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-all"
            >
              Create Bounty
            </Link>
          </div>
        ) : (
          <div className="ag-theme-alpine w-full h-[520px] rounded-lg overflow-hidden">
            <AgGridReact
              rowData={bounties}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              pagination={true}
              paginationPageSize={10}
              animateRows={true}
              rowHeight={50}
              headerHeight={46}
            />
          </div>
        )}
      </div>
    </div>
  );
}
