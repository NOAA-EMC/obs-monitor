import React from "react";
import { useParams } from "react-router-dom";
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "../data/channels";

function ChannelWrapper() {
    const { satellite, instrument, channelNumber } = useParams();

    // Map instrument names to channel data
    const instruments = { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 };
    const instrumentData = instruments[instrument];

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
                This is placeholder content for <strong>{satellite.toUpperCase()} / {" "} {instrumentData.name}</strong> channel <strong>{channelNumber}</strong>.
            </p>
        </div>
    );
}

export default ChannelWrapper;
