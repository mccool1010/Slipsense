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

      <motion.div variants={itemVariants} className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-gradient w-24 h-3 rounded-sm"></span>
        <span className="text-sm">DL Susceptibility (Low → High)</span>
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
