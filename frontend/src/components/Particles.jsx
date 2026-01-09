import React from "react";

/**
 * Floating particles background effect
 * Add this to sidebar or any container for ambient animation
 */
const Particles = ({ count = 6 }) => {
    return (
        <div className="particles-container">
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="particle" />
            ))}
        </div>
    );
};

export default Particles;
