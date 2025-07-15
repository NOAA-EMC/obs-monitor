import React, { useEffect, useState, useMemo } from "react";
import { withBase } from '../utils/paths.js';

const getTextColor = (channel) => {
    if (!channel.assimilated) return "gray";
    if (channel.anomaly === "missing") return "red";
    if (channel.anomaly === "low_count" || channel.anomaly === "high_error") return "orange";
    return "black";
};

export default function SatelliteBlock({
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
    const [filter, setFilter] = useState("all");
    const [allMissing, setAllMissing] = useState(false);

    const satelliteTextColor = useMemo(() => {
        if (allMissing) return "red";
        const values = Object.values(anomaly);
        if (values.includes("high_error")) return "orange";
        if (values.some((v) => v && v !== "ok")) return "orange";
        return "black";
    }, [anomaly, allMissing]);

    const satelliteTooltip = useMemo(() => {
        if (allMissing) return "All data missing from current cycle";

        const values = Object.values(anomaly);
        if (values.includes("high_error")) return "High error value in one or more channels";
        if (values.includes("low_count")) return "Low observation counts in one or more channels";

        return "";  // No tooltip
    }, [anomaly, allMissing]);

    useEffect(() => {
        const fetchStatus = async () => {
            const anomalyFile = `anomalyStatus_${satKey}_${instrument}_${cycleTime}.json`;
            const assimFile = `assimilationStatus_${satKey}_${instrument}.json`;

            try {
                const anomalyRes = await fetch(withBase(`/data/${anomalyFile}`));
                if (!anomalyRes.ok) {
                    throw new Error(`Status file not found: ${anomalyFile}`);
                }
                const anomalyData = await anomalyRes.json();

                setAllMissing(anomalyData.all === "missing");
                setAnomaly(anomalyData);

                const hasAnomaly =
                    anomalyData.all === "missing" ||
                    Object.values(anomalyData).some((v) => v !== "ok");

                // Report using composite key here:
                reportAnomalyStatus?.(`${satKey}_${instrument}`, hasAnomaly);
            } catch (error) {
                console.warn(`Using default empty anomalyStatus for ${satKey}_${instrument}`, error);
                setAnomaly({});
                setAllMissing(false);
                reportAnomalyStatus?.(`${satKey}_${instrument}`, false);
            }

            try {
                const assimRes = await fetch(withBase(`/data/${assimFile}`));
                if (!assimRes.ok) {
                    console.warn(`Missing assimilation file for ${satKey}/${instrument}`);
                    setStatusAvailable(false);
                    return;
                }
                const assimData = await assimRes.json();
                setAssimilation(assimData);
                setStatusAvailable(true);
            } catch (error) {
                console.error(`Error loading assimilation status for ${satKey}/${instrument}:`, error);
                setStatusAvailable(false);
            }
        };

        if (cycleTime) {
            fetchStatus();
        }
    }, [satKey, instrument, cycleTime, reportAnomalyStatus]);

    const enrichedChannels = useMemo(() => {
        return channels.map((id) => ({
            id,
            assimilated: assimilation[id],
            anomaly: anomaly[id] || "ok",
        }));
    }, [channels, assimilation, anomaly]);

    const filteredChannels = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedChannels.filter((ch) => ch.assimilated);
            case "anomalous":
                return enrichedChannels.filter((ch) => ch.anomaly !== "ok");
            case "low_count":
                return enrichedChannels.filter((ch) => ch.anomaly === "low_count");
            default:
                return enrichedChannels;
        }
    }, [enrichedChannels, filter]);

    return (
        <div className="mb-2">
            <button
                onClick={() => toggleSat(satKey)}
                className="custom-button-satellite"
                style={{ color: satelliteTextColor }}
                title={
                    allMissing
                        ? "All data missing from current cycle"
                        : !enrichedChannels.some(ch => ch.assimilated)
                            ? "Not Assimilated"
                            : enrichedChannels.some(ch => ch.anomaly !== "ok")
                                ? enrichedChannels.find(ch => ch.anomaly !== "ok").anomaly
                                : "Assimilated"
                }
            >
                {displayName}
            </button>

            {openSat === satKey && (
                <div className="ml-4 mt-1">
                    <div className="mb-2">
                        <a
                            onClick={() => navigate(`/${satKey.toLowerCase()}/${instrument}/summary`)}
                            className="block px-2 py-1 hover:bg-gray-100 rounded cursor-pointer"
                        >
                            Summary
                        </a>
                    </div>

                    {!statusAvailable && (
                        <div style={{ color: "gray", fontStyle: "italic", marginBottom: "4px" }}>
                            Channel status unavailable
                        </div>
                    )}

                    <div className="mb-2">
                        <label htmlFor="channel-filter" className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id="channel-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Channels</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                            <option value="low_count">Low Count Only</option>
                        </select>
                    </div>

                    <ul>
                        {filteredChannels.map((channel) => (
                            <li
                                key={channel.id}
                                onClick={() =>
                                    navigate(`/${satKey.toLowerCase()}/${instrument}/${channel.id}`)
                                }
                                style={{
                                    color: getTextColor(channel),
                                    fontWeight: "bold",
                                    fontStyle: !channel.assimilated ? "italic" : "normal",
                                    marginBottom: "2px",
                                    cursor: "pointer",
                                    padding: "2px 6px",
                                    borderRadius: "4px",
                                }}
                                className="hover:bg-gray-100"
                                title={
                                    !channel.assimilated
                                        ? "Not Assimilated"
                                        : channel.anomaly !== "ok"
                                            ? channel.anomaly
                                            : "Assimilated"
                                }
                            >
                                Channel {channel.id}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
