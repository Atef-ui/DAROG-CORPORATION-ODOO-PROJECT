import { registry } from "@web/core/registry";
import { getReportUrl } from "@web/webclient/actions/reports/utils";

/**
 * Open Darog PDF documents in a new browser tab instead of downloading them.
 * If the browser blocks the new tab, Odoo falls back to its normal download.
 */
async function openDarogPdfInTab(action) {
    if (action.report_type !== "qweb-pdf" || !action.report_name?.startsWith("DAROG.")) {
        return false;
    }
    const tab = window.open(getReportUrl(action, "pdf"), "_blank");
    return Boolean(tab);
}

registry.category("ir.actions.report handlers").add("darog_open_pdf_in_tab", openDarogPdfInTab);
