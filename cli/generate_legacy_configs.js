const fs = require('fs');
const path = require('path');

const ROOT_MODEL_DIR = 'E:\\Live2d-model';

function scanDir(dir) {
    let entries;
    try {
        entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (e) {
        return;
    }

    const mocs = [];
    const modelJsons = [];
    const model3Jsons = [];
    const subdirs = [];

    for (const entry of entries) {
        if (entry.isDirectory()) {
            subdirs.push(entry.name);
        } else if (entry.isFile()) {
            const name = entry.name.toLowerCase();
            if (name.endsWith('.moc')) {
                mocs.push(entry.name);
            } else if (name.endsWith('.model.json')) {
                modelJsons.push(entry.name);
            } else if (name.endsWith('.model3.json')) {
                model3Jsons.push(entry.name);
            }
        }
    }

    // If we have a legacy .moc file but no .model.json or .model3.json config in this folder
    if (mocs.length > 0 && modelJsons.length === 0 && model3Jsons.length === 0) {
        // Generate a config for the first .moc file
        const mocFile = mocs[0];
        const baseName = path.basename(mocFile, path.extname(mocFile));
        
        // Scan for texture png files
        const textures = [];
        function scanTextures(currentDir, depth = 0) {
            if (depth > 2) return;
            let files;
            try {
                files = fs.readdirSync(currentDir, { withFileTypes: true });
            } catch (e) {
                return;
            }
            for (const file of files) {
                const fullPath = path.join(currentDir, file.name);
                if (file.isFile() && file.name.toLowerCase().endsWith('.png')) {
                    const rel = path.relative(dir, fullPath).replace(/\\/g, '/');
                    if (!rel.toLowerCase().includes('motion') && !rel.toLowerCase().includes('expression')) {
                        textures.push(rel);
                    }
                } else if (file.isDirectory()) {
                    scanTextures(fullPath, depth + 1);
                }
            }
        }
        scanTextures(dir);

        const config = {
            "model": mocFile,
            "textures": textures
        };

        const configFileName = `${baseName}.model.json`;
        const configPath = path.join(dir, configFileName);
        
        console.log(`[Config Gen] Generating config in ${dir} -> ${configFileName} (${textures.length} textures)`);
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
    }

    // Recurse into subdirectories
    for (const subdir of subdirs) {
        scanDir(path.join(dir, subdir));
    }
}

console.log(`Scanning ${ROOT_MODEL_DIR} for legacy .moc files...`);
scanDir(ROOT_MODEL_DIR);
console.log('Scan complete!');
