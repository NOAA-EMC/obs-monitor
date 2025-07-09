import React, { useEffect, useState, useMemo } from "react";
import { withBase } from '../utils/paths.js';

const getTextColor = (channel) => {
    if (!channel.assimilated) return "gray";
    if (channel.anomaly === "missing") return "red";
    if (channel.anomaly === "low_counts" || channel.anomaly === "high_error") return "orange";
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
        if (allMissing) return "Data missing from current cycle";

        const values = Object.values(anomaly);
        if (values.includes("high_error")) return "High error value in one or more channels";
        if (values.includes("low_counts")) return "Low observation counts in one or more channels";

        return "";  // No tooltip
    }, [anomaly, allMissing]);

    useEffect(() => {
        const hasAnomaly = anomaly["all"] === "missing" ||
            Object.values(anomaly).some((v) => v !== "ok");

        reportAnomalyStatus?.(satKey, hasAnomaly);
    }, [anomaly]);


    useEffect(() => {
        const fetchStatus = async () => {
            const anomaly_file = `anomalyStatus_${satKey}_${instrument}_${cycleTime}.json`;
            const assim_file = `assimilationStatus_${satKey}_${instrument}.json`;

            try {
                const response = await fetch(withBase(`/data/${anomaly_file}`));
                if (!response.ok) {
                    throw new Error(`Status file not found: ${anomaly_file}`);
                }

                const data = await response.json();
                if (data.all === "missing") {
                    setAllMissing(true);
                    setAnomaly({});  // Clear per-channel current-cycle anomalies
                } else {
                    setAllMissing(false);
                    setAnomaly(data);
                }

            } catch (error) {
                console.warn(`Using default empty anomalyStatus for ${satKey}_${instrument}`, error);
                setAnomaly({});
            }


            try {
                const [assimilationRes] = await Promise.all([
                    fetch(withBase(`/data/${assim_file}`)),
                ]);

                if (!assimilationRes.ok) {
                    console.warn(`Missing assimilation file for ${satKey}/${instrument}`);
                    setStatusAvailable(false);
                    return;
                }

                const [assimilationJson, anomalyJson] = await Promise.all([
                    assimilationRes.json()
                ]);

                setAssimilation(assimilationJson);
                setStatusAvailable(true);
            } catch (error) {
                console.error(`Error loading status for ${satKey}/${instrument}:`, error);
                setStatusAvailable(false);
            }
        };

        fetchStatus();
    }, [satKey, instrument, cycleTime]);

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
            case "low_counts":
                return enrichedChannels.filter((ch) => ch.anomaly === "low_counts");
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
                title={satelliteTooltip}
            >
                {displayName}
            </button>

            {openSat === satKey && (
                <div className="ml-4 mt-1">
                    {/* Always show Summary link */}
                    <div className="mb-2">
                        <a
                            onClick={() => navigate(`/${satKey.toLowerCase()}/${instrument}/summary`)}
                            className="block px-2 py-1 hover:bg-gray-100 rounded cursor-pointer"
                        >
                            Summary
                        </a>
                    </div>

                    {/* If status data is missing */}
                    {!statusAvailable && (
                        <div style={{ color: "gray", fontStyle: "italic", marginBottom: "4px" }}>
                            Channel status unavailable
                        </div>
                    )}

                    {/* Filter selection */}
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
                        </select>
                    </div>

                    {/* Channel list */}
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
                                            : ""
                                }
                            >
                                Channel {channel.id}
                            </li>
                        ))}
                    </ul>
                </div>
            )
            }
        </div >
    );
}
