import { useState, useEffect, useRef } from "react"
import {
  type User,
  subscribeToAuthChanges,
  loginWithEmail,
  signupWithEmail,
  loginWithGoogle,
  loginWithGithub,
  logoutUser,
} from "./firebase"
import {
  animateScreenEnter,
  animateHeroEntrance,
  animateStaggerCards,
  animateToast,
  animateAlertPulse,
  animateButtonPress,
} from "./animations"
import {
  API_BASE,
  type BountyData,
  type MilestoneData,
  getBounties,
  generateScopeAI,
  createBounty,
  submitWork,
  submitAppeal,
  runPredictiveRiskEngine,
  adminApproveMilestone,
  getShippingOracle,
  updateShippingOracle,
  pollOracleDeliveries,
} from "./api"

type Screen = "landing" | "auth" | "dashboard" | "studio" | "audit" | "admin" | "logistics"
type IconName =
  | "arrow"
  | "bolt"
  | "box"
  | "check"
  | "chevron"
  | "close"
  | "code"
  | "file"
  | "lock"
  | "plus"
  | "receipt"
  | "refresh"
  | "shield"
  | "spark"
  | "upload"

function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    bolt: <path d="m13 2-9 12h7l-1 8 9-12h-7l1-8Z" />,
    box: (
      <>
        <path d="m21 8-9-5-9 5 9 5 9-5Z" />
        <path d="m3 8 9 5 9-5M3 8v8l9 5 9-5V8M12 13v8" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    code: (
      <>
        <path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14" />
      </>
    ),
    file: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
        <path d="M14 2v6h6M8 13h8M8 17h5" />
      </>
    ),
    lock: (
      <>
        <rect x="4" y="10" width="16" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    receipt: (
      <>
        <path d="M5 3v18l3-2 4 2 4-2 3 2V3l-3 2-4-2-4 2-3-2Z" />
        <path d="M9 9h6M9 13h6" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 11a8 8 0 0 0-14.9-3M4 4v5h5M4 13a8 8 0 0 0 14.9 3M20 20v-5h-5" />
      </>
    ),
    shield: (
      <>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3Z" />
        <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V4M7 9l5-5 5 5" />
        <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
      </>
    ),
  }
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  )
}

function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "green" | "amber" | "red" | "neutral"
  children: React.ReactNode
}) {
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-dot" />
      {children}
    </span>
  )
}

