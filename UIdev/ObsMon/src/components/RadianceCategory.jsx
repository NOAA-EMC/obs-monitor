import React, { useMemo, useState } from 'react';
import SatelliteBlock from './SatelliteBlock';
import { useModel } from './ModelContext';

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
    selectedModel,
}) {
    const { instrumentHasAnomaly, categoryHasAnomaly } = useModel();
    const [openInstrument, setOpenInstrument] = useState(null);

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

    const hasAnyCategoryAnomaly = categoryHasAnomaly(sectionKey);

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection(sectionKey)}
                className="custom-button-category"
                style={{ backgroundColor: hasAnyCategoryAnomaly ? "#ffdfdf" : undefined }}
            >
                {label}
            </button>

            {openSection === sectionKey && (
                <div className="ml-4 mt-1">
                    {Object.keys(instrumentToSats).sort().map((instrument) => {
                        const sats = instrumentToSats[instrument];
                        const hasAnomaly = instrumentHasAnomaly(sectionKey, instrument);

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
                                                model={selectedModel}
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
