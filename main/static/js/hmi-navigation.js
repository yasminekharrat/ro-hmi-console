class HmiNavigationRouter {
    constructor() {
        // Added 'diagnostics' to the core managed tabs array
        this.tabs = ['dashboard', 'synoptic', 'hydraulics', 'settings', 'alarms', 'manual', 'diagnostics'];
    }

    switchTab(targetTabId) {
        const viewOverview = document.getElementById('view-overview');
        const viewVfd = document.getElementById('view-vfd');

        // 1. HARD OVERRIDE FOR VFD: If targeting vfd, handle it cleanly without the router loop interfering
        if (targetTabId === 'vfd') {
            if (viewOverview && viewVfd) {
                viewOverview.classList.add('hidden');
                viewVfd.classList.remove('hidden');
            }
            
            // Match the sidebar active state to 'synoptic' manually
            this.tabs.forEach(tab => {
                const navBtnElement = document.getElementById(`nav-${tab}`);
                const viewElement = document.getElementById(`view-${tab}`);
                
                if (tab === 'synoptic') {
                    if (viewElement) {
                        viewElement.classList.remove('hidden');
                        viewElement.classList.add('block');
                    }
                    if (navBtnElement) {
                        navBtnElement.className = "nav-active flex items-center text-left px-4 py-3 font-bold text-sm tracking-wide transition uppercase";
                    }
                } else {
                    if (viewElement && tab !== 'vfd') {
                        viewElement.classList.remove('block');
                        viewElement.classList.add('hidden');
                    }
                    if (navBtnElement) {
                        navBtnElement.className = "nav-inactive flex items-center text-left px-4 py-3 font-bold text-sm tracking-wide transition uppercase";
                    }
                }
            });

            if (typeof startVfdPolling === 'function') startVfdPolling();
            if (typeof HmiRenderer !== 'undefined') {
                HmiRenderer.appendEventLog(`Operator changed view to: [VFD]`, "HMI_NAV");
            }
            return; // Halt execution here so Section 2 cannot touch our layout
        }

        // 2. STANDARD ROUTING LAYER (For Overview and all other general tabs)
        if (targetTabId === 'overview') {
            if (viewOverview && viewVfd) {
                viewOverview.classList.remove('hidden');
                viewVfd.classList.add('hidden');
            }
            if (typeof stopVfdPolling === 'function') stopVfdPolling();
            targetTabId = 'synoptic'; 
        }

        if (!this.tabs.includes(targetTabId)) return;

        this.tabs.forEach(tab => {
            const viewElement = document.getElementById(`view-${tab}`);
            const navBtnElement = document.getElementById(`nav-${tab}`);
            
            if (!viewElement) return; 

            if (tab === targetTabId) {
                viewElement.classList.remove('hidden');
                viewElement.classList.add('block');
                if (navBtnElement) {
                    navBtnElement.className = "nav-active flex items-center text-left px-4 py-3 font-bold text-sm tracking-wide transition uppercase";
                }
            } else {
                viewElement.classList.remove('block');
                viewElement.classList.add('hidden');
                if (navBtnElement) {
                    navBtnElement.className = "nav-inactive flex items-center text-left px-4 py-3 font-bold text-sm tracking-wide transition uppercase";
                }
            }
        });

        if (typeof HmiRenderer !== 'undefined') {
            HmiRenderer.appendEventLog(`Operator changed view to: [${targetTabId.toUpperCase()}]`, "HMI_NAV");
        }
    }
}

const HmiNav = new HmiNavigationRouter();