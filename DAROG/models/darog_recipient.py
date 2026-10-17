from datetime import datetime

from odoo import api, fields, models


class DarogRecipient(models.Model):
    # The technical name keeps its original spelling so existing databases keep their data.
    _name = "darog.reciepent"
    _description = "Recipient"
    _order = "name"

    name = fields.Char(required=True)
    address = fields.Text()
    email = fields.Char(help="Filled in as the To address when sending this recipient's documents by email.")
    bin_no = fields.Char(string="BIN No")
    tin_no = fields.Char(string="TIN No")
    irc_no = fields.Char(string="IRC No")
    erc_no = fields.Char(string="ERC No")
    bond_reg_no = fields.Char(string="Bond Reg No")
    bb_no = fields.Char(string="BB No")
    bank_id = fields.One2many("darog.bank", "reciepent_id", string="Banks")
    order_ids = fields.One2many("darog.order", "reciepent_id", string="Orders")
    order_count = fields.Integer(compute="_compute_order_count")
    default_invoice_no = fields.Integer(
        string="Starting Invoice No",
        default=0,
        help="Last invoice number used before this recipient's first year in Odoo. "
             "The first invoice gets this number + 1. Numbering restarts at 1 every new year.",
    )
    invoice_year = fields.Integer(default=lambda self: datetime.now().year)

    @api.depends("order_ids")
    def _compute_order_count(self):
        counts = dict(self.env["darog.order"]._read_group(
            [("reciepent_id", "in", self.ids)], ["reciepent_id"], ["__count"],
        ))
        for recipient in self:
            recipient.order_count = counts.get(recipient, 0)

    def action_view_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("DAROG.darog_company_orders_action")
        action["domain"] = [("reciepent_id", "=", self.id)]
        action["context"] = {"default_reciepent_id": self.id}
        return action
