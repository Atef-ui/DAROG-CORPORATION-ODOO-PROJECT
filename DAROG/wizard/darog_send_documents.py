"""Email an order's PDF documents to any address."""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_split, formataddr

# (checkbox field, report, file name) in the order the PDFs are attached.
DOCUMENTS = [
    ("attach_proforma", "DAROG.action_report_darog", "Proforma Invoice"),
    ("attach_commercial", "DAROG.action_report_darog_com", "Commercial Invoice"),
    ("attach_bill", "DAROG.action_report_darog_bill", "Bill of Exchange"),
    ("attach_delivery", "DAROG.action_report_darog_delivery", "Delivery Challan"),
    ("attach_packing", "DAROG.action_report_darog_packing", "Packing List"),
    ("attach_origin", "DAROG.action_report_darog_origin", "Certificate of Origin"),
    ("attach_transport", "DAROG.action_report_darog_transport", "Transportation"),
]


class DarogSendDocuments(models.TransientModel):
    _name = "darog.send.documents"
    _description = "Send Documents by Email"

    order_id = fields.Many2one("darog.order", string="Order", required=True, ondelete="cascade")
    email_to = fields.Char(string="To", required=True, help="Any email address. Separate several with commas.")
    email_cc = fields.Char(string="Cc", help="Optional. Separate several with commas.")
    subject = fields.Char(required=True)
    body = fields.Text(string="Message")
    attach_proforma = fields.Boolean(string="Proforma Invoice", default=True)
    attach_commercial = fields.Boolean(string="Commercial Invoice", default=True)
    attach_bill = fields.Boolean(string="Bill of Exchange", default=True)
    attach_delivery = fields.Boolean(string="Delivery Challan", default=True)
    attach_packing = fields.Boolean(string="Packing List", default=True)
    attach_origin = fields.Boolean(string="Certificate of Origin", default=True)
    attach_transport = fields.Boolean(string="Transportation", default=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        order = self.env["darog.order"].browse(vals.get("order_id"))
        if not order:
            return vals
        company = order.company_id.name or ""
        number = order.ci_number if order.invoice_no else ""
        vals.setdefault("email_to", order.reciepent_id.email or False)
        vals.setdefault("subject", " - ".join(filter(None, [f"Documents {number}".strip(), order.reciepent_id.name])))
        vals.setdefault("body", (
            "Dear Sir/Madam,\n\n"
            f"Please find attached the documents{' for invoice ' + number if number else ''}.\n\n"
            f"Best regards,\n{company}"
        ).strip())
        return vals

    def _attachments(self):
        """[(file name, PDF bytes, mimetype)] for the ticked documents, in document order."""
        self.ensure_one()
        number = (self.order_id.ci_number if self.order_id.invoice_no else "").replace("/", "-")
        Report = self.env["ir.actions.report"]
        attachments = []
        for field, report, label in DOCUMENTS:
            if self[field]:
                try:
                    pdf, _type = Report._render_qweb_pdf(report, self.order_id.ids)
                except Exception as error:  # noqa: BLE001 - explain which document failed
                    raise UserError(
                        f"The {label} could not be made: {error.__cause__ or error}\n\n"
                        "Check that the order's dates are filled in (Proforma Invoice Date, "
                        "L/C Issuing Date and Export L/C Date on the L/C & Dates tab), "
                        "or untick this document."
                    ) from error
                name = " - ".join(filter(None, [label, number]))
                attachments.append((f"{name}.pdf", pdf, "application/pdf"))
        return attachments

    @staticmethod
    def _addresses(text, label):
        parts = [part.strip() for part in (text or "").replace(";", ",").split(",") if part.strip()]
        for part in parts:
            if not email_split(part):
                raise UserError(f"'{part}' in {label} is not a valid email address.")
        return [email_split(part)[0] for part in parts]

    def _sender(self, server):
        """'Darog Corporation <darogbd@gmail.com>': the company's sender name with the server's address."""
        address = server.smtp_user or server.from_filter
        company = self.order_id.company_id or self.env["darog.company"].search([], limit=1)
        name = company.email_sender_name or company.name
        return formataddr((name, address)) if name else address

    def action_send(self):
        self.ensure_one()
        to = self._addresses(self.email_to, "To")
        cc = self._addresses(self.email_cc, "Cc")
        if not to:
            raise UserError("Enter at least one email address in To.")
        if not any(self[field] for field, _report, _label in DOCUMENTS):
            raise UserError("Tick at least one document to attach.")

        MailServer = self.env["ir.mail_server"].sudo()
        server = MailServer.search([], order="sequence, id", limit=1)
        if not server:
            raise UserError("No outgoing email server is set up yet.\n"
                            "Go to Darog > Configuration > Outgoing Email Server and add one.")

        attachments = self._attachments()
        message = MailServer.build_email(
            email_from=self._sender(server),
            email_to=to,
            email_cc=cc,
            subject=self.subject,
            body=self.body or "",
            attachments=attachments,
        )
        try:
            MailServer.send_email(message, mail_server_id=server.id)
        except Exception as error:  # noqa: BLE001 - show the reason to the user
            raise UserError(f"The email could not be sent:\n{error}{_login_hint(error)}") from error

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": f"Sent {len(attachments)} document(s) to {', '.join(to + cc)}.",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


def _login_hint(error):
    """Gmail drops the connection or answers 535 when the password is wrong."""
    text = str(error).lower()
    if any(word in text for word in ("unexpectedly closed", "535", "password", "authentication")):
        return ("\n\nThe email server refused the login. For Gmail, the password must be a 16-letter "
                "App Password from https://myaccount.google.com/apppasswords, not your normal password. "
                "Fix it in Darog > Configuration > Outgoing Email Server.")
    return ""
