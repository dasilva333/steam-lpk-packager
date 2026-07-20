import * as PIXI from 'pixi.js';

export const TRANSPARENT_PIXEL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

/**
 * Probes textures referenced in modelSettings.FileReferences.Textures,
 * injects transparent fallbacks for any that fail to load, and corrects
 * bloom texture ordering.
 *
 * Works with both standard model3.json and LPK model0.json since both
 * use the same FileReferences.Textures[] schema.
 */
export async function sanitizeModel(modelUrl, modelSettings) {
    const base = new URL(modelUrl, window.location.href).href;
    const textureBase = base.substring(0, base.lastIndexOf('/') + 1);

    const textures = modelSettings?.FileReferences?.Textures;
    if (!textures || textures.length === 0) {
        console.warn('[Sanitizer] No textures found in FileReferences.Textures');
        return modelSettings;
    }

    const placeholderTexture = PIXI.Texture.from(TRANSPARENT_PIXEL);
    console.log(`[Sanitizer] Probing ${textures.length} texture(s)...`);

    for (let i = 0; i < textures.length; i++) {
        let originalPath = textures[i];
        // Fix hash fragment bug: replace '#' with '%23' to prevent the browser from truncating the URL
        if (originalPath.includes('#')) {
            originalPath = originalPath.replace(/#/g, '%23');
            textures[i] = originalPath;
        }
        const fullUrl = new URL(originalPath, textureBase).href;
        try {
            await PIXI.Assets.load(fullUrl);
            console.log(`[Sanitizer] Texture [${i}] OK: ${originalPath}`);
        } catch (err) {
            console.warn(`[Sanitizer] Texture [${i}] FAILED: ${originalPath} — injecting fallback.`);
            PIXI.Assets.cache.set(fullUrl, placeholderTexture);
            if (PIXI.utils && PIXI.utils.TextureCache) {
                PIXI.utils.TextureCache[fullUrl] = placeholderTexture;
            }
        }
    }

    // Push bloom textures to end (Cubism convention)
    const bloom = textures.filter(t => t.toLowerCase().includes('_bloom'));
    const main  = textures.filter(t => !t.toLowerCase().includes('_bloom') && t !== TRANSPARENT_PIXEL);
    if (bloom.length > 0) {
        modelSettings.FileReferences.Textures = [...main, ...bloom];
        console.log('[Sanitizer] Texture order corrected: blooms pushed to end.');
    }

    return modelSettings;
}
