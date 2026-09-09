import React from "react";
import { motion } from "framer-motion";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.04,
      delayChildren: 0.15,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, x: -8 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { type: "spring", stiffness: 350, damping: 25 }
  },
};

// Calibrated in ml_models/calibrate_alert_threshold.py against the v2 map and checked
// against how much of the 279-point inventory each cutoff recovers. Kept in step with
// SUSCEPTIBILITY_BREAKS in backend/tiles.py and the thresholds in backend/alerts.py.
const SUSCEPTIBILITY_CLASSES = [
  { color: '#dc2626', label: 'Very high', detail: '≥ 0.87 · 0.2% of terrain' },
  { color: '#f97316', label: 'High', detail: '≥ 0.70 · 1% of terrain' },
  { color: '#facc15', label: 'Watch', detail: '≥ 0.45 · 5% of terrain' },
  { color: '#1e4078', label: 'Low', detail: '< 0.45' },
];

const Legend = () => {
  return (
    <motion.div
      className="legend p-2"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <h3 className="text-md font-semibold mb-2">Legend</h3>

      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-color failure w-3 h-3 rounded-sm"></span>
        <span className="text-sm">Failure Zone (Initiation)</span>
      </motion.div>

      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-color transit w-3 h-3 rounded-sm"></span>
        <span className="text-sm">Transit Zone (Movement)</span>
      </motion.div>

      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-color deposition w-3 h-3 rounded-sm"></span>
        <span className="text-sm">Deposition Zone (Accumulation)</span>
      </motion.div>

      <hr className="my-2" />

      <motion.p variants={itemVariants} className="text-xs font-semibold mb-1">
        Susceptibility
      </motion.p>
      {/* Class breaks match the alert tiers in backend/alerts.py, so what is shown on
          the map and what triggers an alert cannot drift apart. The share of terrain
          each tier covers is given because a colour alone does not convey how selective
          it is. */}
      {SUSCEPTIBILITY_CLASSES.map(({ color, label, detail }) => (
        <motion.div
          key={label}
          variants={itemVariants}
          className="legend-item flex items-center gap-2 mb-1"
        >
          <span
            style={{
              display: 'inline-block', width: '12px', height: '12px',
              borderRadius: '2px', backgroundColor: color,
            }}
          ></span>
          <span className="text-xs">
            {label} <span className="opacity-60">{detail}</span>
          </span>
        </motion.div>
      ))}

      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mt-2">
        <span
          style={{
            display: 'inline-block', width: '12px', height: '12px',
            borderRadius: '2px', backgroundColor: '#94a3b8',
          }}
        ></span>
        <span className="text-xs">
          Uncertain <span className="opacity-60">model cannot call (24% of grid)</span>
        </span>
      </motion.div>

      <hr className="my-2" />

      <motion.p variants={itemVariants} className="text-xs font-semibold mb-1">GSI Historical (KSDMA)</motion.p>
      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mb-1">
        <span style={{ display: 'inline-block', width: '12px', height: '12px', borderRadius: '2px', backgroundColor: '#22c55e' }}></span>
        <span className="text-xs">Low</span>
      </motion.div>
      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mb-1">
        <span style={{ display: 'inline-block', width: '12px', height: '12px', borderRadius: '2px', backgroundColor: '#eab308' }}></span>
        <span className="text-xs">Moderate</span>
      </motion.div>
      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2">
        <span style={{ display: 'inline-block', width: '12px', height: '12px', borderRadius: '2px', backgroundColor: '#dc2626' }}></span>
        <span className="text-xs">High</span>
      </motion.div>
    </motion.div>
  );
};

export default Legend;
