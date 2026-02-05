import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { withBase } from "../utils/paths.js";
import { useModel } from "./ModelContext.jsx";
import { useFileExists } from "../hooks/useFileExists.js";

function SummaryWrapper() {
    const { type, satellite, instrument } = useParams();
    const { model, component, cycleTime } = useModel();
    const [filePath, setFilePath] = useState("");
    const fileExists = useFileExists(filePath);

    useEffect(() => {
        if (satellite && instrument && cycleTime && type) {
            const file = `data/${model}/${component}/${type.toLowerCase()}/${instrument.toLowerCase()}/${satellite.toLowerCase()}/${instrument.toLowerCase()}_${satellite.toLowerCase()}_summary_${cycleTime}.png`;
            setFilePath(file);
        }
    }, [satellite, instrument, type, cycleTime, model, component]);

    if (!satellite || !instrument) {
        return (
            <div className="p-4">
                <h1 className="text-xl font-bold text-red-600">Missing satellite or instrument info</h1>
            </div>
        );
    }

    return (
        <div className="p-4 max-w-full overflow-x-auto">
            <h1 className="text-2xl font-bold mb-2">
                {satellite.toUpperCase()} / {instrument.toUpperCase()} Summary Page
            </h1>
            <p>
                This is a summary for <strong>{satellite.toUpperCase()}</strong> / <strong>{instrument}</strong>.
            </p>

            {fileExists === null && <p>Checking for image...<code>{filePath}</code></p>}
            {fileExists === true && (
                <img
                    src={withBase(filePath)}
                    alt={`${satellite}_${instrument} summary`}
                    className="mt-4 max-w-full border rounded shadow"
                />
            )}
            {fileExists === false && (
                <p className="break-words text-red-600 mt-4">
                    Image file <code>{filePath}</code> not available.
                </p>
            )}
        </div>
    );
}

export default SummaryWrapper;
