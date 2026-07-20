/**
 * batch_render.js
 *
 * Orchestrated batch renderer for Live2D models.
 * Finds all *.model3.json files, renders them using Puppeteer,
 * crops/resizes with Sharp, and saves them to a flat folder with a manifest mapping.
 */

const puppeteer = require('puppeteer');
const express   = require('express');
const path      = require('path');
const fs        = require('fs');
const sharp     = require('sharp');

const PORT = 3210;
const HOST = `http://127.0.0.1:${PORT}`;
const CONCURRENCY = 1; // Number of parallel browser tabs
const TIMEOUT_MS = 20000; // Timeout per model

const ROOT_MODEL_DIR = 'E:\\Live2d-model';
const OUTPUT_DIR = 'E:\\Live2d-model-thumbnails';
const MANIFEST_PATH = path.join(OUTPUT_DIR, 'manifest.json');
const ERROR_LOG_PATH = path.join(OUTPUT_DIR, 'errors.json');

// ── Helpers ──────────────────────────────────────────────────────────────────

const TRANSPARENT_PNG_BUFFER = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64'
);

// Helper function to recursively find a file case-insensitively
function findFileRecursive(dir, targetName, maxDepth = 3, currentDepth = 0) {
    if (currentDepth > maxDepth) return null;
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        const targetLower = targetName.toLowerCase();
        
        // Check files in the current directory first
        for (const entry of entries) {
            if (entry.isFile()) {
                const entryLower = entry.name.toLowerCase();
                if (entryLower === targetLower) {
                    return path.join(dir, entry.name);
                }
                // Handle cases where the JSON is missing the extension (e.g. "texture_00" requested but file is "texture_00.png")
                if (!path.extname(targetLower) && entryLower.startsWith(targetLower + '.')) {
                    return path.join(dir, entry.name);
                }
            }
        }
        // Then check subdirectories
        for (const entry of entries) {
            if (entry.isDirectory()) {
                const found = findFileRecursive(path.join(dir, entry.name), targetName, maxDepth, currentDepth + 1);
                if (found) return found;
            }
        }
    } catch (e) {
        // ignore errors
    }
    return null;
}

// Helper function to find the model root directory by looking for a model JSON file
function findModelRoot(startDir) {
    let current = startDir;
    // Don't walk above the ROOT_MODEL_DIR
    while (current && current.length >= ROOT_MODEL_DIR.length && current.startsWith(ROOT_MODEL_DIR)) {
        try {
            const files = fs.readdirSync(current);
            const hasModelJson = files.some(file => {
                const lower = file.toLowerCase();
                return lower === 'model.json' || lower === 'model3.json' || lower.endsWith('.model.json') || lower.endsWith('.model3.json');
            });
            if (hasModelJson) {
                return current;
            }
        } catch (e) {
            // ignore
        }
        const parent = path.dirname(current);
        if (parent === current) break;
        current = parent;
    }
    return null;
}

// Regexes to clean JSON
function cleanJsonString(str) {
    // 1. Strip UTF-8 BOM if present
    if (str.charCodeAt(0) === 0xFEFF) {
        str = str.slice(1);
    }
    // 2. Replace full-width Japanese space (\u3000) with standard space
    str = str.replace(/\u3000/g, ' ');
    // 3. Remove single-line comments // that do not look like URL protocols (e.g. http://)
    str = str.replace(/(?:^|[^:])\/\/.*$/gm, '');
    // 4. Remove multi-line comments /* ... */
    str = str.replace(/\/\*[\s\S]*?\*\//g, '');
    // 5. Remove trailing commas in arrays and objects
    str = str.replace(/,(\s*[\]}])/g, '$1');
    return str;
}

// Recursively find all *.model3.json and *.model.json files
function findModelJsons(dir, fileList = []) {
    let files;
    try {
        files = fs.readdirSync(dir);
    } catch (e) {
        return fileList;
    }
    for (const file of files) {
        const filePath = path.join(dir, file);
        let stat;
        try {
            stat = fs.statSync(filePath);
        } catch (e) {
            continue;
        }
        if (stat.isDirectory()) {
            findModelJsons(filePath, fileList);
        } else if (file.toLowerCase().endsWith('.model3.json') || file.toLowerCase().endsWith('.model.json')) {
            fileList.push(filePath);
        }
    }
    return fileList;
}

