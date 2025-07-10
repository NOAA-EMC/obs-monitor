import React, { useEffect, useState, useMemo } from "react";
import { uvTypes } from "../data/uvtypes";
import TypeBlock from "./TypeBlock";
import { withBase } from '../utils/paths.js';

export default function UvObs({ openSection, toggleSection, navigate, cycleTime }) {
    const [assimilationStatus, setAssimilationStatus] = useState({});
    const [anomalyStatus, setAnomalyStatus] = useState({});
    const [filter, setFilter] = useState("all");
    const [hasAnyAnomaly, setHasAnyAnomaly] = useState(false);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(withBase("data/assimilationStatus_uv.json"));
                if (!res.ok) throw new Error("Assimilation file missing");
                const data = await res.json();
                setAssimilationStatus(data);
            } catch (err) {
                console.warn("Could not load assimilationStatus_uv.json", err);
                setAssimilationStatus({});
            }

            try {
                const res = await fetch(withBase(`data/anomalyStatus_uv_${cycleTime}.json`));
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

    const enrichedUvTypes = useMemo(() => {
        const enriched = uvTypes.map(({ uvkey, displayName }) => ({
            uvkey,
            displayName,
            assimilated: assimilationStatus[uvkey] ?? false,
            anomaly: anomalyStatus[uvkey] ?? "ok",
        }));

        const foundAnomaly = enriched.some((uv) => uv.anomaly && uv.anomaly !== "ok");
        setHasAnyAnomaly(foundAnomaly);

        return enriched;
    }, [assimilationStatus, anomalyStatus]);

    const filteredUvTypes = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedUvTypes.filter((uv) => uv.assimilated);
            case "anomalous":
                return enrichedUvTypes.filter((uv) => uv.anomaly !== "ok");
            default:
                return enrichedUvTypes;
        }
    }, [enrichedUvTypes, filter]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection("uv")}
                className="custom-button-category"
                style={{
                    backgroundColor: hasAnyAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                UV Observations
            </button>

            {openSection === "uv" && (
                <div className="ml-4 mt-1">
                    {/* Filter UI */}
                    <div className="mb-2">
                        <label htmlFor="uv-filter" className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id="uv-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Types</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                        </select>
                    </div>

                    {/* Filtered Uv list */}
                    {filteredUvTypes.map((uv) => (
                        <TypeBlock
                            type="uv"
                            key={uv.uvkey}
                            id={uv.uvkey}
                            displayName={uv.displayName}
                            assimilated={uv.assimilated}
                            anomaly={uv.anomaly}
                            navigate={navigate}
                        />

                    ))}
                </div>
            )}
        </div>
    );
}
