from odoo import api, fields, models

GUMTAPE = "PAPER GUMTAPE"
POLY_ITEMS = ("PRE-PACK: MILKY WHITE", "PRINTED POLY: MILKY WHITE")


def _norm(name):
    return (name or "").strip().upper()


class DarogItem(models.Model):
    _name = "darog.item"
    _description = "Item"

    name = fields.Char(required=True)
    description = fields.Char()
    price_per_unit = fields.Float(
        string="Default Cost Per Unit",
        help="Purchase cost in local currency, filled into new order lines. "
             "Each order line keeps its own cost, so changing this never alters past orders.",
    )
    print_style = fields.Selection(
        [
            ("standard", "Standard (L x W)"),
            ("poly", "Poly bag (L + Adhesive, W)"),
            ("gumtape", "Gum tape (rolls / yards)"),
        ],
        string="Line Type",
        compute="_compute_print_style",
        store=True,
        precompute=True,
        readonly=False,
        required=True,
        help="Which size fields an order line shows, and whether it counts as dozens or gum tape in the totals.",
    )
    order_ids = fields.Many2many("darog.order", string="Orders")
    measurement_ids = fields.One2many("darog.measurement", "items_id", string="Measurements")

    @api.depends("name")
    def _compute_print_style(self):
        for item in self:
            if item.print_style:
                continue
            name = _norm(item.name)
            if name == GUMTAPE:
                item.print_style = "gumtape"
            elif name in POLY_ITEMS:
                item.print_style = "poly"
            else:
                item.print_style = "standard"
