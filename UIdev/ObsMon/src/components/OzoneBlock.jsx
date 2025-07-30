import React, { useEffect, useState, useMemo } from "react";
import { withBase } from '../utils/paths.js';

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
    const [assimilation, setAssimilation] = useState({});
    const [anomaly, setAnomaly] = useState({});
    const [statusAvailable, setStatusAvailable] = useState(true);
    const [allMissing, setAllMissing] = useState(false);
    const [filter, setFilter] = useState("all");

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const [assimilationRes, anomalyRes] = await Promise.all([
                    fetch(withBase(`data/assimilationStatus_${satKey}_${instrument}.json`)),
                    fetch(withBase(`data/anomalyStatus_${satKey}_${instrument}_${cycleTime}.json`)),
                ]);

                if (!assimilationRes.ok || !anomalyRes.ok) {
                    console.warn(`Missing status file(s) for ${satKey}/${instrument}`);
                    setStatusAvailable(false);
                    reportAnomalyStatus?.(satKey, false);
                    return;
                }

                const [assimilationJson, anomalyJson] = await Promise.all([
                    assimilationRes.json(),
                    anomalyRes.json(),
                ]);

                setAssimilation(assimilationJson);

                if (anomalyJson.all === "missing") {
                    setAllMissing(true);
                    setAnomaly({});
                    reportAnomalyStatus?.(satKey, true, instrument);
                } else {
                    setAllMissing(false);
                    setAnomaly(anomalyJson);
                    const hasAnomaly = Object.values(anomalyJson).some((v) => v !== "ok");
                    reportAnomalyStatus?.(satKey, hasAnomaly, instrument);
                }

                setStatusAvailable(true);
            } catch (error) {
                console.error(`Error loading status for ${satKey}/${instrument}:`, error);
                setStatusAvailable(false);
                reportAnomalyStatus?.(satKey, false, instrument);
            }
        };

        fetchStatus();
    }, [satKey, instrument, cycleTime, reportAnomalyStatus]);

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
