import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="shell">
      <section>
        <p className="eyebrow">MIRA Phase 0.5</p>
        <h1>App spine online</h1>
        <p>FastAPI, Supabase Auth, and RLS proof routes are served from one app.</p>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

