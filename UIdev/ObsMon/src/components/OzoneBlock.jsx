import React, { useState, useMemo } from "react";
import useStatusFetch from '../hooks/useStatusFetch';
import { useModel } from './ModelContext';

export default function OzoneBlock({
    satKey,
    displayName,
    instrument,
    channels,
    openSat,
    toggleSat,
    navigate,
    cycleTime,
    reportAnomalyStatus,
}) {
    const { model } = useModel();
    const { assimilation, anomaly, statusAvailable, allMissing } = useStatusFetch(satKey, instrument, cycleTime, model);
    const [filter, setFilter] = useState("all");



    const enrichedChannels = useMemo(() => {
        return channels.map((id) => ({
            id,
            assimilated: assimilation[id],
            anomaly: anomaly[id] || "ok",
        }));
    }, [channels, assimilation, anomaly]);

    const textColor = useMemo(() => {
        if (allMissing) return "red";
        const values = Object.values(anomaly);
        if (values.includes("high_error") || values.includes("low_count")) return "orange";
        return "black";
    }, [anomaly, allMissing]);

    const ozoneTooltip = useMemo(() => {
        if (allMissing) return "All data missing from current cycle";

        const values = Object.values(anomaly);
        if (values.includes("high_error")) return "High error value";
        if (values.includes("low_count")) return "Low observation count";

        return "";  // No tooltip
    }, [anomaly, allMissing]);


    return (
        <div className="mb-2">
            <button
                onClick={() => toggleSat(satKey)}
                className="custom-button-satellite"
                style={{ color: textColor }}
                title={ozoneTooltip}
            >
                {displayName}
            </button>

            {openSat === satKey && (
                <div className="ml-4 mt-1">
                    <div className="mb-2">
                        <a
                            onClick={() => navigate(`/ozn/${satKey.toLowerCase()}/${instrument}/summary`)}
                            className="block px-2 py-1 hover:bg-gray-100 rounded cursor-pointer"
                        >
                            Summary
                        </a>
                    </div>
                    <div className="mb-2">
                        <a
                            onClick={() => navigate(`/ozn/${satKey.toLowerCase()}/${instrument}/time`)}
                            className="block px-2 py-1 hover:bg-gray-100 rounded cursor-pointer"
                        >
                            Time Series
                        </a>
                    </div>

                    {!statusAvailable && (
                        <div style={{ color: "gray", fontStyle: "italic", marginBottom: "4px" }}>
                            Channel status unavailable
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
