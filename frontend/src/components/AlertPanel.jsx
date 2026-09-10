/* AlertPanel.jsx — Interactive Alert Simulation Demo */

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { API_BASE } from "../api";

const STATUS_COLORS = {
  complete: "#10b981",   // green
  warning: "#f59e0b",    // amber
  danger: "#ef4444",     // red
  sent: "#3b82f6",       // blue
};

const STATUS_ICONS = {
  complete: "✓",
  warning: "⚠",
  danger: "🔴",
  sent: "📱",
};

export default function AlertPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [district, setDistrict] = useState("Kasaragod");
  const [rainfall, setRainfall] = useState(180);
  const [sendSms, setSendSms] = useState(false);

  // Animate steps appearing one by one
  useEffect(() => {
    if (result && visibleSteps < result.steps.length) {
      const timer = setTimeout(() => {
        setVisibleSteps((prev) => prev + 1);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [result, visibleSteps]);

  const runSimulation = async () => {
    setLoading(true);
    setResult(null);
    setVisibleSteps(0);

    try {
      const params = new URLSearchParams({
        district,
        rainfall_mm: rainfall,
        soil_saturation: 0.92,
        send_sms_flag: sendSms,
      });
      const res = await fetch(`${API_BASE}/alerts/simulate?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ error: err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="alert-panel">
      {/* Toggle Button */}
      <button
        className="alert-toggle-btn"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="alert-icon">🚨</span>
        <span>Alert Simulation</span>
        <span className="toggle-arrow">{isOpen ? "▲" : "▼"}</span>
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="alert-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            {/* Controls */}
            <div className="alert-controls">
              <div className="control-row">
                <label>District</label>
                <select
                  value={district}
                  onChange={(e) => setDistrict(e.target.value)}
                  className="alert-select"
                >
                  <option value="Kasaragod">★ Kasaragod</option>
                  <option value="Kannur">★ Kannur</option>
                  <option value="Wayanad">Wayanad</option>
                  <option value="Kozhikode">Kozhikode</option>
                  <option value="Idukki">Idukki</option>
                  <option value="Malappuram">Malappuram</option>
                  <option value="Palakkad">Palakkad</option>
                  <option value="Thrissur">Thrissur</option>
                </select>
                </div>
              <p style={{fontSize: '9px', color: '#94a3b8', margin: '0 0 8px 0'}}>★ = has raster data coverage</p>

              <div className="control-row">
                <label>Rainfall (mm)</label>
                <input
                  type="range"
                  min="50"
                  max="300"
                  value={rainfall}
                  onChange={(e) => setRainfall(Number(e.target.value))}
                  className="alert-slider"
                />
                <span className="slider-value">{rainfall}mm</span>
              </div>

              <div className="control-row checkbox-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={sendSms}
                    onChange={(e) => setSendSms(e.target.checked)}
                  />
                  Send real SMS
                </label>
              </div>

              <button
                className="run-simulation-btn"
                onClick={runSimulation}
                disabled={loading}
              >
                {loading ? (
                  <span className="spinner"></span>
                ) : (
                  <>⚡ Run Alert Simulation</>
                )}
              </button>
            </div>

            {/* Results */}
            {result && !result.error && (
              <div className="simulation-results">
                {/* Scenario Header */}
                <div className="scenario-header">
                  <div className="scenario-district">{result.district}</div>
                  <div className="scenario-desc">{result.scenario}</div>
                </div>

                {/* Step-by-step Animation */}
                <div className="steps-container">
                  {result.steps.map((step, idx) => (
                    <AnimatePresence key={step.step}>
                      {idx < visibleSteps && (
                        <motion.div
                          className={`sim-step sim-step-${step.status}`}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.3 }}
                        >
                          <div className="step-indicator">
                            <span
                              className="step-dot"
                              style={{ background: STATUS_COLORS[step.status] }}
                            >
                              {STATUS_ICONS[step.status]}
                            </span>
                            {idx < result.steps.length - 1 && (
                              <div
                                className="step-line"
                                style={{ background: STATUS_COLORS[step.status] }}
                              />
                            )}
                          </div>
                          <div className="step-content">
                            <div className="step-title">{step.title}</div>
                            <div className="step-detail">{step.detail}</div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  ))}
                </div>

                {/* SMS Preview (shown after all steps) */}
                {visibleSteps >= result.steps.length && (
                  <motion.div
                    className="sms-preview"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                  >
                    <div className="sms-header">
                      <span>📩 SMS {result.sms_sent ? "Sent" : "Preview"}</span>
                      <span className={`sms-badge ${result.sms_sent ? "sent" : "preview"}`}>
                        {result.sms_sent ? "✓ Delivered" : "Preview"}
                      </span>
                    </div>
                    <pre className="sms-body">{result.sms_message}</pre>
                    <div className="sms-recipient">
                      To: {result.recipient}
                    </div>
                  </motion.div>
                )}
              </div>
            )}

            {result?.error && (
              <div className="sim-error">
                ❌ Error: {result.error}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
