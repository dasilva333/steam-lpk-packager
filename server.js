const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Serve thumbnails directory locally or fallback to storage path on E drive if available
const localThumbDir = path.join(__dirname, 'public', 'thumbnails');
const extThumbDir = "E:\\lpk-studio-storage\\public\\thumbnails";
const targetThumbDir = fs.existsSync(extThumbDir) ? extThumbDir : localThumbDir;
app.use('/thumbnails', express.static(targetThumbDir));

// Fallback empty DB check/create via python
const dbPath = path.join(__dirname, 'db', 'catalog.sqlite');

// Helper to shell out database updates to python helper
function runDbQuery(action, params = {}) {
    // Check if python or py should be used based on active OS
    const cmdBinary = process.platform === 'win32' ? 'py' : 'python3';
    return new Promise((resolve, reject) => {
        const pythonProcess = spawn(cmdBinary, [
            path.join(__dirname, 'cli', 'db_helper.py'),
            action,
            JSON.stringify(params)
        ]);

        let stdout = '';
        let stderr = '';

        pythonProcess.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        pythonProcess.on('close', (code) => {
            if (code !== 0) {
                return reject(new Error(stderr || `Python db_helper closed with code ${code}`));
            }
            try {
                resolve(JSON.parse(stdout));
            } catch (e) {
                resolve({ success: true, raw: stdout });
            }
        });
    });
}

