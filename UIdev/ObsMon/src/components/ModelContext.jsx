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

        if (comps.length > 0 && !comps.includes(component)) {
            setComponent(comps[0] || "");
        }
    }, [model, modelConfig]);

    // Load satellite data files when model/component changes
    useEffect(() => {
        if (!model || !component) {
            setGeoSats([]);
            setInfraSats([]);
            setMicroSats([]);
            setOzoneSats([]);
            return;
        }

        const loadSatelliteFile = async (filename, setter, label) => {
            try {
                const res = await fetch(`./data/${model}/${component}/obs_types/${filename}`, {
                    cache: "no-store",
                });

                if (!res.ok) {
                    setter([]);
                    return;
                }

                const json = await res.json();
                setter(Array.isArray(json) ? json : []);
            } catch (err) {
                console.error(`Failed to load ${label}:`, err);
                setter([]);
            }
        };

        loadSatelliteFile("geostationarysats.json", setGeoSats, "geostationarysats");
        loadSatelliteFile("infraredsats.json", setInfraSats, "infraredsats");
        loadSatelliteFile("microwavesats.json", setMicroSats, "microwavesats");
        loadSatelliteFile("ozonesats.json", setOzoneSats, "ozonesats");
    }, [model, component]);

    // Fetch anomalies for all satellite categories
    useEffect(() => {
        if (!cycleTime || !model || !component) return;

        const fetchAnomaliesForCategory = async (category, satellites, pathPrefix = "anom_status") => {
            for (const sat of satellites) {
                const url = `./data/${model}/${component}/${pathPrefix}/anomalyStatus_${sat.satKey}_${sat.instrument}_${cycleTime}.json`;
                try {
                    const res = await fetch(url);
                    const data = await (res.ok ? res.json() : Promise.resolve({}));
                    const values = Object.values(data);
                    const hasAnomaly = values.some(v => ["high_error", "low_counts", "missing", "all"].includes(v));
                    reportAnomaly(category, sat.instrument, sat.satKey, hasAnomaly);
                } catch {
                    reportAnomaly(category, sat.instrument, sat.satKey, false);
                }
            }
        };

        fetchAnomaliesForCategory("microwave", microSats);
        fetchAnomaliesForCategory("infrared", infraSats);
        fetchAnomaliesForCategory("geostationary", geoSats);
        fetchAnomaliesForCategory("ozone", ozoneSats);
    }, [cycleTime, model, component, microSats, infraSats, geoSats, ozoneSats]);

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
