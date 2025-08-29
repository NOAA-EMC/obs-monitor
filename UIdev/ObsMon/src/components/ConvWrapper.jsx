import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { withBase } from "../utils/paths.js";
import { useCycle } from "./useCycle";

export default function UnifiedWrapper() {
    const { type, key } = useParams();
    const [fileExists, setFileExists] = useState(null);  // null = checking
    const [filePath, setFilePath] = useState("");
    const cycle = useCycle();

    const titleMap = {
        q: "Q Data Time Series Page",
        t: "T Data Time Series Page",
        gps: "GPS Data Time Series Page",
        ps: "PS Data Time Series Page",
        uv: "UV Data Time Series Page"
    };

    useEffect(() => {
        if (type && key && cycle) {
            const file = `pngs/conv/${type}${key}_count_region1_lev1.${cycle}.png`;
            setFilePath(file);

            fetch(withBase(`/utils/checkfile.php?file=${encodeURIComponent(file)}`))
                .then(res => res.text())
                .then(text => {
                    setFileExists(text.trim() === "true");
                })
                .catch(() => {
                    setFileExists(false);
                });
        }
    }, [type, key, cycle]);

    return (
        <div className="p-4">
            <h2 className="text-2xl font-bold mb-2">
                {titleMap[type] || "Unknown Data Type"}
            </h2>
            <p>
                Time-series plot, global, all levels, <strong>{type?.toUpperCase()}</strong> type{" "}
                <strong>{key}</strong>.
            </p>

            {fileExists === null && <p>Checking for image...</p>}
            {fileExists === true && (

                <img
                    src={withBase(`/${filePath}`)}
                    alt={`${type}${key} plot`}
                    className="mt-4 max-w-full border rounded shadow"
                />
            )}
            {fileExists === false && (
                <p className="break-words text-red-600 mt-4">
                    Image file  <code>{filePath}</code>  not available.
                </p>
            )}
        </div>
    );
}
