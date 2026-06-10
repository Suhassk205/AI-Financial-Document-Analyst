import { useEffect, useState } from "react";
import { getHealth } from "@/services/api";

/**
 * Foundation shell. Proves the frontend boots and can reach the backend's
 * /health endpoint. Real pages/features are added under src/pages & src/features
 * in later phases.
 */
export default function App() {
  const [apiStatus, setApiStatus] = useState<string>("checking…");

  useEffect(() => {
    getHealth()
      .then((res) => setApiStatus(res.status))
      .catch(() => setApiStatus("unreachable"));
  }, []);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-50 text-slate-800">
      <h1 className="text-2xl font-semibold">AI Financial Document Analyst</h1>
      <p className="text-sm text-slate-500">Phase 0.5 — foundation</p>
      <p className="text-sm">
        Backend health: <span className="font-mono">{apiStatus}</span>
      </p>
    </main>
  );
}
