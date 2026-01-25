/**
 * TraceView Review Packages UI Module
 *
 * Provides UI for managing review packages:
 * - Display collapsible packages panel
 * - Create, edit, delete packages
 * - Select active package for filtering
 * - Add/remove REQs from packages
 *
 * IMPLEMENTS REQUIREMENTS:
 *   REQ-tv-d00016: Review JavaScript Integration
 *
 * =============================================================================
 * FILTERING ARCHITECTURE
 * =============================================================================
 *
 * This codebase uses a unified filter orchestrator (applyAllFilters) that
 * coordinates multiple filtering mechanisms:
 *
 * CSS CLASSES:
 * - filtered-out: View filter exclusion (display: none !important)
 * - package-filtered: Package filter exclusion (display: none !important)
 * - collapsed-by-parent: Hierarchy collapse (display: none)
 * - in-active-package, in-other-package, not-in-package: Styling only
 *
 * HIERARCHY PROMOTION MODEL:
 * Items are siblings with data-parent-instance-id (NOT DOM-nested).
 * When filtering is active, matching items are "promoted" by removing
 * collapsed-by-parent, making them visible regardless of parent state.
 *
 * FILTER PRECEDENCE (all ANDed):
 * 1. View filters (filtered-out) - text inputs, dropdowns, checkboxes
 * 2. Package filter (package-filtered) - "Show only Package REQs" toggle
 * 3. Collapse state (collapsed-by-parent) - overridden by promotion when filtering
 *
 * ENTRY POINT:
 * applyAllFilters() in generate_traceability.py - call this when ANY filter changes.
 * Both applyFilters() and applyPackageContext() delegate to applyAllFilters().
 *
 * SINGLE RESPONSIBILITY:
 * - computeViewFilterState(): Computes which items match view filters
 * - computePackageFilterState(): Computes which items match package filter
 * - applyViewFilterClasses(): Manages filtered-out class ONLY
 * - applyPackageFilterClasses(): Manages package-* classes ONLY
 * - applyPromotion(): Removes collapsed-by-parent for promoted items (ONE PLACE)
 * - updateFilteredChildrenIcons(): Updates collapse icons (called ONCE)
 * =============================================================================
 */

