import React, { useEffect, useState, useMemo } from "react";
import { qTypes } from "../data/qtypes";
import TypeBlock from "./TypeBlock";
import { withBase } from '../utils/paths.js';

export default function QObs({ openSection, toggleSection, navigate, cycleTime }) {
    const [assimilationStatus, setAssimilationStatus] = useState({});
    const [anomalyStatus, setAnomalyStatus] = useState({});
    const [filter, setFilter] = useState("all");
    const [hasAnyAnomaly, setHasAnyAnomaly] = useState(false);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(withBase("data/assimilationStatus_q.json"));
                if (!res.ok) throw new Error("Assimilation file missing");
                const data = await res.json();
                setAssimilationStatus(data);
            } catch (err) {
                console.warn("Could not load assimilationStatus_q.json", err);
                setAssimilationStatus({});
            }

            try {
                const res = await fetch(withBase(`data/anomalyStatus_q_${cycleTime}.json`));
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

    const enrichedQTypes = useMemo(() => {
        const enriched = qTypes.map(({ qkey, displayName }) => ({
            qkey,
            displayName,
            assimilated: assimilationStatus[qkey] ?? false,
            anomaly: anomalyStatus[qkey] ?? "ok",
        }));

        const foundAnomaly = enriched.some((t) => t.anomaly && t.anomaly !== "ok");
        setHasAnyAnomaly(foundAnomaly);

        return enriched;
    }, [assimilationStatus, anomalyStatus]);

    const filteredQTypes = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedQTypes.filter((t) => t.assimilated);
            case "anomalous":
                return enrichedQTypes.filter((t) => t.anomaly !== "ok");
            default:
                return enrichedQTypes;
        }
    }, [enrichedQTypes, filter]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection("q")}
                className="custom-button-category"
                style={{
                    backgroundColor: hasAnyAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                Q Observations
            </button>

            {openSection === "q" && (
                <div className="ml-4 mt-1">
                    {/* Filter UI */}
                    <div className="mb-2">
                        <label htmlFor="q-filter" className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id="q-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Types</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                        </select>
                    </div>

                    {/* Filtered Q list */}
                    {filteredQTypes.map((q) => (
                        <TypeBlock
                            type="q"
                            key={q.qkey}
                            id={q.qkey}
                            displayName={q.displayName}
                            assimilated={q.assimilated}
                            anomaly={q.anomaly}
                            navigate={navigate}
                            cycleTime={cycleTime}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
