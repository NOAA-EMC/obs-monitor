import { useEffect, useState } from "react";
import { withBase } from "../utils/paths.js";

/**
 * Hook to resolve a file path that may contain a * wildcard via checkfile.php glob support.
 * @param {string} pattern - Relative file path, optionally containing *
 * @returns {{ resolvedPath: string|null, notFound: boolean }} -
 *   resolvedPath is the matched path (or the original if no wildcard), null while checking.
 *   notFound is true when the server confirmed no match.
 */
export function useResolveFile(pattern) {
    const [resolvedPath, setResolvedPath] = useState(null);
    const [notFound, setNotFound] = useState(false);

    useEffect(() => {
        let isActive = true;
        const controller = new AbortController();

        if (!pattern) {
            setResolvedPath(null);
            setNotFound(false);
            return () => {
                isActive = false;
                controller.abort();
            };
        }
        setResolvedPath(null);
        setNotFound(false);

        fetch(withBase(`utils/checkfile.php?file=${encodeURIComponent(pattern)}`), {
            signal: controller.signal,
        })
            .then(res => res.text())
            .then(text => {
                if (!isActive) return;

                const result = text.trim();
                if (result === "false") {
                    setNotFound(true);
                } else if (result === "true") {
                    // Exact match, no wildcard
                    setResolvedPath(pattern);
                } else {
                    // Glob returned a resolved relative path
                    setResolvedPath(result);
                }
            })
            .catch((error) => {
                if (!isActive || error?.name === "AbortError") return;
                setNotFound(true);
            });

        return () => {
            isActive = false;
            controller.abort();
        };
    }, [pattern]);

    return { resolvedPath, notFound };
}

/**
 * Hook to check if a file exists via checkfile.php
 * @param {string} file - Relative file path to check
 * @returns {boolean|null} - true/false if checked, null if still checking
 */
export function useFileExists(file) {
    const [fileExists, setFileExists] = useState(null);

    useEffect(() => {
        let isActive = true;
        const controller = new AbortController();

        if (!file) {
            setFileExists(null);
            return () => {
                isActive = false;
                controller.abort();
            };
        }

        fetch(withBase(`utils/checkfile.php?file=${encodeURIComponent(file)}`), {
            signal: controller.signal,
        })
            .then(res => res.text())
            .then(text => {
                if (!isActive) return;
                setFileExists(text.trim() === "true");
            })
            .catch((error) => {
                if (!isActive || error?.name === "AbortError") return;
                setFileExists(false);
            });

        return () => {
            isActive = false;
            controller.abort();
        };
    }, [file]);

    return fileExists;
}
