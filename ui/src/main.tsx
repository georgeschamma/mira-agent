import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Session, SupabaseClient } from "@supabase/supabase-js";

import {
  getActionSheet,
  getAuditTrace,
  loadRuntimeConfig,
  runMediaPlan,
  updateApproval,
} from "./api";
import { buildReportMarkdown } from "./reportMarkdown";
import { getSupabaseClient } from "./supabase";
import type {
  ActionSheetReportResponse,
  ApprovalUpdateStatus,
  AuditTraceResponse,
  Recommendation,
  RuntimeConfigResponse,
} from "./types";
import "./styles.css";

const DEMO_ORG_ID = "11111111-1111-4111-8111-111111111111";

type RunState = "idle" | "loading" | "success" | "error";
type ActiveTab = "report" | "audit";

type MediaPlanForm = {
  org_id: string;
  brief: string;
};

const initialMediaPlan: MediaPlanForm = {
  org_id: DEMO_ORG_ID,
  brief: [
    "Product: MIRA",
    "Audience: B2B marketers",
    "Channels: google, linkedin, meta, tiktok",
    "Budget: 10000",
    "Goal: grow pipeline",
  ].join("\n"),
};

function App() {
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfigResponse | null>(null);
  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [booting, setBooting] = useState(true);
  const [email, setEmail] = useState("analyst@mira.local");
  const [password, setPassword] = useState("");
  const [mediaPlan, setMediaPlan] = useState<MediaPlanForm>(initialMediaPlan);
  const [crmFile, setCrmFile] = useState<File | null>(null);
  const [ga4File, setGa4File] = useState<File | null>(null);
  const [runState, setRunState] = useState<RunState>("idle");
  const [activeTab, setActiveTab] = useState<ActiveTab>("report");
  const [report, setReport] = useState<ActionSheetReportResponse | null>(null);
  const [audit, setAudit] = useState<AuditTraceResponse | null>(null);
  const [actionSheetId, setActionSheetId] = useState("");
  const [message, setMessage] = useState("");
  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;

    async function boot() {
      try {
        const config = await loadRuntimeConfig();
        if (!active) {
          return;
        }
        const client = getSupabaseClient(config);
        setRuntimeConfig(config);
        setSupabase(client);

        const sessionResult = await client.auth.getSession();
        if (active) {
          setSession(sessionResult.data.session);
        }

        const { data } = client.auth.onAuthStateChange((_event, nextSession) => {
          if (active) {
            setSession(nextSession);
          }
        });
        unsubscribe = () => data.subscription.unsubscribe();
      } catch (error) {
        if (active) {
          setMessage(error instanceof Error ? error.message : "Runtime config failed.");
        }
      } finally {
        if (active) {
          setBooting(false);
        }
      }
    }

    void boot();
    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  const approvalById = useMemo(() => {
    return new Map(report?.approvals.map((approval) => [approval.recommendation_id, approval]) ?? []);
  }, [report]);

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) {
      setMessage("Supabase client is not ready.");
      return;
    }
    setMessage("");
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setMessage(error.message);
      return;
    }
    setSession(data.session);
    if (data.session && actionSheetId.trim()) {
      void loadReportById(data.session.access_token, actionSheetId);
    }
  }

  async function signOut() {
    if (!supabase) {
      return;
    }
    await supabase.auth.signOut();
    setSession(null);
    setReport(null);
    setAudit(null);
    setRunState("idle");
  }

  async function submitMediaPlan(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.access_token) {
      setMessage("Sign in before running a media plan.");
      return;
    }
    if (!crmFile || !ga4File) {
      setMessage("Upload both CRM and GA4 CSV files.");
      return;
    }

    setRunState("loading");
    setMessage("");
    setReport(null);
    setAudit(null);

    try {
      const analysis = await runMediaPlan(session.access_token, {
        orgId: mediaPlan.org_id.trim(),
        brief: mediaPlan.brief.trim(),
        crmCsv: crmFile,
        ga4Csv: ga4File,
      });
      setActionSheetId(analysis.action_sheet_id);
      const [nextReport, nextAudit] = await Promise.all([
        getActionSheet(session.access_token, analysis.action_sheet_id),
        getAuditTrace(session.access_token, analysis.run_id),
      ]);
      setReport(nextReport);
      setAudit(nextAudit);
      setActiveTab("report");
      setRunState("success");
    } catch (error) {
      setRunState("error");
      setMessage(error instanceof Error ? error.message : "Media plan failed.");
    }
  }

  async function loadReport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.access_token) {
      setMessage("Sign in before loading a report.");
      return;
    }
    await loadReportById(session.access_token, actionSheetId);
  }

  async function loadReportById(token: string, rawActionSheetId: string) {
    const id = rawActionSheetId.trim();
    if (!id) {
      setMessage("Enter an action sheet ID.");
      return;
    }

    setRunState("loading");
    setMessage("");
    setReport(null);
    setAudit(null);
    try {
      const nextReport = await getActionSheet(token, id);
      const nextAudit = await getAuditTrace(token, nextReport.run_id);
      setActionSheetId(id);
      setReport(nextReport);
      setAudit(nextAudit);
      setActiveTab("report");
      setRunState("success");
    } catch (error) {
      setRunState("error");
      setMessage(error instanceof Error ? error.message : "Report load failed.");
    }
  }

  async function changeApproval(recommendation: Recommendation, status: ApprovalUpdateStatus) {
    if (!session?.access_token || !report) {
      return;
    }
    setApprovalBusyId(recommendation.id);
    setMessage("");
    try {
      await updateApproval(
        session.access_token,
        report.action_sheet_id,
        recommendation.id,
        status,
      );
      const refreshedReport = await getActionSheet(session.access_token, report.action_sheet_id);
      setReport(refreshedReport);
      setMessage(`Recommendation ${status}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Approval update failed.");
    } finally {
      setApprovalBusyId(null);
    }
  }

  async function changeDocumentApproval(status: ApprovalUpdateStatus) {
    if (!session?.access_token || !report) {
      return;
    }
    setApprovalBusyId("document");
    setMessage("");
    try {
      await updateApproval(session.access_token, report.action_sheet_id, "document", status);
      const refreshedReport = await getActionSheet(session.access_token, report.action_sheet_id);
      setReport(refreshedReport);
      setMessage(`Media plan ${status}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Approval update failed.");
    } finally {
      setApprovalBusyId(null);
    }
  }

  function exportMarkdown() {
    if (!report) {
      return;
    }
    const markdown = buildReportMarkdown(report, audit);
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mira-report-${report.run_id}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{runtimeConfig?.app_name ?? "MIRA Agent"}</p>
          <h1>Analysis Console</h1>
        </div>
        <div className="session-box">
          {session ? (
            <>
              <span>{session.user.email}</span>
              <button className="secondary-button" type="button" onClick={() => void signOut()}>
                Sign out
              </button>
            </>
          ) : (
            <span>{booting ? "Loading config" : "Signed out"}</span>
          )}
        </div>
      </header>

      {message ? <p className="notice">{message}</p> : null}

      {!session ? (
        <section className="panel auth-panel">
          <div className="panel-heading">
            <h2>Sign In</h2>
            <div className="account-switcher">
              <button
                type="button"
                onClick={() => {
                  setEmail("analyst@mira.local");
                  setPassword("");
                }}
              >
                Analyst
              </button>
              <button
                type="button"
                onClick={() => {
                  setEmail("admin@mira.local");
                  setPassword("");
                }}
              >
                Admin
              </button>
            </div>
          </div>
          <form className="stack-form" onSubmit={(event) => void signIn(event)}>
            <label>
              Email
              <input
                autoComplete="email"
                disabled={booting}
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                autoComplete="current-password"
                disabled={booting}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button className="primary-button" disabled={booting || !supabase} type="submit">
              Sign in
            </button>
          </form>
        </section>
      ) : (
        <div className="workspace">
          <section className="panel brief-panel">
            <div className="panel-heading">
              <h2>Media Plan Input</h2>
              <span className={`status-pill status-${runState}`}>{runState}</span>
            </div>
            <form className="stack-form" onSubmit={(event) => void submitMediaPlan(event)}>
              <label>
                Org ID
                <input
                  value={mediaPlan.org_id}
                  onChange={(event) =>
                    setMediaPlanField("org_id", event.target.value, setMediaPlan)
                  }
                />
              </label>
              <label>
                Brief
                <textarea
                  value={mediaPlan.brief}
                  onChange={(event) =>
                    setMediaPlanField("brief", event.target.value, setMediaPlan)
                  }
                />
              </label>
              <label>
                CRM CSV
                <input
                  accept=".csv,text/csv"
                  type="file"
                  onChange={(event) => setCrmFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <label>
                GA4 CSV
                <input
                  accept=".csv,text/csv"
                  type="file"
                  onChange={(event) => setGa4File(event.target.files?.[0] ?? null)}
                />
              </label>
              <button className="primary-button" disabled={runState === "loading"} type="submit">
                {runState === "loading" ? "Running" : "Run media plan"}
              </button>
            </form>
          </section>

          <section className="panel report-panel">
            <div className="panel-heading">
              <h2>Output</h2>
              <div className="toolbar">
                <div className="tabs">
                  <button
                    className={activeTab === "report" ? "active" : ""}
                    type="button"
                    onClick={() => setActiveTab("report")}
                  >
                    Report
                  </button>
                  <button
                    className={activeTab === "audit" ? "active" : ""}
                    type="button"
                    onClick={() => setActiveTab("audit")}
                  >
                    Audit
                  </button>
                </div>
                <button
                  className="secondary-button"
                  disabled={!report}
                  type="button"
                  onClick={exportMarkdown}
                >
                  Export Markdown
                </button>
              </div>
            </div>
            <form className="report-loader" onSubmit={(event) => void loadReport(event)}>
              <label>
                Action sheet ID
                <input
                  value={actionSheetId}
                  onChange={(event) => setActionSheetId(event.target.value)}
                />
              </label>
              <button className="secondary-button" disabled={runState === "loading"} type="submit">
                Load report
              </button>
            </form>

            {!report ? (
              <div className="empty-state">
                {runState === "loading" ? "Analysis is running." : "No report loaded."}
              </div>
            ) : activeTab === "report" ? (
              report.document_markdown ? (
                <div className="document-output">
                  <div className="document-toolbar">
                    <span className={`badge approval-${documentApprovalStatus(report)}`}>
                      {documentApprovalStatus(report)}
                    </span>
                    {documentApprovalStatus(report) === "pending" ? (
                      <div className="approval-actions">
                        <button
                          className="secondary-button"
                          disabled={approvalBusyId === "document"}
                          type="button"
                          onClick={() => void changeDocumentApproval("approved")}
                        >
                          Approve
                        </button>
                        <button
                          className="secondary-button danger"
                          disabled={approvalBusyId === "document"}
                          type="button"
                          onClick={() => void changeDocumentApproval("rejected")}
                        >
                          Reject
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <pre>{report.document_markdown}</pre>
                  {report.document_metadata && Array.isArray(report.document_metadata.expansion_tests) && report.document_metadata.expansion_tests.length > 0 ? (
                    <div className="recommended-tests-metadata" style={{ marginTop: "32px" }}>
                      <h3 style={{ fontSize: "1.2rem", fontWeight: "600", marginBottom: "12px" }}>Recommended Tests (Metadata Dashboard)</h3>
                      <div className="table-responsive" style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
                          <thead>
                            <tr style={{ textAlign: "left", borderBottom: "2px solid var(--border-color, #e2e8f0)", background: "rgba(0,0,0,0.02)" }}>
                              <th style={{ padding: "12px 8px" }}>Channel</th>
                              <th style={{ padding: "12px 8px" }}>Monthly Test Budget</th>
                              <th style={{ padding: "12px 8px" }}>Hypothesis</th>
                              <th style={{ padding: "12px 8px" }}>Primary KPI</th>
                              <th style={{ padding: "12px 8px" }}>Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(report.document_metadata.expansion_tests as any[]).map((test, index) => (
                              <tr key={index} style={{ borderBottom: "1px solid var(--border-color, #e2e8f0)" }}>
                                <td style={{ padding: "12px 8px", fontWeight: "500" }}>{test.channel}</td>
                                <td style={{ padding: "12px 8px" }}>{test.monthly_budget_range}</td>
                                <td style={{ padding: "12px 8px", color: "var(--text-muted, #4a5568)" }}>{test.hypothesis}</td>
                                <td style={{ padding: "12px 8px" }}>{test.primary_kpi}</td>
                                <td style={{ padding: "12px 8px", fontSize: "0.8rem", color: "var(--text-muted, #718096)" }}>{test.source}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="recommendation-list">
                  {report.recommendations.map((recommendation) => {
                    const approval = approvalById.get(recommendation.id);
                    const approvalStatus = recommendation.needs_approval
                      ? approval?.status ?? "pending"
                      : "not required";
                    const canUpdate = recommendation.needs_approval && approvalStatus === "pending";

                    return (
                      <article className="recommendation-item" key={recommendation.id}>
                        <div className="item-header">
                          <div>
                            <p className="eyebrow">{recommendation.domain}</p>
                            <h3>{recommendation.finding}</h3>
                          </div>
                          <span className={`badge approval-${approvalStatus.replace(" ", "-")}`}>
                            {approvalStatus}
                          </span>
                        </div>
                        <p>{recommendation.action}</p>
                        <div className="meta-row">
                          <span className={`badge effort-${recommendation.effort}`}>
                            Effort: {recommendation.effort}
                          </span>
                          <span className={`badge impact-${recommendation.impact}`}>
                            Impact: {recommendation.impact}
                          </span>
                          {sourceElement(recommendation.source)}
                        </div>
                        {canUpdate ? (
                          <div className="approval-actions">
                            <button
                              className="secondary-button"
                              disabled={approvalBusyId === recommendation.id}
                              type="button"
                              onClick={() => void changeApproval(recommendation, "approved")}
                            >
                              Approve
                            </button>
                            <button
                              className="secondary-button danger"
                              disabled={approvalBusyId === recommendation.id}
                              type="button"
                              onClick={() => void changeApproval(recommendation, "rejected")}
                            >
                              Reject
                            </button>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              )
            ) : (
              <div className="audit-list">
                {(audit?.rows ?? []).map((row) => (
                  <article className="audit-row" key={row.id}>
                    <div className="step-index">{row.step_index}</div>
                    <div>
                      <div className="item-header compact">
                        <h3>{row.node}</h3>
                        <span className={`badge confidence-${row.confidence ?? "unknown"}`}>
                          {row.confidence ?? "unknown"}
                        </span>
                      </div>
                      <p>{row.summary}</p>
                      <div className="meta-row">
                        {sourceElement(row.source)}
                        <span>{row.model_used ?? "no model"}</span>
                        <span>{formatDate(row.created_at)}</span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

function setMediaPlanField(
  field: keyof MediaPlanForm,
  value: string,
  setMediaPlan: React.Dispatch<React.SetStateAction<MediaPlanForm>>,
) {
  setMediaPlan((current) => ({ ...current, [field]: value }));
}

function documentApprovalStatus(report: ActionSheetReportResponse): string {
  const approval = report.approvals.find((item) => item.recommendation_id === "document");
  return approval?.status ?? report.document_status ?? "pending";
}

function sourceElement(source: string | null) {
  if (!source) {
    return <span>Source: none</span>;
  }
  if (source.startsWith("http://") || source.startsWith("https://")) {
    return (
      <a href={source} rel="noreferrer" target="_blank">
        Source
      </a>
    );
  }
  return <span>Source: {source}</span>;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "no timestamp";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
