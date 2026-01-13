import React, { useMemo, useState } from 'react';
import OzoneBlock from './OzoneBlock.jsx';
import { useModel } from './ModelContext';

export default function OzoneObs({
    openSection,
    toggleSection,
    openSat,
    toggleSat,
    navigate,
    ozoneSatellites,
    channelMap,
    cycleTime,
}) {
    const { instrumentHasAnomaly, categoryHasAnomaly } = useModel();
    const [openInstrument, setOpenInstrument] = useState(null);

    const instrumentToSats = useMemo(() => {
        const map = {};
        for (const sat of ozoneSatellites) {
            if (!map[sat.instrument]) {
                map[sat.instrument] = [];
            }
            map[sat.instrument].push(sat);
        }
        return map;
    }, [ozoneSatellites]);

    const hasAnyCategoryAnomaly = categoryHasAnomaly('ozone');

    return (
        <div className="mb-4">
            <button
                onClick={() => toggleSection('ozone')}
                className="custom-button-category"
                style={{
                    backgroundColor: hasAnyCategoryAnomaly ? '#ffdfdf' : undefined
                }}
            >
                Ozone Observations
            </button>

            {openSection === 'ozone' && (
                <div className="ml-4 mt-1">
                    {Object.keys(instrumentToSats).sort().map((instrument) => {
                        const sats = instrumentToSats[instrument];
                        const hasAnomaly = instrumentHasAnomaly('ozone', instrument);

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
                                        backgroundColor: hasAnomaly ? '#ffdfdf' : undefined,
                                    }}
                                >
                                    {instrument}
                                </button>

                                {openInstrument === instrument && (
                                    <div className="ml-4 mt-1">
                                        {sats.map((sat) => (
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
