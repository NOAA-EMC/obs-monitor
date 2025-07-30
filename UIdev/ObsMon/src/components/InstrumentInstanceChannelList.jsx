import React, { useEffect, useState, useMemo } from "react";
import { MHS } from "../data/channels";

// Utility for styling
const getTextColor = (channel) => {
    if (!channel.assimilated) return "gray";
    if (channel.anomaly === "low_count") return "orange";
    if (channel.anomaly === "high_error") return "red";
    return "black";
};

export default function InstrumentInstanceChannelList({ satellite, instrument }) {
    const [assimilation, setAssimilation] = useState({});
    const [anomaly, setAnomaly] = useState({});

    // Construct status filenames
    const statusBase = `../data`;
    const assimPath = `${statusBase}/assimilationStatus_${satellite}_${instrument}.json`;
    const anomalyPath = `${statusBase}/anomalyStatus_${satellite}_${instrument}.json`;

    useEffect(() => {
        const fetchStatus = async () => {
            const [assimilationRes, anomalyRes] = await Promise.all([
                fetch(assimPath),
                fetch(anomalyPath),
            ]);
            setAssimilation(await assimilationRes.json());
            setAnomaly(await anomalyRes.json());
        };

        fetchStatus();
    }, [assimPath, anomalyPath]);

    const instrumentDef = MHS; // Could be dynamically chosen later

    const enrichedChannels = useMemo(() => {
        return instrumentDef.channels.map((id) => ({
            id,
            assimilated: assimilation[id],
            anomaly: anomaly[id] || "ok",
        }));
    }, [instrumentDef, assimilation, anomaly]);

    return (
        <div>
            <h2>{satellite} / {instrument} Channels</h2>
            <ul>
                {enrichedChannels.map((channel) => (
                    <li
                        key={channel.id}
                        style={{
                            color: getTextColor(channel),
                            fontWeight: "bold",
                            marginBottom: "4px"
                        }}
                    >
                        Channel {channel.id}
                        {channel.anomaly !== "ok" && ` (${channel.anomaly})`}
                        {!channel.assimilated && " [Not Assimilated]"}
                    </li>
                ))}
            </ul>
        </div>
    );
}
