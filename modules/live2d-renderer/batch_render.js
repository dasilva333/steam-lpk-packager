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
const CONCURRENCY = 4; // Number of parallel browser tabs
const TIMEOUT_MS = 20000; // Timeout per model

const ROOT_MODEL_DIR = 'E:\\Live2d-model';
const OUTPUT_DIR = 'E:\\Live2d-model-thumbnails';
const MANIFEST_PATH = path.join(OUTPUT_DIR, 'manifest.json');
const ERROR_LOG_PATH = path.join(OUTPUT_DIR, 'errors.json');

// ── Helpers ──────────────────────────────────────────────────────────────────

// Recursively find all *.model3.json files
function findModelJsons(dir, fileList = []) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
        const filePath = path.join(dir, file);
        const stat = fs.statSync(filePath);
        if (stat.isDirectory()) {
            findModelJsons(filePath, fileList);
        } else if (file.toLowerCase().endsWith('.model3.json')) {
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
        .replace(/\.model3\.json$/i, '') // Remove extension
        .replace(/[^a-zA-Z0-9_\-]/g, ''); // Keep only alphanumeric, underscores, hyphens
}

// ── Express Setup ────────────────────────────────────────────────────────────
const app = express();
app.use(express.static(__dirname));
app.use('/model', express.static(ROOT_MODEL_DIR));

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
    console.log(`[batch-renderer] Found ${absoluteModelPaths.length} model3.json configurations.`);

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

            let page;
            try {
                page = await browser.newPage();
                await page.setViewport({ width: 5000, height: 5000, deviceScaleFactor: 1 });

                // Set up page console logging to error log if desired
                let browserConsoleLogs = [];
                page.on('console', msg => browserConsoleLogs.push(msg.text()));
                page.on('pageerror', err => browserConsoleLogs.push(`JS Error: ${err.message}`));

                await page.goto(`${HOST}/template.html`, { waitUntil: 'networkidle0', timeout: TIMEOUT_MS });

                const bundlePath = path.join(__dirname, 'bundle.js');
                await page.addScriptTag({ path: bundlePath });

                await page.waitForFunction(() => typeof window.renderModel === 'function', { timeout: TIMEOUT_MS });

                // Construct model URL. Ensure slashes are forward slashes for URL resolution
                const urlPath = relative.split(path.sep).map(encodeURIComponent).join('/');
                const modelUrl = `${HOST}/model/${urlPath}`;

                const renderError = await page.evaluate(async (url) => {
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
                await page.screenshot({ path: rawPngPath, omitBackground: true });

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

            } catch (err) {
                completedCount++;
                console.error(`[${completedCount}/${absoluteModelPaths.length}] ❌ Failed: ${slug}. Error: ${err.message}`);
                errorLogs.push({ slug, relative, error: err.message });
                
                // Cleanup raw screenshot if exists
                if (fs.existsSync(rawPngPath)) {
                    try { fs.unlinkSync(rawPngPath); } catch (_) {}
                }
            } finally {
                if (page) {
                    await page.close();
                }
            }
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
