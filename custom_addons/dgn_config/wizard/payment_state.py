# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
from odoo.exceptions import UserError, ValidationError


class AccountPaymentConfirm(models.TransientModel):
    """
    This wizard will confirm the all the selected open payments
    """

    _name = "account.payment.confirm"
    _description = "Confirm the selected invoices"

    @api.multi
    def payment_confirm(self):
        context = dict(self._context or {})
        active_ids = context.get('active_ids', []) or []

        for record in self.env['account.payment'].browse(active_ids):
            if record.state not in ('draft'):
                raise UserError(
                    _("Only a draft payment can be posted. Trying to post a payment in state %s.") % record.state)
            if any(inv.state != 'open' for inv in record.invoice_ids):
                raise ValidationError(_("The payment cannot be processed because the invoice is not open!"))

            record.post()
        return {'type': 'ir.actions.act_window_close'}
