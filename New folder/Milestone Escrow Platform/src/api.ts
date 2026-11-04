export const API_BASE = "http://localhost:8000"

export interface MilestoneData {
  id: number
  description: string
  deadline: string
  percentage: number
  amount_usd: number
  status: string
  authorization_ids?: string[]
  tracking_number?: string
  shipping_status?: string
  paypal_payout_batch_id?: string
  certificate_id?: string
  has_certificate?: boolean
  requires_human_approval?: boolean
}

export interface BountyData {
  id: number
  title: string
  acceptance_criteria: string
  amount_usd: number
  remaining_amount_usd: number
  freelancer_email: string
  freelancer_phone?: string
  tracking_number?: string
  shipping_status?: string
  status: string
  risk_score?: "LOW" | "MEDIUM" | "HIGH"
  risk_percentage?: number
  risk_factors?: string[]
  requires_human_approval?: boolean
  is_high_value?: boolean
  milestones: MilestoneData[]
}

/**
 * Fetch all bounties from backend API with fallback mock data
 */
export async function getBounties(): Promise<BountyData[]> {
  try {
    const res = await fetch(`${API_BASE}/api/bounties`, { method: "GET" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (Array.isArray(data) && data.length > 0) {
      return data
    }
  } catch (err) {
    console.warn("[API] Using offline fallback for bounties:", err)
  }

  // Fallback demo data if backend is offline
  return [
    {
      id: 2401,
      title: "Enterprise Payments API Migration",
      acceptance_criteria: "Complete migration to new ISO payment gateway with 90%+ test coverage.",
      amount_usd: 120000,
      remaining_amount_usd: 96000,
      freelancer_email: "alex.chen@fintech-dev.io",
      status: "IN_PROGRESS",
      risk_score: "LOW",
      risk_percentage: 12,
      risk_factors: ["Normal submission cadence", "Phase 1 complete"],
      milestones: [
        {
          id: 1,
          description: "Architecture & schema design",
          deadline: "2026-11-10",
          percentage: 20,
          amount_usd: 24000,
          status: "COMPLETED",
          certificate_id: "ESC-9A8B7C",
          has_certificate: true,
        },
        {
          id: 2,
          description: "Core gateway integration & webhook handling",
          deadline: "2026-11-25",
          percentage: 50,
          amount_usd: 60000,
          status: "IN_PROGRESS",
        },
        {
          id: 3,
          description: "End-to-end load tests & documentation",
          deadline: "2026-12-15",
          percentage: 30,
          amount_usd: 36000,
          status: "LOCKED",
        },
      ],
    },
    {
      id: 2398,
      title: "Humanitarian Medical Crates Consignment",
      acceptance_criteria: "Deliver certified medical supplies to regional health center #4 with signed receipt.",
      amount_usd: 48500,
      remaining_amount_usd: 48500,
      freelancer_email: "field.logistics@ngo-relief.org",
      tracking_number: "TRACK-DELIVERED-001",
      shipping_status: "DELIVERED",
      status: "LOCKED",
      risk_score: "LOW",
      risk_percentage: 15,
      milestones: [
        {
          id: 4,
          description: "Cold-chain vaccine transport to regional clinic",
          deadline: "2026-11-18",
          percentage: 100,
          amount_usd: 48500,
          status: "LOCKED",
          tracking_number: "TRACK-DELIVERED-001",
          shipping_status: "DELIVERED",
        },
      ],
    },
    {
      id: 2395,
      title: "Real-time AI Audio Streaming Pipeline",
      acceptance_criteria: "Bidirectional WebSocket with sub-200ms latency.",
      amount_usd: 14500,
      remaining_amount_usd: 7250,
      freelancer_email: "dev@audio-stream.co",
      status: "PENDING_ADMIN",
      requires_human_approval: true,
      risk_score: "MEDIUM",
      risk_percentage: 45,
      risk_factors: ["Pending multi-sig co-signer sign-off (> $5,000 threshold)"],
      milestones: [
        {
          id: 5,
          description: "WebSocket gateway & buffer queue",
          deadline: "2026-11-05",
          percentage: 50,
          amount_usd: 7250,
          status: "COMPLETED",
          has_certificate: true,
        },
        {
          id: 6,
          description: "VAD & neural speech synthesis engine",
          deadline: "2026-11-20",
          percentage: 50,
          amount_usd: 7250,
          status: "PENDING_ADMIN",
          requires_human_approval: true,
        },
      ],
    },
  ]
}

/**
 * Conversational Escrow Scope Generation via Gemini
 */
export async function generateScopeAI(prompt: string) {
  const res = await fetch(`${API_BASE}/api/bounties/generate-scope`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) throw new Error("Failed to generate AI contract scope")
  return res.json()
}

/**
 * Create a new contract on the backend
 */
export async function createBounty(payload: any) {
  const res = await fetch(`${API_BASE}/api/bounties`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    throw new Error(errData.detail || "Failed to create escrow contract")
  }
  return res.json()
}

/**
 * Submit deliverable for AI audit (files or GitHub)
 */
export async function submitWork(
  bountyId: number,
  milestoneId: number,
  payload: { github_url?: string; file?: File }
) {
  let body: any
  let headers: HeadersInit = {}

  if (payload.file) {
    const formData = new FormData()
    formData.append("file", payload.file)
    formData.append("milestone_id", String(milestoneId))
    if (payload.github_url) formData.append("github_url", payload.github_url)
    body = formData
  } else {
    headers["Content-Type"] = "application/json"
    body = JSON.stringify({
      github_url: payload.github_url,
      milestone_id: milestoneId,
    })
  }

  const res = await fetch(
    `${API_BASE}/api/bounties/${bountyId}/milestones/${milestoneId}/submit-work`,
    {
      method: "POST",
      headers,
      body,
    }
  )

  const data = await res.json()
  if (!res.ok && res.status !== 400) {
    throw new Error(data.detail || "Failed to audit submission")
  }
  return data
}

/**
 * Submit appeal to Mediator AI
 */
export async function submitAppeal(
  bountyId: number,
  milestoneId: number,
  appeal_text: string
) {
  const res = await fetch(`${API_BASE}/api/bounties/${bountyId}/appeal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ appeal_text, milestone_id: milestoneId }),
  })
  return res.json()
}

/**
 * Run Gemini Predictive Risk Engine across active contracts
 */
export async function runPredictiveRiskEngine() {
  const res = await fetch(`${API_BASE}/api/analytics/predictive-risk/evaluate`, {
    method: "POST",
  })
  return res.json()
}

/**
 * Admin Multi-Sig Final Approval
 */
export async function adminApproveMilestone(
  bountyId: number,
  milestoneId: number,
  adminNotes: string
) {
  const res = await fetch(
    `${API_BASE}/api/admin/bounties/${bountyId}/milestones/${milestoneId}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_notes: adminNotes }),
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || "Admin approval co-sign failed")
  }
  return res.json()
}

/**
 * Get Logistics Shipping Oracle Status
 */
export async function getShippingOracle(trackingNumber: string) {
  const res = await fetch(
    `${API_BASE}/api/oracle/shipping/${encodeURIComponent(trackingNumber)}`
  )
  return res.json()
}

/**
 * Simulate Carrier Update
 */
export async function updateShippingOracle(trackingNumber: string, status: string) {
  const res = await fetch(
    `${API_BASE}/api/oracle/shipping/${encodeURIComponent(trackingNumber)}/status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }
  )
  return res.json()
}

/**
 * Poll Oracle immediately to trigger auto-approvals
 */
export async function pollOracleDeliveries() {
  const res = await fetch(`${API_BASE}/api/oracle/poll`, { method: "POST" })
  return res.json()
}