(function() {
    'use strict';

    // Initialize TraceView.review if not exists
    window.TraceView = window.TraceView || {};
    TraceView.review = TraceView.review || { state: {} };
    const review = TraceView.review;

    // Package state
    // REQ-d00001-B: No automatic "default" package - packages must be explicitly created
    // REQ-d00005: Archive state for viewing archived packages
    review.packages = {
        items: [],
        archivedItems: [],  // REQ-d00005: Archived packages list
        activeId: null,
        panelExpanded: true,
        archivePanelExpanded: false,  // REQ-d00005: Archive viewer collapse state
        filterEnabled: false,  // Whether "Show only Package REQs" is active
        isArchiveMode: false  // REQ-d00005: Whether viewing archived package (read-only)
    };

    // ==========================================================================
    // Toast Notification
    // ==========================================================================

    let toastElement = null;

    /**
     * Show a toast notification positioned near the packages panel
     */
    function showToast(message, showSpinner = false) {
        if (!toastElement) {
            toastElement = document.createElement('div');
            toastElement.className = 'rs-toast';
            document.body.appendChild(toastElement);
        }

        toastElement.innerHTML = showSpinner
            ? `<div class="rs-toast-spinner"></div><span>${message}</span>`
            : `<span>${message}</span>`;

        // Position near the packages panel header
        const packagesPanel = document.getElementById('reviewPackagesPanel');
        if (packagesPanel) {
            const rect = packagesPanel.getBoundingClientRect();
            toastElement.style.top = `${rect.top + window.scrollY + 8}px`;
            toastElement.style.left = `${rect.left + rect.width / 2}px`;
            toastElement.style.transform = 'translateX(-50%) scale(0.9)';
        } else {
            // Fallback to fixed position
            toastElement.style.position = 'fixed';
            toastElement.style.top = '80px';
            toastElement.style.left = '50%';
            toastElement.style.transform = 'translateX(-50%) scale(0.9)';
        }

        // Force reflow then show
        toastElement.offsetHeight;
        toastElement.classList.add('visible');
        if (packagesPanel) {
            toastElement.style.transform = 'translateX(-50%) scale(1)';
        } else {
            toastElement.style.transform = 'translateX(-50%) scale(1)';
        }
    }

    /**
     * Hide the toast notification
     */
    function hideToast() {
        if (toastElement) {
            toastElement.classList.remove('visible');
        }
    }

    // ==========================================================================
    // API Functions
    // ==========================================================================

    /**
     * Fetch all packages from the API
     * REQ-d00001-B: No default package - packages must be explicitly created
     */
    async function fetchPackages() {
        try {
            const response = await fetch('/api/reviews/packages');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            review.packages.items = data.packages || [];
            review.packages.activeId = data.activePackageId || null;

            // REQ-d00001-B: Validate activePackageId exists in packages list
            if (review.packages.activeId) {
                const exists = review.packages.items.some(p => p.packageId === review.packages.activeId);
                if (!exists) {
                    console.warn('Stale activePackageId detected, clearing:', review.packages.activeId);
                    const staleId = review.packages.activeId;
                    review.packages.activeId = null;
                    // Persist the cleanup via API (async, don't await)
                    fetch('/api/reviews/packages/active', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ packageId: null, user: 'system' })
                    }).catch(err => console.error('Failed to clear stale activePackageId:', staleId, err));
                }
            }

            console.log('Packages loaded:', {
                count: review.packages.items.length,
                activeId: review.packages.activeId,
                packages: review.packages.items.map(p => ({
                    id: p.packageId,
                    name: p.name,
                    reqCount: (p.reqIds || []).length
                }))
            });

            return review.packages;
        } catch (error) {
            console.error('Failed to fetch packages:', error);
            return { items: [], activeId: null };
        }
    }

    /**
     * Fetch archived packages from the API
     * REQ-d00005: Read-only access to archived packages
     */
    async function fetchArchivedPackages() {
        try {
            const response = await fetch('/api/reviews/archive');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            review.packages.archivedItems = data.packages || [];

            console.log('Archived packages loaded:', {
                count: review.packages.archivedItems.length,
                packages: review.packages.archivedItems.map(p => ({
                    id: p.packageId,
                    name: p.name,
                    archiveReason: p.archiveReason
                }))
            });

            return review.packages.archivedItems;
        } catch (error) {
            console.error('Failed to fetch archived packages:', error);
            return [];
        }
    }

    /**
     * Create a new package
     */
    async function createPackage(name, description) {
        const user = review.state.currentUser || 'anonymous';
        try {
            const response = await fetch('/api/reviews/packages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, user })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                await fetchPackages();
                renderPackagesPanel();
            }
            return result;
        } catch (error) {
            console.error('Failed to create package:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Update a package's name or description
     */
    async function updatePackage(packageId, updates) {
        try {
            const response = await fetch(`/api/reviews/packages/${packageId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                await fetchPackages();
                renderPackagesPanel();
            }
            return result;
        } catch (error) {
            console.error('Failed to update package:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Delete a package (archives it per REQ-d00003-E)
     * REQ-d00001-F: Package deletion SHALL archive (not destroy) the package
     */
    async function deletePackage(packageId) {
        try {
            const response = await fetch(`/api/reviews/packages/${packageId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                await fetchPackages();
                await fetchArchivedPackages();  // REQ-d00003: Deleted packages go to archive
                renderPackagesPanel();
            }
            return result;
        } catch (error) {
            console.error('Failed to delete package:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Manually archive a package
     * REQ-d00003-D: Manual archive action
     */
    async function archivePackage(packageId, reason = 'manual') {
        const user = review.state.currentUser || 'anonymous';
        try {
            const response = await fetch(`/api/reviews/packages/${packageId}/archive`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason, user })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                showToast(`Package archived (${reason})`);
                await fetchPackages();
                await fetchArchivedPackages();
                renderPackagesPanel();
            }
            return result;
        } catch (error) {
            console.error('Failed to archive package:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * View an archived package (read-only mode)
     * REQ-d00005-B: Archived packages open in read-only mode
     */
    async function viewArchivedPackage(packageId) {
        try {
            const response = await fetch(`/api/reviews/archive/${packageId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const pkg = await response.json();
            review.packages.isArchiveMode = true;
            review.packages.viewingArchivedPackage = pkg;

            // Trigger event for UI updates
            document.dispatchEvent(new CustomEvent('traceview:archive-view-opened', {
                detail: { package: pkg }
            }));

            // Render archive viewer
            renderArchiveViewer(pkg);
            return pkg;
        } catch (error) {
            console.error('Failed to view archived package:', error);
            return null;
        }
    }

    /**
     * Close archive viewer and exit read-only mode
     */
    function closeArchiveViewer() {
        review.packages.isArchiveMode = false;
        review.packages.viewingArchivedPackage = null;

        // Hide archive viewer
        const viewer = document.getElementById('archiveViewer');
        if (viewer) {
            viewer.style.display = 'none';
        }

        document.dispatchEvent(new CustomEvent('traceview:archive-view-closed'));
    }

    /**
     * Set the active package and switch to its git branch
     */
    async function setActivePackage(packageId) {
        const user = review.state.currentUser || 'anonymous';

        // Show toast when switching to a package (not when selecting None)
        if (packageId) {
            showToast('Syncing with GitHub...', true);
        }

        try {
            // 1. Set the active package in packages.json
            const response = await fetch('/api/reviews/packages/active', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ packageId, user })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) {
                hideToast();
                return result;
            }

            review.packages.activeId = packageId;

            // 2. Switch to package branch (creates branch if needed)
            if (packageId) {
                await switchToPackageBranch(packageId, user);
            }

            // 3. Re-render panel to update radio buttons and highlights
            renderPackagesPanel();

            // 4. Apply context styling
            applyPackageFilter();

            // 5. Update git sync indicator to show new branch
            if (review.updateGitSyncIndicator) {
                review.updateGitSyncIndicator();
            }

            // Toast is hidden in fetchConsolidatedPackageData after sync completes
            // But if no packageId, hide it now
            if (!packageId) {
                hideToast();
            }

            return result;
        } catch (error) {
            console.error('Failed to set active package:', error);
            hideToast();
            return { success: false, error: error.message };
        }
    }

    /**
     * Switch to a package branch for the current user
     */
    async function switchToPackageBranch(packageId, user) {
        try {
            const response = await fetch('/api/reviews/packages/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ packageId, user })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                console.log(`Switched to branch: ${result.branch}`);
                review.packages.currentBranch = result.branch;

                // Re-fetch packages to get updated reqIds from new branch
                await fetchPackages();

                // Fetch consolidated data from all package branches
                await fetchConsolidatedPackageData();
            } else {
                // Branch switch failed, hide the toast
                hideToast();
            }
            return result;
        } catch (error) {
            console.error('Failed to switch to package branch:', error);
            hideToast();
            return { success: false, error: error.message };
        }
    }

    /**
     * Fetch consolidated review data from all users' branches for current package
     */
    async function fetchConsolidatedPackageData() {
        // Toast already shown by setActivePackage

        try {
            const response = await fetch('/api/reviews/sync/fetch-all-package', {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            review.packages.contributors = data.contributors || [];

            // If there's merged thread data, update the state
            if (data.threads && Object.keys(data.threads).length > 0) {
                console.log(`Loaded threads from ${data.contributors.length} contributor(s)`);
                // Trigger refresh event so UI updates
                document.dispatchEvent(new CustomEvent('traceview:data-fetched', {
                    detail: { data, timestamp: new Date() }
                }));
            }

            hideToast();
            return data;
        } catch (error) {
            console.error('Failed to fetch consolidated package data:', error);
            hideToast();
            return { threads: {}, flags: {}, contributors: [] };
        }
    }

    /**
     * Get package contributors (users who have branches for this package)
     */
    async function getPackageContributors(packageId) {
        try {
            const response = await fetch(`/api/reviews/packages/${packageId}/contributors`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            return data.contributors || [];
        } catch (error) {
            console.error('Failed to get package contributors:', error);
            return [];
        }
    }

    /**
     * Get current package context from git branch
     */
    async function getCurrentPackageContext() {
        try {
            const response = await fetch('/api/reviews/context');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            return data; // { packageId, user, branch } or null
        } catch (error) {
            console.error('Failed to get package context:', error);
            return null;
        }
    }

    /**
     * Add a REQ to a package
     */
    async function addReqToPackage(packageId, reqId) {
        try {
            const response = await fetch(`/api/reviews/packages/${packageId}/reqs/${reqId}`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                // Update local state
                const pkg = review.packages.items.find(p => p.packageId === packageId);
                if (pkg && !pkg.reqIds.includes(reqId)) {
                    pkg.reqIds.push(reqId);
                }
                renderPackagesPanel();
            }
            return result;
        } catch (error) {
            console.error('Failed to add REQ to package:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Remove a REQ from a package
     */
    async function removeReqFromPackage(packageId, reqId) {
        try {
            const response = await fetch(`/api/reviews/packages/${packageId}/reqs/${reqId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                // Update local state
                const pkg = review.packages.items.find(p => p.packageId === packageId);
                if (pkg) {
                    pkg.reqIds = pkg.reqIds.filter(id => id !== reqId);
                }
                renderPackagesPanel();
            }
            return result;
        } catch (error) {
            console.error('Failed to remove REQ from package:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Add REQ to active package
     * REQ-d00001-B: Requires explicit package selection (no default)
     */
    async function addReqToActivePackage(reqId) {
        const packageId = review.packages.activeId;
        if (!packageId) {
            console.warn('addReqToActivePackage: No package selected. Select a package first.');
            showToast('Please select a package first');
            return { success: false, error: 'No package selected' };
        }
        return addReqToPackage(packageId, reqId);
    }

    // ==========================================================================
    // UI Functions
    // ==========================================================================

    /**
     * Render the packages panel
     * REQ-d00001-B: No default package concept
     * REQ-d00005: Include archive viewer section
     */
    function renderPackagesPanel() {
        const panel = document.getElementById('reviewPackagesPanel');
        if (!panel) return;

        const packagesContent = panel.querySelector('.packages-content');
        if (!packagesContent) return;

        const items = review.packages.items;
        const archivedItems = review.packages.archivedItems;
        const activeId = review.packages.activeId;

        // Build package list HTML
        let html = '<div class="package-list">';

        // "None" option (show all REQs)
        html += `
            <label class="package-item${!activeId ? ' active' : ''}">
                <input type="radio" name="activePackage" value=""
                       ${!activeId ? 'checked' : ''}
                       onchange="TraceView.review.setActivePackage(null)">
                <span class="package-info">
                    <span class="package-name">None (Show All)</span>
                    <span class="package-desc">No package filter applied</span>
                </span>
            </label>
        `;

        // Package items - REQ-d00001-B: All packages are explicit (no default)
        for (const pkg of items) {
            const isActive = pkg.packageId === activeId;
            const reqCount = pkg.reqIds ? pkg.reqIds.length : 0;
            const reqIds = pkg.reqIds || [];

            // Build REQ list HTML for active package
            let reqListHtml = '';
            if (isActive && reqIds.length > 0) {
                reqListHtml = `
                    <div class="package-req-list">
                        ${reqIds.map(reqId => `
                            <div class="package-req-item" data-req-id="${reqId}">
                                <span class="package-req-id" onclick="TraceView.panel.open('${reqId}')" title="View REQ-${reqId}">REQ-${reqId}</span>
                                <button class="rs-btn rs-btn-sm rs-btn-danger package-req-remove"
                                        onclick="TraceView.review.removeReqFromPackage('${pkg.packageId}', '${reqId}'); event.stopPropagation();"
                                        title="Remove from package">&times;</button>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            html += `
                <div class="package-item-wrapper${isActive ? ' active' : ''}">
                    <label class="package-item${isActive ? ' active' : ''}">
                        <input type="radio" name="activePackage" value="${pkg.packageId}"
                               ${isActive ? 'checked' : ''}
                               onchange="TraceView.review.setActivePackage('${pkg.packageId}')">
                        <span class="package-info">
                            <span class="package-name">${escapeHtml(pkg.name)}</span>
                            <span class="package-desc">${escapeHtml(pkg.description || '')}</span>
                        </span>
                        <span class="package-count">${reqCount}</span>
                        <span class="package-actions">
                            <button class="rs-btn rs-btn-sm" onclick="TraceView.review.editPackageDialog('${pkg.packageId}', event)" title="Edit">
                                &#9998;
                            </button>
                            <button class="rs-btn rs-btn-sm" onclick="TraceView.review.confirmArchivePackage('${pkg.packageId}', event)" title="Archive">
                                &#128451;
                            </button>
                            <button class="rs-btn rs-btn-sm rs-btn-danger" onclick="TraceView.review.confirmDeletePackage('${pkg.packageId}', event)" title="Delete (archives)">
                                &times;
                            </button>
                        </span>
                    </label>
                    ${reqListHtml}
                </div>
            `;
        }

        html += '</div>';

        // REQ-d00005: Archive viewer section
        if (archivedItems.length > 0) {
            const archiveExpanded = review.packages.archivePanelExpanded;
            html += `
                <div class="archive-section">
                    <div class="archive-header" onclick="TraceView.review.toggleArchivePanel()">
                        <span class="collapse-icon">${archiveExpanded ? '▼' : '▶'}</span>
                        <h4>Archived Packages (${archivedItems.length})</h4>
                    </div>
                    <div class="archive-list" style="${archiveExpanded ? '' : 'display: none;'}">
                        ${archivedItems.map(pkg => `
                            <div class="archive-item" onclick="TraceView.review.viewArchivedPackage('${pkg.packageId}')">
                                <span class="archive-item-name">${escapeHtml(pkg.name)}</span>
                                <span class="archive-item-reason rs-badge rs-badge-${pkg.archiveReason || 'manual'}">${pkg.archiveReason || 'archived'}</span>
                                <span class="archive-item-date" title="${pkg.archivedAt || ''}">${formatArchiveDate(pkg.archivedAt)}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        packagesContent.innerHTML = html;
    }

    /**
     * Format archive date for display
     */
    function formatArchiveDate(isoDate) {
        if (!isoDate) return '';
        try {
            const date = new Date(isoDate);
            return date.toLocaleDateString();
        } catch (e) {
            return '';
        }
    }

    /**
     * Toggle archive panel expansion
     * REQ-d00005: Archive viewer
     */
    function toggleArchivePanel() {
        review.packages.archivePanelExpanded = !review.packages.archivePanelExpanded;
        renderPackagesPanel();
    }

    /**
     * Render archive viewer for a specific archived package
     * REQ-d00005: Read-only archive viewer
     */
    function renderArchiveViewer(pkg) {
        let viewer = document.getElementById('archiveViewer');
        if (!viewer) {
            viewer = document.createElement('div');
            viewer.id = 'archiveViewer';
            viewer.className = 'archive-viewer';
            document.body.appendChild(viewer);
        }

        // REQ-d00005-D: Display archival metadata
        // REQ-d00005-E: Display git audit trail information
        viewer.innerHTML = `
            <div class="archive-viewer-overlay" onclick="TraceView.review.closeArchiveViewer()"></div>
            <div class="archive-viewer-content">
                <div class="archive-viewer-header">
                    <h3>${escapeHtml(pkg.name)} <span class="archive-badge">ARCHIVED</span></h3>
                    <button class="rs-btn rs-btn-link" onclick="TraceView.review.closeArchiveViewer()">&times;</button>
                </div>
                <div class="archive-viewer-meta">
                    <div class="archive-meta-row">
                        <span class="archive-meta-label">Archive Reason:</span>
                        <span class="archive-meta-value rs-badge rs-badge-${pkg.archiveReason || 'manual'}">${pkg.archiveReason || 'archived'}</span>
                    </div>
                    <div class="archive-meta-row">
                        <span class="archive-meta-label">Archived At:</span>
                        <span class="archive-meta-value">${pkg.archivedAt || 'Unknown'}</span>
                    </div>
                    <div class="archive-meta-row">
                        <span class="archive-meta-label">Archived By:</span>
                        <span class="archive-meta-value">${escapeHtml(pkg.archivedBy || 'Unknown')}</span>
                    </div>
                    ${pkg.branchName ? `
                    <div class="archive-meta-row">
                        <span class="archive-meta-label">Branch:</span>
                        <span class="archive-meta-value">${escapeHtml(pkg.branchName)}</span>
                    </div>
                    ` : ''}
                    ${pkg.creationCommitHash ? `
                    <div class="archive-meta-row">
                        <span class="archive-meta-label">Creation Commit:</span>
                        <span class="archive-meta-value commit-hash" title="May not exist if branch was squash-merged">${pkg.creationCommitHash.substring(0, 7)}</span>
                    </div>
                    ` : ''}
                    ${pkg.lastReviewedCommitHash ? `
                    <div class="archive-meta-row">
                        <span class="archive-meta-label">Last Reviewed Commit:</span>
                        <span class="archive-meta-value commit-hash" title="May not exist if branch was squash-merged">${pkg.lastReviewedCommitHash.substring(0, 7)}</span>
                    </div>
                    ` : ''}
                </div>
                <div class="archive-viewer-body">
                    <p class="archive-readonly-notice">This package is archived and read-only. Comments cannot be added or modified.</p>
                    ${pkg.description ? `<p class="archive-description">${escapeHtml(pkg.description)}</p>` : ''}
                    <div class="archive-reqs">
                        <h4>Requirements (${(pkg.reqIds || []).length})</h4>
                        <div class="archive-req-list">
                            ${(pkg.reqIds || []).map(reqId => `
                                <span class="archive-req-badge">REQ-${reqId}</span>
                            `).join(' ')}
                        </div>
                    </div>
                </div>
                <div class="archive-viewer-footer">
                    <button class="rs-btn" onclick="TraceView.review.closeArchiveViewer()">Close</button>
                </div>
            </div>
        `;

        viewer.style.display = 'flex';
    }

    /**
     * Toggle packages panel expansion
     */
    function togglePackagesPanel() {
        const panel = document.getElementById('reviewPackagesPanel');
        if (!panel) return;

        review.packages.panelExpanded = !review.packages.panelExpanded;
        panel.classList.toggle('collapsed', !review.packages.panelExpanded);

        const icon = panel.querySelector('.collapse-icon');
        if (icon) {
            icon.textContent = review.packages.panelExpanded ? '\u25BC' : '\u25B6';
        }
    }

    /**
     * Show create package dialog
     */
    function showCreatePackageDialog(event) {
        if (event) event.stopPropagation();

        const name = prompt('Package name:');
        if (!name || !name.trim()) return;

        const description = prompt('Package description (optional):') || '';
        createPackage(name.trim(), description.trim());
    }

    /**
     * Show edit package dialog
     */
    function editPackageDialog(packageId, event) {
        if (event) event.stopPropagation();

        const pkg = review.packages.items.find(p => p.packageId === packageId);
        if (!pkg) return;

        const name = prompt('Package name:', pkg.name);
        if (!name || !name.trim()) return;

        const description = prompt('Package description:', pkg.description || '');
        updatePackage(packageId, {
            name: name.trim(),
            description: description ? description.trim() : ''
        });
    }

    /**
     * Confirm and delete package (archives it per REQ-d00001-F)
     */
    function confirmDeletePackage(packageId, event) {
        if (event) event.stopPropagation();

        const pkg = review.packages.items.find(p => p.packageId === packageId);
        if (!pkg) return;

        if (confirm(`Delete package "${pkg.name}"?\n\nThis will archive the package (not destroy it). REQs will not be deleted.`)) {
            deletePackage(packageId);
        }
    }

    /**
     * Confirm and archive a package manually
     * REQ-d00003-D: Manual archive action
     */
    function confirmArchivePackage(packageId, event) {
        if (event) event.stopPropagation();

        const pkg = review.packages.items.find(p => p.packageId === packageId);
        if (!pkg) return;

        if (confirm(`Archive package "${pkg.name}"?\n\nArchived packages are read-only but preserved for audit purposes.`)) {
            archivePackage(packageId, 'manual');
        }
    }

    /**
     * Apply package context and optional filtering to the requirement tree.
     * Context (activeId) determines which package new REQs are added to.
     * Filter (filterEnabled) determines whether to hide non-package REQs.
     *
     * NOTE: This function delegates to the unified applyAllFilters() orchestrator
     * which handles all filtering (view filters, package filters, and hierarchy promotion)
     * in a single, consistent pass. See generate_traceability.py for the implementation.
     */
    function applyPackageContext() {
        // Update context indicator UI
        updateContextIndicator(review.packages.activeId);

        // Delegate all filtering to the unified orchestrator
        // This handles: view filters, package filters, hierarchy promotion, icon updates, and stats
        if (typeof applyAllFilters === 'function') {
            applyAllFilters();
        }
    }

    /**
     * Update context indicator in UI
     */
    function updateContextIndicator(activeId) {
        const indicator = document.getElementById('packageContextIndicator');
        if (!indicator) return;

        if (activeId) {
            const pkg = review.packages.items.find(p => p.packageId === activeId);
            const name = pkg ? pkg.name : 'Unknown';
            indicator.textContent = `Context: ${name}`;
        } else {
            indicator.textContent = 'Context: Default';
        }
    }

    /**
     * Toggle the package filter on/off
     */
    function togglePackageFilter(event) {
        if (event) event.stopPropagation();

        review.packages.filterEnabled = !review.packages.filterEnabled;

        // Update toggle button styling
        const toggle = document.getElementById('packageFilterToggle');
        if (toggle) {
            toggle.classList.toggle('active', review.packages.filterEnabled);
        }

        // Re-apply filtering
        applyPackageContext();
    }

    // Alias for backwards compatibility
    function applyPackageFilter() {
        applyPackageContext();
    }

    /**
     * Escape HTML special characters
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Initialize packages panel when review mode is activated
     * REQ-d00005: Also fetch archived packages
     */
    async function initPackagesPanel() {
        await Promise.all([
            fetchPackages(),
            fetchArchivedPackages()  // REQ-d00005: Load archived packages
        ]);
        renderPackagesPanel();
        applyPackageFilter();
    }

    // ==========================================================================
    // Export Functions
    // ==========================================================================

    review.fetchPackages = fetchPackages;
    review.fetchArchivedPackages = fetchArchivedPackages;  // REQ-d00005
    review.createPackage = createPackage;
    review.updatePackage = updatePackage;
    review.deletePackage = deletePackage;
    review.archivePackage = archivePackage;  // REQ-d00003
    review.viewArchivedPackage = viewArchivedPackage;  // REQ-d00005
    review.closeArchiveViewer = closeArchiveViewer;  // REQ-d00005
    review.setActivePackage = setActivePackage;
    review.switchToPackageBranch = switchToPackageBranch;
    review.fetchConsolidatedPackageData = fetchConsolidatedPackageData;
    review.getPackageContributors = getPackageContributors;
    review.getCurrentPackageContext = getCurrentPackageContext;
    review.addReqToPackage = addReqToPackage;
    review.removeReqFromPackage = removeReqFromPackage;
    review.addReqToActivePackage = addReqToActivePackage;
    review.renderPackagesPanel = renderPackagesPanel;
    review.togglePackagesPanel = togglePackagesPanel;
    review.toggleArchivePanel = toggleArchivePanel;  // REQ-d00005
    review.togglePackageFilter = togglePackageFilter;
    review.showCreatePackageDialog = showCreatePackageDialog;
    review.editPackageDialog = editPackageDialog;
    review.confirmDeletePackage = confirmDeletePackage;
    review.confirmArchivePackage = confirmArchivePackage;  // REQ-d00003
    review.initPackagesPanel = initPackagesPanel;
    review.applyPackageFilter = applyPackageFilter;
    review.applyPackageContext = applyPackageContext;

})();

// Export to ReviewSystem alias with RS. pattern (REQ-d00012)
window.ReviewSystem = window.ReviewSystem || {};
var RS = window.ReviewSystem;

// Initialize packages state on ReviewSystem (REQ-d00012)
RS.packages = {
    items: [],
    activeId: null,
    filterEnabled: false
};

// Export package functions
RS.renderPackagesPanel = TraceView.review.renderPackagesPanel;
RS.togglePackagesPanel = TraceView.review.togglePackagesPanel;
RS.togglePackageFilter = TraceView.review.togglePackageFilter;
RS.toggleArchivePanel = TraceView.review.toggleArchivePanel;  // REQ-d00005
RS.showCreatePackageDialog = TraceView.review.showCreatePackageDialog;
RS.setActivePackage = TraceView.review.setActivePackage;
RS.initPackagesPanel = TraceView.review.initPackagesPanel;
RS.applyPackageFilter = TraceView.review.applyPackageFilter;
RS.archivePackage = TraceView.review.archivePackage;  // REQ-d00003
RS.viewArchivedPackage = TraceView.review.viewArchivedPackage;  // REQ-d00005
RS.closeArchiveViewer = TraceView.review.closeArchiveViewer;  // REQ-d00005
RS.confirmArchivePackage = TraceView.review.confirmArchivePackage;  // REQ-d00003
