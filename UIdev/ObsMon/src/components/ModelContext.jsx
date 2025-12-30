// src/ModelContext.jsx
import React, { createContext, useContext, useState, useEffect } from "react";

const ModelContext = createContext();

export function ModelProvider({ children }) {
    const [model, setModel] = useState("");
    const [component, setComponent] = useState("");

    const [availableModels, setAvailableModels] = useState([]);
    const [availableComponents, setAvailableComponents] = useState([]);

    const [modelConfig, setModelConfig] = useState(null);
    const [geoSats, setGeoSats] = useState([]);
    const [infraSats, setInfraSats] = useState([]);
    const [microSats, setMicroSats] = useState([]);
    const [ozoneSats, setOzoneSats] = useState([]);

    const [anomalies, setAnomalies] = useState({});
    const [cycleTime, setCycleTime] = useState(null);

    const reportAnomaly = (category, instrument, satKey, hasAnomaly) => {
        setAnomalies((prev) => ({
            ...prev,
            [category]: {
                ...(prev[category] || {}),
                [instrument]: {
                    ...((prev[category] || {})[instrument] || {}),
                    [satKey]: hasAnomaly,
                },
            },
        }));
    };

    const instrumentHasAnomaly = (category, instrument) => {
        const sats = anomalies?.[category]?.[instrument];
        if (!sats) return false;
        return Object.values(sats).some(Boolean);
    };

    const categoryHasAnomaly = (category) => {
        const instruments = anomalies?.[category];
        if (!instruments) return false;
        return Object.values(instruments).some((sats) =>
            Object.values(sats).some(Boolean)
        );
    };

    // Load models.json once
    useEffect(() => {
        const loadConfig = async () => {
            try {
                const res = await fetch("./data/models.json", { cache: "no-store" });
                if (!res.ok) throw new Error("Failed to load models.json");

                const json = await res.json();
                setModelConfig(json);

                const models = json.models || [];
                setAvailableModels(models);

                if (!model && models.length > 0) {
                    setModel(models[0]);
                }
            } catch (err) {
                console.error("Could not load model configuration:", err);
            }
        };

        loadConfig();
    }, []);

    // Load cycleTime when model is stable
    useEffect(() => {
        if (!model) return;

        const loadCycleTime = async () => {
            try {
                const res = await fetch(
                    `./data/${model}/latestCycle.json`,
                    { cache: "no-store" }
                );

                if (!res.ok) throw new Error("No cycle time");

                const json = await res.json();
                setCycleTime(json.cycleTime);
            } catch (err) {
                console.error("Failed to load cycleTime:", err);
                setCycleTime(null);
            }
        };

        loadCycleTime();
    }, [model, component]);

    // Update components when model changes
    useEffect(() => {
        if (!modelConfig || !model) return;

        const comps = modelConfig.components[model] || [];
        setAvailableComponents(comps);

        if (!comps.includes(component)) {
            setComponent(comps[0] || "");
        }
    }, [model, modelConfig]);

    // ✅ Load geosats when model changes
    useEffect(() => {
        if (!model) {
            setGeoSats([]);
            return;
        }

        const loadGeoSats = async () => {
            try {
                const res = await fetch(`./data/${model}/geosats.json`, {
                    cache: "no-store",
                });

                if (!res.ok) {
                    setGeoSats([]);
                    return;
                }

                const json = await res.json();
                setGeoSats(Array.isArray(json) ? json : []);
            } catch (err) {
                console.error("Failed to load geosats:", err);
                setGeoSats([]);
            }
        };

        loadGeoSats();
    }, [model]);

    useEffect(() => {
        if (!model) {
            setInfraSats([]);
            return;
        }

        const loadInfraSats = async () => {
            try {
                const res = await fetch(`./data/${model}/infrasats.json`, {
                    cache: "no-store",
                });

                if (!res.ok) {
                    setInfraSats([]);
                    return;
                }

                const json = await res.json();
                setInfraSats(Array.isArray(json) ? json : []);
            } catch (err) {
                console.error("Failed to load infraSats:", err);
                setInfraSats([]);
            }
        };

        loadInfraSats();
    }, [model]);

    useEffect(() => {
        if (!model) {
            setMicroSats([]);
            return;
        }

        const loadMicroSats = async () => {
            try {
                const res = await fetch(`./data/${model}/microsats.json`, {
                    cache: "no-store",
                });

                if (!res.ok) {
                    setMicroSats([]);
                    return;
                }

                const json = await res.json();
                setMicroSats(Array.isArray(json) ? json : []);
            } catch (err) {
                console.error("Failed to load microsats.json:", err);
                setMicroSats([]);
            }
        };

        loadMicroSats();
    }, [model]);

    useEffect(() => {
        if (!model) {
            setOzoneSats([]);
            return;
        }

        const loadOzoneSats = async () => {
            try {
                const res = await fetch(`./data/${model}/ozonesats.json`, {
                    cache: "no-store",
                });

                if (!res.ok) {
                    setOzoneSats([]);
                    return;
                }

                const json = await res.json();
                setOzoneSats(Array.isArray(json) ? json : []);
            } catch (err) {
                console.error("Failed to load ozonesats.json:", err);
                setOzoneSats([]);
            }
        };

        loadOzoneSats();
    }, [model]);


    useEffect(() => {
        if (!cycleTime || !model) return;

        const fetchMicrowaveAnomalies = async () => {
            for (const sat of microSats) {
                const url = `./data/${model}/${component}/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`;
                try {
                    const res = await fetch(url);
                    const data = await (res.ok ? res.json() : Promise.resolve({}));
                    const values = Object.values(data);
                    const hasAnomaly = values.some(v => ["high_error", "low_counts", "missing", "all"].includes(v));
                    reportAnomaly("microwave", sat.instrument, sat.satKey, hasAnomaly);
                } catch {
                    reportAnomaly("microwave", sat.instrument, sat.satKey, false);
                }
            }
        };

        fetchMicrowaveAnomalies();
    }, [cycleTime, model, component, microSats]);

    useEffect(() => {
        if (!cycleTime || !model) return;

        const fetchInfraredAnomalies = async () => {
            for (const sat of infraSats) {
                const url = `./data/${model}/${component}/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`;
                try {
                    const res = await fetch(url);
                    const data = await (res.ok ? res.json() : Promise.resolve({}));
                    const values = Object.values(data);
                    const hasAnomaly = values.some(v => ["high_error", "low_counts", "missing", "all"].includes(v));
                    reportAnomaly("infrared", sat.instrument, sat.satKey, hasAnomaly);
                } catch {
                    reportAnomaly("infrared", sat.instrument, sat.satKey, false);
                }
            }
        };

        fetchInfraredAnomalies();
    }, [cycleTime, model, component, infraSats]);

    useEffect(() => {
        if (!cycleTime || !model) return;

        const fetchGeostationaryAnomalies = async () => {
            for (const sat of geoSats) {
                const url = `./data/${model}/${component}/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`;
                try {
                    const res = await fetch(url);
                    const data = await (res.ok ? res.json() : Promise.resolve({}));
                    const values = Object.values(data);
                    const hasAnomaly = values.some(v => ["high_error", "low_counts", "missing", "all"].includes(v));
                    reportAnomaly("geostationary", sat.instrument, sat.satKey, hasAnomaly);
                } catch {
                    reportAnomaly("geostationary", sat.instrument, sat.satKey, false);
                }
            }
        };

        fetchGeostationaryAnomalies();
    }, [cycleTime, model, component, geoSats]);

    useEffect(() => {
        if (!cycleTime || !model) return;

        const fetchOzoneAnomalies = async () => {
            for (const sat of ozoneSats) {
                const url = `./data/${model}/${component}/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`;
                try {
                    const res = await fetch(url);
                    const data = await (res.ok ? res.json() : Promise.resolve({}));
                    const values = Object.values(data);
                    const hasAnomaly = values.some(v => ["high_error", "low_counts", "missing", "all"].includes(v));
                    reportAnomaly("ozone", sat.instrument, sat.satKey, hasAnomaly);
                } catch {
                    reportAnomaly("ozone", sat.instrument, sat.satKey, false);
                }
            }
        };

        fetchOzoneAnomalies();
    }, [cycleTime, model, component, ozoneSats]);

    return (
        <ModelContext.Provider
            value={{
                model,
                setModel,
                component,
                setComponent,
                availableModels,
                availableComponents,
                anomalies,
                reportAnomaly,
                instrumentHasAnomaly,
                categoryHasAnomaly,
                geoSats,
                infraSats,
                microSats,
                ozoneSats,
                cycleTime,
                setCycleTime,
            }}
        >
            {children}
        </ModelContext.Provider>
    );
}

export function useModel() {
    return useContext(ModelContext);
}