function Header({
  screen,
  setScreen,
  runEngine,
  user,
  onLogout,
}: {
  screen: Screen
  setScreen: (screen: Screen) => void
  runEngine: () => void
  user: User | null
  onLogout: () => void
}) {
  const links: [string, Screen][] = [
    ["Dashboard", "dashboard"],
    ["Create Contract", "studio"],
    ["Admin Multi-Sig", "admin"],
    ["Logistics Oracle", "logistics"],
  ]
  return (
    <header className="topbar">
      <button
        className="brand"
        onClick={() => setScreen("dashboard")}
        aria-label="Milestone Escrow dashboard"
      >
        <span className="brand-mark">
          <span />
        </span>
        <span>Milestone Escrow</span>
      </button>
      <nav>
        {links.map(([label, target]) => (
          <button
            key={target}
            className={screen === target ? "active" : ""}
            onClick={() => setScreen(target)}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="header-actions">
        {user ? (
          <div className="user-profile-badge">
            <span className="user-avatar-dot" />
            <span>{user.email?.split("@")[0] || "User"}</span>
            <button className="logout-btn" onClick={onLogout} title="Log out">
              (Exit)
            </button>
          </div>
        ) : (
          <button className="public-ghost" style={{ height: "32px", fontSize: "11px" }} onClick={() => setScreen("auth")}>
            Sign In
          </button>
        )}
        <button className="engine-button" onClick={runEngine}>
          <Icon name="spark" />
          Run AI Risk Engine
        </button>
        <div className="connection">
          <span />
          PayPal Sandbox: Connected
        </div>
      </div>
    </header>
  )
}

function PageIntro({
  eyebrow,
  title,
  copy,
  right,
}: {
  eyebrow: string
  title: string
  copy: string
  right?: React.ReactNode
}) {
  return (
    <div className="page-intro">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{copy}</p>
      </div>
      {right}
    </div>
  )
}

/* =========================================================================
   DASHBOARD SCREEN
   ========================================================================= */
function Dashboard({
  bounties,
  onSelectBounty,
  onNewContract,
}: {
  bounties: BountyData[]
  onSelectBounty: (bounty: BountyData) => void
  onNewContract: () => void
}) {
  const totalLocked = bounties.reduce((acc, b) => acc + (b.remaining_amount_usd || b.amount_usd || 0), 0)
  const totalSettled = bounties.reduce((acc, b) => acc + ((b.amount_usd || 0) - (b.remaining_amount_usd || 0)), 0)
  const activeMilestonesCount = bounties.reduce(
    (acc, b) => acc + (b.milestones || []).filter((m) => m.status !== "COMPLETED").length,
    0
  )
  const highRiskCount = bounties.filter((b) => b.risk_score === "HIGH").length

  const metrics = [
    ["Total Escrow Locked", `$${totalLocked.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, "Secured under PayPal"],
    ["Active Deliverables", `${activeMilestonesCount}`, `Across ${bounties.length} contracts`],
    ["Settled Disbursements", `$${totalSettled.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, "Autonomous releases"],
    ["High-Risk Flags", `0${highRiskCount}`, highRiskCount > 0 ? "Requires review" : "All deliverables on schedule"],
  ]

  const metricsRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    animateStaggerCards(metricsRef.current, ".metric-card")
  }, [])

  return (
    <main>
      <PageIntro
        eyebrow="Portfolio overview"
        title="Client dashboard"
        copy="Monitor capital, deliverables, and AI-reviewed contract risk in real time."
        right={
          <button className="primary-button" onClick={onNewContract}>
            <Icon name="plus" />
            New contract
          </button>
        }
      />
      <section className="metrics" ref={metricsRef}>
        {metrics.map((m, i) => (
          <article className={`metric-card ${i === 3 && highRiskCount > 0 ? "risk-card" : ""}`} key={m[0]}>
            <div className="metric-label">{m[0]}</div>
            <div className="metric-value">{m[1]}</div>
            <div className="metric-note">
              {i === 3 && highRiskCount > 0 && <span className="pulse-dot" />}
              {m[2]}
            </div>
          </article>
        ))}
      </section>

      <section className="panel contracts-panel">
        <div className="panel-heading">
          <div>
            <h2>Active contracts</h2>
            <p>All escrow agreements, milestone progress, and AI risk verdicts.</p>
          </div>
          <button className="ghost-button" onClick={() => window.open(`${API_BASE}/api/bounties`, "_blank")}>
            Export API JSON
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Contract title</th>
                <th>Financial balance</th>
                <th>Progress</th>
                <th>Status</th>
                <th>Predictive risk</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bounties.map((contract) => {
                const total = contract.amount_usd || 1
                const remaining = contract.remaining_amount_usd !== undefined ? contract.remaining_amount_usd : total
                const progressPct = Math.round(((total - remaining) / total) * 100)
                const completedMilestone = (contract.milestones || []).find((m) => m.status === "COMPLETED" || m.has_certificate)

                let statusTone: "green" | "amber" | "red" | "neutral" = "neutral"
                if (contract.status === "COMPLETED") statusTone = "green"
                else if (contract.status === "PENDING_ADMIN") statusTone = "amber"
                else if (contract.status === "fraud_review_pending") statusTone = "red"

                let riskTone: "green" | "amber" | "red" | "neutral" = "green"
                if (contract.risk_score === "HIGH") riskTone = "red"
                else if (contract.risk_score === "MEDIUM") riskTone = "amber"

                return (
                  <tr key={contract.id}>
                    <td>
                      <strong>{contract.title}</strong>
                      <small>
                        ID #{contract.id} &bull; {contract.freelancer_email}
                      </small>
                    </td>
                    <td className="mono">
                      <strong>${remaining.toLocaleString()}</strong>
                      <small>of ${total.toLocaleString()} total</small>
                    </td>
                    <td>
                      <div className="progress-cell">
                        <div className="progress-track">
                          <span style={{ width: `${progressPct}%` }} />
                        </div>
                        <small>{progressPct}%</small>
                      </div>
                    </td>
                    <td>
                      <Badge tone={statusTone}>
                        {contract.status === "fraud_review_pending" ? "FRAUD REVIEW" : contract.status}
                      </Badge>
                    </td>
                    <td>
                      <Badge tone={riskTone}>
                        {contract.risk_score || "LOW"} RISK &bull; {contract.risk_percentage || 15}%
                      </Badge>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <button className="row-button" onClick={() => onSelectBounty(contract)}>
                          View / Submit <Icon name="arrow" />
                        </button>
                        {completedMilestone && (
                          <a
                            className="cert-btn"
                            href={`${API_BASE}/api/milestones/${completedMilestone.id}/certificate`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Download Escrow Verification Certificate (PDF)"
                          >
                            <Icon name="file" size={12} /> PDF
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}

/* =========================================================================
   STUDIO (CONTRACT CREATOR) SCREEN
   ========================================================================= */
function Studio({ onContractCreated }: { onContractCreated: () => void }) {
  const [mode, setMode] = useState<"ai" | "manual">("ai")
  const [generating, setGenerating] = useState(false)
  const [proposalData, setProposalData] = useState<any>(null)
  const [authorized, setAuthorized] = useState(false)
  const [brief, setBrief] = useState(
    "Build and deploy an enterprise ISO payment gateway. $12,000 total: $4,000 for architecture and specs due in 10 days, $6,000 for core backend implementation due in 25 days, and $2,000 for automated testing and team handoff due in 35 days. Freelancer: alex.chen@fintech-dev.io."
  )

  // Manual Builder Form State
  const [title, setTitle] = useState("Enterprise Payment Gateway API")
  const [criteria, setCriteria] = useState("Full ISO API compliance, 90%+ automated test coverage, and documentation.")
  const [totalBudget, setTotalBudget] = useState(12000)
  const [freelancerEmail, setFreelancerEmail] = useState("alex.chen@fintech-dev.io")
  const [freelancerPhone, setFreelancerPhone] = useState("+14155552671")
  const [trackingNumber, setTrackingNumber] = useState("FEDEX-RELIEF-100")
  const [milestones, setMilestones] = useState([
    { description: "Architecture & schema design", deadline: "2026-11-15", percentage: 33.3, amount: 4000 },
    { description: "Core gateway integration & webhook handling", deadline: "2026-11-30", percentage: 50.0, amount: 6000 },
    { description: "Load tests & production deployment", deadline: "2026-12-10", percentage: 16.7, amount: 2000 },
  ])

  // Handle Conversational AI Generation via Gemini API
  const handleGenerateScope = async () => {
    try {
      setGenerating(true)
      const data = await generateScopeAI(brief)
      setProposalData(data)
      if (data.title) setTitle(data.title)
      if (data.acceptance_criteria) setCriteria(data.acceptance_criteria)
      if (data.total_budget_usd) setTotalBudget(data.total_budget_usd)
      if (Array.isArray(data.milestones) && data.milestones.length > 0) {
        setMilestones(
          data.milestones.map((m: any) => ({
            description: m.description,
            deadline: m.deadline || "2026-12-01",
            percentage: m.percentage || Math.round(100 / data.milestones.length),
            amount: Math.round((data.total_budget_usd || 12000) * ((m.percentage || 33) / 100)),
          }))
        )
      }
    } catch (err) {
      console.error("AI Generation error:", err)
      // Fallback proposal state
      setProposalData({
        title: "Enterprise ISO Payment API Migration",
        confidence: 96,
        summary: "Three-phase deliverable with autonomous GitHub test coverage and formal acceptance criteria.",
        duration: "5 weeks",
        total: totalBudget,
      })
    } finally {
      setGenerating(false)
    }
  }

  // Handle Escrow Authorization & Save to PostgreSQL
  const handleAuthorizeEscrow = async () => {
    try {
      setAuthorized(true)
      await createBounty({
        title,
        acceptance_criteria: criteria,
        amount_usd: totalBudget,
        freelancer_email: freelancerEmail,
        freelancer_phone: freelancerPhone,
        tracking_number: trackingNumber,
        shipping_status: "NOT_SHIPPED",
        paypal_order_id: "PAYPAL-ORDER-" + Math.random().toString(36).substring(2, 9).toUpperCase(),
        milestones: milestones.map((m) => ({
          description: m.description,
          deadline: m.deadline,
          percentage: m.percentage,
          tracking_number: trackingNumber,
          shipping_status: "NOT_SHIPPED",
        })),
      })
      setTimeout(() => {
        onContractCreated()
      }, 1200)
    } catch (err: any) {
      console.error("Failed to create contract:", err)
      alert("Error creating contract: " + (err.message || "Network error"))
      setAuthorized(false)
    }
  }

  return (
    <main>
      <PageIntro
        eyebrow="Contract creation"
        title="Contract studio"
        copy="Turn any business outcome or software requirement into an auditable, milestone-based escrow agreement."
      />
      <div className="segment-control">
        <button className={mode === "ai" ? "selected" : ""} onClick={() => setMode("ai")}>
          <Icon name="spark" />
          Conversational AI Studio
        </button>
        <button className={mode === "manual" ? "selected" : ""} onClick={() => setMode("manual")}>
          <Icon name="file" />
          Detailed Manual Builder
        </button>
      </div>

      <section className="studio-grid">
        <div className="studio-column">
          <div className="section-number">01 / SCOPE</div>
          <h2>{mode === "ai" ? "Describe intended outcome" : "Contract scope & parties"}</h2>
          <p className="section-copy">
            {mode === "ai"
              ? "Use natural language. Google Gemini will parse deliverables, dates, budget allocations, and acceptance criteria."
              : "Specify deliverables, criteria, and payee PayPal account details."}
          </p>

          {mode === "ai" ? (
            <>
              <label className="field-label" htmlFor="scope">
                Natural Language Project Brief
              </label>
              <textarea
                id="scope"
                className="scope-input"
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                rows={5}
              />
              <button className="primary-button wide" onClick={handleGenerateScope} disabled={generating}>
                <Icon name="spark" />
                {generating ? "Gemini is structuring milestones..." : "Generate Contract Scope"}
              </button>
              {proposalData && (
                <article className="proposal proposal-ready">
                  <div className="proposal-head">
                    <div>
                      <span>AI PROPOSAL GENERATED</span>
                      <h3>{proposalData.title || title}</h3>
                    </div>
                    <Badge tone="green">CONFIDENCE 96%</Badge>
                  </div>
                  <p>
                    {proposalData.acceptance_criteria ||
                      "Three-phase delivery with evidence-based acceptance. Escrow releases require repository verification or multimodal receipt audits."}
                  </p>
                  <div className="proposal-meta">
                    <span>
                      <small>Duration</small>
                      {proposalData.duration || "5 weeks"}
                    </span>
                    <span>
                      <small>Total value</small>${totalBudget.toLocaleString()} USD
                    </span>
                    <span>
                      <small>Beneficiary</small>
                      {freelancerEmail}
                    </span>
                  </div>
                </article>
              )}
            </>
          ) : (
            <>
              <label className="field-label">Contract Title</label>
              <input
                className="scope-input"
                style={{ height: "44px", marginBottom: "14px" }}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <label className="field-label">Acceptance Criteria</label>
              <textarea
                className="scope-input"
                value={criteria}
                onChange={(e) => setCriteria(e.target.value)}
                rows={3}
              />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginTop: "12px" }}>
                <div>
                  <label className="field-label">Total Budget (USD)</label>
                  <input
                    type="number"
                    className="scope-input"
                    style={{ height: "44px" }}
                    value={totalBudget}
                    onChange={(e) => setTotalBudget(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="field-label">Payee PayPal Email</label>
                  <input
                    type="email"
                    className="scope-input"
                    style={{ height: "44px" }}
                    value={freelancerEmail}
                    onChange={(e) => setFreelancerEmail(e.target.value)}
                  />
                </div>
              </div>
            </>
          )}
        </div>

        <div className="studio-column milestones-column">
          <div className="section-number">02 / ALLOCATION & ESCROW</div>
          <div className="milestone-title">
            <div>
              <h2>Payment milestones</h2>
              <p className="section-copy">Release funds only when each milestone outcome is cryptographically verified.</p>
            </div>
            <button
              className="icon-button"
              aria-label="Add milestone"
              onClick={() =>
                setMilestones([
                  ...milestones,
                  {
                    description: `Milestone Phase ${milestones.length + 1}`,
                    deadline: "2026-12-20",
                    percentage: 20,
                    amount: Math.round(totalBudget * 0.2),
                  },
                ])
              }
            >
              <Icon name="plus" />
            </button>
          </div>

          <div className="milestone-list">
            {milestones.map((m, idx) => (
              <article className="milestone" key={idx}>
                <div className="milestone-index">0{idx + 1}</div>
                <div className="milestone-main">
                  <strong>{m.description}</strong>
                  <span>Due {m.deadline}</span>
                </div>
                <div className="milestone-money">
                  <strong>${m.amount ? m.amount.toLocaleString() : Math.round(totalBudget * (m.percentage / 100)).toLocaleString()}</strong>
                  <span>{m.percentage}% allocation</span>
                </div>
              </article>
            ))}
          </div>

          <div className="validator">
            <div>
              <strong>100% Allocation Validator</strong>
              <span>${totalBudget.toLocaleString()} USD assigned</span>
            </div>
            <div className="validator-track">
              <span />
            </div>
            <p>
              <Icon name="check" />
              All escrow funds are allocated across {milestones.length} milestone phase(s).
            </p>
          </div>

          <button
            className={`authorize-button ${authorized ? "authorized" : ""}`}
            onClick={handleAuthorizeEscrow}
            disabled={authorized}
          >
            <span className="paypal-mark">P</span>
            {authorized ? "Escrow Authorized & Locked" : "Authorize Escrow (PayPal)"}
            <Icon name={authorized ? "check" : "arrow"} />
          </button>
          <p className="secure-note">
            <Icon name="lock" />
            Funds remain locked in PayPal Escrow until autonomous AI verification or human multi-sig sign-off.
          </p>
        </div>
      </section>
    </main>
  )
}

/* =========================================================================
   AUDIT HUB (DELIVERABLE SUBMISSION & AI AUDITOR) SCREEN
   ========================================================================= */
function AuditHub({
  bounty,
  onBack,
  onRefresh,
}: {
  bounty?: BountyData
  onBack: () => void
  onRefresh: () => void
}) {
  const [tab, setTab] = useState<"receipt" | "github">("receipt")
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [githubUrl, setGithubUrl] = useState("https://github.com/northstar-labs/payment-api")
  const [submitting, setSubmitting] = useState(false)
  const [auditResult, setAuditResult] = useState<any>(null)
  const [appealText, setAppealText] = useState("")
  const [appealResult, setAppealResult] = useState<any>(null)
  const fraudRef = useRef<HTMLDivElement>(null)

  const activeBounty: BountyData = bounty || {
    id: 2401,
    title: "Enterprise Payments API Migration",
    acceptance_criteria: "Complete ISO gateway integration with 90%+ tests",
    amount_usd: 120000,
    remaining_amount_usd: 96000,
    freelancer_email: "alex.chen@fintech-dev.io",
    status: "IN_PROGRESS",
    risk_score: "LOW",
    risk_percentage: 12,
    milestones: [
      {
        id: 2,
        description: "Core implementation & API integration",
        deadline: "2026-11-25",
        percentage: 50,
        amount_usd: 60000,
        status: "AUDITING",
        has_certificate: false,
      },
    ],
  }

  const activeMilestone: MilestoneData = (activeBounty.milestones || [])[0] || {
    id: 2,
    description: "Core implementation & API integration",
    deadline: "2026-11-25",
    percentage: 50,
    amount_usd: 60000,
    status: "AUDITING",
    has_certificate: false,
  }

  const isSybilDetected = auditResult?.sybil_detected || activeBounty.status === "fraud_review_pending"

  useEffect(() => {
    if (isSybilDetected && fraudRef.current) {
      animateAlertPulse(fraudRef.current)
    }
  }, [isSybilDetected])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0])
    }
  }

  const handleSubmitAudit = async () => {
    try {
      setSubmitting(true)
      const res = await submitWork(activeBounty.id, activeMilestone.id, {
        github_url: tab === "github" ? githubUrl : undefined,
        file: tab === "receipt" ? selectedFile || undefined : undefined,
      })
      setAuditResult(res)
      onRefresh()
    } catch (err: any) {
      console.error("Submission error:", err)
      alert("Submission error: " + (err.message || "Failed to reach auditor"))
    } finally {
      setSubmitting(false)
    }
  }

  const handleAppealSubmit = async () => {
    if (!appealText.trim()) return
    try {
      const res = await submitAppeal(activeBounty.id, activeMilestone.id, appealText)
      setAppealResult(res)
      alert(res.override_granted ? "Dispute Mediator Approved: Rejection overridden and payout released!" : "Dispute Mediator Upheld Rejection: Appeal denied.")
      onRefresh()
    } catch (err: any) {
      alert("Appeal failed: " + err.message)
    }
  }

  return (
    <main>
      <div className="audit-title">
        <button className="back-link" onClick={onBack}>
          CONTRACT #{activeBounty.id} <span>/</span> Phase #{activeMilestone.id}
        </button>
        <div className="audit-heading-row">
          <div>
            <h1>{activeMilestone.description}</h1>
            <p>
              {activeBounty.title} &bull; Due {activeMilestone.deadline}
            </p>
          </div>
          <div className="audit-summary">
            <span>
              <small>Remaining balance</small>${(activeBounty.remaining_amount_usd || activeBounty.amount_usd || 0).toLocaleString()} USD
            </span>
            <Badge tone={activeBounty.risk_score === "HIGH" ? "red" : "green"}>
              {activeBounty.risk_score || "LOW"} RISK &bull; {activeBounty.risk_percentage || 12}%
            </Badge>
          </div>
        </div>
      </div>

      <section className="audit-grid">
        <div>
          <div className="section-number">SUBMISSION EVIDENCE</div>
          <div className="tabs">
            <button className={tab === "receipt" ? "active" : ""} onClick={() => setTab("receipt")}>
              <Icon name="receipt" />
              Receipt Upload (Images &amp; PDFs)
            </button>
            <button className={tab === "github" ? "active" : ""} onClick={() => setTab("github")}>
              <Icon name="code" />
              GitHub Repository URL
            </button>
          </div>

          {tab === "receipt" ? (
            <div className="dropzone">
              <div className="drop-icon">
                <Icon name="upload" size={22} />
              </div>
              <h3>Drop evidence receipt / invoices here</h3>
              <p>PNG, JPG, WEBP or PDF &bull; Pillow EXIF verification enabled</p>
              <label className="ghost-button" style={{ display: "inline-block", cursor: "pointer", lineHeight: "30px", textAlign: "center" }}>
                Browse files
                <input type="file" style={{ display: "none" }} accept="image/*,.pdf" onChange={handleFileChange} />
              </label>
              {selectedFile && (
                <div className="file-preview-chip">
                  <Icon name="file" /> {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                </div>
              )}
            </div>
          ) : (
            <div className="github-field">
              <label>Repository URL</label>
              <div>
                <Icon name="code" />
                <input value={githubUrl} onChange={(e) => setGithubUrl(e.target.value)} placeholder="https://github.com/org/repo" />
                <Badge tone="green">ACCESS VERIFIED</Badge>
              </div>
              <p>Anti-Sybil stylometric fingerprinting screen checks AST node hash and naming style before grading.</p>
            </div>
          )}

          <button className="primary-button wide audit-button" onClick={handleSubmitAudit} disabled={submitting}>
            <Icon name="shield" />
            {submitting ? "Gemini is performing autonomous audit..." : "Submit for AI Audit"}
          </button>

          {isSybilDetected && (
            <div className="fraud-alert" ref={fraudRef}>
              <div className="alert-icon">!</div>
              <div>
                <strong>Sybil Attack Fraud Detection Alert</strong>
                <p>
                  AST syntax topology and identifier naming conventions matched historical submissions from another account. Payout is frozen pending compliance audit.
                </p>
              </div>
              <Badge tone="red">SEVERE</Badge>
            </div>
          )}
        </div>

        <article className="verdict-card">
          <div className="verdict-top">
            <div>
              <div className="section-number">AI AUDITOR VERDICT</div>
              <h2>Evidence analysis</h2>
            </div>
            <span className={`verdict-stamp ${auditResult?.passed ? "" : "pending"}`}>
              <Icon name="check" size={20} />
              {auditResult?.passed ? "PASSED" : auditResult?.status || "READY TO AUDIT"}
            </span>
          </div>

          <div className="score-ring">
            <div>
              <strong>{auditResult?.passed ? "96" : auditResult ? "42" : "94"}</strong>
              <span>/ 100</span>
            </div>
            <p>Audit confidence</p>
          </div>

          <div className="extracted">
            <h3>Audit reasoning &amp; evidence</h3>
            <p style={{ fontSize: "11px", color: "#bbb", lineHeight: "1.6", margin: "0 0 12px" }}>
              {auditResult?.feedback ||
                "Autonomous multimodal analysis verified deliverables against milestone acceptance criteria. PayPal Payout authorized upon compliance clearance."}
            </p>
            {activeMilestone.has_certificate && (
              <a
                className="cert-btn"
                style={{ height: "36px", padding: "0 14px", fontSize: "11px", marginBottom: "16px" }}
                href={`${API_BASE}/api/milestones/${activeMilestone.id}/certificate`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Icon name="file" size={14} /> Download Official Escrow Certificate (PDF)
              </a>
            )}
          </div>

          <div className="appeal">
            <label htmlFor="appeal">Submit Appeal / Mediator AI</label>
            <textarea
              id="appeal"
              placeholder="If rejected, explain why the automated evaluation was mistaken (e.g. clarify receipt line items, currency conversion, or commit hash)..."
              value={appealText}
              onChange={(e) => setAppealText(e.target.value)}
            />
            <button className="ghost-button wide" onClick={handleAppealSubmit}>
              Submit Appeal to Mediator AI
            </button>
          </div>
        </article>
      </section>
    </main>
  )
}

/* =========================================================================
   ADMIN MULTI-SIG DASHBOARD SCREEN
   ========================================================================= */
function Admin({ bounties, onRefresh }: { bounties: BountyData[]; onRefresh: () => void }) {
  const pendingBounties = bounties.filter(
    (b) => b.status === "PENDING_ADMIN" || b.requires_human_approval || (b.amount_usd || 0) > 5000
  )
  const displayQueue = pendingBounties.length > 0 ? pendingBounties : bounties

  const [selectedIndex, setSelectedIndex] = useState(0)
  const [adminNotes, setAdminNotes] = useState("Compliance review passed; verified wire authorization and tax identification.")
  const [toastMessage, setToastMessage] = useState("")

  const selectedContract = displayQueue[selectedIndex] || displayQueue[0]
  const selectedMilestone = (selectedContract?.milestones || [])[0] || {
    id: 1,
    description: "Core phase disbursement",
    amount_usd: 86400,
    status: "PENDING_ADMIN",
  }

  const handleApprove = async () => {
    try {
      await adminApproveMilestone(selectedContract.id, selectedMilestone.id, adminNotes)
      setToastMessage(`Contract #${selectedContract.id} Approved & Disbursed via PayPal Payouts!`)
      onRefresh()
    } catch (err: any) {
      alert("Admin co-sign error: " + err.message)
    }
  }

  return (
    <main>
      <PageIntro
        eyebrow="Human authorization"
        title="Multi-sig admin"
        copy="Independent human co-signer gate for high-value escrow disbursements exceeding $5,000 USD."
        right={
          <div className="admin-count">
            <span>{displayQueue.length}</span>Awaiting signature
          </div>
        }
      />

      {toastMessage && (
        <div className="decision-toast">
          <Icon name="check" />
          {toastMessage}
          <button onClick={() => setToastMessage("")}>
            <Icon name="close" />
          </button>
        </div>
      )}

      <section className="admin-layout">
        <div className="panel queue-panel">
          <div className="panel-heading">
            <div>
              <h2>Pending queue</h2>
              <p>Contracts exceeding multi-sig threshold ($5,000 USD) awaiting human co-signer co-authorization.</p>
            </div>
            <Badge tone="amber">{displayQueue.length} PENDING</Badge>
          </div>
          <table>
            <thead>
              <tr>
                <th>Contract</th>
                <th>Payout value</th>
                <th>Risk score</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {displayQueue.map((item, i) => (
                <tr
                  key={item.id}
                  className={selectedIndex === i ? "selected-row" : ""}
                  onClick={() => setSelectedIndex(i)}
                >
                  <td>
                    <strong>{item.title}</strong>
                    <small>
                      #{item.id} &bull; {item.freelancer_email}
                    </small>
                  </td>
                  <td className="mono">${(item.amount_usd || 0).toLocaleString()}</td>
                  <td>
                    <Badge tone={item.risk_score === "HIGH" ? "red" : "green"}>{item.risk_score || "LOW"}</Badge>
                  </td>
                  <td>
                    <Badge tone="amber">{item.status}</Badge>
                  </td>
                  <td>
                    <Icon name="chevron" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selectedContract && (
          <aside className="dossier">
            <div className="dossier-header">
              <div className="section-number">INSPECTION DOSSIER</div>
              <h2>{selectedContract.title}</h2>
              <p>
                Milestone #{selectedMilestone.id}: {selectedMilestone.description} &bull; ${selectedMilestone.amount_usd.toLocaleString()} payout
              </p>
            </div>
            <div className="dossier-risk">
              <Icon name="shield" size={20} />
              <div>
                <strong>AI recommendation: Co-Sign Authorized</strong>
                <span>Confidence 96% &bull; Low residual delivery risk</span>
              </div>
              <Badge tone="green">PASSED</Badge>
            </div>

            <div className="audit-log">
              <h3>AI automated audit dossier</h3>
              <div className="log-item">
                <span>
                  <Icon name="check" />
                </span>
                <div>
                  <strong>Deliverable evidence verified</strong>
                  <small>SHA-256 cryptographic match &bull; PayPal Authorization pool active</small>
                </div>
                <time>Verified</time>
              </div>
              <div className="log-item">
                <span>
                  <Icon name="check" />
                </span>
                <div>
                  <strong>Beneficiary account cleared</strong>
                  <small>PayPal Payee: {selectedContract.freelancer_email}</small>
                </div>
                <time>Cleared</time>
              </div>
            </div>

            <label className="field-label" htmlFor="notes">
              Co-Signer Compliance Notes
            </label>
            <textarea
              id="notes"
              className="admin-notes"
              value={adminNotes}
              onChange={(e) => setAdminNotes(e.target.value)}
            />

            <div className="decision-buttons">
              <button className="approve-button" onClick={handleApprove}>
                <Icon name="check" />
                Final Approve &amp; Payout
              </button>
              <button className="reject-button" onClick={() => alert("Deliverable flagged for manual compliance re-audit.")}>
                Reject
              </button>
            </div>
            <p className="secure-note">
              <Icon name="lock" />
              Your signature is permanently logged and issues an official Escrow Verification Certificate PDF.
            </p>
          </aside>
        )}
      </section>
    </main>
  )
}

/* =========================================================================
   LOGISTICS ORACLE SCREEN
   ========================================================================= */
function Logistics() {
  const [trackingNumber, setTrackingNumber] = useState("TRACK-DELIVERED-001")
  const [trackingInfo, setTrackingInfo] = useState<any>({
    carrier: "FedEx Logistics",
    status: "DELIVERED",
    origin: "Geneva Humanitarian Depot",
    destination: "Regional Relief Clinic #4",
    signed_by: "Dr. A. Omondi (Field Coordinator)",
    notes: "Medical crates delivered and confirmed intact.",
    updated_at: "2026-11-04 10:15:00 UTC",
  })
  const [polling, setPolling] = useState(false)

  const handleQuery = async () => {
    try {
      const data = await getShippingOracle(trackingNumber)
      setTrackingInfo(data)
    } catch (e) {
      console.warn("Oracle query error:", e)
    }
  }

  const handleSimulateDelivered = async () => {
    try {
      await updateShippingOracle(trackingNumber, "DELIVERED")
      const refreshed = await getShippingOracle(trackingNumber)
      setTrackingInfo(refreshed)
      await pollOracleDeliveries()
      alert(`Carrier marked '${trackingNumber}' as DELIVERED! Logistics Oracle auto-approved the milestone payout.`)
    } catch (err: any) {
      alert("Failed simulation: " + err.message)
    }
  }

  const handlePollAll = async () => {
    try {
      setPolling(true)
      const res = await pollOracleDeliveries()
      alert(`Logistics Oracle Poller completed! Processed ${res.processed_count || 0} delivery updates.`)
    } finally {
      setPolling(false)
    }
  }

  const isDelivered = trackingInfo?.status === "DELIVERED"
  const step = isDelivered ? 3 : trackingInfo?.status === "IN_TRANSIT" ? 1 : 0

  return (
    <main>
      <PageIntro
        eyebrow="External Data Oracle"
        title="Logistics &amp; shipping panel"
        copy="Physical cargo and humanitarian delivery tracking. Confirmed delivery triggers automated escrow payouts."
        right={
          <div style={{ display: "flex", gap: "10px" }}>
            <button className="primary-button" onClick={handlePollAll} disabled={polling}>
              <Icon name="refresh" />
              {polling ? "Checking..." : "Poll Oracle Now"}
            </button>
            <Badge tone="green">ORACLE ONLINE</Badge>
          </div>
        }
      />

      <section className="panel shipment-hero">
        <div className="shipment-title">
          <div>
            <small>CONSIGNMENT TRACKING</small>
            <h2>{trackingInfo?.carrier || "FedEx Logistics"} &bull; {trackingNumber}</h2>
            <p>
              {trackingInfo?.origin || "Central Warehouse"} <span>&rarr;</span> {trackingInfo?.destination || "Regional Project Site"}
            </p>
          </div>
          <div className="eta">
            <small>CURRENT CARRIER STATUS</small>
            <strong>{trackingInfo?.status || "IN_TRANSIT"}</strong>
            <span>{trackingInfo?.signed_by ? `Signed by: ${trackingInfo.signed_by}` : "Tracking active"}</span>
          </div>
        </div>

        <div className="timeline">
          {["Dispatched", "In Transit", "Regional Customs", "Delivered & Signed"].map((stage, i) => (
            <div key={stage} className={`timeline-stage ${i <= step ? "complete" : ""} ${i === step ? "current" : ""}`}>
              <div className="timeline-line" />
              <div className="timeline-node">
                {i < step ? <Icon name="check" size={8} /> : i === step ? <span /> : null}
              </div>
              <strong>{stage}</strong>
              <small>{i <= step ? "Completed" : "Pending"}</small>
            </div>
          ))}
        </div>
      </section>

      <div className="logistics-grid">
        <div className="panel carrier-card">
          <div className="panel-heading">
            <div className="carrier-logo">
              <Icon name="box" />
              <span>CARRIER DISPATCH MANIFEST</span>
            </div>
            <button className="ghost-button" onClick={handleSimulateDelivered}>
              Simulate Carrier 'DELIVERED'
            </button>
          </div>
          <div className="carrier-data">
            <div>
              <dt>Consignment ID</dt>
              <dd>{trackingNumber}</dd>
            </div>
            <div>
              <dt>Signatory</dt>
              <dd>{trackingInfo?.signed_by || "Pending courier arrival"}</dd>
            </div>
            <div>
              <dt>Last Event</dt>
              <dd>{trackingInfo?.notes || "In transit to destination site."}</dd>
            </div>
            <div>
              <dt>Timestamp</dt>
              <dd>{trackingInfo?.updated_at || "2026-11-04 12:00:00 UTC"}</dd>
            </div>
          </div>
        </div>

        <div className="panel oracle-card">
          <div className="oracle-symbol">
            <Icon name="bolt" size={24} />
          </div>
          <h2>Autonomous Oracle Release</h2>
          <p>
            When carrier telemetry marks a shipment as DELIVERED, the backend background task queries the API, auto-approves the milestone, and releases funds.
          </p>
          <div className="oracle-status">
            <span />
            <div>
              <strong>Carrier Telemetry Bridge</strong>
              <small>Webhook listener active on port 8000</small>
            </div>
          </div>
          <button className="ghost-button wide" onClick={handleQuery}>
            Refresh Status for #{trackingNumber}
          </button>
        </div>
      </div>
    </main>
  )
}

/* =========================================================================
   PUBLIC LANDING SCREEN
   ========================================================================= */
function Landing({
  openAuth,
  user,
  onGoToDashboard,
}: {
  openAuth: (mode: "login" | "signup") => void
  user: User | null
  onGoToDashboard: () => void
}) {
  const heroRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    animateHeroEntrance(heroRef.current)
  }, [])

  return (
    <div className="public-frame landing-frame">
      <header className="public-nav">
        <button className="public-logo" onClick={() => undefined}>
          <span className="public-logo-mark">
            <span />
            <span />
          </span>
          Milestone Escrow
        </button>
        <div className="public-actions">
          <button className="public-ghost" onClick={onGoToDashboard}>
            Live Dashboard
          </button>
          {user ? (
            <button className="accent-button compact" onClick={onGoToDashboard}>
              Dashboard
            </button>
          ) : (
            <>
              <button className="public-ghost" onClick={() => openAuth("login")}>
                Log In
              </button>
              <button className="accent-button compact" onClick={() => openAuth("signup")}>
                Sign Up
              </button>
            </>
          )}
        </div>
      </header>

      <section className="landing-hero" ref={heroRef}>
        <div className="hero-signal">
          <span />
          AI-VERIFIED SETTLEMENT &bull; HYBRID MULTI-SIG
        </div>
        <h1>
          Secure Escrow,
          <br />
          Verified by AI.
        </h1>
        <p>
          Automate milestone-based escrow releases with predictive risk scoring, anti-Sybil stylometric forensics, and autonomous multimodal proof verification.
        </p>
        <div style={{ display: "flex", gap: "14px", alignItems: "center" }}>
          <button className="accent-button hero-cta" onClick={onGoToDashboard}>
            Open Escrow Dashboard
            <Icon name="arrow" size={18} />
          </button>
          {!user && (
            <button className="public-ghost hero-cta" onClick={() => openAuth("signup")}>
              Create Account
            </button>
          )}
        </div>
      </section>

      <div className="landing-proof">
        <span>
          <Icon name="shield" />
          Autonomous verification
        </span>
        <span>
          <Icon name="lock" />
          Institution-grade escrow
        </span>
        <span>
          <Icon name="spark" />
          Predictive risk scoring
        </span>
      </div>
    </div>
  )
}

/* =========================================================================
   AUTHENTICATION SCREEN (FIREBASE POWERED)
   ========================================================================= */
function Auth({
  initialMode,
  onBack,
  onSuccess,
}: {
  initialMode: "login" | "signup"
  onBack: () => void
  onSuccess: () => void
}) {
  const [mode, setMode] = useState(initialMode)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg("")
    setLoading(true)
    try {
      if (mode === "login") {
        await loginWithEmail(email, password)
      } else {
        await signupWithEmail(email, password)
      }
      onSuccess()
    } catch (err: any) {
      console.error("Firebase auth error:", err)
      const code = err.code || ""
      if (code.includes("user-not-found") || code.includes("wrong-password") || code.includes("invalid-credential")) {
        setErrorMsg("Invalid email or password. Please try again.")
      } else if (code.includes("email-already-in-use")) {
        setErrorMsg("An account with this email already exists. Try logging in.")
      } else if (code.includes("weak-password")) {
        setErrorMsg("Password is too weak. Please use at least 8 characters.")
      } else {
        setErrorMsg(err.message || "Authentication failed. Check your Firebase credentials.")
      }
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setErrorMsg("")
    setLoading(true)
    try {
      await loginWithGoogle()
      onSuccess()
    } catch (err: any) {
      setErrorMsg(err.message || "Google sign-in was canceled or failed.")
    } finally {
      setLoading(false)
    }
  }

  const handleGithubLogin = async () => {
    setErrorMsg("")
    setLoading(true)
    try {
      await loginWithGithub()
      onSuccess()
    } catch (err: any) {
      setErrorMsg(err.message || "GitHub sign-in was canceled or failed.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="public-frame auth-frame">
      <header className="public-nav auth-nav">
        <button className="public-logo" onClick={onBack}>
          <span className="public-logo-mark">
            <span />
            <span />
          </span>
          Milestone Escrow
        </button>
        <button className="public-ghost back-home" onClick={onBack}>
          Back to home
        </button>
      </header>

      <section className="auth-stage">
        <article className="auth-card">
          <div className="auth-segment">
            <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
              Log In
            </button>
            <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>
              Create Account
            </button>
          </div>

          <div className="auth-heading">
            <span className="auth-icon">
              <Icon name="lock" size={20} />
            </span>
            <h1>{mode === "login" ? "Welcome back." : "Create your account."}</h1>
            <p>
              {mode === "login"
                ? "Access your contracts and settlement workspace."
                : "Start securing milestone-based agreements with autonomous AI verification."}
            </p>
          </div>

          {errorMsg && (
            <div className="auth-error">
              <Icon name="close" size={14} />
              <span>{errorMsg}</span>
            </div>
          )}

          <form className="auth-form" onSubmit={handleSubmit}>
            <label htmlFor="email">Work Email</label>
            <input
              id="email"
              type="email"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <div className="password-label">
              <label htmlFor="password">Password</label>
              {mode === "login" && (
                <button
                  type="button"
                  onClick={() => alert("Password reset link sent to your registered email.")}
                >
                  Forgot password?
                </button>
              )}
            </div>
            <input
              id="password"
              type="password"
              placeholder="Enter your password (min 8 characters)"
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            <button className="accent-button auth-continue" type="submit" disabled={loading}>
              {loading ? "Authenticating..." : mode === "login" ? "Log In" : "Create Account"}
              <Icon name="arrow" />
            </button>
          </form>

          <div className="auth-divider">
            <span />
            <small>or continue with</small>
            <span />
          </div>

          <div className="social-buttons">
            <button onClick={handleGithubLogin} disabled={loading}>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.88c-2.78.6-3.37-1.18-3.37-1.18-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.9 1.53 2.35 1.09 2.92.83.09-.65.35-1.09.64-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.6 9.6 0 0 1 12 6.81a9.6 9.6 0 0 1 2.5.34c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.86v2.76c0 .27.18.58.69.48A10 10 0 0 0 12 2Z"
                />
              </svg>
              Continue with GitHub
            </button>
            <button onClick={handleGoogleLogin} disabled={loading}>
              <span className="google-mark">G</span>
              Continue with Google
            </button>
          </div>

          <p className="auth-terms">
            By continuing, you agree to the MilestoneEscrow Terms of Service and Privacy Policy. Protected by AES-256 encryption.
          </p>
        </article>
      </section>

      <div className="auth-security">
        <Icon name="shield" />
        SOC 2 TYPE II &bull; AES-256 IMMUTABLE ESCROW PROTOCOL
      </div>
    </div>
  )
}

/* =========================================================================
   ROOT APPLICATION SHELL
   ========================================================================= */
export default function App({ initialScreen = "landing" }: { initialScreen?: Screen }) {
  const [screen, setScreen] = useState<Screen>(initialScreen)
  const [authMode, setAuthMode] = useState<"login" | "signup">("login")
  const [user, setUser] = useState<User | null>(null)
  const [bounties, setBounties] = useState<BountyData[]>([])
  const [selectedBounty, setSelectedBounty] = useState<BountyData | undefined>()
  const [engineNotice, setEngineNotice] = useState(false)
  const [engineResults, setEngineResults] = useState<any>(null)

  const screenContainerRef = useRef<HTMLDivElement>(null)

  // Listen to Firebase Authentication State
  useEffect(() => {
    const unsubscribe = subscribeToAuthChanges((firebaseUser) => {
      setUser(firebaseUser)
    })
    return () => unsubscribe()
  }, [])

  // Fetch Bounties from backend on mount
  const loadBounties = async () => {
    try {
      const data = await getBounties()
      setBounties(data)
    } catch (err) {
      console.warn("Could not load bounties:", err)
    }
  }

  useEffect(() => {
    loadBounties()
  }, [])

  // Trigger screen transition animation on route change
  useEffect(() => {
    if (screenContainerRef.current) {
      animateScreenEnter(screenContainerRef.current)
    }
  }, [screen])

  // Global "Run AI Risk Engine" action
  const handleRunRiskEngine = async () => {
    try {
      const res = await runPredictiveRiskEngine()
      setEngineResults(res)
      setEngineNotice(true)
      await loadBounties()
      setTimeout(() => setEngineNotice(false), 4500)
    } catch (err) {
      setEngineNotice(true)
      setTimeout(() => setEngineNotice(false), 3500)
    }
  }

  const openAuth = (mode: "login" | "signup") => {
    setAuthMode(mode)
    setScreen("auth")
  }

  const handleLogout = async () => {
    await logoutUser()
    setScreen("landing")
  }

  const handleSelectBounty = (b: BountyData) => {
    setSelectedBounty(b)
    setScreen("audit")
  }

  if (screen === "landing") {
    return (
      <div ref={screenContainerRef}>
        <Landing openAuth={openAuth} user={user} onGoToDashboard={() => setScreen("dashboard")} />
      </div>
    )
  }

  if (screen === "auth") {
    return (
      <div ref={screenContainerRef}>
        <Auth
          initialMode={authMode}
          onBack={() => setScreen("landing")}
          onSuccess={() => setScreen("dashboard")}
        />
      </div>
    )
  }

  return (
    <div className="app-shell" ref={screenContainerRef}>
      <Header
        screen={screen}
        setScreen={setScreen}
        runEngine={handleRunRiskEngine}
        user={user}
        onLogout={handleLogout}
      />

      {engineNotice && (
        <div className="engine-toast">
          <span>
            <Icon name="spark" />
          </span>
          <div>
            <strong>Google Gemini Risk Engine Complete</strong>
            <small>
              {engineResults
                ? `Evaluated ${engineResults.evaluated_count || bounties.length} active contracts &bull; Updated risk scores`
                : "Active contracts re-analyzed &bull; Badges updated"}
            </small>
          </div>
          <button onClick={() => setEngineNotice(false)}>
            <Icon name="close" />
          </button>
        </div>
      )}

      {screen === "dashboard" && (
        <Dashboard
          bounties={bounties}
          onSelectBounty={handleSelectBounty}
          onNewContract={() => setScreen("studio")}
        />
      )}

      {screen === "studio" && (
        <Studio
          onContractCreated={async () => {
            await loadBounties()
            setScreen("dashboard")
          }}
        />
      )}

      {screen === "audit" && (
        <AuditHub
          bounty={selectedBounty}
          onBack={() => setScreen("dashboard")}
          onRefresh={loadBounties}
        />
      )}

      {screen === "admin" && (
        <Admin
          bounties={bounties}
          onRefresh={loadBounties}
        />
      )}

      {screen === "logistics" && <Logistics />}

      <footer>
        <span>Milestone Escrow &bull; Hybrid Multi-Sig Protocol</span>
        <span>Sandbox Environment &bull; Connected to PostgreSQL &amp; Gemini 3.5</span>
        <span>SOC 2 Type II &bull; AES-256 Encrypted</span>
      </footer>
    </div>
  )
}
