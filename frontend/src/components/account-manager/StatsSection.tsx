import React from "react";

export default function StatsGrid() {
    const stats = [
      { value: '3K+', label: 'Videos launched monthly' },
      { value: '1.2K', label: 'Creators thriving' },
      { value: '5M+', label: 'Views delivered' },
      { value: '24/7', label: 'Always-on scheduling' },
    ];
    return (
      <div className="lg:col-span-1 grid grid-cols-2 gap-4 text-center">
        {stats.map((s) => (
          <div key={s.label}>
            <h3 className="text-3xl font-bold">{s.value}</h3>
            <p className="text-sm text-gray-400">{s.label}</p>
          </div>
        ))}
      </div>
    );
  }