// src/components/Home.jsx
import React, { useEffect, useState } from "react";
import { withBase } from "../utils/paths";

export default function Home() {
    const [config, setConfig] = useState(null);

    useEffect(() => {
        let isMounted = true; // Track if component is mounted

        fetch(withBase("data/configIndex.json"))
            .then((res) => {
                if (!res.ok) {
                    throw new Error(`HTTP error! Status: ${res.status}`);
                }
                return res.json();
            })
            .then((data) => {
                if (isMounted) {
                    setConfig(data);
                }
            })
            .catch((err) => {
                if (isMounted) {
                    console.error("Failed to load configIndex.json:", err);
                }
            });

        return () => {
            isMounted = false; // Cleanup flag on unmount
        };
    }, []);

    if (!config) {
        return (
            <div style={{ padding: "2rem" }} role="status" aria-live="polite">
                Loading...
            </div>
        );
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
