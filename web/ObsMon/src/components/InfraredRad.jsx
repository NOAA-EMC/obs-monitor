import React, { useEffect, useMemo, useState } from 'react';
import SatelliteBlock from './SatelliteBlock';
import { infraredSatellites } from '../data/infrasats';
import { withBase } from '../utils/paths';

export default function InfraredRad({
    openSection,
    toggleSection,
    openSat,
    toggleSat,
    navigate,
    CrIS,
    IASI,
    cycleTime,
}) {
    const channelMap = {
        CrIS: CrIS.channels,
        IASI: IASI.channels,
    };

    // Group satellites by instrument
    const instrumentToSats = useMemo(() => {
        const map = {};
        for (const sat of infraredSatellites) {
            if (!map[sat.instrument]) {
                map[sat.instrument] = [];
            }
            map[sat.instrument].push(sat);
        }
        return map;
    }, []);

    const [openInstrument, setOpenInstrument] = useState(null);
    const [anomalyMap, setAnomalyMap] = useState({});

    const handleAnomalyStatus = (satKey, hasAnomaly) => {
        setAnomalyMap((prev) => ({ ...prev, [satKey]: hasAnomaly }));
    };

    const instrumentHasAnomaly = (instrument) => {
        return infraredSatellites
            .filter((s) => s.instrument === instrument)
            .some((s) => anomalyMap[s.satKey]);
    };

    const categoryHasAnomaly = Object.keys(instrumentToSats)
        .some((instrument) => instrumentHasAnomaly(instrument));

    // Eagerly fetch anomaly status for all infrared satellites
    useEffect(() => {
        const fetchAllAnomalies = async () => {
            const newMap = {};

            await Promise.all(
                infraredSatellites.map(async (sat) => {
                    // const anomalyUrl = `/data/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`;
                    const anomalyUrl = withBase(`data/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`);
                    try {
                        const res = await fetch(anomalyUrl);
                        if (res.ok) {
                            const data = await res.json();
                            const values = Object.values(data);
                            const hasAnomaly = values.includes("high_error") ||
                                values.includes("low_counts") ||
                                values.includes("missing") ||
                                values.includes("all");
                            newMap[sat.satKey] = hasAnomaly;
                        } else {
                            newMap[sat.satKey] = false;
                        }
                    } catch {
                        newMap[sat.satKey] = false;
                    }
                })
            );

            setAnomalyMap(newMap);
        };

        if (cycleTime) {
            fetchAllAnomalies();
        }
    }, [cycleTime]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection('inf')}
                className="custom-button-category"
                style={{
                    backgroundColor: categoryHasAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                Infrared Observations
            </button>

            {openSection === 'inf' && (
                <div className="ml-4 mt-1">
                    {Object.keys(instrumentToSats).sort().map((instrument) => {
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
                                    style={{
                                        backgroundColor: hasAnomaly ? "#ffdfdf" : undefined,
                                    }}
                                >
                                    {instrument}
                                </button>

                                {openInstrument === instrument && (
                                    <div className="ml-4 mt-1">
                                        {instrumentToSats[instrument].map((sat) => (
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
                                                reportAnomalyStatus={handleAnomalyStatus}
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
