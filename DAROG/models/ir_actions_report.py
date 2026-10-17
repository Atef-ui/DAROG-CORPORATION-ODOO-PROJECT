"""Darog documents: the company pad behind them, and big orders shrunk to one page.

- Pad: static/src/img/Pad.pdf is placed behind every page of PAD_REPORTS.
- One page: a FIT_REPORTS document that runs past one page is made again, shrunk evenly
  (text and spacing together), using the largest size that still fits on one page.
"""
import io
import logging

from markupsafe import Markup

from odoo import models
from odoo.tools import file_open
from odoo.tools.pdf import PdfFileReader, PdfFileWriter, merge_pdf

_logger = logging.getLogger(__name__)

PAD_PATH = "DAROG/static/src/img/Pad.pdf"

# Documents printed on the pad. Bill of Exchange, Certificate of Origin and Transportation stay plain.
PAD_REPORTS = {
    "DAROG.report_darog",           # Proforma Invoice
    "DAROG.report_darog_com",       # Commercial Invoice
    "DAROG.report_darog_delivery",  # Delivery Challan
    "DAROG.report_darog_packing",   # Packing List
}

# Documents with order lines that must always fit on one page.
FIT_REPORTS = {
    "DAROG.report_darog",
    "DAROG.report_darog_com",
    "DAROG.report_darog_delivery",
    "DAROG.report_darog_packing",
}
MIN_SCALE = 0.35   # never shrink below 35 % (stays readable); longer still means more pages
FIT_STEPS = 4      # tries to find the largest size that fits (within about 3 %)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        ids = [res_ids] if isinstance(res_ids, int) else list(res_ids or [])
        if report.report_name in FIT_REPORTS and ids:
            # One record at a time, so each order gets its own single page.
            parts = [self._darog_render_one_page(report_ref, res_id, data) for res_id in ids]
            content_type = "pdf"
            content = parts[0] if len(parts) == 1 or parts[0][:5] != b"%PDF-" else merge_pdf(parts)
        else:
            content, content_type = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        if report.report_name in PAD_REPORTS and content[:5] == b"%PDF-":
            try:
                content = self._darog_add_pad(content)
            except Exception:  # noqa: BLE001 - a broken pad must never stop printing
                _logger.exception("Could not add the pad background; printing without it.")
        return content, content_type

    # ------------------------------------------------------------------
    # One page
    # ------------------------------------------------------------------
    def _darog_render_at(self, report_ref, res_id, data, scale):
        """The document without the pad, shrunk to `scale` (1 = normal size)."""
        report = self.with_context(darog_scale=scale) if scale < 1 else self
        return super(IrActionsReport, report)._render_qweb_pdf(report_ref, res_ids=[res_id], data=data)[0]

    def _darog_render_one_page(self, report_ref, res_id, data):
        content = self._darog_render_at(report_ref, res_id, data, 1.0)
        if content[:5] != b"%PDF-":  # tests make HTML instead of PDF
            return content
        pages = _page_count(content)
        if pages <= 1:
            return content

        # Content spread over `pages` pages fits on one at roughly 1/pages to 1/(pages - 1)
        # of its size. Halve that range a few times, keeping the largest size that fits.
        fits = fitted = None
        low = max(MIN_SCALE, 0.97 / pages)
        too_big = max(low, 1.0 / (pages - 1))
        for _step in range(FIT_STEPS if too_big > low else 0):
            scale = (low + too_big) / 2
            trial = self._darog_render_at(report_ref, res_id, data, scale)
            if _page_count(trial) == 1:
                fits, fitted, low = scale, trial, scale
            else:
                too_big = scale
        while fitted is None:
            trial = self._darog_render_at(report_ref, res_id, data, low)
            if _page_count(trial) == 1 or low <= MIN_SCALE:
                fits, fitted = low, trial
            else:
                low = max(MIN_SCALE, low * 0.85)
        if _page_count(fitted) > 1:
            _logger.warning("Order %s is too long for one page even at %d%%; printing %d pages.",
                            res_id, MIN_SCALE * 100, _page_count(fitted))
        else:
            _logger.info("Order %s shrunk to %d%% to fit on one page.", res_id, fits * 100)
        return fitted

    def _run_wkhtmltopdf(self, bodies, report_ref=False, header=None, footer=None, landscape=False,
                         specific_paperformat_args=None, set_viewport_size=False):
        scale = self.env.context.get("darog_scale")
        if scale:
            style = f"<style>.article {{ zoom: {scale:.4f}; }}</style></head>"
            bodies = [_with_markup_type(body, str(body).replace("</head>", style, 1)) for body in bodies]
        return super()._run_wkhtmltopdf(
            bodies, report_ref=report_ref, header=header, footer=footer, landscape=landscape,
            specific_paperformat_args=specific_paperformat_args, set_viewport_size=set_viewport_size)

    # ------------------------------------------------------------------
    # Pad
    # ------------------------------------------------------------------
    def _darog_add_pad(self, pdf_content):
        """Put the pad underneath every page, covering the page."""
        with file_open(PAD_PATH, "rb") as pad_file:
            pad_data = pad_file.read()
        document = PdfFileReader(io.BytesIO(pdf_content), strict=False)
        writer = PdfFileWriter()
        for page in document.pages:
            left, bottom, right, top = _box(page)
            width, height = right - left, top - bottom

            # A fresh copy of the pad for every page. Its visible area (the crop box) is scaled
            # to cover the page exactly, so nothing outside it (edge lines) shows.
            pad = PdfFileReader(io.BytesIO(pad_data), strict=False).pages[0]
            crop = [float(value) for value in pad.get("/CropBox") or _box(pad)]
            crop_width, crop_height = crop[2] - crop[0], crop[3] - crop[1]
            scale = max(width / crop_width, height / crop_height)
            offset_x = -crop[0] * scale + (width - crop_width * scale) / 2
            offset_y = -crop[1] * scale + (height - crop_height * scale) / 2

            sheet = _blank_page(writer, width, height)
            _merge_transformed(sheet, pad, scale, offset_x, offset_y)
            _merge_transformed(sheet, page, 1, -left, -bottom)
            if hasattr(sheet, "compress_content_streams"):
                sheet.compress_content_streams()
            elif hasattr(sheet, "compressContentStreams"):
                sheet.compressContentStreams()

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()


def _page_count(pdf_content):
    return len(PdfFileReader(io.BytesIO(pdf_content), strict=False).pages)


def _with_markup_type(original, text):
    return Markup(text) if isinstance(original, Markup) else text


# PyPDF2 1.x, PyPDF2 2.x and pypdf name these differently; Odoo supports all three.
def _box(page):
    box = page.mediabox if hasattr(page, "mediabox") else page.mediaBox
    return [float(value) for value in box]


def _blank_page(writer, width, height):
    if hasattr(writer, "add_blank_page"):
        return writer.add_blank_page(width, height)
    return writer.addBlankPage(width, height)


def _merge_transformed(base, page, scale, offset_x, offset_y):
    if hasattr(base, "merge_transformed_page"):
        base.merge_transformed_page(page, (scale, 0, 0, scale, offset_x, offset_y))
    else:
        base.mergeTransformedPage(page, [scale, 0, 0, scale, offset_x, offset_y])
