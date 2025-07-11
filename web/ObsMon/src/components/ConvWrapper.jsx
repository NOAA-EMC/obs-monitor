import React from "react";
import { useParams } from "react-router-dom";

export default function UnifiedWrapper() {
    const { type, key } = useParams();

    const titleMap = {
        q: "Q Data Time Series Page",
        t: "T Data Time Series Page",
        gps: "GPS Data Time Series Page",
    };

    return (
        <div className="p-4">
            <h2 className="text-2xl font-bold mb-2">
                {titleMap[type] || "Unknown Data Type"}
            </h2>
            <p>
                This is a placeholder for the time-series plot for <strong>{type?.toUpperCase()}</strong> type{" "}
                <strong>{key}</strong>.
            </p>
            {/* Insert your plot component here */}
        </div>
    );
}
