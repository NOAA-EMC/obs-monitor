//src/utils/paths.js

export const withBase = (path) => {
    const base = import.meta.env.BASE_URL;
    if (base.endsWith('/') && path.startsWith('/')) {
        return base + path.slice(1);
    }
    return base + path;
};