// Generate a clean safe slug from a relative path
function generateSlug(relativePath) {
    return relativePath
        .replace(/^[\\/]+/, '') // Remove leading slashes
        .replace(/[\\/]/g, '_') // Replace directory separators with underscores
        .replace(/\.(model3|model)\.json$/i, '') // Remove extension (handling both model3 and model)
        .replace(/[^a-zA-Z0-9_\-]/g, ''); // Keep only alphanumeric, underscores, hyphens
}

// ── Express Setup ────────────────────────────────────────────────────────────
const app = express();
app.use(express.static(__dirname));

// Custom middleware to serve models with JSON sanitization and fuzzy texture lookup
app.use('/model', (req, res, next) => {
    let decodedPath = '';
    try {
        decodedPath = decodeURIComponent(req.path);
    } catch (e) {
        decodedPath = req.path;
    }

    const targetPath = path.join(ROOT_MODEL_DIR, decodedPath);
    const ext = path.extname(targetPath).toLowerCase();

    // Check if file exists
    fs.access(targetPath, fs.constants.F_OK, (err) => {
        if (!err) {
            // File exists
            if (ext === '.json') {
                fs.readFile(targetPath, 'utf8', (readErr, content) => {
                    if (readErr) {
                        return res.status(500).send(`Error reading JSON: ${readErr.message}`);
                    }
                    try {
                        const cleaned = cleanJsonString(content);
                        const json = JSON.parse(cleaned);

                        // Only auto-reconstruct textures for actual model config files
                        const isModelConfig = decodedPath.toLowerCase().endsWith('.model3.json') || 
                                              decodedPath.toLowerCase().endsWith('.model.json') || 
                                              json.Moc !== undefined || 
                                              (json.FileReferences && json.FileReferences.Moc !== undefined) ||
                                              json.model !== undefined;

                        if (isModelConfig) {
                            let textures = [];
                            let isCubism3 = false;

                            if (json.FileReferences && Array.isArray(json.FileReferences.Textures)) {
                                textures = json.FileReferences.Textures;
                                isCubism3 = true;
                            } else if (Array.isArray(json.textures)) {
                                textures = json.textures;
                            }

                            if (textures.length === 0) {
                                console.log(`[batch-renderer] [Sanitizer] Empty textures array detected in JSON: ${decodedPath}. Reconstructing...`);
                                const modelDir = path.dirname(targetPath);
                                const foundFiles = [];
                                function scan(dir, depth = 0) {
                                    if (depth > 2) return;
                                    try {
                                        const entries = fs.readdirSync(dir, { withFileTypes: true });
                                        for (const entry of entries) {
                                            const full = path.join(dir, entry.name);
                                            if (entry.isFile() && entry.name.toLowerCase().endsWith('.png')) {
                                                const rel = path.relative(modelDir, full).replace(/\\/g, '/');
                                                if (!rel.toLowerCase().includes('motion') && !rel.toLowerCase().includes('expression')) {
                                                    foundFiles.push(rel);
                                                }
                                            } else if (entry.isDirectory()) {
                                                scan(full, depth + 1);
                                            }
                                        }
                                    } catch (_) {}
                                }
                                scan(modelDir);
                                if (foundFiles.length > 0) {
                                    console.log(`[batch-renderer] [Sanitizer] Found textures:`, foundFiles);
                                    if (isCubism3) {
                                        json.FileReferences.Textures = foundFiles;
                                    } else {
                                        json.textures = foundFiles;
                                    }
                                }
                            }
                        }

                        res.setHeader('Content-Type', 'application/json');
                        return res.send(JSON.stringify(json, null, 2));
                    } catch (parseErr) {
                        console.warn(`[batch-renderer] Fallback parsing raw JSON for ${decodedPath} due to: ${parseErr.message}`);
                        res.setHeader('Content-Type', 'application/json');
                        return res.send(content);
                    }
                });
            } else {
                return res.sendFile(targetPath, { dotfiles: 'allow' });
            }
        } else {
            // File does not exist
            const isImage = ['.png', '.jpg', '.jpeg', '.tga', '.bmp', '.gif', '.webp'].includes(ext) || 
                            decodedPath.toLowerCase().includes('/textures/') ||
                            decodedPath.toLowerCase().includes('texture');
            if (isImage) {
                const filename = path.basename(targetPath);
                const parentDir = path.dirname(targetPath);
                const modelRoot = findModelRoot(parentDir);

                if (modelRoot) {
                    let fuzzyFile = findFileRecursive(modelRoot, filename);
                    // Sibling search fallback (check parent/franchise folder) if not found in model root
                    if (!fuzzyFile) {
                        const franchiseRoot = path.dirname(modelRoot);
                        if (franchiseRoot.length >= ROOT_MODEL_DIR.length && franchiseRoot.startsWith(ROOT_MODEL_DIR)) {
                            fuzzyFile = findFileRecursive(franchiseRoot, filename);
                        }
                    }
                    if (fuzzyFile) {
                        console.log(`[batch-renderer] [Fuzzy Match] Redirected ${decodedPath} to ${path.relative(ROOT_MODEL_DIR, fuzzyFile)}`);
                        return res.sendFile(fuzzyFile, { dotfiles: 'allow' });
                    }
                }

                console.log(`[batch-renderer] [Fallback] serving transparent pixel for missing texture: ${decodedPath}`);
                res.setHeader('Content-Type', 'image/png');
                return res.send(TRANSPARENT_PNG_BUFFER);
            } else {
                return res.status(404).send('File not found');
            }
        }
    });
});

