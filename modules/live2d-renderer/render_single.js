/**
 * render_single.js
 *
 * Faithful port of the working 5K live2d-characters-reverse-1999 renderer.
 * Outputs high-fidelity, centered renders using a native 5000x5000 canvas.
 *
 * Usage:
 *   node render_single.js <path/to/model.model3.json> <output.png>
 */

const puppeteer = require('puppeteer');
const express   = require('express');
const path      = require('path');
const fs        = require('fs');
const sharp     = require('sharp');

const PORT = 3210;
const HOST = `http://127.0.0.1:${PORT}`;

// ── Args ────────────────────────────────────────────────────────────────────
const [,, modelJsonPath, outputPngPath] = process.argv;

if (!modelJsonPath || !outputPngPath) {
    console.error('Usage: node render_single.js <model.json> <output.png>');
    process.exit(1);
}

const modelJsonAbs  = path.resolve(modelJsonPath);
const modelDir      = path.dirname(modelJsonAbs);
const modelJsonName = path.basename(modelJsonAbs);

if (!fs.existsSync(modelJsonAbs)) {
    console.error(`Model file not found: ${modelJsonAbs}`);
    process.exit(1);
}

// ── Express ──────────────────────────────────────────────────────────────────
const app = express();
app.use(express.static(__dirname));
app.use('/model', express.static(modelDir, { dotfiles: 'allow' }));

const server = app.listen(PORT, () => {
    console.log(`[live2d-renderer] Server running on ${HOST}`);
});

// ── Main ─────────────────────────────────────────────────────────────────────
async function run() {
    const chromePath = (() => {
        const candidates = [
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ];
        return candidates.find(p => fs.existsSync(p));
    })();

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

    try {
        const page = await browser.newPage();
        // Viewport must match the native 5000x5000 canvas size to capture the full frame
        await page.setViewport({ width: 5000, height: 5000, deviceScaleFactor: 1 });

        page.on('console', msg => console.log(`[Browser] ${msg.text()}`));
        page.on('pageerror', err => console.error(`[Browser Error] ${err.message}`));

        await page.goto(`${HOST}/template.html`, { waitUntil: 'networkidle0' });

        const bundlePath = path.join(__dirname, 'bundle.js');
        await page.addScriptTag({ path: bundlePath });

        await page.waitForFunction(() => typeof window.renderModel === 'function', { timeout: 30000 });

        const modelUrl = `${HOST}/model/${modelJsonName}`;
        console.log(`[live2d-renderer] Rendering: ${modelUrl}`);

        const renderError = await page.evaluate(async (url) => {
            try {
                await window.renderModel(url);
                return null;
            } catch (e) {
                return e.message || String(e);
            }
        }, modelUrl);

        if (renderError) {
            throw new Error(`Render failed: ${renderError}`);
        }

        const ext = path.extname(outputPngPath);
        const rawPath = outputPngPath.replace(new RegExp(ext + '$', 'i'), '_raw.png');
        await page.screenshot({ path: rawPath, omitBackground: true });

        // Trim transparent borders, resize down to target size
        const isJpg = ext.toLowerCase() === '.jpg' || ext.toLowerCase() === '.jpeg';
        let pipeline = sharp(rawPath).trim();
        
        if (isJpg) {
            pipeline = pipeline
                .resize(512, 512, { fit: 'contain', background: '#181b28' })
                .jpeg({ quality: 75 });
        } else {
            pipeline = pipeline
                .resize(1024, 1024, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } });
        }
        
        await pipeline.toFile(outputPngPath);
            
        fs.unlinkSync(rawPath);
        console.log(`[live2d-renderer] ✅ Done: ${outputPngPath}`);

    } finally {
        await browser.close();
        server.close();
    }
}

run().catch(err => {
    console.error('[live2d-renderer] Fatal:', err.message);
    process.exit(1);
});
