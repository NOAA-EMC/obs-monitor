import React, { useMemo, useState, useEffect } from 'react';
import OzoneBlock from './OzoneBlock.jsx';
import { ozoneSatellites } from '../data/ozonesats.js';
import { withBase } from '../utils/paths.js';

export default function OzoneObs({
    openSection,
    toggleSection,
    openSat,
    toggleSat,
    navigate,
    OMI,
    OMPSNP,
    OMPSTC8,
    cycleTime,
}) {
    const [openInstrument, setOpenInstrument] = useState(null);
    const [satelliteAnomalies, setSatelliteAnomalies] = useState({});

    const channelMap = {
        OMI: OMI.channels,
        OMPSNP: OMPSNP.channels,
        OMPSTC8: OMPSTC8.channels,
    };

    const instrumentToSats = useMemo(() => {
        const map = {};
        for (const sat of ozoneSatellites) {
            if (!map[sat.instrument]) {
                map[sat.instrument] = [];
            }
            map[sat.instrument].push(sat);
        }
        return map;
    }, []);

    useEffect(() => {
        if (!cycleTime) return;
        const fetchAllAnomalies = async () => {
            const newMap = {};

            await Promise.all(
                ozoneSatellites.map(async (sat) => {
                    const key = `${sat.satKey}_${sat.instrument}`;
                    const anomalyUrl = withBase(`data/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`);

                    try {
                        const res = await fetch(anomalyUrl);
                        if (res.ok) {
                            const data = await res.json();
                            const values = Object.values(data);
                            const hasAnomaly =
                                values.includes("high_error") ||
                                values.includes("low_count") ||
                                values.includes("missing") ||
                                values.includes("all"); // for missing full data
                            newMap[key] = hasAnomaly;
                        } else {
                            newMap[key] = false;
                        }
                    } catch {
                        newMap[key] = false;
                    }
                })
            );

            setSatelliteAnomalies(newMap);
        };

        fetchAllAnomalies();
    }, [cycleTime]);

    const reportAnomalyStatus = (satKey, hasAnomaly) => {
        setSatelliteAnomalies((prev) => {
            if (prev[satKey] === hasAnomaly) return prev; // avoid unnecessary state update
            const updated = { ...prev, [satKey]: hasAnomaly };
            console.debug('reportAnomalyStatus:', satKey, hasAnomaly, 'updated state:', updated);
            return updated;
        });
    };

    const instrumentHasAnomaly = (instrument) => {
        return instrumentToSats[instrument]?.some(
            (sat) => satelliteAnomalies[`${sat.satKey}_${instrument}`]
        );
    };

    const categoryHasAnomaly = Object.keys(instrumentToSats)
        .some((instrument) => instrumentHasAnomaly(instrument));

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection('ozn')}
                className="custom-button-category"
                style={{
                    backgroundColor: categoryHasAnomaly ? '#ffdfdf' : undefined
                }}
            >
                Ozone Observations
            </button>

            {openSection === 'ozn' && (
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
                                    backgroundColor: instrumentHasAnomaly(instrument)
                                        ? '#ffdfdf'
                                        : undefined,
                                }}
                            >
                                {instrument}
                            </button>

                            {openInstrument === instrument && (
                                <div className="ml-4 mt-1">
                                    {instrumentToSats[instrument].map((sat) => (
                                        <OzoneBlock
                                            key={`${sat.satKey}_${instrument}`}
                                            satKey={sat.satKey}
                                            displayName={sat.displayName}
                                            instrument={instrument}
                                            channels={channelMap[sat.channelKey]}
                                            openSat={openSat}
                                            toggleSat={toggleSat}
                                            navigate={navigate}
                                            cycleTime={cycleTime}
                                            reportAnomalyStatus={reportAnomalyStatus}
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
