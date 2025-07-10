import React, { useEffect, useState, useMemo } from "react";
import { psTypes } from "../data/pstypes";
import TypeBlock from "./TypeBlock";
import { withBase } from '../utils/paths.js';

export default function PsObs({ openSection, toggleSection, navigate, cycleTime }) {
    const [assimilationStatus, setAssimilationStatus] = useState({});
    const [anomalyStatus, setAnomalyStatus] = useState({});
    const [filter, setFilter] = useState("all");
    const [hasAnyAnomaly, setHasAnyAnomaly] = useState(false);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(withBase("data/assimilationStatus_ps.json"));
                if (!res.ok) throw new Error("Assimilation file missing");
                const data = await res.json();
                setAssimilationStatus(data);
            } catch (err) {
                console.warn("Could not load assimilationStatus_ps.json", err);
                setAssimilationStatus({});
            }

            try {
                const res = await fetch(withBase(`data/anomalyStatus_ps_${cycleTime}.json`));
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

    const enrichedPsTypes = useMemo(() => {
        const enriched = psTypes.map(({ pskey, displayName }) => ({
            pskey,
            displayName,
            assimilated: assimilationStatus[pskey] ?? false,
            anomaly: anomalyStatus[pskey] ?? "ok",
        }));

        const foundAnomaly = enriched.some((ps) => ps.anomaly && ps.anomaly !== "ok");
        setHasAnyAnomaly(foundAnomaly);

        return enriched;
    }, [assimilationStatus, anomalyStatus]);

    const filteredPsTypes = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedPsTypes.filter((ps) => ps.assimilated);
            case "anomalous":
                return enrichedPsTypes.filter((ps) => ps.anomaly !== "ok");
            default:
                return enrichedPsTypes;
        }
    }, [enrichedPsTypes, filter]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection("ps")}
                className="custom-button-category"
                style={{
                    backgroundColor: hasAnyAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                PS Observations
            </button>

            {openSection === "ps" && (
                <div className="ml-4 mt-1">
                    {/* Filter UI */}
                    <div className="mb-2">
                        <label htmlFor="ps-filter" className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id="ps-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Types</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                        </select>
                    </div>

                    {/* Filtered Ps list */}
                    {filteredPsTypes.map((ps) => (
                        <TypeBlock
                            type="ps"
                            key={ps.pskey}
                            id={ps.pskey}
                            displayName={ps.displayName}
                            assimilated={ps.assimilated}
                            anomaly={ps.anomaly}
                            navigate={navigate}
                            cycleTime={cycleTime}
                        />

                    ))}
                </div>
            )}
        </div>
    );
}
