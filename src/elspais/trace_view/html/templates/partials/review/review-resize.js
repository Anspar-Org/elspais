/**
 * TraceView Review Resize Module
 * Handle resizable review panel.
 * IMPLEMENTS REQUIREMENTS: REQ-d00012
 */
window.TraceView = window.TraceView || {};
TraceView.review = TraceView.review || {};

(function(review) {
    'use strict';

    const MIN_WIDTH = 200;
    const MAX_WIDTH = 600;
    const DEFAULT_WIDTH = 350;
    const STORAGE_KEY = 'traceview_review_panel_width';

    let isResizing = false;
    let startX, startWidth;

    /**
     * Initialize resize functionality
     */
    function initResize() {
        const handle = document.getElementById('reviewResizeHandle');
        const column = document.getElementById('review-column');

        if (!handle || !column) return;

        // Restore saved width
        const savedWidth = localStorage.getItem(STORAGE_KEY);
        if (savedWidth) {
            column.style.width = savedWidth + 'px';
        }

        handle.addEventListener('mousedown', startResize);
        document.addEventListener('mousemove', doResize);
        document.addEventListener('mouseup', stopResize);
    }

    /**
     * Start resize operation
     * @param {MouseEvent} e - Mouse event
     */
    function startResize(e) {
        const column = document.getElementById('review-column');
        if (!column) return;

        isResizing = true;
        startX = e.clientX;
        startWidth = column.offsetWidth;

        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    }

    /**
     * Handle resize movement
     * @param {MouseEvent} e - Mouse event
     */
    function doResize(e) {
        if (!isResizing) return;

        const column = document.getElementById('review-column');
        if (!column) return;

        // Panel is on the right, so dragging left increases width
        const diff = startX - e.clientX;
        let newWidth = startWidth + diff;

        // Clamp to min/max bounds
        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth));
        column.style.width = newWidth + 'px';
    }

    /**
     * Stop resize operation
     */
    function stopResize() {
        if (!isResizing) return;

        isResizing = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';

        // Save width to localStorage
        const column = document.getElementById('review-column');
        if (column) {
            localStorage.setItem(STORAGE_KEY, column.offsetWidth);
        }
    }

    /**
     * Enable or disable resize functionality
     * @param {boolean} enable - Whether to enable resizing
     */
    function resize(enable) {
        if (enable) {
            initResize();
        }
    }

    // Auto-initialize on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', initResize);

    // Export to review namespace
    review.resize = resize;
    review.initResize = initResize;

})(TraceView.review);

// Update ReviewSystem alias
window.ReviewSystem = window.ReviewSystem || {};
window.ReviewSystem.resize = TraceView.review.resize;
window.ReviewSystem.initResize = TraceView.review.initResize;
