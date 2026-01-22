/**
 * TraceView Review Init Module
 * Orchestrates review mode initialization and provides global functions.
 * IMPLEMENTS REQUIREMENTS: REQ-d00012
 */
window.TraceView = window.TraceView || {};
TraceView.review = TraceView.review || {};
window.ReviewSystem = window.ReviewSystem || {};
var RS = window.ReviewSystem;

(function(review, RS) {
    'use strict';

    let reviewModeActive = false;
    let selectedCardElement = null;

    /**
     * Toggle review mode on/off
     * @param {boolean} enabled - Optional: explicitly set mode state
     * @returns {boolean} Current review mode state
     */
    function toggleReviewMode(enabled) {
        if (enabled === undefined) {
            reviewModeActive = !reviewModeActive;
        } else {
            reviewModeActive = !!enabled;
        }

        const column = document.getElementById('review-column');
        const btn = document.getElementById('btnReviewMode');
        const packagesPanel = document.getElementById('reviewPackagesPanel');

        // Use classList.toggle for body class (REQ-d00012-G)
        document.body.classList.toggle('review-mode-active', reviewModeActive);

        if (reviewModeActive) {
            if (column) column.classList.remove('hidden');
            if (btn) btn.classList.add('active');
            if (packagesPanel) packagesPanel.style.display = 'block';

            // Initialize if first activation
            if (review.init && !review._initialized) {
                review.init();
                review._initialized = true;
            }

            // If there are already open REQ cards, apply interactive line numbers to all of them
            if (window.TraceView && window.TraceView.state && window.TraceView.state.reqCardStack) {
                const openCards = window.TraceView.state.reqCardStack;

                // Apply line numbers to ALL open cards
                openCards.forEach(cardReqId => {
                    const cardElement = document.getElementById(`req-card-${cardReqId}`);
                    if (cardElement && review.applyLineNumbersToCard) {
                        review.applyLineNumbersToCard(cardElement, cardReqId);
                    }
                });

                // Select the most recently opened card (first in stack) for review
                if (openCards.length > 0) {
                    const reqId = openCards[0];
                    const req = window.REQ_CONTENT_DATA ? window.REQ_CONTENT_DATA[reqId] : null;
                    document.dispatchEvent(new CustomEvent('traceview:req-selected', {
                        detail: { reqId, req }
                    }));
                }
            }
        } else {
            if (column) column.classList.add('hidden');
            if (btn) btn.classList.remove('active');
            if (packagesPanel) packagesPanel.style.display = 'none';

            // Clear selection when deactivating (REQ-d00012-G)
            clearCurrentSelection();
        }

        // Dispatch event for review mode change (REQ-d00012-E)
        document.dispatchEvent(new CustomEvent('rs:review-mode-changed', {
            detail: { active: reviewModeActive }
        }));

        return reviewModeActive;
    }

    /**
     * Clear current selection (card and line selections)
     */
    function clearCurrentSelection() {
        if (selectedCardElement) {
            selectedCardElement.classList.remove('rs-selected');
            // Clear line selections using RS namespace
            if (RS.clearAllLineSelections) {
                RS.clearAllLineSelections();
            }
            selectedCardElement = null;
        }
        review.selectedReqId = null;
    }

    /**
     * Apply line numbers to the currently selected requirement card
     * @param {HTMLElement} cardElement - The card element
     * @param {string} reqId - Requirement ID
     */
    function applyLineNumbersToReqCard(cardElement, reqId) {
        // Use RS namespace to apply line numbers (REQ-d00012)
        if (RS.applyLineNumbersToCard) {
            RS.applyLineNumbersToCard(cardElement, reqId);
        }
    }

    /**
     * Select a requirement for review
     * @param {string} reqId - Requirement ID to select
     */
    function selectReqForReview(reqId) {
        if (!reviewModeActive) {
            toggleReviewMode(true);
        }

        // Clear previous selection
        clearCurrentSelection();

        review.selectedReqId = reqId;
        const req = window.REQ_CONTENT_DATA ? window.REQ_CONTENT_DATA[reqId] : null;

        // Find and mark the card element
        const cardElement = document.querySelector(`[data-req-id="${reqId}"]`);
        if (cardElement) {
            selectedCardElement = cardElement;
            cardElement.classList.add('rs-selected');

            // Apply line numbers to the selected card (REQ-d00012-E)
            applyLineNumbersToReqCard(cardElement, reqId);
        }

        document.dispatchEvent(new CustomEvent('traceview:req-selected', {
            detail: { reqId, req }
        }));
    }

    /**
     * Check if review mode is currently active
     * @returns {boolean} True if review mode is active
     */
    function isReviewModeActive() {
        return reviewModeActive;
    }

    // Auto-initialize on DOMContentLoaded if review mode data exists
    document.addEventListener('DOMContentLoaded', function() {
        if (document.body.getAttribute('data-review-mode') === 'true') {
            if (window.REVIEW_DATA) {
                console.log('Review mode auto-initializing...');
                // Don't auto-enable review mode, just set up the system
                if (review.init && !review._initialized) {
                    review.init();
                    review._initialized = true;
                }
            }
        }
    });

    // Export functions to review namespace
    review.toggleReviewMode = toggleReviewMode;
    review.selectReqForReview = selectReqForReview;
    review.isReviewModeActive = isReviewModeActive;
    review.clearCurrentSelection = clearCurrentSelection;
    review.applyLineNumbersToReqCard = applyLineNumbersToReqCard;

    // Export to ReviewSystem alias (RS pattern)
    RS.toggleReviewMode = toggleReviewMode;
    RS.selectReqForReview = selectReqForReview;
    RS.isReviewModeActive = isReviewModeActive;
    RS.clearCurrentSelection = clearCurrentSelection;

})(TraceView.review, RS);
