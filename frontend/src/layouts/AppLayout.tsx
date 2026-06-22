import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import Breadcrumbs from "@/design-system/components/Breadcrumbs";
import DemoGuide from "@/design-system/patterns/DemoGuide";
import { useObservability, usePerformanceTimer } from "@/hooks/useObservability";
import { Activity, X, Sun, Moon } from "lucide-react";
import Button from "@/design-system/components/Button";
import { useThemeContext } from "@/lib/ThemeContext";

/** Main application layout with sidebar navigation, header, and diagnostics dashboard. */
export default function AppLayout() {
  usePerformanceTimer("AppLayout");
  const { logs } = useObservability();
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const { theme, toggleTheme } = useThemeContext();

  return (
    <div className="flex min-h-screen bg-surface-50 dark:bg-surface-950 transition-colors duration-200">
      <Sidebar />
      
      <div className="flex-1 flex flex-col min-w-0">
        {/* Sticky Top Header */}
        <header
          className="sticky top-0 z-30 h-16 bg-white/80 dark:bg-surface-900/80 backdrop-blur-md border-b border-surface-200 dark:border-surface-700 px-6 flex items-center justify-between transition-colors duration-200"
          role="banner"
        >
          <div className="flex items-center gap-4">
            <Breadcrumbs />
          </div>

          <div className="flex items-center gap-3">
            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="flex items-center justify-center w-9 h-9 rounded-lg border border-surface-200 dark:border-surface-700 text-surface-500 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-brand-500"
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              id="theme-toggle-btn"
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? (
                <Sun className="w-4 h-4" aria-hidden="true" />
              ) : (
                <Moon className="w-4 h-4" aria-hidden="true" />
              )}
            </button>

            {/* Guided Tour Widget */}
            <DemoGuide />

            {/* Diagnostics Telemetry Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowDiagnostics(!showDiagnostics)}
              className="flex items-center gap-1.5"
              aria-label="Toggle frontend diagnostics panel"
            >
              <Activity className="w-4 h-4 text-surface-500" />
              Diagnostics
              {logs.filter(l => l.category === "error").length > 0 && (
                <span className="h-2 w-2 rounded-full bg-danger animate-pulse" />
              )}
            </Button>
          </div>
        </header>

        {/* Floating Diagnostics Drawer */}
        {showDiagnostics && (
          <section
            className="border-b border-surface-200 dark:border-surface-700 bg-surface-900 text-white p-5 animate-slide-down"
            aria-label="Frontend Telemetry Logs"
          >
            <div className="flex justify-between items-center mb-3">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-brand-400" />
                <h3 className="text-sm font-semibold">Real-Time Presentation Observability</h3>
              </div>
              <button
                onClick={() => setShowDiagnostics(false)}
                className="text-surface-400 hover:text-white p-1"
                aria-label="Close panel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <div className="bg-surface-800 p-3 rounded border border-surface-700">
                <h4 className="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-2">Metrics Summary</h4>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span>Active Telemetry Logs:</span>
                    <span className="font-semibold text-brand-300">{logs.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Recorded Errors:</span>
                    <span className="font-semibold text-danger">
                      {logs.filter(l => l.category === "error").length}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Performance Traces:</span>
                    <span className="font-semibold text-success">
                      {logs.filter(l => l.category === "performance").length}
                    </span>
                  </div>
                </div>
              </div>

              <div className="col-span-2 bg-surface-800 p-3 rounded border border-surface-700 max-h-36 overflow-y-auto">
                <h4 className="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-2">Live Log Feed</h4>
                {logs.length === 0 ? (
                  <p className="text-xs text-surface-500 italic">No interaction recorded yet. Try navigating or clicking export.</p>
                ) : (
                  <div className="space-y-1.5">
                    {logs.map((log, idx) => (
                      <div key={idx} className="flex items-start justify-between text-xs font-mono">
                        <span className="text-surface-400 shrink-0 mr-3">[{log.timestamp}]</span>
                        <span className="text-brand-300 shrink-0 mr-3 uppercase text-[10px] bg-brand-900 px-1 rounded">
                          {log.category}
                        </span>
                        <span className="text-surface-200 flex-1 truncate">{log.name}</span>
                        <span className="text-success font-semibold shrink-0 ml-3">{log.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        <main className="flex-1 overflow-y-auto" role="main">
          <div className="max-w-7xl mx-auto px-6 py-6">
            <Outlet />
          </div>
        </main>

        {/* Footer */}
        <footer className="border-t border-surface-200 dark:border-surface-800 px-6 py-3 text-center transition-colors duration-200">
          <p className="text-xs text-surface-400 dark:text-surface-500">
            © {new Date().getFullYear()} FinAnalyst &middot; Built with AI-powered document analysis
          </p>
        </footer>
      </div>
    </div>
  );
}

