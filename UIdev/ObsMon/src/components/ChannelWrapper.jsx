import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { withBase } from "../utils/paths.js";
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "../data/channels";
import { useModel } from "./ModelContext.jsx";
import { useFileExists } from "../hooks/useFileExists.js";

function ChannelWrapper() {
    const { type, satellite, instrument, channelNumber } = useParams();
    const [filePath, setFilePath] = useState("");
    const { model, component, cycleTime } = useModel();
    const fileExists = useFileExists(filePath);

    const instruments = { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 };
    const instrumentData = instruments[instrument];

    useEffect(() => {
        if (satellite && instrument && channelNumber && type && cycleTime) {
            const file = `data/${model}/${component}/${type.toLowerCase()}/${instrument.toLowerCase()}/${satellite.toLowerCase()}/${instrument.toLowerCase()}_${satellite.toLowerCase()}_chan_${channelNumber}_${cycleTime}.png`;
            setFilePath(file);
        }
    }, [satellite, instrument, channelNumber, type, cycleTime, model, component]);

    if (!instrumentData) {
        return (
            <div className="p-4">
                <h1 className="text-xl font-bold text-red-600">
                    Unknown instrument: {instrument}
                </h1>
            </div>
        );
    }

    return (
        <div className="p-4">
            <h1 className="text-2xl font-bold mb-2">
                {satellite.toUpperCase()} / {instrumentData.name} Channel {channelNumber}
            </h1>
            <p>
                This is a channel-level time-series for <strong>{satellite.toUpperCase()} / {instrumentData.name}</strong>, channel <strong>{channelNumber}</strong>.
            </p>

            {fileExists === null && <p>Checking for image...</p>}
            {fileExists === true && (
                <img
                    src={withBase(filePath)}
                    alt={`${instrument}_${satellite} channel ${channelNumber}`}
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

export default ChannelWrapper;
