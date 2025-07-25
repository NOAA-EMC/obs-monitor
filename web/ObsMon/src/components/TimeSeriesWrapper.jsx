import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { withBase } from "../utils/paths.js";
import { useCycle } from "./useCycle";

function TimeSeriesWrapper() {
    const { type, satellite, instrument } = useParams();
    const cycle = useCycle();
    const [fileExists, setFileExists] = useState(null);

    const file = (type && satellite && instrument && cycle)
        ? `pngs/${type.toLowerCase()}/${instrument.toLowerCase()}_${satellite.toLowerCase()}_cnt_ts_${cycle}.png`
        : "";

    useEffect(() => {
        if (file) {
            fetch(withBase(`/utils/checkfile.php?file=${encodeURIComponent(file)}`))
                .then(res => res.text())
                .then(text => {
                    setFileExists(text.trim() === "true");
                })
                .catch(() => {
                    setFileExists(false);
                });
        }
    }, [file]);

    if (!satellite || !instrument) {
        return (
            <div className="p-4">
                <h1 className="text-xl font-bold text-red-600">Missing satellite or instrument info</h1>
            </div>
        );
    }

    return (
        <div className="p-4">
            <h1 className="text-2xl font-bold mb-2">
                {satellite.toUpperCase()} / {instrument.toUpperCase()} Time Series Page
            </h1>
            <p>
                Type: <strong>{type.toUpperCase()}</strong>
            </p>
            <p>
                Cycle: <strong>{cycle || "Loading..."}</strong>
            </p>
            <p>
                This is a time-series plot for <strong>{satellite.toUpperCase()}</strong> / <strong>{instrument}</strong>.
            </p>

            {fileExists === null && <p>Checking for image... <code>{file}</code></p>}
            {fileExists === true && (
                <img
                    src={withBase(`/${file}`)}
                    alt={`${satellite}_${instrument} summary`}
                    className="mt-4 max-w-full border rounded shadow"
                />
            )}
            {fileExists === false && (
                <p className="text-red-600 mt-4">
                    Image file <code>{file}</code> not available.
                </p>
            )}
        </div>
    );
}

export default TimeSeriesWrapper;
