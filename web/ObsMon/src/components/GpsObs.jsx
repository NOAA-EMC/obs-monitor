import React, { useEffect, useState, useMemo } from "react";
import { gpsTypes } from "../data/gpstypes";
import TypeBlock from "./TypeBlock";
import { withBase } from '../utils/paths.js';


export default function GpsObs({ openSection, toggleSection, navigate, cycleTime }) {
    const [assimilationStatus, setAssimilationStatus] = useState({});
    const [anomalyStatus, setAnomalyStatus] = useState({});
    const [filter, setFilter] = useState("all");

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                // const res = await fetch("/data/assimilationStatus_gps.json");
                const res = await fetch(withBase('data/assimilationStatus_gps.json'));
                if (!res.ok) throw new Error("Assimilation file missing");
                const data = await res.json();
                setAssimilationStatus(data);
            } catch (err) {
                console.warn("Could not load assimilationStatus_gps.json", err);
                setAssimilationStatus({});
            }

            try {
                // const res = await fetch(`/data/anomalyStatus_gps_${cycleTime}.json`);
                const res = await fetch(withBase(`data/anomalyStatus_gps_${cycleTime}.json`));
                if (!res.ok) throw new Error("Anomaly file missing");
                const data = await res.json();
                setAnomalyStatus(data);
            } catch (err) {
                console.warn(`Missing anomaly file for cycle ${cycleTime}`, err);
                setAnomalyStatus({});
            }
        };

        if (cycleTime) {
            fetchStatus();
        }
    }, [cycleTime]);

    const enrichedGpsTypes = useMemo(() => {
        return gpsTypes.map(({ gpskey, displayName }) => ({
            gpskey,
            displayName,
            assimilated: assimilationStatus[gpskey] ?? false,
            anomaly: anomalyStatus[gpskey] ?? "ok",
        }));
    }, [assimilationStatus, anomalyStatus]);

    const filteredGpsTypes = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedGpsTypes.filter((t) => t.assimilated);
            case "anomalous":
                return enrichedGpsTypes.filter((t) => t.anomaly !== "ok");
            default:
                return enrichedGpsTypes;
        }
    }, [enrichedGpsTypes, filter]);

    // ✅ Determine if any GPS type has an anomaly
    const categoryHasAnomaly = enrichedGpsTypes.some((g) => g.anomaly !== "ok");

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection("gps")}
                className="custom-button-category"
                style={{
                    backgroundColor: categoryHasAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                GPS Observations
            </button>

            {openSection === "gps" && (
                <div className="ml-4 mt-1">
                    {/* Filter UI */}
                    <div className="mb-2">
                        <label htmlFor="gps-filter" className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id="gps-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Types</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                        </select>
                    </div>

                    {/* Filtered GPS list */}
                    {filteredGpsTypes.map((gps) => (
                        <TypeBlock
                            type="gps"
                            key={gps.gpskey}
                            id={gps.gpskey}
                            displayName={gps.displayName}
                            assimilated={gps.assimilated}
                            anomaly={gps.anomaly}
                            navigate={navigate}
                            cycleTime={cycleTime}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}