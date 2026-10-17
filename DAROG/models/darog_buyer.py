from odoo import fields, models


class DarogBuyer(models.Model):
    _name = "darog.buyer"
    _description = "Buyer"
    _order = "name"

    name = fields.Char(required=True)
    # Legacy field kept for existing data; orders link to buyers via darog.order.buyer_id.
    order_ids = fields.Many2one("darog.order", string="Order")
