import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

/**
 * Hook to create click ripple effects
 * Returns { ripples, createRipple, RippleContainer }
 */
export const useRipple = () => {
    const [ripples, setRipples] = useState([]);

    const createRipple = useCallback((e) => {
        const rect = e.currentTarget
            ? e.currentTarget.getBoundingClientRect()
            : { left: 0, top: 0 };

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const ripple = {
            id: Date.now(),
            x,
            y,
        };

        setRipples((prev) => [...prev, ripple]);

        // Remove ripple after animation
        setTimeout(() => {
            setRipples((prev) => prev.filter((r) => r.id !== ripple.id));
        }, 800);
    }, []);

    return { ripples, createRipple };
};

/**
 * Map click ripple component
 * Place at x,y coordinates to show ripple effect
 */
export const MapRipple = ({ x, y, onComplete }) => {
    React.useEffect(() => {
        const timer = setTimeout(() => {
            if (onComplete) onComplete();
        }, 800);
        return () => clearTimeout(timer);
    }, [onComplete]);

    return (
        <motion.div
            className="map-ripple"
            style={{
                left: x - 15,
                top: y - 15,
            }}
            initial={{ scale: 0, opacity: 0.7 }}
            animate={{ scale: 4, opacity: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
        />
    );
};

/**
 * Ripple container component for buttons and interactive elements
 */
export const RippleButton = ({ children, onClick, className = "", ...props }) => {
    const { ripples, createRipple } = useRipple();

    const handleClick = (e) => {
        createRipple(e);
        if (onClick) onClick(e);
    };

    return (
        <button
            className={`ripple-container ${className}`}
            onClick={handleClick}
            {...props}
        >
            {children}
            <AnimatePresence>
                {ripples.map((ripple) => (
                    <motion.span
                        key={ripple.id}
                        className="ripple"
                        style={{
                            left: ripple.x - 10,
                            top: ripple.y - 10,
                        }}
                        initial={{ scale: 0, opacity: 0.6 }}
                        animate={{ scale: 4, opacity: 0 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.6, ease: "easeOut" }}
                    />
                ))}
            </AnimatePresence>
        </button>
    );
};

export default MapRipple;
