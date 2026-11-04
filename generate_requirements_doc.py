import os
import sys
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

sys.stdout.reconfigure(encoding="utf-8")


def set_cell_background(cell, hex_color: str):
    """Sets background fill color of a table cell."""
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets inner cell padding in twips (1 pt = 20 twips)."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def add_callout_box(doc, text: str, title: str = "IMPORTANT ARCHITECTURE NOTE", border_color="2563EB", bg_color="F8FAFC"):
    """Adds a stylish callout alert block."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    
    cell = tbl.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)

    # Set left border thick, others none
    tcPr = cell._element.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    run_t = p.add_run(f"[{title}]\n")
    run_t.bold = True
    run_t.font.size = Pt(9.5)
    run_t.font.color.rgb = RGBColor.from_string(border_color)

    run_b = p.add_run(text)
    run_b.font.size = Pt(9.5)
    run_b.font.color.rgb = RGBColor(51, 65, 85)

    doc.add_paragraph()  # Spacing after callout


def build_word_document():
    doc = Document()

    # Page Margins (1 inch all around)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Palette
    COLOR_PRIMARY = RGBColor(15, 23, 42)      # Slate 900
    COLOR_SECONDARY = RGBColor(37, 99, 235)   # Blue 600
    COLOR_MUTED = RGBColor(100, 116, 139)     # Slate 500
    COLOR_DARK = RGBColor(30, 41, 59)         # Slate 800

    # Document Header / Title
    p_pre = doc.add_paragraph()
    p_pre.paragraph_format.space_before = Pt(0)
    p_pre.paragraph_format.space_after = Pt(2)
    run_pre = p_pre.add_run("MILESTONE ESCROW & HYBRID MULTI-SIG PLATFORM")
    run_pre.font.name = "Arial"
    run_pre.font.size = Pt(10)
    run_pre.bold = True
    run_pre.font.color.rgb = COLOR_SECONDARY

    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(2)
    p_title.paragraph_format.space_after = Pt(6)
    run_title = p_title.add_run("Frontend Architecture & UI Requirements Specification")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(22)
    run_title.bold = True
    run_title.font.color.rgb = COLOR_PRIMARY

    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(16)
    run_meta = p_meta.add_run(
        "System Version: 2.5 Enterprise Security & Analytics Edition  |  Document Status: Approved Architecture Specification  |  Target: Next.js Frontend & FastAPI Microservice"
    )
    run_meta.font.name = "Arial"
    run_meta.font.size = Pt(9)
    run_meta.italic = True
    run_meta.font.color.rgb = COLOR_MUTED

    # Divider line
    p_hr = doc.add_paragraph()
    p_hr.paragraph_format.space_after = Pt(14)
    run_hr = p_hr.add_run("―" * 58)
    run_hr.font.color.rgb = RGBColor(226, 232, 240)

    # -------------------------------------------------------------
    # SECTION 1: EXECUTIVE SUMMARY & USER ROLES
    # -------------------------------------------------------------
    h1 = doc.add_heading(level=1)
    run_h1 = h1.add_run("1. Platform Architecture & User Roles Overview")
    run_h1.font.name = "Arial"
    run_h1.font.size = Pt(15)
    run_h1.bold = True
    run_h1.font.color.rgb = COLOR_PRIMARY
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(6)

    p1 = doc.add_paragraph(
        "MilestoneEscrow is an enterprise-grade phased escrow platform built with Next.js (App Router), "
        "FastAPI, PostgreSQL, and Google Gemini AI. The platform enforces algorithmic milestone release, "
        "multi-sponsor authorization pooling, autonomous AI multimodal audits (both digital codebases and "
        "real-world physical receipts), anti-Sybil stylometric code forensics, predictive delivery risk scoring, "
        "and hybrid multi-signature governance."
    )
    p1.paragraph_format.line_spacing = 1.15
    p1.paragraph_format.space_after = Pt(8)

    doc.add_paragraph(
        "The frontend accommodates four primary participant personas and autonomous agents:",
        style="Normal"
    ).paragraph_format.space_after = Pt(4)

    roles = [
        ("The Client / Sponsor", "Creates single or multi-phase escrow bounties, funds contracts by authorizing payments via PayPal, tracks real-time milestone delivery progress, and receives automated compliance receipts."),
        ("The Freelancer / Beneficiary / Field Worker", "Reviews contract deliverables, negotiates scope and budget using an AI Mediator, submits code (GitHub repos) or physical proofs (invoices/receipts), files formal appeals on rejections, and downloads verified settlement certificates."),
        ("The Multi-Sig Compliance Administrator", "Acts as the human co-signer for high-value contracts (exceeding $5,000 USD). Reviews Gemini's autonomous audit dossier and executes final payout authorization."),
        ("Autonomous AI Agents (Gemini Engine)", "The Autonomous QA Auditor (code execution & multimodal vision), Anti-Sybil Stylometric Sentry (AST syntax topology & naming habits), Scope Negotiator, Mediator AI (dispute arbitration), and Predictive Risk Engine.")
    ]

    for role_name, role_desc in roles:
        p_role = doc.add_paragraph(style="List Bullet")
        p_role.paragraph_format.space_after = Pt(3)
        r_title = p_role.add_run(f"{role_name}: ")
        r_title.bold = True
        r_title.font.color.rgb = COLOR_DARK
        r_desc = p_role.add_run(role_desc)
        r_desc.font.color.rgb = COLOR_DARK

    add_callout_box(
        doc,
        "All visual components and buttons detailed in this specification are designed to be style-agnostic. "
        "They define the core functional requirements, user interactions, states, and API contracts necessary "
        "to ensure seamless integration with the backend.",
        title="SPECIFICATION GUIDELINE"
    )

    # -------------------------------------------------------------
    # SECTION 2: GLOBAL NAVIGATION & LAYOUT
    # -------------------------------------------------------------
    h2 = doc.add_heading(level=1)
    run_h2 = h2.add_run("2. Global Navigation & Layout Architecture")
    run_h2.font.name = "Arial"
    run_h2.font.size = Pt(15)
    run_h2.bold = True
    run_h2.font.color.rgb = COLOR_PRIMARY
    h2.paragraph_format.space_before = Pt(14)
    h2.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "The application provides a persistent top navigation shell present across all routes, "
        "delivering immediate situational awareness regarding escrow funds, network status, and analytics engines.",
        style="Normal"
    ).paragraph_format.space_after = Pt(6)

    nav_items = [
        ("Application Logo / Brand Header", "Clicking returns the user to the primary Dashboard (`/`). Displays brand name and active environment indicator."),
        ("Global Route Links", "Direct links to `Dashboard` (`/`), `Create Contract` (`/create`), and `Admin Multi-Sig` (`/admin`)."),
        ("Global 'Run AI Risk Engine' Action Button", "A prominent header button triggering `POST /api/analytics/predictive-risk/evaluate`. Initiates real-time delivery risk evaluation across all active contracts in the system, re-calculating risk scores and dynamically updating dashboard badges without requiring page reload."),
        ("PayPal Sandbox Status Pill", "Reflects active PayPal credentials, Client ID binding, and sandbox settlement readiness.")
    ]

    for item, desc in nav_items:
        p_item = doc.add_paragraph(style="List Bullet")
        p_item.paragraph_format.space_after = Pt(3)
        r_i = p_item.add_run(f"{item}: ")
        r_i.bold = True
        p_item.add_run(desc)

    # -------------------------------------------------------------
    # SECTION 3: SCREEN-BY-SCREEN REQUIREMENTS
    # -------------------------------------------------------------
    h3 = doc.add_heading(level=1)
    run_h3 = h3.add_run("3. Detailed Screen-by-Screen Functional Requirements")
    run_h3.font.name = "Arial"
    run_h3.font.size = Pt(15)
    run_h3.bold = True
    run_h3.font.color.rgb = COLOR_PRIMARY
    h3.paragraph_format.space_before = Pt(16)
    h3.paragraph_format.space_after = Pt(6)

    # Screen 1
    doc.add_heading("Screen 1: Client Dashboard & Contract Management (`/`)", level=2)
    doc.add_paragraph(
        "The primary landing screen offering high-level portfolio surveillance over all escrow agreements, "
        "milestone progress, remaining funds, predictive risk metrics, and automated compliance receipts."
    ).paragraph_format.space_after = Pt(4)

    s1_features = [
        ("Summary Portfolio Metric Cards", "Displays four aggregate tiles: (1) Total Value Locked in Escrow (USD), (2) Active Deliverables / Milestones in Progress, (3) Settled Disbursements to Freelancers, and (4) High-Risk Delivery Flags count."),
        ("Enterprise Contract Data Table (AG Grid / Interactive Grid)", "Displays all bounties returned by `GET /api/bounties`. Features sorting, full-text searching, and pagination."),
        ("Table Column - Contract ID & Title", "Displays contract number, title, and truncated scope description."),
        ("Table Column - Financial Balance", "Displays Total Contract Value alongside Remaining Locked Escrow Balance."),
        ("Table Column - Progress Stepper", "Visual progress bar showing completed milestones vs total milestones (e.g. 2 of 3 phases completed)."),
        ("Table Column - Multi-State Status Badge", "Renders distinct states: LOCKED (escrow funded), AUDITING (AI grading in progress), PENDING_ADMIN (AI approved but awaiting human co-signer co-authorization for > $5,000 contracts), fraud_review_pending (Sybil attack flagged), and COMPLETED."),
        ("Table Column - Predictive Risk Badge", "Interactive color-coded badge (LOW = Emerald, MEDIUM = Amber, HIGH = Pulsing Crimson). Shows risk probability percentage and opens a popover detailing Gemini's specific risk factors upon click or hover."),
        ("Table Column - Logistics Oracle Badge", "Displays real-time shipping status for physical deliverables: SHIPPED, IN_TRANSIT, or DELIVERED."),
        ("Action - 'View / Submit Deliverable' Button", "Primary action row button that routes directly to `/bounty/[id]/submit`."),
        ("Action - 'Download Receipt' Button", "Becomes active as soon as any milestone achieves COMPLETED status. Triggers `GET /api/milestones/{mid}/certificate` to download the official Escrow Verification Certificate PDF.")
    ]
    for feat, fdesc in s1_features:
        p_f = doc.add_paragraph(style="List Bullet")
        p_f.paragraph_format.space_after = Pt(3)
        r_f = p_f.add_run(f"{feat}: ")
        r_f.bold = True
        p_f.add_run(fdesc)

    # Screen 2
    doc.add_heading("Screen 2: Dual-Mode Contract Studio (`/create`)", level=2)
    doc.add_paragraph(
        "Allows project sponsors to structure phased contracts using either autonomous conversational AI "
        "or a granular manual builder."
    ).paragraph_format.space_after = Pt(4)

    s2_features = [
        ("Dual-Mode Segmented Control", "Allows instant toggling between 'Mode 1: Conversational AI Studio' and 'Mode 2: Detailed Manual Builder'."),
        ("Mode 1 - Natural Language Chat Input", "Textarea where users enter plain-English requirements (e.g. 'Pay $500 total: $100 on initial Figma mockups due next Friday, $400 on deployment due at the end of the month')."),
        ("Mode 1 - 'Generate Contract Scope' Button", "Calls `POST /api/bounties/generate-scope`. Prompts Gemini to parse the unstructured text into a strict milestone array and acceptance criteria."),
        ("Mode 1 - AI Proposal Preview Card", "Renders Gemini's structured response with extracted title, acceptance checklist, and breakdown table."),
        ("Mode 1 - 'Transfer to Builder' Button", "Transfers the AI's generated milestones into the manual builder for granular adjustments."),
        ("Mode 2 - Contract Details Inputs", "Title, Acceptance Criteria markdown editor, Total Budget (USD), Freelancer PayPal Email, optional Field-Worker WhatsApp Phone Number, and optional Carrier Tracking Number."),
        ("Mode 2 - Dynamic Milestone Card List", "Allows adding/removing milestone phases. Each phase captures: Description, Deadline datepicker, Percentage allocation slider/input, Calculated USD value, and individual carrier tracking number."),
        ("Mode 2 - 'Add Milestone Phase' Button", "Appends a new milestone row and dynamically recalculates percentage distribution."),
        ("Mode 2 - 'Delete Milestone' Button", "Removes the milestone row (safeguarded so at least 1 milestone remains)."),
        ("Mode 2 - Real-Time 100% Allocation Validator", "Progress bar that dynamically calculates total milestone percentages. Locks escrow submission until total equals exactly 100%."),
        ("Multi-Sponsor Pooling Section", "Accordion allowing multiple sponsor authorization slots to be pooled for a single milestone."),
        ("Integrated PayPal Escrow Funding Button", "PayPal JavaScript SDK button container. Authorizes (locks) the total contract amount in escrow without capturing funds immediately, saving order and authorization IDs to the backend.")
    ]
    for feat, fdesc in s2_features:
        p_f = doc.add_paragraph(style="List Bullet")
        p_f.paragraph_format.space_after = Pt(3)
        r_f = p_f.add_run(f"{feat}: ")
        r_f.bold = True
        p_f.add_run(fdesc)

    # Screen 3
    doc.add_heading("Screen 3: Work Submission, AI Auditor & Dispute Hub (`/bounty/[id]/submit`)", level=2)
    doc.add_paragraph(
        "The operational hub where freelancers submit deliverables, receive real-time autonomous AI evaluations, "
        "download compliance certificates, resolve disputes, or negotiate terms."
    ).paragraph_format.space_after = Pt(4)

    s3_features = [
        ("Header & Contract Overview", "Displays Contract Title, Client Email, Freelancer Target Email, Total Budget, Remaining Escrow Balance, and the Predictive Risk Badge."),
        ("Milestone Phase Selector", "Interactive tab bar / stepper allowing the user to select which specific milestone they are addressing."),
        ("Submission Mode Toggle", "Switches between 'Tab A: Receipt / Proof Upload (Images & PDFs)' and 'Tab B: GitHub Repository (Codebase)'."),
        ("Tab A - File Dropzone & EXIF Preview", "Accepts receipt and invoice files (JPG, PNG, WEBP, PDF). Automatically runs Pillow EXIF extraction on the backend to match the photograph's creation date against the milestone deadline."),
        ("Tab B - GitHub Repository URL Input", "Validates git URLs. Alerts user that AST syntax topology and variable naming habits will be screened for Sybil duplicate detection before automated tests are run."),
        ("Action - 'Submit Deliverable for AI Audit' Button", "Sends multipart form data or JSON payload to `POST /api/bounties/{id}/milestones/{mid}/submit-work`."),
        ("Sybil Attack Security Alert Banner", "Triggers if the backend detects identical AST structures from another freelancer account. Flags status as `fraud_review_pending`, freezes payout, and displays forensic evidence."),
        ("AI Auditor Verdict & Gemini Reasoning Card", "Renders the definitive decision (PASSED or REJECTED) along with Gemini's raw JSON audit explanation, acceptance criteria checklists, and extracted receipt data (vendor, itemized lines, total)."),
        ("Action - 'Download Official Certificate (PDF)' Button", "Appears upon approval. Calls `GET /api/milestones/{mid}/certificate` to download the ReportLab settlement certificate."),
        ("Dispute Resolution / Appeal Section", "Active only when a submission is REJECTED. Freelancer enters a text defense clarifying mistaken audit findings."),
        ("Action - 'Submit Appeal to Mediator AI' Button", "Calls `POST /api/bounties/{id}/milestones/{mid}/appeal`. Prompts the Mediator AI to arbitrate between the milestone criteria, auditor rejection notes, and freelancer defense to override or uphold the rejection."),
        ("Scope Negotiation Hub (Split-Screen Drawer)", "Opens when clicking 'Negotiate Terms'. Allows the freelancer to submit a counter-offer. Displays a side-by-side comparison of 'Original Terms' vs 'AI Proposed Compromise' with an 'Accept Compromise' button (`POST /api/bounties/{id}/accept-compromise`).")
    ]
    for feat, fdesc in s3_features:
        p_f = doc.add_paragraph(style="List Bullet")
        p_f.paragraph_format.space_after = Pt(3)
        r_f = p_f.add_run(f"{feat}: ")
        r_f.bold = True
        p_f.add_run(fdesc)

    # Screen 4
    doc.add_heading("Screen 4: Enterprise Multi-Sig Admin Dashboard (`/admin`)", level=2)
    doc.add_paragraph(
        "A restricted compliance dashboard enforcing the human co-signer approval gate for high-value payouts (> $5,000 USD)."
    ).paragraph_format.space_after = Pt(4)

    s4_features = [
        ("Multi-Sig Pending Queue Table", "Lists all deliverables with `PENDING_ADMIN` status. Shows Contract ID, Payee Email, Total Value, Milestone Amount, and AI Audit Pass confirmation."),
        ("Detailed Inspection Modal / Drawer", "Shows Gemini's full audit dossier, acceptance criteria verification logs, and the list of authorized sponsor PayPal IDs."),
        ("Admin Notes Textarea", "Allows the compliance administrator to document sign-off notes (e.g. 'Verified bank receipt against supplier order #402')."),
        ("Action - 'Final Approve & Execute Payout' Button", "Primary co-sign button. Calls `POST /api/admin/bounties/{id}/milestones/{mid}/approve`. Simultaneously captures all pooled sponsor authorization IDs, triggers PayPal Payouts to the freelancer, decrements remaining escrow funds, and issues the compliance certificate."),
        ("Action - 'Reject / Request Re-Audit' Button", "Overrides AI approval and reverts the deliverable for manual review.")
    ]
    for feat, fdesc in s4_features:
        p_f = doc.add_paragraph(style="List Bullet")
        p_f.paragraph_format.space_after = Pt(3)
        r_f = p_f.add_run(f"{feat}: ")
        r_f.bold = True
        p_f.add_run(fdesc)

    # Screen 5
    doc.add_heading("Screen 5: Physical Logistics & Oracle Tracking Panel", level=2)
    doc.add_paragraph(
        "A monitoring panel for physical deliverables (e.g. humanitarian shipments, water filtration hardware, medical kits)."
    ).paragraph_format.space_after = Pt(4)

    s5_features = [
        ("Carrier Milestone Timeline", "Step-by-step progress tracking: Dispatched -> In Transit -> Customs / Regional Depot -> Delivered & Signed."),
        ("Consignment Metadata Details", "Carrier name (FedEx, DHL, UPS), Origin, Destination, Tracking ID, and Recipient Signatory."),
        ("Action - 'Manual Submission Fallback' Button", "Remains active as a fail-safe so the field worker can upload physical delivery slips even if carrier tracking APIs fail."),
        ("Simulation Controls (For Demonstrations & Testing)", "Provides 'Simulate Carrier Update' (`POST /api/oracle/shipping/{trk}/status`) and 'Poll Logistics Oracle Now' (`POST /api/oracle/poll`) to immediately trigger auto-approval upon carrier delivery.")
    ]
    for feat, fdesc in s5_features:
        p_f = doc.add_paragraph(style="List Bullet")
        p_f.paragraph_format.space_after = Pt(3)
        r_f = p_f.add_run(f"{feat}: ")
        r_f.bold = True
        p_f.add_run(fdesc)

    # -------------------------------------------------------------
    # SECTION 4: MASTER BUTTONS & ACTIONS TABLE
    # -------------------------------------------------------------
    h4 = doc.add_heading(level=1)
    run_h4 = h4.add_run("4. Master Interactive Controls & API Endpoints Reference")
    run_h4.font.name = "Arial"
    run_h4.font.size = Pt(15)
    run_h4.bold = True
    run_h4.font.color.rgb = COLOR_PRIMARY
    h4.paragraph_format.space_before = Pt(16)
    h4.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "The following master reference table documents every button and interactive control required across the entire application, "
        "its associated API route, trigger payload, and expected behavior.",
        style="Normal"
    ).paragraph_format.space_after = Pt(8)

    table_data = [
        ("Screen / Component", "Button Label", "API Endpoint & Method", "Behavior & State Changes"),
        ("Global Header", "Run AI Risk Engine", "POST /api/analytics/predictive-risk/evaluate", "Recalculates predictive risk scores across all active contracts. Updates badges in real time."),
        ("Dashboard", "+ Create Bounty", "Client Navigation (/create)", "Navigates client to the contract creation studio."),
        ("Dashboard", "View / Submit Work", "Client Navigation (/submit)", "Navigates freelancer or client to the work submission and auditing hub."),
        ("Dashboard", "Download Receipt", "GET /api/milestones/{id}/certificate", "Downloads the ReportLab Escrow Verification Certificate PDF for any completed phase."),
        ("Dashboard", "Risk Badge Popover", "GET /api/bounties/{id}/risk", "Opens popover displaying Gemini's qualitative risk factors and action recommendations."),
        ("Create Studio", "Generate Scope", "POST /api/bounties/generate-scope", "Parses natural language prompt into structured milestones, criteria, and budgets."),
        ("Create Studio", "Transfer to Builder", "Client State Transfer", "Populates AI-generated milestones into manual editable form fields."),
        ("Create Studio", "+ Add Milestone", "Client State Update", "Adds a new milestone row; updates percentage allocation validator."),
        ("Create Studio", "Delete Milestone", "Client State Update", "Removes milestone row; updates percentage allocation validator."),
        ("Create Studio", "Authorize Escrow", "PayPal SDK -> POST /api/bounties", "Authorizes payment hold on PayPal; saves contract, escrow, and milestones in DB."),
        ("Submit Hub", "Tab: Receipt Upload", "Client State Toggle", "Switches submission form to image/PDF dropzone with EXIF date verification."),
        ("Submit Hub", "Tab: GitHub Code", "Client State Toggle", "Switches submission form to GitHub repo URL with AST anti-Sybil screening."),
        ("Submit Hub", "Submit Deliverable", "POST /api/bounties/{id}/submit-work", "Executes AI audit (Gemini Vision or Code QA). Releases funds or flags fraud review."),
        ("Submit Hub", "Download Certificate", "GET /api/milestones/{id}/certificate", "Downloads official compliance certificate PDF containing exact Gemini JSON reasoning."),
        ("Submit Hub", "Submit Appeal", "POST /api/bounties/{id}/appeal", "Invokes Mediator AI to arbitrate rejection defense and potentially override ruling."),
        ("Submit Hub", "Negotiate Scope", "Client Drawer Toggle", "Opens AI contract renegotiation tool with counter-offer inputs."),
        ("Submit Hub", "Generate Compromise", "POST /api/bounties/{id}/negotiate", "Gemini generates fair middle-ground compromise terms on budget and deadlines."),
        ("Submit Hub", "Accept Compromise", "POST /api/bounties/{id}/accept-compromise", "Commits compromise terms to the database and refreshes contract state."),
        ("Admin Dashboard", "Inspect Dossier", "Client Modal Open", "Opens full AI audit log, multi-sponsor authorizations, and payee payout details."),
        ("Admin Dashboard", "Final Approve", "POST /api/admin/.../approve", "Co-signs high-value release (> $5k), captures authorizations, executes PayPal Payout."),
        ("Admin Dashboard", "Reject / Re-Audit", "Client State Update", "Blocks high-value payout and sends milestone back for audit revisions."),
        ("Logistics Panel", "Poll Oracle Now", "POST /api/oracle/poll", "Queries carrier API; auto-approves deliverables marked DELIVERED and triggers payout.")
    ]

    table = doc.add_table(rows=len(table_data), cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(1.2), Inches(1.3), Inches(1.8), Inches(2.2)]

    for row_idx, row in enumerate(table.rows):
        is_header = (row_idx == 0)
        # Prevent row split across pages
        trPr = row._element.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
        if is_header:
            trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

        for col_idx, cell in enumerate(row.cells):
            cell.width = col_widths[col_idx]
            cell_text = table_data[row_idx][col_idx]
            
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            
            run = p.add_run(cell_text)
            run.font.name = "Arial"
            
            if is_header:
                run.bold = True
                run.font.size = Pt(8.5)
                run.font.color.rgb = RGBColor(255, 255, 255)
                set_cell_background(cell, "1E293B")  # Dark Slate header
                set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
            else:
                run.font.size = Pt(8.0)
                if col_idx == 1:
                    run.bold = True
                    run.font.color.rgb = COLOR_SECONDARY
                elif col_idx == 2:
                    run.font.name = "Courier New"
                    run.font.size = Pt(7.5)
                    run.font.color.rgb = RGBColor(15, 23, 42)
                else:
                    run.font.color.rgb = COLOR_DARK
                
                # Alternating row background
                bg_hex = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"
                set_cell_background(cell, bg_hex)
                set_cell_margins(cell, top=80, bottom=80, left=90, right=90)

            # Cell borders
            tcPr = cell._element.get_or_add_tcPr()
            borders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                f'<w:left w:val="none"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                f'<w:right w:val="none"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(borders)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # -------------------------------------------------------------
    # SECTION 5: SECURITY, DISPUTE & FEEDBACK STATES
    # -------------------------------------------------------------
    h5 = doc.add_heading(level=1)
    run_h5 = h5.add_run("5. Dynamic Security Indicators & System Feedback States")
    run_h5.font.name = "Arial"
    run_h5.font.size = Pt(15)
    run_h5.bold = True
    run_h5.font.color.rgb = COLOR_PRIMARY
    h5.paragraph_format.space_before = Pt(16)
    h5.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "The frontend must accurately communicate real-time security events, algorithmic holds, "
        "and compliance validations through distinct visual indicator states:",
        style="Normal"
    ).paragraph_format.space_after = Pt(6)

    states = [
        ("Anti-Sybil Fraud Review Banner", "Activated when `status === 'fraud_review_pending'`. High-priority alert banner notifying the user that AST syntactic structures and identifier naming habits matched historical accounts in the database. Payout execution is locked pending human compliance intervention."),
        ("Hybrid Multi-Sig Co-Signer Gate", "Displayed whenever total contract value exceeds $5,000 USD. Explains that while the autonomous AI evaluation has PASSED, the second key of the multi-sig protocol requires human co-signer verification on the admin dashboard before PayPal capture occurs."),
        ("Predictive Risk Scoring Badges", "Dynamic color-coded states: LOW (Green with checkmark), MEDIUM (Amber with schedule caution), and HIGH (Pulsing crimson with imminent deadline warning and recommendation advice)."),
        ("Extracted Receipt Dossier Card", "Structured summary showing extracted vendor, verified transaction date, invoice currency, itemized purchases list, and matched EXIF camera timestamp."),
        ("Cryptographic Compliance Watermark", "Visual verification footer confirming settlement under MilestoneEscrow protocol with unique Certificate ID and PayPal transaction batch hash.")
    ]

    for stitle, sdesc in states:
        p_s = doc.add_paragraph(style="List Bullet")
        p_s.paragraph_format.space_after = Pt(3)
        r_st = p_s.add_run(f"{stitle}: ")
        r_st.bold = True
        p_s.add_run(sdesc)

    # Output file
    output_filename = "MilestoneEscrow_Frontend_Requirements_Specification.docx"
    doc.save(output_filename)
    abs_path = os.path.abspath(output_filename)
    print(f"Successfully generated requirements document: {abs_path}")
    return abs_path


if __name__ == "__main__":
    build_word_document()

