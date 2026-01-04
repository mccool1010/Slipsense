import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FiMenu, FiX, FiMap, FiCloud } from "react-icons/fi";

const Navbar = ({ onToggleSidebar, sidebarOpen, weatherData }) => {
  return (
    <nav className="navbar">
      <div className="navbar-content">
        {/* Toggle Button (Left) */}
        <button
          className="navbar-toggle"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
        >
          <motion.div
            animate={{ rotate: sidebarOpen ? 90 : 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
          >
            {sidebarOpen ? <FiX size={24} /> : <FiMenu size={24} />}
          </motion.div>
        </button>

        {/* Weather Widget (Left of Brand) */}
        {weatherData && (
          <motion.div
            className="weather-widget"
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
          >
            <FiCloud className="weather-icon" />
            <div className="weather-info">
              <div className="weather-temp">{Math.round(weatherData.temp)}°C</div>
              <div className="weather-desc">{weatherData.description}</div>
              <div className="weather-rain">Rain: {weatherData.rainfall.toFixed(1)} mm</div>
            </div>
          </motion.div>
        )}

        {/* Brand + Logo */}
        <div className="navbar-brand">
          <FiMap className="navbar-icon" />
          <h1 className="navbar-title">SlipSense</h1>
          <p className="navbar-subtitle">Landslide Analytics</p>
        </div>

        {/* Center Spacer */}
        <div className="navbar-spacer"></div>
      </div>
    </nav>
  );
};

export default Navbar;
