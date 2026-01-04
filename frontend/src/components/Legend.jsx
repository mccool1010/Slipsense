import React from "react";

const Legend = () => {
  return (
    <div className="legend p-2">
      <h3 className="text-md font-semibold mb-2">Legend</h3>

      <div className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-color failure w-3 h-3 rounded-sm"></span>
        <span className="text-sm">Failure Zone (Initiation)</span>
      </div>

      <div className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-color transit w-3 h-3 rounded-sm"></span>
        <span className="text-sm">Transit Zone (Movement)</span>
      </div>

      <div className="legend-item flex items-center gap-2 mb-2">
        <span className="legend-color deposition w-3 h-3 rounded-sm"></span>
        <span className="text-sm">Deposition Zone (Accumulation)</span>
      </div>

      <hr className="my-2" />

      <div className="legend-item flex items-center gap-2">
        <span className="legend-gradient w-24 h-3 rounded-sm"></span>
        <span className="text-sm">Susceptibility (Low → High)</span>
      </div>
    </div>
  );
};

export default Legend;
