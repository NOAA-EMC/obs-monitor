import { useEffect, useState } from 'react';
import { withBase } from '../utils/paths.js';
import { useModel } from '../components/ModelContext';

export default function useStatusFetch(satKey, instrument, cycleTime, model) {
    const { component } = useModel();
    const [assimilation, setAssimilation] = useState({});
    const [anomaly, setAnomaly] = useState({});
    const [statusAvailable, setStatusAvailable] = useState(true);
    const [allMissing, setAllMissing] = useState(false);

    useEffect(() => {
        if (!model || !component || !cycleTime) return;

        const fetchStatus = async () => {
            const assimUrl = withBase(`data/${model}/${component}/assim_status/assimilationStatus_${satKey}_${instrument}.json`);
            const anomUrl = withBase(`data/${model}/${component}/anom_status/anomalyStatus_${satKey}_${instrument}_${cycleTime}.json`);

            console.log(`Fetching status for ${satKey}/${instrument}:`, { assimUrl, anomUrl });

            try {
                const [assimilationRes, anomalyRes] = await Promise.all([
                    fetch(assimUrl),
                    fetch(anomUrl),
                ]);

                if (!assimilationRes.ok) {
                    console.warn(`Missing assimilation file for ${satKey}/${instrument}:`, assimilationRes.status);
                    setStatusAvailable(false);
                    setAssimilation({});
                    setAnomaly({});
                    setAllMissing(false);
                    return;
                }

                const assimilationJson = await assimilationRes.json();
                console.log(`Successfully loaded assimilation for ${satKey}/${instrument}:`, {
                    assimilationJson,
                    numAssimChannels: Object.keys(assimilationJson).length,
                });

                setAssimilation(assimilationJson);
                setStatusAvailable(true);

                // Anomaly file may not exist (404), but that's okay
                if (anomalyRes.ok) {
                    const anomalyJson = await anomalyRes.json();
                    console.log(`Successfully loaded anomaly for ${satKey}/${instrument}:`, anomalyJson);

                    if (anomalyJson.all === "missing") {
                        setAllMissing(true);
                        setAnomaly({});
                    } else {
                        setAllMissing(false);
                        setAnomaly(anomalyJson);
                    }
                } else {
                    console.warn(`Anomaly file not found for ${satKey}/${instrument} (${anomalyRes.status})`);
                    setAnomaly({});
                    setAllMissing(false);
                }
            } catch (error) {
                console.error(`Error loading status for ${satKey}/${instrument}:`, error);
                setStatusAvailable(false);
                setAllMissing(false);
                setAnomaly({});
                setAssimilation({});
            }
        };

        fetchStatus();
    }, [model, component, satKey, instrument, cycleTime]);

    return {
        assimilation,
        anomaly,
        statusAvailable,
        allMissing,
    };
}
