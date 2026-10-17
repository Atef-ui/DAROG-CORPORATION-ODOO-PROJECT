from odoo import api, fields, models


class DarogMeasurement(models.Model):
    _name = "darog.measurement"
    _description = "Order Line"
    _order = "orders_id, id"

    orders_id = fields.Many2one("darog.order", string="Order", ondelete="cascade", index=True)
    items_id = fields.Many2one("darog.item", string="Item")
    print_style = fields.Selection(related="items_id.print_style")
    width = fields.Integer()
    length = fields.Integer()
    adhesive = fields.Integer()
    measure = fields.Selection([("inch", "INCH"), ("cm", "CM")], string="Unit of Size")
    quantity = fields.Float()
    quantity_unit = fields.Selection(
        [("dozon", "DZN"), ("yards", "YARDS"), ("roll", "ROLL")],
        string="Qty Unit",
    )
    yards = fields.Float(string="Yards per Roll", digits=(16, 2))
    per_unit_price = fields.Float(string="Unit Price", digits=(16, 4))
    total_price = fields.Float(compute="_compute_total_price", digits=(16, 2), string="Amount")

    @api.depends("quantity", "per_unit_price", "quantity_unit", "yards")
    def _compute_total_price(self):
        for line in self:
            total = line.quantity * line.per_unit_price
            if line.quantity_unit == "yards":
                total *= line.yards
            line.total_price = total

    @api.depends("items_id", "length", "width", "adhesive", "measure")
    def _compute_display_name(self):
        for line in self:
            size = line._size_text() if line.print_style != "gumtape" else ""
            line.display_name = " - ".join(filter(None, [line.items_id.name, size])) or "New Line"

    @api.onchange("items_id")
    def _onchange_items_id(self):
        if self.items_id and self.print_style != "gumtape":
            self.quantity_unit = "dozon"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.orders_id._add_missing_items()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "items_id" in vals or "orders_id" in vals:
            self.orders_id._add_missing_items()
        return res

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _size_text(self):
        """Short size, e.g. '12 X 10 INCH' or '12 X 10 + AD 2 INCH'."""
        self.ensure_one()
        unit = (self.measure or "").upper()
        if self.print_style == "poly":
            return f"{self.length} X {self.width} + AD {self.adhesive} {unit}".strip()
        return f"{self.length} X {self.width} {unit}".strip()

    def _total_yards(self):
        self.ensure_one()
        return self.quantity * self.yards
