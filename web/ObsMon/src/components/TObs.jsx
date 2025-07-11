import React, { useEffect, useState, useMemo } from "react";
import { tTypes } from "../data/ttypes";
import TypeBlock from "./TypeBlock";
import { withBase } from '../utils/paths.js';

export default function TObs({ openSection, toggleSection, navigate, cycleTime }) {
    const [assimilationStatus, setAssimilationStatus] = useState({});
    const [anomalyStatus, setAnomalyStatus] = useState({});
    const [filter, setFilter] = useState("all");
    const [hasAnyAnomaly, setHasAnyAnomaly] = useState(false);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(withBase("data/assimilationStatus_t.json"));
                if (!res.ok) throw new Error("Assimilation file missing");
                const data = await res.json();
                setAssimilationStatus(data);
            } catch (err) {
                console.warn("Could not load assimilationStatus_t.json", err);
                setAssimilationStatus({});
            }

            try {
                const res = await fetch(withBase(`data/anomalyStatus_t_${cycleTime}.json`));
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

    const enrichedTTypes = useMemo(() => {
        const enriched = tTypes.map(({ tkey, displayName }) => ({
            tkey,
            displayName,
            assimilated: assimilationStatus[tkey] ?? false,
            anomaly: anomalyStatus[tkey] ?? "ok",
        }));

        const foundAnomaly = enriched.some((t) => t.anomaly && t.anomaly !== "ok");
        setHasAnyAnomaly(foundAnomaly);

        return enriched;
    }, [assimilationStatus, anomalyStatus]);

    const filteredTTypes = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedTTypes.filter((t) => t.assimilated);
            case "anomalous":
                return enrichedTTypes.filter((t) => t.anomaly !== "ok");
            default:
                return enrichedTTypes;
        }
    }, [enrichedTTypes, filter]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection("t")}
                className="custom-button-category"
                style={{
                    backgroundColor: hasAnyAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                T Observations
            </button>

            {openSection === "t" && (
                <div className="ml-4 mt-1">
                    {/* Filter UI */}
                    <div className="mb-2">
                        <label htmlFor="t-filter" className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id="t-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Types</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                        </select>
                    </div>

                    {/* Filtered T list */}
                    {filteredTTypes.map((t) => (
                        <TypeBlock
                            type="t"
                            key={t.tkey}
                            id={t.tkey}
                            displayName={t.displayName}
                            assimilated={t.assimilated}
                            anomaly={t.anomaly}
                            navigate={navigate}
                            cycleTime={cycleTime}
                        />

                    ))}
                </div>
            )}
        </div>
    );
}
