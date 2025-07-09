import React, { useEffect, useMemo, useState } from 'react';
import SatelliteBlock from './SatelliteBlock';
import { microwaveSatellites } from '../data/microwavesats';
import { withBase } from '../utils/paths.js';

export default function MicrowaveRad({
    openSection,
    toggleSection,
    openSat,
    toggleSat,
    navigate,
    AMSUA,
    ATMS,
    MHS,
    SSMIS,
    cycleTime,
}) {
    const [anomalyMap, setAnomalyMap] = useState({});

    // Prefetch anomaly status for all sat/instrument pairs when cycleTime is ready
    useEffect(() => {
        if (!cycleTime) return;

        const loadAllAnomalies = async () => {
            const newMap = {};

            for (const { satKey, instrument } of microwaveSatellites) {
                const key = `${satKey}_${instrument}`;
                try {
                    // const res = await fetch(`/data/anomalyStatus_${key}_${cycleTime}.json`);
                    const res = await fetch(withBase(`data/anomalyStatus_${key}_${cycleTime}.json`));

                    if (!res.ok) throw new Error("Not found");

                    const data = await res.json();

                    const hasAnomaly =
                        data.all === "missing" ||
                        Object.values(data).some((v) => v && v !== "ok");

                    newMap[key] = hasAnomaly;
                } catch {
                    newMap[key] = false;
                }
            }

            setAnomalyMap(newMap);
        };

        loadAllAnomalies();
    }, [cycleTime]);

    const instrumentHasAnomaly = (instrument) =>
        microwaveSatellites
            .filter((s) => s.instrument === instrument)
            .some((s) => anomalyMap[`${s.satKey}_${instrument}`]);

    const channelMap = {
        AMSUA: AMSUA.channels,
        ATMS: ATMS.channels,
        MHS: MHS.channels,
        SSMIS: SSMIS.channels,
    };

    const instrumentToSats = useMemo(() => {
        const map = {};
        for (const sat of microwaveSatellites) {
            if (!map[sat.instrument]) map[sat.instrument] = [];
            map[sat.instrument].push(sat);
        }
        return map;
    }, []);

    const [openInstrument, setOpenInstrument] = useState(null);

    const categoryHasAnomaly = useMemo(() => {
        return Object.keys(instrumentToSats).some((instrument) =>
            instrumentHasAnomaly(instrument)
        );
    }, [anomalyMap, instrumentToSats]);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection('mw')}
                className="custom-button-category"
                style={{
                    backgroundColor: categoryHasAnomaly ? "#ffdfdf" : undefined,
                }}
            >
                Microwave Observations
            </button>

            {openSection === 'mw' && (
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
                                                reportAnomalyStatus={() => { }}
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