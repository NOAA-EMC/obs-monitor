import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { withBase } from "../utils/paths.js";
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "../data/channels";
import { useCycle } from "./useCycle";

function ChannelWrapper() {
    const { type, satellite, instrument, channelNumber } = useParams();
    const [fileExists, setFileExists] = useState(null);
    const [filePath, setFilePath] = useState("");
    const cycle = useCycle();

    const instruments = { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 };
    const instrumentData = instruments[instrument];

    useEffect(() => {
        if (satellite && instrument && channelNumber && type && cycle) {
            const file = `pngs/${type.toLowerCase()}/${instrument.toLowerCase()}_${satellite.toLowerCase()}_chan${channelNumber}_${cycle}.png`;
            console.log("Checking file:", file);
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
    }, [satellite, instrument, channelNumber, type, cycle]);

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
                    src={withBase(`/${filePath}`)}
                    alt={`${instrument}_${satellite} channel ${channelNumber}`}
                    className="mt-4 max-w-full border rounded shadow"
                />
            )}
            {fileExists === false && (
                <p className="text-red-600 mt-4">
                    Image file <code>{filePath}</code> not available.
                </p>
            )}
        </div>
    );
}

export default ChannelWrapper;
