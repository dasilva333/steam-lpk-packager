import * as PIXI from 'pixi.js';
import { sanitizeModel } from './sanitizer';
import { createRenderer, renderToStage, finalizeRender } from './renderer';

window.PIXI = PIXI;

let app;
let currentModel = null;

async function init() {
    console.log('[live2d-renderer] Initializing PIXI renderer...');
    app = await createRenderer();
    console.log('[live2d-renderer] Renderer ready.');
}

/**
 * Renders a Live2D model from a model JSON URL.
 * Compatible with both model3.json (Cubism standard) and model0.json (LPK/MLive format),
 * since both share the FileReferences.{Moc, Textures, Motions} schema.
 *
 * @param {string} modelUrl - Full URL to the model JSON (e.g. http://localhost:PORT/path/model0.json)
 */
window.renderModel = async function(modelUrl) {
    console.log('[live2d-renderer] renderModel called:', modelUrl);

    if (!app) await init();

    // Cleanup previous model
    if (currentModel) {
        console.log('[live2d-renderer] Cleaning up previous model...');
        try {
            if (app.stage.children.includes(currentModel)) {
                app.stage.removeChild(currentModel);
            }
            if (typeof currentModel.destroy === 'function') {
                currentModel.destroy({ children: true, texture: true, baseTexture: true });
            }
        } catch (cleanupErr) {
            console.warn('[live2d-renderer] Cleanup warning:', cleanupErr.message);
        }
        currentModel = null;
    }

    try {
        // Fetch model JSON, sanitize textures, render
        const response = await fetch(modelUrl);
        if (!response.ok) throw new Error(`HTTP ${response.status} fetching ${modelUrl}`);
        const settings = await response.json();

        const sanitizedSettings = await sanitizeModel(modelUrl, settings);
        currentModel = await renderToStage(app, sanitizedSettings, modelUrl);
        await finalizeRender(app, currentModel);

        console.log('[live2d-renderer] Render complete.');
    } catch (err) {
        console.error('[live2d-renderer] ERROR:', err.message || err);
        if (err.stack) console.error(err.stack);
        throw err;
    }
};

init();
