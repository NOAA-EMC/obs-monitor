import React, { useEffect, useMemo, useState } from 'react';
import SatelliteBlock from './SatelliteBlock';
import { withBase } from '../utils/paths';

export default function RadianceCategory({
    sectionKey,
    label,
    satelliteList,
    channelMap,
    openSection,
    toggleSection,
    openSat,
    toggleSat,
    navigate,
    cycleTime,
}) {
    const [openInstrument, setOpenInstrument] = useState(null);
    const [anomalyMap, setAnomalyMap] = useState({});

    // Add or update anomaly status when reported by SatelliteBlock
    const handleReportAnomalyStatus = (key, hasAnomaly) => {
        setAnomalyMap((prev) => {
            if (prev[key] === hasAnomaly) return prev;
            return { ...prev, [key]: hasAnomaly };
        });
    };

    // Group satellites by instrument
    const instrumentToSats = useMemo(() => {
        const map = {};
        for (const sat of satelliteList) {
            if (!map[sat.instrument]) {
                map[sat.instrument] = [];
            }
            map[sat.instrument].push(sat);
        }
        return map;
    }, [satelliteList]);

    // Eagerly prefetch anomaly status on mount / cycle change
    useEffect(() => {
        const fetchAllAnomalies = async () => {
            const newMap = {};

            await Promise.all(
                satelliteList.map(async (sat) => {
                    const key = `${sat.satKey}_${sat.instrument}`;
                    const anomalyUrl = withBase(`data/anomalyStatus_${key}_${cycleTime}.json`);
                    try {
                        const res = await fetch(anomalyUrl, { cache: 'no-store' });
                        if (res.ok) {
                            const data = await res.json();
                            const values = Object.values(data);
                            const hasAnomaly =
                                values.includes("high_error") ||
                                values.includes("low_count") ||
                                values.includes("missing") ||
                                values.includes("all");  // fallback: "all" is sometimes set when missing

                            newMap[key] = hasAnomaly;
                        } else {
                            newMap[key] = false;
                        }
                    } catch (err) {
                        console.warn(`Anomaly fetch failed for ${key}:`, err);
                        newMap[key] = false;
                    }
                })
            );

            setAnomalyMap(newMap);
        };

        if (cycleTime) {
            fetchAllAnomalies();
        }
    }, [satelliteList, cycleTime]);


    const instrumentHasAnomaly = (instrument) =>
        instrumentToSats[instrument]?.some(sat => anomalyMap[`${sat.satKey}_${instrument}`]);

    const categoryHasAnomaly = useMemo(() => {
        return Object.keys(instrumentToSats).some((instrument) =>
            instrumentHasAnomaly(instrument)
        );
    }, [instrumentToSats, anomalyMap]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection(sectionKey)}
                className="custom-button-category"
                style={{ backgroundColor: categoryHasAnomaly ? "#ffdfdf" : undefined }}
            >
                {label}
            </button>

            {openSection === sectionKey && (
                <div className="ml-4 mt-1">
                    {Object.keys(instrumentToSats).sort().map((instrument) => {
                        const sats = instrumentToSats[instrument];
                        const hasAnomaly = instrumentHasAnomaly(instrument);

                        return (
                            <div key={instrument} className="mb-2">
                                <button
                                    onClick={() =>
                                        setOpenInstrument(
                                            openInstrument === instrument ? null : instrument
                                        )
                                    }
                                    className="custom-button-instrument"
                                    style={{ backgroundColor: hasAnomaly ? "#ffdfdf" : undefined }}
                                >
                                    {instrument}
                                </button>

                                {openInstrument === instrument && (
                                    <div className="ml-4 mt-1">
                                        {sats.map((sat) => (
                                            <SatelliteBlock
                                                key={`${sat.satKey}_${instrument}`}
                                                satKey={sat.satKey}
                                                displayName={sat.displayName}
                                                instrument={instrument}
                                                channels={channelMap[sat.channelKey]}
                                                openSat={openSat}
                                                toggleSat={toggleSat}
                                                navigate={navigate}
                                                cycleTime={cycleTime}
                                                reportAnomalyStatus={handleReportAnomalyStatus}
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