// Fallback static files middleware supporting dotfiles (e.g. .model3.json)
app.use('/model', express.static(ROOT_MODEL_DIR, { dotfiles: 'allow' }));

const server = app.listen(PORT, () => {
    console.log(`[batch-renderer] Static server listening on ${HOST}`);
});

// ── Main Orchestrator ────────────────────────────────────────────────────────
async function main() {
    if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    }

    console.log(`[batch-renderer] Scanning ${ROOT_MODEL_DIR} for models...`);
    const absoluteModelPaths = findModelJsons(ROOT_MODEL_DIR);
    console.log(`[batch-renderer] Found ${absoluteModelPaths.length} model configurations.`);

    const chromePath = (() => {
        const candidates = [
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ];
        return candidates.find(p => fs.existsSync(p));
    })();

    console.log(`[batch-renderer] Launching Puppeteer...`);
    const browser = await puppeteer.launch({
        headless: 'new',
        executablePath: chromePath,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--enable-webgl',
            '--ignore-gpu-blocklist',
        ],
    });

    const manifest = [];
    const errorLogs = [];
    let completedCount = 0;

    // Queue of models to process
    const queue = absoluteModelPaths.map(absPath => {
        const relative = path.relative(ROOT_MODEL_DIR, absPath);
        const slug = generateSlug(relative);
        return { absPath, relative, slug };
    });

    console.log(`[batch-renderer] Starting batch rendering with concurrency = ${CONCURRENCY}`);

    async function worker() {
        let page = null;
        const bundlePath = path.join(__dirname, 'bundle.js');

        async function ensurePage() {
            if (page) {
                // Check page health before continuing
                try {
                    await page.evaluate(() => 1);
                    return page;
                } catch (e) {
                    console.warn(`[batch-renderer] Browser page unhealthy, recreating... Reason: ${e.message}`);
                    try { await page.close(); } catch (_) {}
                    page = null;
                }
            }

            page = await browser.newPage();
            await page.setViewport({ width: 5000, height: 5000, deviceScaleFactor: 1 });
            await page.goto(`${HOST}/template.html`, { waitUntil: 'networkidle0', timeout: TIMEOUT_MS });
            await page.addScriptTag({ path: bundlePath });
            await page.waitForFunction(() => typeof window.renderModel === 'function', { timeout: TIMEOUT_MS });
            return page;
        }

        while (queue.length > 0) {
            const item = queue.shift();
            if (!item) break;

            const { absPath, relative, slug } = item;
            const outputPngPath = path.join(OUTPUT_DIR, `${slug}.png`);
            const rawPngPath = path.join(OUTPUT_DIR, `${slug}_raw.png`);

            // Skip if already rendered
            if (fs.existsSync(outputPngPath)) {
                completedCount++;
                console.log(`[${completedCount}/${absoluteModelPaths.length}] Skipped (exists): ${slug}`);
                manifest.push({ slug: `${slug}.png`, originalPath: relative });
                continue;
            }

            try {
                const activePage = await ensurePage();

                // Construct model URL. Ensure slashes are forward slashes for URL resolution
                const urlPath = relative.split(path.sep).map(encodeURIComponent).join('/');
                const modelUrl = `${HOST}/model/${urlPath}`;

                // Set up page console logging
                let browserConsoleLogs = [];
                const consoleListener = msg => browserConsoleLogs.push(msg.text());
                const errorListener = err => browserConsoleLogs.push(`JS Error: ${err.message}`);
                activePage.on('console', consoleListener);
                activePage.on('pageerror', errorListener);

                try {
                    const renderError = await activePage.evaluate(async (url) => {
                        try {
                            await window.renderModel(url);
                            return null;
                        } catch (e) {
                            return e.message || String(e);
                        }
                    }, modelUrl);

                    if (renderError) {
                        throw new Error(`Renderer: ${renderError}`);
                    }

                    // Take screenshot of the 5000x5000 frame
                    await activePage.screenshot({ path: rawPngPath, omitBackground: true });

                    // Post-process with Sharp
                    await sharp(rawPngPath)
                        .trim()
                        .resize(1024, 1024, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
                        .toFile(outputPngPath);

                    if (fs.existsSync(rawPngPath)) {
                        fs.unlinkSync(rawPngPath);
                    }

                    completedCount++;
                    console.log(`[${completedCount}/${absoluteModelPaths.length}] ✅ Rendered: ${slug}`);
                    manifest.push({ slug: `${slug}.png`, originalPath: relative });

                } finally {
                    activePage.off('console', consoleListener);
                    activePage.off('pageerror', errorListener);
                }

            } catch (err) {
                // Cleanup raw screenshot if exists
                if (fs.existsSync(rawPngPath)) {
                    try { fs.unlinkSync(rawPngPath); } catch (_) {}
                }

                // Handle Puppeteer protocol errors / target closed by discarding the page and retrying
                const isProtocolError = err.message.includes('Protocol error') || 
                                        err.message.includes('Session closed') || 
                                        err.message.includes('Target closed') || 
                                        err.message.includes('detached');
                if (isProtocolError) {
                    console.log(`[batch-renderer] Discarding Puppeteer page due to crash / protocol disconnect on: ${slug}`);
                    try { await page.close(); } catch (_) {}
                    page = null;

                    const retries = item.retries || 0;
                    if (retries < 2) {
                        item.retries = retries + 1;
                        console.log(`[batch-renderer] Queueing retry #${item.retries} for: ${slug}`);
                        queue.unshift(item);
                        continue;
                    }
                }

                completedCount++;
                console.error(`[${completedCount}/${absoluteModelPaths.length}] ❌ Failed: ${slug}. Error: ${err.message}`);
                errorLogs.push({ slug, relative, error: err.message });
            }
        }

        if (page) {
            try { await page.close(); } catch (_) {}
        }
    }

    // Spawn workers
    const workers = Array.from({ length: CONCURRENCY }, () => worker());
    await Promise.all(workers);

    // Save outputs
    fs.writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2));
    fs.writeFileSync(ERROR_LOG_PATH, JSON.stringify(errorLogs, null, 2));

    console.log(`[batch-renderer] Finished batch processing!`);
    console.log(`[batch-renderer] Total successful: ${manifest.length}`);
    console.log(`[batch-renderer] Total failed: ${errorLogs.length}`);
    console.log(`[batch-renderer] Manifest saved to: ${MANIFEST_PATH}`);
    console.log(`[batch-renderer] Error log saved to: ${ERROR_LOG_PATH}`);

    await browser.close();
    server.close();
}

main().catch(err => {
    console.error('[batch-renderer] Fatal orchestration error:', err);
    if (server) server.close();
});
