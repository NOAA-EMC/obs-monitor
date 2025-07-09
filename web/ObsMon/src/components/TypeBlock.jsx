import React, { useMemo } from "react";

const getTextColor = (assimilated, anomaly) => {
    if (!assimilated) return "gray";
    if (anomaly === "missing") return "red";
    if (anomaly === "high_error" || anomaly === "low_counts") return "orange";
    return "black";
};

export default function TypeBlock({ type, id, displayName, assimilated, anomaly, navigate }) {
    const textColor = getTextColor(assimilated, anomaly);
    const fontStyle = assimilated ? "normal" : "italic";

    const tooltip = useMemo(() => {
        if (anomaly === "missing") return "Data missing from current cycle";
        if (anomaly === "high_error") return "High error value";
        if (anomaly === "low_counts") return "Low observation count";
        return assimilated ? "Assimilated" : "Not Assimilated";
    }, [anomaly, assimilated]);

    return (
        <div className="mb-2">
            <button
                onClick={() => navigate(`/${type}/${id}`)}
                className="custom-button-satellite"
                style={{ color: textColor, fontStyle }}
                title={tooltip}
            >
                {displayName}
            </button>
        </div>
    );
}
