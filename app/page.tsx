"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { AgGridReact } from "ag-grid-react";
import { ColDef, ICellRendererParams } from "ag-grid-community";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

interface Bounty {
  id: number;
  title: string;
  acceptance_criteria: string;
  amount_usd: number;
  freelancer_email: string;
  status: string;
}

// Custom Cell Renderer for color-coding bounty statuses
const StatusBadgeRenderer = (params: ICellRendererParams) => {
  const status = (params.value || "").toUpperCase();

  let badgeClasses = "bg-gray-100 text-gray-800 border-gray-300";

  switch (status) {
    case "LOCKED":
      badgeClasses = "bg-blue-50 text-blue-700 border-blue-200 ring-1 ring-blue-500/20";
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

// Custom Cell Renderer for the Submit Work Action button
const ActionCellRenderer = (params: ICellRendererParams) => {
  const bountyId = params.data?.id;
  const status = params.data?.status;
  const isCompleted = status === "COMPLETED";

  return (
    <div className="flex items-center h-full gap-2">
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
        headerName: "Title",
        flex: 2,
        minWidth: 200,
        sortable: true,
        filter: true,
        cellClass: "font-medium text-slate-900",
      },
      {
        field: "amount_usd",
        headerName: "Amount",
        width: 130,
        sortable: true,
        filter: true,
        valueFormatter: (params) =>
          params.value != null ? `$${Number(params.value).toFixed(2)}` : "$0.00",
        cellClass: "font-semibold text-emerald-600 font-mono",
      },
      {
        field: "freelancer_email",
        headerName: "Freelancer Email",
        flex: 1.5,
        minWidth: 220,
        sortable: true,
        filter: true,
        cellClass: "text-slate-600",
      },
      {
        field: "status",
        headerName: "Status",
        width: 150,
        cellRenderer: StatusBadgeRenderer,
        sortable: true,
        filter: true,
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
      {/* Top Banner & Stats */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Escrow Bounties Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time status of milestone funds locked in PayPal Sandbox Escrow.
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
            + New Bounty
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
            <p className="text-sm text-slate-500">Loading bounties from backend...</p>
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
              Create your first freelance milestone escrow bounty to test PayPal authorization.
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