// API: Dry Run
app.post('/api/dry-run', async (req, res) => {
    try {
        const { urls } = req.body;
        if (!urls || !urls.trim()) {
            return res.status(400).json({ error: 'No Workshop URLs or IDs provided' });
        }

        // Clean & parse URLs into IDs
        const ids = [];
        const lines = urls.split('\n');
        for (let line of lines) {
            line = line.trim();
            if (!line) continue;
            const match = line.match(/\?id=(\d+)/) || line.match(/(\d+)/);
            if (match) {
                ids.push(match[1]);
            }
        }

        if (ids.length === 0) {
            return res.status(400).json({ error: 'Failed to extract valid Workshop IDs' });
        }

        // Write a temp file for the dry-run command inside cli/
        const tempFilePath = path.join(__dirname, 'cli', 'temp_gui_batch.txt');
        fs.writeFileSync(tempFilePath, ids.join('\n'));

        // Shell out to Python orchestrator
        const pythonProcess = spawn('python3', [
            path.join(__dirname, 'cli', 'process_batch2_safe.py'),
            '--batch', 'temp_gui_batch.txt',
            '--dry-run'
        ]);

        let output = '';
        pythonProcess.stdout.on('data', (data) => {
            output += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            output += data.toString();
        });

        pythonProcess.on('close', (code) => {
            // Clean up temp file
            if (fs.existsSync(tempFilePath)) {
                fs.unlinkSync(tempFilePath);
            }
            res.json({ output });
        });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Process batch (starts background process and streams back via Server-Sent Events)
app.get('/api/process-stream', (req, res) => {
    const urls = req.query.urls;
    if (!urls) {
        return res.status(400).send('No URLs provided');
    }

    const ids = [];
    const lines = urls.split('\n');
    for (let line of lines) {
        line = line.trim();
        if (!line) continue;
        const match = line.match(/\?id=(\d+)/) || line.match(/(\d+)/);
        if (match) {
            ids.push(match[1]);
        }
    }

    if (ids.length === 0) {
        return res.status(400).send('No valid IDs found');
    }

    // Set up SSE headers
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();

    const tempFilePath = path.join(__dirname, 'cli', 'temp_gui_batch.txt');
    fs.writeFileSync(tempFilePath, ids.join('\n'));

    // Start execution
    const child = spawn('python3', [
        path.join(__dirname, 'cli', 'process_batch2_safe.py'),
        '--batch', 'temp_gui_batch.txt'
    ]);

    const sendSSE = (event, data) => {
        res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    };

    child.stdout.on('data', (data) => {
        sendSSE('stdout', data.toString());
    });

    child.stderr.on('data', (data) => {
        sendSSE('stderr', data.toString());
    });

    child.on('close', (code) => {
        if (fs.existsSync(tempFilePath)) {
            fs.unlinkSync(tempFilePath);
        }
        sendSSE('exit', { code });
        res.end();
    });
});

// API: Browse Packaged ZIPs
app.get('/api/packages', (req, res) => {
    const live2dPath = path.join(__dirname, 'cli', 'live2d_packages');
    const spinePath = path.join(__dirname, 'cli', 'spine_packages');
    const packages = [];

    const scanDir = (dirPath, type) => {
        if (fs.existsSync(dirPath)) {
            const files = fs.readdirSync(dirPath);
            files.forEach(file => {
                if (file.endsWith('.zip')) {
                    const stats = fs.statSync(path.join(dirPath, file));
                    packages.push({
                        name: file,
                        size: (stats.size / (1024 * 1024)).toFixed(2) + ' MB',
                        type: type,
                        path: `/download/${type}/${file}`
                    });
                }
            });
        }
    };

    scanDir(live2dPath, 'live2d');
    scanDir(spinePath, 'spine');
    res.json(packages);
});

// API: Catalog Query
app.get('/api/catalog', async (req, res) => {
    try {
        const { search, types, compatibilities, sort, page, limit } = req.query;
        
        const params = {
            search: search || '',
            types: types ? types.split(',') : [],
            compatibilities: compatibilities ? compatibilities.split(',') : [],
            sort: sort || 'subscriptions',
            limit: parseInt(limit || 20),
            offset: (parseInt(page || 1) - 1) * parseInt(limit || 20)
        };
        
        const data = await runDbQuery('query', params);
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Stats Summary
app.get('/api/stats', async (req, res) => {
    try {
        const stats = await runDbQuery('stats');
        res.json(stats);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Helper to read .env key=values
function loadEnv() {
    const envPath = path.join(__dirname, '.env');
    const config = {};
    if (fs.existsSync(envPath)) {
        const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
        lines.forEach(line => {
            const trimmed = line.trim();
            if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
                const [k, v] = trimmed.split('=', 2);
                config[k.trim()] = v.trim();
            }
        });
    }
    return config;
}

// Helper to write/update .env key=values
function saveEnv(updates) {
    const envPath = path.join(__dirname, '.env');
    const current = loadEnv();
    const merged = { ...current, ...updates };
    const lines = Object.entries(merged).map(([k, v]) => `${k}=${v}`);
    fs.writeFileSync(envPath, lines.join('\n'), 'utf-8');
}

// API: Config Info
app.get('/api/config', (req, res) => {
    const envConfig = loadEnv();
    
    // Resolve Steam content directory dynamically (cross-platform relative folder fallback)
    let steamContentDir = envConfig.STEAM_CONTENT_DIR || '';
    if (!steamContentDir) {
        if (process.platform === 'win32') {
            steamContentDir = 'C:\\Program Files (x86)\\Steam\\steamapps\\workshop\\content\\616720';
        } else {
            const home = process.env.HOME || process.env.USERPROFILE || '';
            steamContentDir = path.join(home, 'Library', 'Application Support', 'Steam', 'steamapps', 'workshop', 'content', '616720');
        }
    }
    
    res.json({ 
        projectPath: __dirname,
        steamContentDir: steamContentDir,
        storageRoot: envConfig.STORAGE_ROOT || 'E:\\lpk-studio-storage',
        maxSizeGB: envConfig.MAX_SIZE_GB || '1.5'
    });
});

// API: Save Config Info
app.post('/api/config', (req, res) => {
    try {
        const { steamContentDir, storageRoot, maxSizeGB } = req.body;
        const updates = {};
        if (steamContentDir !== undefined) updates.STEAM_CONTENT_DIR = steamContentDir;
        if (storageRoot !== undefined) updates.STORAGE_ROOT = storageRoot;
        if (maxSizeGB !== undefined) updates.MAX_SIZE_GB = maxSizeGB;
        
        saveEnv(updates);
        res.json({ success: true, message: 'Settings configuration saved successfully!' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Download endpoints for packages
app.get('/download/:type/:filename', (req, res) => {
    const { type, filename } = req.params;
    const folder = type === 'live2d' ? 'live2d_packages' : 'spine_packages';
    const filePath = path.join(__dirname, 'cli', folder, filename);

    if (fs.existsSync(filePath)) {
        res.download(filePath);
    } else {
        res.status(404).send('File not found');
    }
});

// Start Express App
app.listen(PORT, () => {
    console.log(`========================================`);
    console.log(`  LPK Studio running at http://localhost:${PORT}`);
    console.log(`========================================`);
});
