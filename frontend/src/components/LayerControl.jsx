import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FiMap } from "react-icons/fi";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, x: -12 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { type: "spring", stiffness: 300, damping: 24 }
  },
};

const LayerRow = ({ children }) => (
  <motion.div
    className="flex items-center justify-between gap-3 py-2"
    variants={itemVariants}
  >
    {children}
  </motion.div>
);

const LayerControl = ({ activeLayers, layerOpacity, onToggle, onOpacityChange, selectedDistrict, onDistrictChange }) => {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="layer-control p-3"
    >
      <div className="flex items-center gap-2 mb-2">
        <FiMap className="text-xl" />
        <h3 className="text-lg font-semibold m-0">Layers</h3>
      </div>

      <AnimatePresence>
        <motion.div variants={containerVariants} initial="hidden" animate="visible" exit="hidden">
          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.streets}
                onChange={() => onToggle("streets")}
              />
              <span className="text-sm">Streets</span>
            </label>
            {activeLayers.streets && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.streets}
                onChange={(e) => onOpacityChange("streets", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>

          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.susceptibilityDL}
                onChange={() => onToggle("susceptibilityDL")}
              />
              <span className="text-sm">DL Refined Susceptibility</span>
            </label>
            {activeLayers.susceptibilityDL && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.susceptibilityDL}
                onChange={(e) => onOpacityChange("susceptibilityDL", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>

          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.historicalSusceptibility}
                onChange={() => onToggle("historicalSusceptibility")}
              />
              <span className="text-sm">Historical Susceptibility (GSI)</span>
            </label>
            {activeLayers.historicalSusceptibility && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.historicalSusceptibility}
                onChange={(e) => onOpacityChange("historicalSusceptibility", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>

          {/* District dropdown for historical layer */}
          {activeLayers.historicalSusceptibility && (
            <div className="pl-6 pb-2">
              <select
                className="district-select w-full p-1 text-sm rounded border border-gray-600 bg-gray-800 text-white"
                value={selectedDistrict || "all"}
                onChange={(e) => onDistrictChange && onDistrictChange(e.target.value)}
              >
                <option value="all">All Districts</option>
                <option value="thiruvananthapuram">Thiruvananthapuram</option>
                <option value="kollam">Kollam</option>
                <option value="pathanamthitta">Pathanamthitta</option>
                <option value="alappuzha">Alappuzha</option>
                <option value="kottayam">Kottayam</option>
                <option value="idukki">Idukki</option>
                <option value="ernakulam">Ernakulam</option>
                <option value="thrissur">Thrissur</option>
                <option value="palakkad">Palakkad</option>
                <option value="malappuram">Malappuram</option>
                <option value="kozhikode">Kozhikode</option>
                <option value="wayanad">Wayanad</option>
                <option value="kannur">Kannur</option>
                <option value="kasaragod">Kasaragod</option>
              </select>
            </div>
          )}

          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.hazardFused}
                onChange={() => onToggle("hazardFused")}
              />
              <span className="text-sm">Final Hazard Map</span>
            </label>
            {activeLayers.hazardFused && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.hazardFused}
                onChange={(e) => onOpacityChange("hazardFused", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>

          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.runout}
                onChange={() => onToggle("runout")}
              />
              <span className="text-sm">Runout Paths</span>
            </label>
            {activeLayers.runout && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.runout}
                onChange={(e) => onOpacityChange("runout", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>

          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.transit}
                onChange={() => onToggle("transit")}
              />
              <span className="text-sm">Transit Zone</span>
            </label>
            {activeLayers.transit && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.transit}
                onChange={(e) => onOpacityChange("transit", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>

          <LayerRow>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                className="form-checkbox"
                type="checkbox"
                checked={activeLayers.deposition}
                onChange={() => onToggle("deposition")}
              />
              <span className="text-sm">Deposition Zone</span>
            </label>
            {activeLayers.deposition && (
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerOpacity.deposition}
                onChange={(e) => onOpacityChange("deposition", parseFloat(e.target.value))}
                className="w-28"
              />
            )}
          </LayerRow>
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
};

export default LayerControl;
