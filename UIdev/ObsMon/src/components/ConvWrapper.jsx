import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { withBase } from "../utils/paths.js";
import { useModel } from "./ModelContext.jsx";
import { useResolveFile } from "../hooks/useFileExists.js";
import { CONVENTIONAL_TYPES } from "../data/conventionalTypes.js";

export default function noscUnifiedWrapper() {
    const { type, key, plot_type } = useParams();
    const [filePath, setFilePath] = useState("");
    const [plotTypeConfig, setPlotTypeConfig] = useState(null);
    const { model, component, cycleTime } = useModel();
    const { resolvedPath, notFound } = useResolveFile(filePath);
    const selectedPlotType = plot_type || "time-series";

    const titleMap = {
        q: "Q Data Time Series Page",
        t: "T Data Time Series Page",
        gps: "GPS Data Time Series Page",
        ps: "Station Pressure Data",
        uv: "UV Data Time Series Page"
    };

    const defaultTemplates = {
        "time-series": "data/${model}/gdas.${pdy}/${cyc}/${component}/${key}/stationPressure/${key}_time_series_*_${cycleTime}.png",
        "gridded-mean": "data/${model}/gdas.${pdy}/${cyc}/${component}/${key}/stationPressure/${key}_mean_stationPressure_global_binned_avg_*_${cycleTime}.png",
    };

    const renderTemplate = (template, values) => {
        return template.replace(/\$\{(\w+)\}/g, (_, token) => values[token] ?? "");
    };

    useEffect(() => {
        let cancelled = false;

        if (!type || !key || !model || !component) {
            setPlotTypeConfig(null);
            return;
        }

        const typeConfig = CONVENTIONAL_TYPES[type];
        if (!typeConfig) {
            setPlotTypeConfig(null);
            return;
        }

        const keyField = `${type}key`;

        fetch(withBase(`data/${model}/${component}/obs_types/${typeConfig.file}`), { cache: "no-store" })
            .then((res) => {
                if (!res.ok) throw new Error(`Failed to load ${typeConfig.file}`);
                return res.json();
            })
            .then((list) => {
                if (cancelled || !Array.isArray(list)) return;

                const matchedEntry = list.find((entry) => String(entry[keyField]) === String(key));
                const plotTypes = Array.isArray(matchedEntry?.plot_types) ? matchedEntry.plot_types : [];
                const matched = plotTypes.find((item) => item.plot_type === selectedPlotType) || null;
                setPlotTypeConfig(matched);
            })
            .catch(() => {
                if (!cancelled) setPlotTypeConfig(null);
            });

        return () => {
            cancelled = true;
        };
    }, [type, key, model, component, selectedPlotType]);

    useEffect(() => {
        if (type && key && cycleTime && model && component) {
            const pdy = cycleTime.slice(0, 8);
            const cyc = cycleTime.slice(8);

            const template = plotTypeConfig?.path_template
                || plotTypeConfig?.pathTemplate
                || defaultTemplates[selectedPlotType]
                || defaultTemplates["time-series"];

            const file = renderTemplate(template, {
                model,
                component,
                type,
                key,
                cycleTime,
                pdy,
                cyc,
                plot_type: selectedPlotType,
            });

            console.log("ConvWrapper file:", file);
            setFilePath(file);
        }
    }, [type, key, cycleTime, model, component, selectedPlotType, plotTypeConfig]);

    useEffect(() => {
        if (filePath) {
            console.log("ConvWrapper resolve status:", {
                filePath,
                resolvedPath,
                notFound
            });
        }
    }, [filePath, resolvedPath, notFound]);

    return (
        <div className="p-4">
            <h2 className="text-2xl font-bold mb-2">
                {plotTypeConfig?.label
                    ? `${titleMap[type] || "Unknown Data Type"} - ${plotTypeConfig.label}`
                    : (titleMap[type] || "Unknown Data Type")}
            </h2>
            {/* <p>
                Time-series plot, <strong>{type?.toUpperCase()}</strong> type{" "}
                <strong>{key}</strong>.
            </p> */}

            {resolvedPath === null && !notFound && <p>Checking for image...</p>}
            {resolvedPath !== null && (

                <img
                    src={withBase(resolvedPath)}
                    alt={`${type}${key} plot`}
                    className="mt-4 max-w-full border rounded shadow"
                />
            )}
            {notFound && (
                <p className="break-words text-red-600 mt-4">
                    Image file  <code>{filePath}</code>  not available.
                </p>
            )}
        </div>
    );
}
