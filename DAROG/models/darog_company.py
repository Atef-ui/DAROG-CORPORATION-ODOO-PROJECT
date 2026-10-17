from odoo import fields, models

DEFAULT_HS_CODE = "6217.10.00"
DEFAULT_EXCHANGE_RATE = 120.0


class DarogCompany(models.Model):
    _name = "darog.company"
    _description = "Company"

    name = fields.Char(required=True)
    logo = fields.Binary()
    certificate = fields.Binary(
        string="Certificate Title Image",
        help="Banner printed at the top of the Certificate of Origin.",
    )
    address = fields.Text()
    hs_code = fields.Char(string="HS Code", default=DEFAULT_HS_CODE, help="Printed on the Certificate of Origin.")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    exchange_rate = fields.Float(
        string="Cost Exchange Rate",
        default=DEFAULT_EXCHANGE_RATE,
        digits=(16, 4),
        help="Local currency per 1 USD. Item cost prices are divided by this rate to compute profit.",
    )
    item_ids = fields.Many2many("darog.item", string="Items")
    email_sender_name = fields.Char(
        string="Email Sender Name",
        help="Name people see as the sender of emailed documents. Leave empty to use the company name.",
    )
