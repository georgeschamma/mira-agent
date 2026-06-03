import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Session, SupabaseClient } from "@supabase/supabase-js";

import {
  getActionSheet,
  getAuditTrace,
  loadRuntimeConfig,
  runAnalyze,
  updateApproval,
} from "./api";
import { buildReportMarkdown } from "./reportMarkdown";
import { getSupabaseClient } from "./supabase";
import type {
  ActionSheetReportResponse,
  AnalyzeRequest,
  ApprovalUpdateStatus,
  AuditTraceResponse,
  Recommendation,
  RuntimeConfigResponse,
} from "./types";
import "./styles.css";

const DEMO_ORG_ID = "11111111-1111-4111-8111-111111111111";

type RunState = "idle" | "loading" | "success" | "error";
type ActiveTab = "report" | "audit";

type BriefForm = {
  org_id: string;
  product: string;
  audience: string;
  channels: string;
  budget: string;
  goal: string;
};

const initialBrief: BriefForm = {
  org_id: DEMO_ORG_ID,
  product: "MIRA",
  audience: "B2B marketers",
  channels: "linkedin",
  budget: "1000",
  goal: "book demos",
};

function App() {
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfigResponse | null>(null);
  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [booting, setBooting] = useState(true);
  const [email, setEmail] = useState("analyst@mira.local");
  const [password, setPassword] = useState("");
  const [brief, setBrief] = useState<BriefForm>(initialBrief);
  const [runState, setRunState] = useState<RunState>("idle");
  const [activeTab, setActiveTab] = useState<ActiveTab>("report");
  const [report, setReport] = useState<ActionSheetReportResponse | null>(null);
  const [audit, setAudit] = useState<AuditTraceResponse | null>(null);
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

  async function submitBrief(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.access_token) {
      setMessage("Sign in before running analysis.");
      return;
    }

    setRunState("loading");
    setMessage("");
    setReport(null);
    setAudit(null);

    try {
      const payload = briefToRequest(brief);
      const analysis = await runAnalyze(session.access_token, payload);
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
      setMessage(error instanceof Error ? error.message : "Analysis failed.");
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
              <h2>Campaign Brief</h2>
              <span className={`status-pill status-${runState}`}>{runState}</span>
            </div>
            <form className="brief-grid" onSubmit={(event) => void submitBrief(event)}>
              <label>
                Org ID
                <input
                  value={brief.org_id}
                  onChange={(event) => setBriefField("org_id", event.target.value, setBrief)}
                />
              </label>
              <label>
                Product
                <input
                  value={brief.product}
                  onChange={(event) => setBriefField("product", event.target.value, setBrief)}
                />
              </label>
              <label>
                Audience
                <input
                  value={brief.audience}
                  onChange={(event) => setBriefField("audience", event.target.value, setBrief)}
                />
              </label>
              <label>
                Channels
                <input
                  value={brief.channels}
                  onChange={(event) => setBriefField("channels", event.target.value, setBrief)}
                />
              </label>
              <label>
                Budget
                <input
                  min="0"
                  type="number"
                  value={brief.budget}
                  onChange={(event) => setBriefField("budget", event.target.value, setBrief)}
                />
              </label>
              <label>
                Goal
                <input
                  value={brief.goal}
                  onChange={(event) => setBriefField("goal", event.target.value, setBrief)}
                />
              </label>
              <button className="primary-button full-width" disabled={runState === "loading"} type="submit">
                {runState === "loading" ? "Running" : "Run analysis"}
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

            {!report ? (
              <div className="empty-state">
                {runState === "loading" ? "Analysis is running." : "No report loaded."}
              </div>
            ) : activeTab === "report" ? (
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

function setBriefField(
  field: keyof BriefForm,
  value: string,
  setBrief: React.Dispatch<React.SetStateAction<BriefForm>>,
) {
  setBrief((current) => ({ ...current, [field]: value }));
}

function briefToRequest(brief: BriefForm): AnalyzeRequest {
  return {
    org_id: brief.org_id.trim(),
    product: brief.product.trim(),
    audience: brief.audience.trim(),
    channels: brief.channels
      .split(",")
      .map((channel) => channel.trim())
      .filter(Boolean),
    budget: Number.parseInt(brief.budget, 10) || 0,
    goal: brief.goal.trim(),
  };
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
