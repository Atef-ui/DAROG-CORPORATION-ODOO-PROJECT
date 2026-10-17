from odoo import fields, models


class DarogBank(models.Model):
    _name = "darog.bank"
    _description = "Bank"

    name = fields.Char(required=True)
    address = fields.Text()
    bank_bin = fields.Char(string="Bank BIN")
    reciepent_id = fields.Many2one("darog.reciepent", string="Recipient")
    order_ids = fields.Many2many("darog.order", string="Orders")
