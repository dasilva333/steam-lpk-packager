const { createApp, ref, reactive, computed, onMounted, nextTick } = Vue;

createApp({
    setup() {
        const currentTab = ref('packer');
        const urls = ref('');
        const isProcessing = ref(false);
        const log = ref([]);
        const packages = ref([]);
        const terminal = ref(null);

        // Catalog Browser state
        const catalogItems = ref([]);
        const catalogTotal = ref(0);
        const catalogLoading = ref(false);
        const catalogFilters = reactive({
            search: '',
            types: ['Live2D', 'Spine'],
            compatibilities: ['ready', 'incompatible', 'unknown'],
            sort: 'subscriptions',
            page: 1,
            limit: 12
        });

        // Settings / Statistics state
        const stats = ref({});
        const statsLoading = ref(false);
        const toastMessage = ref('');

        const copyPath = (item) => {
            const folder = item.steam_type.toLowerCase() === 'live2d' ? 'live2d_packages' : 'spine_packages';
            const filename = `${item.steam_type.toLowerCase()}_${item.id}.zip`;
            const relativePath = `cli/${folder}/${filename}`;
            
            navigator.clipboard.writeText(relativePath).then(() => {
                toastMessage.value = `Copied to clipboard: ${relativePath}`;
                setTimeout(() => {
                    toastMessage.value = '';
                }, 3000);
            }).catch(err => {
                console.error('Could not copy path: ', err);
            });
        };

        const appendLog = (text, type = 'info') => {
            log.value.push({ text, type });
            nextTick(() => {
                if (terminal.value) {
                    terminal.value.scrollTop = terminal.value.scrollHeight;
                }
            });
        };

        const clearLog = () => {
            log.value = [];
        };

        // API Call: Fetch pre-existing ZIPs
        const fetchPackages = async () => {
            try {
                const res = await fetch('/api/packages');
                packages.value = await res.json();
            } catch (err) {
                console.error("Failed to load packages:", err);
            }
        };

        // API Call: Fetch Catalog Items with filter parameters
        const fetchCatalog = async () => {
            catalogLoading.value = true;
            try {
                const queryParams = new URLSearchParams({
                    search: catalogFilters.search,
                    types: catalogFilters.types.join(','),
                    compatibilities: catalogFilters.compatibilities.join(','),
                    sort: catalogFilters.sort,
                    page: catalogFilters.page,
                    limit: catalogFilters.limit
                });
                const res = await fetch(`/api/catalog?${queryParams.toString()}`);
                const data = await res.json();
                catalogItems.value = data.items || [];
                catalogTotal.value = data.total || 0;
            } catch (err) {
                console.error("Failed to fetch catalog:", err);
            } finally {
                catalogLoading.value = false;
            }
        };

        const resetPageAndFetch = () => {
            catalogFilters.page = 1;
            fetchCatalog();
        };

        const nextPage = () => {
            if (catalogFilters.page < totalPages.value) {
                catalogFilters.page++;
                fetchCatalog();
            }
        };

        const prevPage = () => {
            if (catalogFilters.page > 1) {
                catalogFilters.page--;
                fetchCatalog();
            }
        };

        const totalPages = computed(() => {
            return Math.ceil(catalogTotal.value / catalogFilters.limit) || 1;
        });

        // API Call: Fetch statistics for Settings screen
        const fetchStats = async () => {
            statsLoading.value = true;
            try {
                const res = await fetch('/api/stats');
                stats.value = await res.json();
            } catch (err) {
                console.error("Failed to fetch statistics:", err);
            } finally {
                statsLoading.value = false;
            }
        };

        // Action: Run Report (Dry-run wrapper)
        const runReport = async () => {
            if (!urls.value.trim()) return;
            isProcessing.value = true;
            clearLog();
            appendLog("📡 Fetching Dry Run Report from Steam Web API...", "info");

            try {
                const response = await fetch('/api/dry-run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ urls: urls.value })
                });
                
                const data = await response.json();
                if (data.error) {
                    appendLog(`❌ Error: ${data.error}`, "error");
                } else {
                    const lines = data.output.split('\n');
                    lines.forEach(line => {
                        if (line.trim()) {
                            if (line.includes('❌') || line.includes('[CRITICAL WARNING]') || line.includes('failed') || line.includes('Error:')) {
                                appendLog(line, 'error');
                            } else if (line.includes('⚠️') || line.includes('[WARNING]')) {
                                appendLog(line, 'warning');
                            } else if (line.includes('✅') || line.includes('Success') || line.includes('successful')) {
                                appendLog(line, 'success');
                            } else {
                                appendLog(line, 'info');
                            }
                        }
                    });
                }
            } catch (err) {
                appendLog(`❌ Network error while requesting report: ${err.message}`, "error");
            } finally {
                isProcessing.value = false;
            }
        };

        // Action: Download & Package Batch (using SSE streaming)
        const startPackaging = () => {
            if (!urls.value.trim()) return;
            isProcessing.value = true;
            clearLog();
            appendLog("🚀 Starting Batch Packaging Job...", "info");

            const eventSource = new EventSource(`/api/process-stream?urls=${encodeURIComponent(urls.value)}`);

            eventSource.addEventListener('stdout', (e) => {
                const text = JSON.parse(e.data);
                const lines = text.split('\n');
                lines.forEach(line => {
                    if (line.trim()) {
                        if (line.includes('✅') || line.includes('Success') || line.includes('Outcome:')) {
                            appendLog(line, 'success');
                        } else if (line.includes('⚠️') || line.includes('[WARNING]')) {
                            appendLog(line, 'warning');
                        } else if (line.includes('❌') || line.includes('[ERROR]') || line.includes('failed')) {
                            appendLog(line, 'error');
                        } else {
                            appendLog(line, 'info');
                        }
                    }
                });
            });

            eventSource.addEventListener('stderr', (e) => {
                const text = JSON.parse(e.data);
                appendLog(text, 'error');
            });

            eventSource.addEventListener('exit', (e) => {
                const { code } = JSON.parse(e.data);
                if (code === 0) {
                    appendLog("✨ Batch extraction and packaging completed successfully!", "success");
                } else {
                    appendLog(`⚠️ Process terminated with code: ${code}`, "warning");
                }
                eventSource.close();
                isProcessing.value = false;
                fetchPackages();
            });

            eventSource.onerror = (err) => {
                appendLog("❌ Connection to batch execution server lost.", "error");
                eventSource.close();
                isProcessing.value = false;
            };
        };

        // Watch tab changes to lazy load statistics or model list
        Vue.watch(currentTab, (newTab) => {
            if (newTab === 'catalog') {
                fetchCatalog();
            } else if (newTab === 'settings') {
                fetchStats();
            }
        });

        onMounted(() => {
            fetchPackages();
        });

        return {
            currentTab,
            urls,
            isProcessing,
            log,
            packages,
            terminal,
            catalogItems,
            catalogTotal,
            catalogLoading,
            catalogFilters,
            totalPages,
            stats,
            statsLoading,
            toastMessage,
            copyPath,
            runReport,
            startPackaging,
            clearLog,
            fetchPackages,
            fetchCatalog,
            resetPageAndFetch,
            nextPage,
            prevPage,
            fetchStats
        };
    }
}).mount('#app');
