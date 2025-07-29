import React, { useEffect, useState, useMemo } from "react";
import TypeBlock from "./TypeBlock.jsx";
import { withBase } from "../utils/paths.js";

export default function ConventionalObs({
    obsType,          // e.g., "gps", "ps", "q"
    typeList,         // e.g., gpsTypes, psTypes (array of { gpskey/pskey, displayName })
    keyProp,          // e.g., "gpskey", "pskey"
    displayLabel,     // e.g., "GPS Observations"
    openSection,
    toggleSection,
    navigate,
    cycleTime
}) {
    const [assimilationStatus, setAssimilationStatus] = useState({});
    const [anomalyStatus, setAnomalyStatus] = useState({});
    const [filter, setFilter] = useState("all");

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(withBase(`data/assimilationStatus_${obsType}.json`));
                if (!res.ok) throw new Error("Assimilation file missing");
                const data = await res.json();
                setAssimilationStatus(data);
            } catch (err) {
                console.warn(`Could not load assimilationStatus_${obsType}.json`, err);
                setAssimilationStatus({});
            }

            try {
                const res = await fetch(withBase(`data/anomalyStatus_${obsType}_${cycleTime}.json`));
                if (!res.ok) throw new Error("Anomaly file missing");
                const data = await res.json();
                setAnomalyStatus(data);
            } catch (err) {
                console.warn(`Missing anomaly file for ${obsType} at ${cycleTime}`, err);
                setAnomalyStatus({});
            }
        };

        if (cycleTime) {
            fetchStatus();
        }
    }, [obsType, cycleTime]);

    const enrichedTypes = useMemo(() => {
        return typeList.map((entry) => {
            const id = entry[keyProp];
            return {
                ...entry,
                id,
                assimilated: assimilationStatus[id] ?? false,
                anomaly: anomalyStatus[id] ?? "ok",
            };
        });
    }, [typeList, assimilationStatus, anomalyStatus, keyProp]);

    const filteredTypes = useMemo(() => {
        switch (filter) {
            case "assimilated":
                return enrichedTypes.filter((t) => t.assimilated);
            case "anomalous":
                return enrichedTypes.filter((t) => t.anomaly !== "ok");
            default:
                return enrichedTypes;
        }
    }, [enrichedTypes, filter]);

    const categoryHasAnomaly = enrichedTypes.some((t) => t.anomaly && t.anomaly !== "ok");

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection(obsType)}
                className="custom-button-category"
                style={{
                    backgroundColor: categoryHasAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                {displayLabel}
            </button>

            {openSection === obsType && (
                <div className="ml-4 mt-1">
                    <div className="mb-2">
                        <label htmlFor={`${obsType}-filter`} className="mr-2 font-medium">
                            Filter:
                        </label>
                        <select
                            id={`${obsType}-filter`}
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="border rounded px-2 py-1"
                        >
                            <option value="all">All Types</option>
                            <option value="assimilated">Assimilated Only</option>
                            <option value="anomalous">Anomalous Only</option>
                        </select>
                    </div>

                    {filteredTypes.map((entry) => (
                        <TypeBlock
                            key={entry.id}
                            type={obsType}
                            id={entry.id}
                            displayName={entry.displayName}
                            assimilated={entry.assimilated}
                            anomaly={entry.anomaly}
                            navigate={navigate}
                            cycleTime={cycleTime}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
