import React, { useMemo } from "react";

const getTextColor = (assimilated, anomaly) => {
    if (!assimilated) return "gray";
    if (anomaly === "missing") return "red";
    if (anomaly === "high_error" || anomaly === "low_count") return "orange";
    return "black";
};

export default function TypeBlock({
    type,
    id,
    displayName,
    assimilated,
    anomaly,
    navigate,
    plotTypes = [],
    isOpen = false,
    onToggle,
}) {
    const textColor = getTextColor(assimilated, anomaly);
    const fontStyle = assimilated ? "normal" : "italic";
    const hasPlotTypes = Array.isArray(plotTypes) && plotTypes.length > 0;

    const tooltip = useMemo(() => {
        if (anomaly === "missing") return "Data missing from current cycle";
        if (anomaly === "high_error") return "High error value";
        if (anomaly === "low_count") return "Low observation count";
        return assimilated ? "Assimilated" : "Not Assimilated";
    }, [anomaly, assimilated]);

    return (
        <div className="mb-2">
            <button
                onClick={() => {
                    if (hasPlotTypes) {
                        onToggle?.();
                    } else {
                        navigate(`/${type}/${id}`);
                    }
                }}
                className="custom-button-satellite"
                style={{ color: textColor, fontStyle }}
                title={tooltip}
            >
                {displayName}
            </button>

            {hasPlotTypes && isOpen && (
                <div className="ml-4 mt-1 space-y-1">
                    {plotTypes.map((entry) => {
                        const plotTypeId = entry.plot_type;
                        const label = entry.label || entry.plot_type;

                        return (
                            <button
                                key={plotTypeId}
                                onClick={() => navigate(`/${type}/${id}/${plotTypeId}`)}
                                className="custom-button-satellite"
                                style={{ color: "black" }}
                            >
                                {label}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
