<?php
// Keep warnings out of HTTP responses so hook consumers receive only expected values.
ini_set('display_errors', 0);
error_reporting(E_ALL);

// Set the base directory to the deployment root (adjust as needed)
$baseDir = realpath(__DIR__ . '/..');

if ($baseDir === false) {
    http_response_code(500);
    echo "false";
    exit;
}

$baseDirPrefix = $baseDir . DIRECTORY_SEPARATOR;

// Get the requested file path from the query parameter
$relativePath = isset($_GET['file']) ? $_GET['file'] : '';

function isWithinBaseDir($path, $baseDir, $baseDirPrefix)
{
    return $path === $baseDir || strpos($path, $baseDirPrefix) === 0;
}

function normalizeRelativePath($path)
{
    if (!is_string($path)) {
        return false;
    }

    // Reject UNC and drive-qualified absolute inputs.
    if (
        strpos($path, '//') === 0 ||
        strpos($path, '\\\\') === 0 ||
        preg_match('#^[A-Za-z]:[\\/]#', $path)
    ) {
        return false;
    }

    $path = str_replace(array('\\', '/'), DIRECTORY_SEPARATOR, $path);
    $path = ltrim($path, DIRECTORY_SEPARATOR);

    $segments = explode(DIRECTORY_SEPARATOR, $path);
    foreach ($segments as $segment) {
        if ($segment === '..') {
            return false;
        }
    }

    return $path;
}

function hasWildcardInDirectorySegments($path)
{
    $segments = explode(DIRECTORY_SEPARATOR, $path);
    if (count($segments) <= 1) {
        return false;
    }

    // Only allow wildcard usage in the final segment (typically the filename).
    for ($i = 0; $i < count($segments) - 1; $i++) {
        if (strpos($segments[$i], '*') !== false) {
            return true;
        }
    }

    return false;
}

$normalizedPath = normalizeRelativePath($relativePath);

if ($normalizedPath === false) {
    echo "false";
    exit;
}

if (hasWildcardInDirectorySegments($normalizedPath)) {
    echo "false";
    exit;
}

if (strpos($normalizedPath, '*') !== false) {
    // Glob pattern: build the pattern path and search
    $pattern = $baseDir . DIRECTORY_SEPARATOR . $normalizedPath;
    $matches = glob($pattern);

    if ($matches) {
        foreach ($matches as $match) {
            $resolvedMatch = realpath($match);

            if (
                $resolvedMatch !== false &&
                is_file($resolvedMatch) &&
                isWithinBaseDir($resolvedMatch, $baseDir, $baseDirPrefix)
            ) {
                // Return the relative path of the first safe match so the client can use it
                $resolved = substr($resolvedMatch, strlen($baseDirPrefix));
                echo str_replace(DIRECTORY_SEPARATOR, '/', $resolved);
                exit;
            }
        }
    }

    echo "false";
} else {
    // Exact path: normalize and check
    $fullPath = realpath($baseDir . DIRECTORY_SEPARATOR . $normalizedPath);

    if (
        $fullPath !== false &&
        is_file($fullPath) &&
        isWithinBaseDir($fullPath, $baseDir, $baseDirPrefix)
    ) {
        echo "true";
    } else {
        echo "false";
    }
}
?>
