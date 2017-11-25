from odoo import api, fields, models


class PaymentTransaction(models.Model):
    _name = 'payment.transaction'
    _inherit = 'payment.transaction'

    invoice_id = fields.Many2one('account.invoice', 'Invoice')
