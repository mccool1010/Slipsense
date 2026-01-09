import React from "react";
import { motion } from "framer-motion";

/**
 * Loading shimmer skeleton components
 * Use when content is loading to show placeholders
 */

export const ShimmerText = ({ width = "80%" }) => (
    <div className="shimmer shimmer-text" style={{ width }} />
);

export const ShimmerTitle = ({ width = "60%" }) => (
    <div className="shimmer shimmer-title" style={{ width }} />
);

export const ShimmerBox = ({ height = 100 }) => (
    <div className="shimmer shimmer-box" style={{ height }} />
);

/**
 * Loading overlay with spinner and progress bar
 */
export const LoadingOverlay = ({ text = "Loading..." }) => (
    <motion.div
        className="loading-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
    >
        <div className="loading-spinner" />
        <div className="loading-bar">
            <div className="loading-bar-progress" />
        </div>
        <span className="loading-text">{text}</span>
    </motion.div>
);

/**
 * Skeleton card placeholder
 */
export const SkeletonCard = () => (
    <div style={{ padding: "16px" }}>
        <ShimmerTitle />
        <ShimmerText />
        <ShimmerText width="60%" />
        <ShimmerBox height={80} />
    </div>
);

export default LoadingOverlay;
