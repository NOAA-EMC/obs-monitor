// src/components/Home.jsx
import React, { useEffect, useState } from "react";
import { withBase } from "../utils/paths";

export default function Home() {
    const [config, setConfig] = useState(null);

    useEffect(() => {
        fetch(withBase("data/configIndex.json"))
            .then((res) => {
                if (!res.ok) {
                    throw new Error(`HTTP error! Status: ${res.status}`);
                }
                return res.json();
            })
            .then((data) => {
                setConfig(data);
            })
            .catch((err) => {
                console.error("Failed to load config.json:", err);
            });
    }, []);

    if (!config) {
        return <div style={{ padding: "2rem" }}>Loading...</div>;
    }

    return (
        <div style={{ padding: "2rem" }}>
            <h1>Welcome to ObsMon</h1>
            <h2>
                {config.type} {config.name}
            </h2>
            {config.description && <p>{config.description}</p>}
        </div>
    );
}
