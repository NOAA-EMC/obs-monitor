import React, { useMemo, useState, useEffect } from 'react';
import SatelliteBlock from './SatelliteBlock';
import { geostationarySatellites } from '../data/geosats';
import { withBase } from '../utils/paths';

export default function GeostationaryRad({
    openSection,
    toggleSection,
    openSat,
    toggleSat,
    navigate,
    ABI,
    AHI,
    cycleTime,
}) {
    const [anomalyMap, setAnomalyMap] = useState({});

    useEffect(() => {
        const fetchAllAnomalies = async () => {
            const newMap = {};

            await Promise.all(
                geostationarySatellites.map(async (sat) => {
                    const anomalyUrl = withBase(`data/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`);

                    try {
                        const res = await fetch(anomalyUrl);
                        if (res.ok) {
                            const data = await res.json();
                            const values = Object.values(data);
                            const hasAnomaly = values.includes("high_error") ||
                                values.includes("low_counts") ||
                                values.includes("missing") ||
                                values.includes("all");  // in case of missing full data
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


    const channelMap = {
        ABI: ABI.channels,
        AHI: AHI.channels,
    };
    // Group satellites by instrument
    const instrumentToSats = useMemo(() => {
        const map = {};
        for (const sat of geostationarySatellites) {
            if (!map[sat.instrument]) {
                map[sat.instrument] = [];
            }
            map[sat.instrument].push(sat);
        }
        return map;
    }, []);

    const [openInstrument, setOpenInstrument] = useState(null);
    const handleAnomalyStatus = (satKey, hasAnomaly) => {
        setAnomalyMap((prev) => ({ ...prev, [satKey]: hasAnomaly }));
    };

    const instrumentHasAnomaly = (instrument) => {
        return geostationarySatellites
            .filter((s) => s.instrument === instrument)
            .some((s) => anomalyMap[s.satKey]);
    };

    const categoryHasAnomaly = Object.keys(instrumentToSats)
        .some((instrument) => instrumentHasAnomaly(instrument));
    return (
        <div className="mb-4">

            <button
                onClick={() => toggleSection('geo')}
                className="custom-button-category"
                style={{
                    backgroundColor: categoryHasAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                Geostationary Radiance
            </button>

            {openSection === 'geo' && (
                <div className="ml-4 mt-1">
                    {Object.keys(instrumentToSats).sort().map((instrument) => (
                        <div key={instrument} className="mb-2">
                            <button
                                onClick={() =>
                                    setOpenInstrument(
                                        openInstrument === instrument ? null : instrument
                                    )
                                }
                                className="custom-button-instrument"
                                style={{
                                    backgroundColor: instrumentHasAnomaly(instrument) ? "#ffdfdf" : undefined,
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
                    ))}
                </div>
            )}
        </div>

    );
}
